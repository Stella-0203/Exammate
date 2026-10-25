from storage.db import get_connection, init_db

TEST_DB = "data/exammate_test.db"

# 初始化测试数据库
init_db(db_path=TEST_DB)

# 检查原有表和新增表
with get_connection(db_path=TEST_DB) as conn:
    tables = {
        row["name"]
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    }

expected_tables = {
    "courses",
    "exam_goals",
    "syllabus_items",
    "materials",
    "chat_conversations",
    "chat_messages",
}

missing = expected_tables - tables

if missing:
    raise RuntimeError(f"缺少数据表：{missing}")

print("数据库初始化成功！")
print("原有业务表和新增聊天表均存在。")