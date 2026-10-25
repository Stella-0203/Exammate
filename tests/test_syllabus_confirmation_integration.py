
import os
import tempfile
import unittest

from storage.db import get_connection, init_db
from services.syllabus_service import confirm_exam_syllabus


class TestSyllabusConfirmationIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(
            self.temp_dir.name,
            "test_exammate.db",
        )
        init_db(db_path=self.db_path)

        # 准备一门课程和一场尚未确认考纲的考试。
        connection = get_connection(self.db_path)
        try:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO courses (name) VALUES (?)",
                    ("测试课程",),
                )
                self.course_id = cursor.lastrowid

                cursor = connection.execute(
                    """
                    INSERT INTO exam_goals
                        (course_id, name, exam_date, raw_syllabus_text, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.course_id,
                        "期末考试",
                        "2099-12-31",
                        "1. 线性表",
                        "needs_review",
                    ),
                )
                self.exam_id = cursor.lastrowid
        finally:
            connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_syllabus_item(self, content, status):
        connection = get_connection(self.db_path)
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO syllabus_items
                        (exam_id, parent_id, content, item_type,
                         origin, review_status, sort_order)
                    VALUES (?, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.exam_id,
                        content,
                        "other",
                        "original",
                        status,
                        1,
                    ),
                )
        finally:
            connection.close()

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

    def test_pending_item_prevents_confirmation(self):
        # 产品规则：还有待审核条目，就不能确认整份考纲。
        self.add_syllabus_item("线性表", "pending")

        with self.assertRaisesRegex(ValueError, "仍有待审核"):
            confirm_exam_syllabus(
                self.exam_id,
                db_path=self.db_path,
            )

        # 确认失败后，考试仍然处于待审核状态。
        self.assertEqual(self.get_exam_status(), "needs_review")

    def test_all_reviewed_items_allow_confirmation(self):
        # 产品规则：所有条目都已处理，才能确认考纲。
        self.add_syllabus_item("线性表", "confirmed")

        result = confirm_exam_syllabus(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertEqual(result, "confirmed")
        self.assertEqual(self.get_exam_status(), "confirmed")

    def test_missing_exam_raises_error(self):
        with self.assertRaisesRegex(ValueError, "考试目标不存在"):
            confirm_exam_syllabus(
                999999,
                db_path=self.db_path,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
