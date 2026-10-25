import sqlite3
import tempfile
from pathlib import Path

from core.llm_client import chat_completion
from storage.db import get_connection, init_db


def check_database() -> None:
    """检查正式数据库初始化，以及临时数据库的写入和读取。"""

    # 初始化项目正式数据库
    init_db()

    # 用临时数据库测试读写，避免向正式数据库写入测试数据
    with tempfile.TemporaryDirectory() as temp_dir:
        test_db_path = Path(temp_dir) / "test.db"

        init_db(test_db_path)

        connection = get_connection(test_db_path)

        try:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE test_records (
                        id INTEGER PRIMARY KEY,
                        content TEXT NOT NULL
                    )
                    """
                )

                connection.execute(
                    "INSERT INTO test_records (content) VALUES (?)",
                    ("ExamMate 数据库读写成功",),
                )

            row = connection.execute(
                "SELECT content FROM test_records WHERE id = 1"
            ).fetchone()

            assert row is not None
            assert row["content"] == "ExamMate 数据库读写成功"

        finally:
            connection.close()

    print("SQLite 初始化、写入和读取：通过")


def check_model_api() -> None:
    """检查统一模型客户端是否可以正常工作。"""

    result = chat_completion(
        messages=[
            {
                "role": "system",
                "content": "你是一个简洁的助手。",
            },
            {
                "role": "user",
                "content": "请只回复：ExamMate 模型调用成功",
            },
        ]
    )

    assert result.strip(), "模型返回内容为空。"

    print("DeepSeek 统一客户端调用：通过")
    print("模型返回内容：", result.strip())


def main() -> None:
    print("开始检查 ExamMate 基础设施...\n")

    check_database()
    check_model_api()

    print("\n基础设施检查完成。")


if __name__ == "__main__":
    main()