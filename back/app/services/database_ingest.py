"""MySQL 数据源读取并写入平台数据集的连接器。"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models.tables import DatasetRecord

MAX_DATABASE_ROWS = 100_000
FETCH_SIZE = 500
TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")
READ_ONLY_QUERY = re.compile(r"^\s*(?:select|with)\b", re.IGNORECASE)
FROM_CLAUSE = re.compile(r"\bfrom\b", re.IGNORECASE)
FORBIDDEN_SQL = re.compile(
    r";|--|/\*|\b(?:insert|update|delete|drop|alter|create|grant|revoke|truncate|call)\b",
    re.IGNORECASE,
)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, Decimal, UUID)):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return str(value)


def _statement(input_data: dict[str, Any]) -> tuple[str, str]:
    query = input_data.get("sourceQuery") or input_data.get("source_query")
    table = input_data.get("sourceTable") or input_data.get("source_table")
    if query:
        if (
            not isinstance(query, str)
            or not READ_ONLY_QUERY.match(query)
            or not FROM_CLAUSE.search(query)
            or FORBIDDEN_SQL.search(query)
        ):
            raise ValueError("数据库查询必须是一条包含 FROM 的只读 SELECT 语句，例如 SELECT * FROM course")
        return query.strip(), "query"
    if not isinstance(table, str) or not TABLE_NAME.fullmatch(table.strip()):
        raise ValueError("请填写要接入的数据表，或提供只读 SELECT 查询")
    return f"SELECT * FROM {table.strip()}", "table"


def read_mysql_rows(input_data: dict[str, Any]) -> tuple[list[dict[str, Any]], int, str]:
    """从外部 MySQL 读取数据。连接串必须为 mysql+pymysql://...。"""
    address = input_data.get("sourceAddress") or input_data.get("source_address")
    if not isinstance(address, str) or not address.strip():
        raise ValueError("数据库连接地址不能为空")
    try:
        url = make_url(address.strip())
    except Exception as error:
        raise ValueError("数据库连接地址格式无效") from error
    if url.drivername != "mysql+pymysql":
        raise ValueError("数据库地址必须使用 mysql+pymysql:// 格式")

    statement, source_kind = _statement(input_data)
    engine = create_engine(address.strip(), pool_pre_ping=True, connect_args={"connect_timeout": 10})
    rows: list[dict[str, Any]] = []
    byte_count = 0
    try:
        with engine.connect() as connection:
            result = connection.execution_options(stream_results=True).execute(text(statement))
            while batch := result.mappings().fetchmany(FETCH_SIZE):
                if len(rows) + len(batch) > MAX_DATABASE_ROWS:
                    raise ValueError(f"单次数据库接入最多 {MAX_DATABASE_ROWS} 条记录")
                for row in batch:
                    payload = _json_value(dict(row))
                    rows.append(payload)
                    byte_count += len(str(payload).encode("utf-8"))
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"MySQL 连接或读取失败：{error}") from error
    finally:
        engine.dispose()
    return rows, byte_count, source_kind


def save_dataset_rows(
    db: Session,
    *,
    dataset_id: int,
    task_id: str,
    rows: list[dict[str, Any]],
    dataset_version_id: int | None = None,
) -> None:
    """将接入的每一行写入平台自身的 MySQL，并记录它属于哪个版本。

    每条记录都带 dataset_version_id：这是"所有版本的数据都存下来、
    并且查得出来"的关键；缺了它就只能看到总数，看不到版本明细。
    """
    for start in range(0, len(rows), FETCH_SIZE):
        db.add_all(
            DatasetRecord(
                dataset_id=dataset_id,
                dataset_version_id=dataset_version_id,
                task_id=task_id,
                payload=row,
            )
            for row in rows[start : start + FETCH_SIZE]
        )
        db.flush()
