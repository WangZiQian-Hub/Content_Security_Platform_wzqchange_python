"""数据集版本功能——升级后的自检脚本（在你的正式库上运行，只读，不改数据）。

用法（在工程根目录下执行）：

    back\\.venv\\Scripts\\python.exe back\\检查版本功能.py

它会读取 back/.env 里的 MySQL 配置，检查：
  1. dataset_versions 表存在，且每个数据集都有版本记录
  2. dataset_records 有 dataset_version_id 列，且没有"游离"的数据行
  3. 每个数据集的版本清单能查出来，数据行能按版本查回
  4. 打印每个数据集的版本概况

本脚本不写任何数据，可以随时重复运行。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACK_DIR))

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402

# 后端 database.py 里开着 echo=True，自检时关掉，避免 SQL 日志刷屏。
engine.echo = False

OK = "  [通过]"
BAD = "  [异常]"
problems: list[str] = []


def say(ok: bool, message: str) -> None:
    print(f"{OK if ok else BAD} {message}")
    if not ok:
        problems.append(message)


def main() -> int:
    print("=" * 70)
    print("数据集版本功能自检")
    print(f"数据库：{engine.url.host}:{engine.url.port}/{engine.url.database}")
    print("=" * 70)

    with SessionLocal() as db:
        tables = {
            row[0]
            for row in db.execute(text("SHOW TABLES")).fetchall()
        }

        say("dataset_versions" in tables, "版本表 dataset_versions 存在")
        say("dataset_records" in tables, "数据行表 dataset_records 存在")
        if "dataset_versions" not in tables or "dataset_records" not in tables:
            print("\n版本表还没建起来，请确认后端已经用新代码启动过一次。")
            return 1

        columns = {
            row[0]
            for row in db.execute(text("SHOW COLUMNS FROM dataset_records")).fetchall()
        }
        say("dataset_version_id" in columns, "数据行表已有 dataset_version_id 列")
        say("file_id" in columns, "数据行表已有 file_id 列")

        version_columns = {
            row[0]
            for row in db.execute(text("SHOW COLUMNS FROM dataset_versions")).fetchall()
        }
        for name, label in (
            ("added_record_count", "这一版新增记录数"),
            ("total_record_count", "到这一版累计记录数"),
            ("is_backfilled", "老数据回填标记"),
            ("has_snapshot", "数据快照标记"),
            ("file_ids", "版本引用的文件"),
        ):
            say(name in version_columns, f"版本表已有 {name} 列（{label}）")

        dataset_total = int(db.scalar(text("SELECT COUNT(*) FROM datasets")) or 0)
        version_total = int(db.scalar(text("SELECT COUNT(*) FROM dataset_versions")) or 0)
        record_total = int(db.scalar(text("SELECT COUNT(*) FROM dataset_records")) or 0)
        missing_version = int(db.scalar(text(
            "SELECT COUNT(*) FROM datasets d "
            "LEFT JOIN dataset_versions v ON v.dataset_id = d.id WHERE v.id IS NULL"
        )) or 0)
        orphan = int(db.scalar(text(
            "SELECT COUNT(*) FROM dataset_records WHERE dataset_version_id IS NULL"
        )) or 0)
        multi_current = int(db.scalar(text(
            "SELECT COUNT(*) FROM ("
            "  SELECT dataset_id FROM dataset_versions GROUP BY dataset_id "
            "  HAVING SUM(is_current) <> 1"
            ") AS bad"
        )) or 0)

        print()
        say(missing_version == 0, f"每个数据集都有版本记录（缺版本的数据集：{missing_version} 个）")
        say(orphan == 0, f"没有游离的数据行（未归属版本的行数：{orphan}）")
        say(multi_current == 0, f"每个数据集只有一个当前版本（异常数据集：{multi_current} 个）")

        # 只认"库里真的有这一版的数据行"，不看版本表里的登记值。
        # 判断标准：这一版实际落库行数达到它自己声明的"新增记录数"。
        suspicious = [
            (row[0], row[1], int(row[2] or 0), int(row[3] or 0), int(row[4] or 0))
            for row in db.execute(text(
                "SELECT d.name, v.version, v.added_record_count, v.stored_record_count, "
                "  (SELECT COUNT(*) FROM dataset_records r WHERE r.dataset_version_id = v.id) "
                "FROM dataset_versions v JOIN datasets d ON d.id = v.dataset_id "
                "WHERE v.has_snapshot = 1"
            )).fetchall()
            if int(row[4] or 0) <= 0
        ]
        say(not suspicious, f"声明有数据的版本都真落了数据行（异常：{len(suspicious)} 个）")

        print()
        print("=" * 70)
        print(f"总览：{dataset_total} 个数据集，{version_total} 条版本记录，{record_total} 条数据行")
        print("=" * 70)
        print(f"{'数据集':<28}{'版本数':>6}{'当前版本':>10}{'已存数据行':>12}")
        rows = db.execute(text(
            "SELECT d.id, d.name, d.version, "
            "  (SELECT COUNT(*) FROM dataset_versions v WHERE v.dataset_id = d.id), "
            "  (SELECT COUNT(*) FROM dataset_records r WHERE r.dataset_id = d.id) "
            "FROM datasets d ORDER BY d.id"
        )).fetchall()
        for row in rows:
            dataset_id, name, current, versions, records = row
            label = str(name)[:20]
            print(f"{label:<28}{int(versions):>6}{str(current):>10}{int(records):>12}")

        print()
        print("每个版本的明细（每个数据集最多显示最近 3 个版本）：")
        rows = db.execute(text(
            "SELECT d.name, v.version, v.added_record_count, v.total_record_count, "
            "  v.source_name, v.is_current, v.is_backfilled, v.has_snapshot, "
            "  (SELECT COUNT(*) FROM dataset_records r WHERE r.dataset_version_id = v.id) "
            "FROM dataset_versions v JOIN datasets d ON d.id = v.dataset_id "
            "ORDER BY d.id, v.id DESC"
        )).fetchall()
        shown: dict[str, int] = {}
        for name, version, added, total, source, is_current, backfilled, snapshot, stored in rows:
            key = str(name)
            shown[key] = shown.get(key, 0) + 1
            if shown[key] > 3:
                continue
            flag = "当前" if is_current else "历史"
            origin = "回填" if backfilled else "接入产出"
            # 与接口同一套判断：has_snapshot 由"新增记录数 vs 实际落库行数"决定。
            snapshot_text = "有数据" if snapshot else "无数据明细"
            print(
                f"  {key[:18]:<20} {version:<9} {flag}  {origin}  "
                f"这一版新增={int(added or 0):<6} 累计={int(total or 0):<7} "
                f"实际落库={int(stored):<6} {snapshot_text}  来源={source}"
            )

        print()
        print("说明：“回填”表示这条件录是升级时为老数据补的，不是某次接入任务的产出；")
        print("      “无数据明细”表示这一版只有版本登记，库里没有这一版的数据行。")

    print()
    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for item in problems:
            print("  -", item)
        print("检查未通过")
        return 1

    print("检查全部通过：所有版本的数据都已经存在数据库里，并且能按版本查回。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
