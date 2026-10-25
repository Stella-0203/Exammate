
import os
import tempfile
import unittest
from unittest.mock import patch

from storage.db import get_connection, init_db
from services.syllabus_service import create_exam_with_syllabus


class TestExamCreationIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(
            self.temp_dir.name,
            "test_exammate.db",
        )
        init_db(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("services.syllabus_service.generate_syllabus_suggestions")
    def test_create_exam_and_save_syllabus(self, mock_generate):
        # 模拟模型返回的候选项，避免产生真实 API 调用。
        mock_generate.return_value = [
            {
                "source_sort_order": 1,
                "content": "掌握线性表的顺序存储与链式存储",
                "item_type": "knowledge",
                "rationale": "这是理解线性表的核心知识点。",
            },
            {
                "source_sort_order": 2,
                "content": "理解二叉树的遍历方法",
                "item_type": "knowledge",
                "rationale": "这是树与二叉树的重要内容。",
            },
        ]

        result = create_exam_with_syllabus(
            course_name="集成测试课程",
            exam_name="期末考试",
            raw_syllabus_text="1. 线性表\n2. 树与二叉树",
            exam_date="2099-12-31",
            db_path=self.db_path,
        )

        # 1. 检查业务服务返回值。
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["original_count"], 2)
        self.assertEqual(result["suggestion_count"], 2)
        self.assertGreater(result["course_id"], 0)
        self.assertGreater(result["exam_id"], 0)

        # 2. 检查数据库中的课程和考试。
        connection = get_connection(self.db_path)
        try:
            course = connection.execute(
                "SELECT * FROM courses WHERE id = ?",
                (result["course_id"],),
            ).fetchone()

            exam = connection.execute(
                "SELECT * FROM exam_goals WHERE id = ?",
                (result["exam_id"],),
            ).fetchone()

            self.assertIsNotNone(course)
            self.assertEqual(course["name"], "集成测试课程")
            self.assertIsNotNone(exam)
            self.assertEqual(exam["name"], "期末考试")
            self.assertEqual(exam["status"], "needs_review")

            # 3. 检查原始条目与候选项的父子关系。
            items = connection.execute(
                """
                SELECT id, parent_id, content, origin, review_status
                FROM syllabus_items
                WHERE exam_id = ?
                ORDER BY id
                """,
                (result["exam_id"],),
            ).fetchall()

            originals = [
                item for item in items
                if item["origin"] == "original"
            ]
            suggestions = [
                item for item in items
                if item["origin"] == "inferred"
            ]

            self.assertEqual(len(originals), 2)
            self.assertEqual(len(suggestions), 2)

            original_ids = {item["id"] for item in originals}

            for item in originals:
                self.assertIsNone(item["parent_id"])
                self.assertEqual(item["review_status"], "pending")

            for item in suggestions:
                self.assertIn(item["parent_id"], original_ids)
                self.assertEqual(item["review_status"], "pending")

        finally:
            connection.close()

        # 确认测试使用了模拟结果，没有调用真实模型生成函数。
        mock_generate.assert_called_once()

    @patch("services.syllabus_service.generate_syllabus_suggestions")
    def test_model_failure_does_not_create_database_records(
        self, mock_generate
    ):
        mock_generate.side_effect = RuntimeError("模拟模型调用失败")

        with self.assertRaisesRegex(RuntimeError, "模拟模型调用失败"):
            create_exam_with_syllabus(
                course_name="不应创建的课程",
                exam_name="测试考试",
                raw_syllabus_text="1. 线性表",
                db_path=self.db_path,
            )

        # 模型生成失败发生在数据库事务之前，不应写入课程或考试。
        connection = get_connection(self.db_path)
        try:
            course_count = connection.execute(
                "SELECT COUNT(*) FROM courses"
            ).fetchone()[0]

            exam_count = connection.execute(
                "SELECT COUNT(*) FROM exam_goals"
            ).fetchone()[0]

            self.assertEqual(course_count, 0)
            self.assertEqual(exam_count, 0)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
