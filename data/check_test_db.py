
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "exammate_test.db"

print(f"测试数据库路径：{DB_PATH}")
print(f"文件存在：{DB_PATH.is_file()}")

if not DB_PATH.is_file():
    print("尚未找到测试数据库文件。")
else:
    try:
        connection = sqlite3.connect(
            f"{DB_PATH.resolve().as_uri()}?mode=ro",
            uri=True
        )

        result = connection.execute("PRAGMA quick_check").fetchone()
        print(f"完整性检查：{result[0]}")

        tables = connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
        """).fetchall()

        print("现有数据表：")
        for table in tables:
            print(f"- {table[0]}")

        connection.close()

    except sqlite3.Error as exc:
        print(f"SQLite 检查失败：{exc}")
