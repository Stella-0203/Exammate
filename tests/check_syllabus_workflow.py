
from pathlib import Path
from tempfile import TemporaryDirectory

from services.syllabus_service import create_exam_with_syllabus
from storage.db import get_connection, init_db


def main() -> None:
    raw_text = """
    1. 线性表的基本概念与存储结构
    2. 掌握栈和队列的基本操作
    3. 熟悉图的遍历算法，理解 BFS 和 DFS 的区别
    """

    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "workflow_test.db"
        init_db(db_path)

        print("开始执行考纲业务闭环测试...")
        print("正在调用 DeepSeek，请稍候。\n")

        result = create_exam_with_syllabus(
            course_name="数据结构",
            exam_name="数据结构期末考试",
            raw_syllabus_text=raw_text,
            db_path=db_path,
        )

        print("考试创建与考纲保存：通过")
        print("原始条目数量：", result["original_count"])
        print("候选展开项数量：", result["suggestion_count"])

        connection = get_connection(db_path)

        try:
            # 检查考试记录和原始全文
            exam = connection.execute(
                """
                SELECT *
                FROM exam_goals
                WHERE id = ?
                """,
                (result["exam_id"],),
            ).fetchone()

            assert exam is not None
            assert exam["raw_syllabus_text"] == raw_text
            assert exam["status"] == "needs_review"

            # 检查原始条目和候选项
            originals = connection.execute(
                """
                SELECT id, content, sort_order
                FROM syllabus_items
                WHERE exam_id = ? AND origin = 'original'
                ORDER BY sort_order
                """,
                (result["exam_id"],),
            ).fetchall()

            suggestions = connection.execute(
                """
                SELECT child.*, parent.origin AS parent_origin
                FROM syllabus_items AS child
                JOIN syllabus_items AS parent
                    ON child.parent_id = parent.id
                WHERE child.exam_id = ?
                  AND child.origin = 'inferred'
                ORDER BY child.id
                """,
                (result["exam_id"],),
            ).fetchall()

            assert len(originals) == result["original_count"]
            assert len(suggestions) == result["suggestion_count"]

            assert all(
                item["parent_origin"] == "original"
                for item in suggestions
            )

            assert all(
                item["review_status"] == "pending"
                for item in suggestions
            )

            assert all(
                item["parent_id"] in {
                    original["id"] for original in originals
                }
                for item in suggestions
            )

            print("原始考纲全文完整保存：通过")
            print("原始条目与候选项关联：通过")
            print("候选项审核状态正确：通过")

            print("\n数据库读取结果摘要：")
            for original in originals:
                child_count = sum(
                    item["parent_id"] == original["id"]
                    for item in suggestions
                )
                print(
                    f'{original["sort_order"]}. '
                    f'{original["content"]} '
                    f'（候选项 {child_count} 条）'
                )

        finally:
            connection.close()

    print("\n考纲业务闭环测试完成。")


if __name__ == "__main__":
    main()
