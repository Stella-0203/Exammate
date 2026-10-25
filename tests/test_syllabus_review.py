
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from services.syllabus_service import (
    confirm_original_syllabus_item,
    confirm_suggestion,
    edit_suggestion,
    exclude_suggestion,
)
from storage.db import get_connection, init_db


class SyllabusReviewTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "review_test.db"
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
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        course_id,
                        "测试考试",
                        "1. 测试考纲",
                        "needs_review",
                    ),
                ).lastrowid

                self.original_id = connection.execute(
                    """
                    INSERT INTO syllabus_items (
                        exam_id, content, item_type, origin,
                        review_status, sort_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.exam_id,
                        "测试考纲",
                        "other",
                        "original",
                        "pending",
                        1,
                    ),
                ).lastrowid

                self.suggestion_ids = []
                for content in ("候选知识点 A", "候选知识点 B"):
                    suggestion_id = connection.execute(
                        """
                        INSERT INTO syllabus_items (
                            exam_id, parent_id, content, item_type,
                            origin, review_status, rationale, sort_order
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.exam_id,
                            self.original_id,
                            content,
                            "knowledge",
                            "inferred",
                            "pending",
                            "测试依据",
                            1,
                        ),
                    ).lastrowid

                    self.suggestion_ids.append(suggestion_id)
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

    def get_suggestion(self, suggestion_id):
        connection = get_connection(self.db_path)
        try:
            return connection.execute(
                """
                SELECT content, review_status, parent_id
                FROM syllabus_items
                WHERE id = ?
                """,
                (suggestion_id,),
            ).fetchone()
        finally:
            connection.close()

    def test_partial_review_then_complete(self):
        first, second = self.suggestion_ids

        # 只审核一个候选项，仍有其他待审核条目
        status = confirm_suggestion(first, self.db_path)
        self.assertEqual(status, "needs_review")
        self.assertEqual(self.get_exam_status(), "needs_review")

        # 第二个候选项被排除，但原始考纲仍待审核
        status = exclude_suggestion(second, self.db_path)
        self.assertEqual(status, "needs_review")
        self.assertEqual(self.get_exam_status(), "needs_review")
        self.assertEqual(
            self.get_suggestion(second)["review_status"],
            "excluded",
        )

        # 完成原始考纲审核后，考试才全部审核完成
        status = confirm_original_syllabus_item(
            self.original_id,
            self.db_path,
        )
        self.assertEqual(status, "confirmed")
        self.assertEqual(self.get_exam_status(), "confirmed")

    def test_edit_suggestion(self):
        suggestion_id = self.suggestion_ids[0]

        status = edit_suggestion(
            suggestion_id,
            "修改后的知识点",
            self.db_path,
        )

        item = self.get_suggestion(suggestion_id)
        self.assertEqual(item["content"], "修改后的知识点")
        self.assertEqual(item["review_status"], "edited")
        self.assertEqual(item["parent_id"], self.original_id)
        self.assertEqual(status, "needs_review")

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            edit_suggestion(
                self.suggestion_ids[0],
                "   ",
                self.db_path,
            )

        with self.assertRaises(ValueError):
            confirm_suggestion(999999, self.db_path)

        # 原始考纲条目不能作为候选项审核
        with self.assertRaises(ValueError):
            exclude_suggestion(self.original_id, self.db_path)


if __name__ == "__main__":
    unittest.main()
