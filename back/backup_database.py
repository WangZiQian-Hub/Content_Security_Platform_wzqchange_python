"""数据库备份脚本（升级前先跑一次）。

用法（在工程根目录执行）：

    back\\.venv\\Scripts\\python.exe back\\backup_database.py

优先使用 mysqldump（自动在常见位置查找）；找不到时退回纯 Python 导出，
两种方式都能生成可以直接还原的 .sql 文件。

备份文件默认放在：<工程根目录>\\版本\\数据库备份\\content_safety_日期_时间.sql
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACK_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACK_DIR.parent

# mysqldump 的常见位置；找不到就在 PATH 里找。
DUMP_CANDIDATES = [
    Path(r"D:\MySQL\bin\mysqldump.exe"),
    Path(r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysqldump.exe"),
    Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"),
    Path(r"C:\Program Files (x86)\MySQL\MySQL Server 8.0\bin\mysqldump.exe"),
]

ENV_FILE = BACK_DIR / ".env"


def read_env() -> dict[str, str]:
    """读取 back/.env 里的 MySQL 配置。"""
    config = {
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "",
        "MYSQL_DATABASE": "content_safety",
    }
    if not ENV_FILE.exists():
        return config
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in config:
            config[key] = value.strip().strip('"').strip("'")
    return config


def find_mysqldump() -> Path | None:
    found = shutil.which("mysqldump")
    if found:
        return Path(found)
    for candidate in DUMP_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def backup_with_mysqldump(dump_exe: Path, config: dict[str, str], target: Path) -> bool:
    arguments = [
        str(dump_exe),
        f"--host={config['MYSQL_HOST']}",
        f"--port={config['MYSQL_PORT']}",
        f"--user={config['MYSQL_USER']}",
        "--default-character-set=utf8mb4",
        "--single-transaction",
        "--routines",
        "--events",
        "--add-drop-table",
        "--databases",
        config["MYSQL_DATABASE"],
        f"--result-file={target}",
    ]
    # 密码为空时不传 --password，避免部分版本把它当成"要求交互输入"。
    if config["MYSQL_PASSWORD"]:
        arguments.insert(4, f"--password={config['MYSQL_PASSWORD']}")

    print(f"使用 mysqldump：{dump_exe}")
    completed = subprocess.run(arguments, capture_output=True, text=True)
    if completed.returncode != 0:
        print("mysqldump 执行失败，改用纯 Python 方式：")
        print((completed.stderr or "").strip()[:500])
        return False
    return target.exists() and target.stat().st_size > 0


def backup_with_python(config: dict[str, str], target: Path) -> bool:
    try:
        import pymysql
    except ImportError:
        print("没有找到 pymysql，无法使用 Python 方式备份。")
        return False

    print("使用 Python 方式导出（逐表导出结构与数据）")
    connection = pymysql.connect(
        host=config["MYSQL_HOST"],
        port=int(config["MYSQL_PORT"]),
        user=config["MYSQL_USER"],
        password=config["MYSQL_PASSWORD"],
        database=config["MYSQL_DATABASE"],
        charset="utf8mb4",
    )
    try:
        with connection.cursor() as cursor, target.open("w", encoding="utf-8") as output:
            output.write(f"-- {config['MYSQL_DATABASE']} 备份 {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            output.write("SET NAMES utf8mb4;\n")

            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                quoted_table = "`" + table + "`"
                cursor.execute(f"SHOW CREATE TABLE {quoted_table}")
                output.write(f"\nDROP TABLE IF EXISTS {quoted_table};\n")
                output.write(cursor.fetchone()[1] + ";\n")

                cursor.execute(f"SELECT * FROM {quoted_table}")
                rows = cursor.fetchall()
                if not rows:
                    continue

                cursor.execute(f"SHOW COLUMNS FROM {quoted_table}")
                columns = [row[0] for row in cursor.fetchall()]
                column_list = ", ".join("`" + column + "`" for column in columns)

                for row in rows:
                    values = ", ".join(
                        "NULL" if value is None else connection.escape(value) for value in row
                    )
                    output.write(
                        f"INSERT INTO {quoted_table} ({column_list}) VALUES ({values});\n"
                    )
        return True
    finally:
        connection.close()


def main() -> int:
    config = read_env()
    backup_dir = PROJECT_DIR / "版本" / "数据库备份"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    target = backup_dir / f"{config['MYSQL_DATABASE']}_{stamp}.sql"

    print("=" * 70)
    print("数据库备份")
    print(f"数据库：{config['MYSQL_HOST']}:{config['MYSQL_PORT']}/{config['MYSQL_DATABASE']}")
    print(f"备份到：{target}")
    print("=" * 70)

    dump_exe = find_mysqldump()
    if dump_exe is not None:
        ok = backup_with_mysqldump(dump_exe, config, target)
    else:
        ok = backup_with_python(config, target)

    if not ok:
        # mysqldump 失败时再试一次纯 Python 方式。
        target.unlink(missing_ok=True)
        ok = backup_with_python(config, target)

    if not ok or not target.exists() or target.stat().st_size == 0:
        print("备份失败，请不要继续升级，先把上面的报错发出来。")
        return 1

    size_mb = target.stat().st_size / 1024 / 1024
    print()
    print(f"备份成功：{target}")
    print(f"文件大小：{size_mb:.2f} MB")
    print()
    print("请把这个文件复制到别的地方（U盘/网盘）再继续升级。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
