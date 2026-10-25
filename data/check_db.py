
import sqlite3
from pathlib import Path


# 定位原来的正式数据库
DB_PATH = Path(__file__).resolve().parent / "exammate.db"


def check_database():
    print(f"数据库路径：{DB_PATH}")
    print(f"文件存在：{DB_PATH.is_file()}")

    if not DB_PATH.is_file():
        print("检查终止：没有找到数据库文件，请核对路径。")
        return

    # mode=ro：只读打开，不允许通过此连接修改数据库
    db_uri = DB_PATH.resolve().as_uri() + "?mode=ro"

    try:
        with sqlite3.connect(db_uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row

            # 1. 检查数据库完整性
            result = connection.execute(
                "PRAGMA quick_check"
            ).fetchall()

            print("\n【完整性检查】")
            for row in result:
                print(row[0])

            # 2. 查看数据库中的表
            tables = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()

            print("\n【数据表列表】")
            if not tables:
                print("没有找到用户数据表。")
                return

            for row in tables:
                table_name = row["name"]
                print(f"\n表名：{table_name}")

                # 表名来自 SQLite 元数据，双引号转义后再用于查询
                safe_name = table_name.replace('"', '""')
                count = connection.execute(
                    f'SELECT COUNT(*) FROM "{safe_name}"'
                ).fetchone()[0]

                print(f"记录数量：{count}")

            print("\n只读检查完成。")

    except sqlite3.Error as exc:
        print(f"\n数据库读取或检查失败：{exc}")


if __name__ == "__main__":
    check_database()
