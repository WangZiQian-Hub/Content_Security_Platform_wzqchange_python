"""数据库还原脚本（只在升级出问题、需要退回时用）。

用法（在工程根目录执行）：

    back\\.venv\\Scripts\\python.exe back\\restore_database.py "D:\\...\\content_safety_20261001_2030.sql"

**注意：还原会用备份文件覆盖当前数据库，当前库里的新数据会消失。**
执行前会让你再确认一次。

建议先只还原代码（把备份的 app 目录覆盖回去）就够了，数据库通常不用还原：
新增的表和列旧代码不会读，不影响旧代码运行。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BACK_DIR = Path(__file__).resolve().parent

MYSQL_CANDIDATES = [
    Path(r"D:\MySQL\bin\mysql.exe"),
    Path(r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"),
    Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"),
    Path(r"C:\Program Files (x86)\MySQL\MySQL Server 8.0\bin\mysql.exe"),
]

# 备份文件里这些语句在"连到指定库执行"时不需要，跳过以免误建/误切库。
SKIP_PREFIXES = (
    "CREATE DATABASE",
    "DROP DATABASE",
    "USE ",
    "/*!",
    "SET @@",
    "LOCK TABLES",
    "UNLOCK TABLES",
    "DELIMITER",
)


def read_env() -> dict[str, str]:
    config = {
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "",
        "MYSQL_DATABASE": "content_safety",
    }
    env_file = BACK_DIR / ".env"
    if not env_file.exists():
        return config
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in config:
            config[key] = value.strip().strip('"').strip("'")
    return config


def split_statements(sql_text: str) -> list[str]:
    """按分号切分 SQL；跳过备份文件里的库级语句，避免误建库/误切库。"""
    statements: list[str] = []
    buffer: list[str] = []

    for raw_line in sql_text.splitlines():
        line = raw_line.strip()
        if not buffer and (not line or line.startswith("--") or line.startswith("/*")):
            continue
        if not buffer and line.upper().startswith(SKIP_PREFIXES):
            continue
        buffer.append(raw_line)
        if line.endswith(";"):
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            buffer = []

    trailing = "\n".join(buffer).strip().rstrip(";").strip()
    if trailing:
        statements.append(trailing)

    return statements


def restore_with_mysql_exe(mysql_exe: Path, config: dict[str, str], sql_path: Path) -> bool:
    arguments = [
        str(mysql_exe),
        f"--host={config['MYSQL_HOST']}",
        f"--port={config['MYSQL_PORT']}",
        f"--user={config['MYSQL_USER']}",
        "--default-character-set=utf8mb4",
        config["MYSQL_DATABASE"],
    ]
    if config["MYSQL_PASSWORD"]:
        arguments.insert(4, f"--password={config['MYSQL_PASSWORD']}")

    print(f"使用 mysql 客户端还原：{mysql_exe}")
    with sql_path.open("rb") as handle:
        completed = subprocess.run(arguments, stdin=handle, capture_output=True, text=True)
    if completed.returncode != 0:
        print("mysql 客户端还原失败：")
        print((completed.stderr or "").strip()[:800])
        return False
    return True


def restore_with_python(config: dict[str, str], sql_path: Path) -> bool:
    try:
        import pymysql
    except ImportError:
        print("没有找到 pymysql，无法使用 Python 方式还原。")
        return False

    print("使用 Python 方式还原（逐条执行 SQL）")
    statements = split_statements(sql_path.read_text(encoding="utf-8", errors="replace"))
    print(f"共 {len(statements)} 条语句")

    connection = pymysql.connect(
        host=config["MYSQL_HOST"],
        port=int(config["MYSQL_PORT"]),
        user=config["MYSQL_USER"],
        password=config["MYSQL_PASSWORD"],
        database=config["MYSQL_DATABASE"],
        charset="utf8mb4",
        autocommit=True,
    )
    executed = 0
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                try:
                    cursor.execute(statement)
                    executed += 1
                except Exception as error:  # noqa: BLE001
                    head = statement.splitlines()[0][:80]
                    print(f"  跳过一条失败语句（{head}...）：{error}")
    finally:
        connection.close()

    print(f"成功执行 {executed} / {len(statements)} 条语句")
    return executed > 0


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：python back\\restore_database.py <备份文件.sql>")
        return 2

    sql_path = Path(sys.argv[1])
    if not sql_path.exists():
        print(f"找不到备份文件：{sql_path}")
        return 1

    config = read_env()
    print("=" * 70)
    print("数据库还原")
    print(f"备份文件：{sql_path}")
    print(f"目标数据库：{config['MYSQL_HOST']}:{config['MYSQL_PORT']}/{config['MYSQL_DATABASE']}")
    print("=" * 70)
    print("警告：这会把数据库恢复到备份那一刻的状态，之后新增的数据会消失。")
    answer = input("确认还原请输入 yes：").strip().lower()
    if answer != "yes":
        print("已取消，没有做任何改动。")
        return 1

    mysql_exe = shutil.which("mysql")
    if mysql_exe is None:
        for candidate in MYSQL_CANDIDATES:
            if candidate.exists():
                mysql_exe = str(candidate)
                break

    ok = False
    if mysql_exe is not None:
        ok = restore_with_mysql_exe(Path(mysql_exe), config, sql_path)
    if not ok:
        ok = restore_with_python(config, sql_path)

    if not ok:
        print("还原失败，请把上面的报错发出来。")
        return 1

    print()
    print("还原完成。请重启后端，然后运行 back\\check_dataset_versions.py 确认状态。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
