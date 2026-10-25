
from pathlib import Path
from tempfile import TemporaryDirectory

from storage.db import get_connection, init_db


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_exammate.db"
        init_db(db_path)

        connection = get_connection(db_path)

        try:
            # 创建一门课程
            cursor = connection.execute(
                "INSERT INTO courses (name) VALUES (?)",
                ("数据结构",),
            )
            course_id = cursor.lastrowid

            # 创建一次考试，并保存原始考纲全文
            cursor = connection.execute(
                """
                INSERT INTO exam_goals
                    (course_id, name, raw_syllabus_text, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    course_id,
                    "数据结构期末考试",
                    "熟悉图的遍历算法，理解 BFS 和 DFS 的区别",
                    "needs_review",
                ),
            )
            exam_id = cursor.lastrowid

            # 保存原始考纲条目
            cursor = connection.execute(
                """
                INSERT INTO syllabus_items
                    (exam_id, content, origin, review_status, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    exam_id,
                    "熟悉图的遍历算法，理解 BFS 和 DFS 的区别",
                    "original",
                    "pending",
                    #"confirmed",
                    1,
                ),
            )
            original_item_id = cursor.lastrowid

            # 保存一个模型提出的展开项
            connection.execute(
                """
                INSERT INTO syllabus_items
                    (
                        exam_id, parent_id, content, item_type,
                        origin, review_status, rationale, sort_order
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exam_id,
                    original_item_id,
                    "能够解释 BFS 与 DFS 的遍历策略差异",
                    "skill",
                    "inferred",
                    "pending",
                    "原始考纲要求理解两种遍历算法的区别",
                    1,
                ),
            )

            connection.commit()

            # 联合查询，验证课程、考试和条目之间的关联
            row = connection.execute(
                """
                SELECT
                    c.name AS course_name,
                    e.name AS exam_name,
                    e.raw_syllabus_text,
                    parent.content AS original_content,
                    child.content AS inferred_content,
                    child.origin,
                    child.review_status
                FROM syllabus_items AS child
                JOIN syllabus_items AS parent
                    ON child.parent_id = parent.id
                JOIN exam_goals AS e
                    ON child.exam_id = e.id
                JOIN courses AS c
                    ON e.course_id = c.id
                WHERE child.origin = 'inferred'
                """
            ).fetchone()

            assert row is not None
            assert row["course_name"] == "数据结构"
            assert row["exam_name"] == "数据结构期末考试"
            assert row["raw_syllabus_text"] != ""
            assert row["original_content"].startswith("熟悉图的遍历")
            assert row["origin"] == "inferred"
            assert row["review_status"] == "pending"

            print("课程创建与读取：通过")
            print("考试目标与原始考纲保存：通过")
            print("原始条目与展开项的父子关联：通过")
            print("展开项来源与审核状态保存：通过")

        finally:
            connection.close()


if __name__ == "__main__":
    main()
