
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from services.syllabus_service import add_syllabus_suggestion
from storage.db import get_connection, init_db


class AddSuggestionTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "add_test.db"
        init_db(self.db_path)

        connection = get_connection(self.db_path)

        try:
            with connection:
                course_id = connection.execute(
                    "INSERT INTO courses (name) VALUES (?)",
                    ("测试课程",),
                ).lastrowid

                self.exam_id = connection.execute(
                    """
                    INSERT INTO exam_goals (
                        course_id, name, raw_syllabus_text, status
                    )
                    VALUES (?, ?, ?, 'confirmed')
                    """,
                    (course_id, "测试考试", "1. 测试考纲"),
                ).lastrowid

                self.other_exam_id = connection.execute(
                    """
                    INSERT INTO exam_goals (
                        course_id, name, raw_syllabus_text, status
                    )
                    VALUES (?, ?, ?, 'confirmed')
                    """,
                    (course_id, "另一份考试", "1. 其他考纲"),
                ).lastrowid

                self.parent_id = connection.execute(
                    """
                    INSERT INTO syllabus_items (
                        exam_id, content, item_type, origin,
                        review_status, sort_order
                    )
                    VALUES (?, ?, 'other', 'original', 'confirmed', 1)
                    """,
                    (self.exam_id, "测试原始条目"),
                ).lastrowid

                self.other_parent_id = connection.execute(
                    """
                    INSERT INTO syllabus_items (
                        exam_id, content, item_type, origin,
                        review_status, sort_order
                    )
                    VALUES (?, ?, 'other', 'original', 'confirmed', 1)
                    """,
                    (self.other_exam_id, "另一份考试的条目"),
                ).lastrowid
        finally:
            connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def get_exam_status(self):
        connection = get_connection(self.db_path)
        try:
            row = connection.execute(
                "SELECT status FROM exam_goals WHERE id = ?",
                (self.exam_id,),
            ).fetchone()
            return row["status"]
        finally:
            connection.close()

    def test_add_reopens_review(self):
        result = add_syllabus_suggestion(
            exam_id=self.exam_id,
            parent_id=self.parent_id,
            content="用户补充的知识点",
            db_path=self.db_path,
        )

        self.assertEqual(result["review_status"], "pending")
        self.assertEqual(result["exam_status"], "needs_review")
        self.assertEqual(self.get_exam_status(), "needs_review")

        connection = get_connection(self.db_path)
        try:
            item = connection.execute(
                """
                SELECT *
                FROM syllabus_items
                WHERE id = ?
                """,
                (result["suggestion_id"],),
            ).fetchone()

            self.assertEqual(item["origin"], "inferred")
            self.assertEqual(item["review_status"], "pending")
            self.assertEqual(item["parent_id"], self.parent_id)
        finally:
            connection.close()

    def test_reject_invalid_parent(self):
        with self.assertRaises(ValueError):
            add_syllabus_suggestion(
                exam_id=self.exam_id,
                parent_id=self.other_parent_id,
                content="不应被插入",
                db_path=self.db_path,
            )

        self.assertEqual(self.get_exam_status(), "confirmed")

        connection = get_connection(self.db_path)
        try:
            count = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM syllabus_items
                WHERE exam_id = ? AND origin = 'inferred'
                """,
                (self.exam_id,),
            ).fetchone()["count"]

            self.assertEqual(count, 0)
        finally:
            connection.close()

    def test_reject_empty_content(self):
        with self.assertRaises(ValueError):
            add_syllabus_suggestion(
                exam_id=self.exam_id,
                parent_id=self.parent_id,
                content="   ",
                db_path=self.db_path,
            )

        self.assertEqual(self.get_exam_status(), "confirmed")



    def test_add_then_confirm_completes_review(self):
        # 1. 初始状态应为审核完成
        self.assertEqual(self.get_exam_status(), "confirmed")

        # 2. 新增候选项，考试应重新进入待审核状态
        result = add_syllabus_suggestion(
            exam_id=self.exam_id,
            parent_id=self.parent_id,
            content="新增后需要审核的知识点",
            db_path=self.db_path,
        )

        suggestion_id = result["suggestion_id"]

        self.assertEqual(result["review_status"], "pending")
        self.assertEqual(self.get_exam_status(), "needs_review")

        # 3. 确认新候选项
        from services.syllabus_service import confirm_suggestion

        status = confirm_suggestion(
            suggestion_id=suggestion_id,
            db_path=self.db_path,
        )

        # 4. 所有候选项处理完成后，考试应重新确认
        self.assertEqual(status, "confirmed")
        self.assertEqual(self.get_exam_status(), "confirmed")

        # 5. 检查新候选项确实已确认
        connection = get_connection(self.db_path)
        try:
            item = connection.execute(
                """
                SELECT review_status
                FROM syllabus_items
                WHERE id = ?
                """,
                (suggestion_id,),
            ).fetchone()

            self.assertEqual(item["review_status"], "confirmed")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
