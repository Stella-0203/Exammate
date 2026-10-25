
import unittest
from unittest.mock import patch

from core import agent


class TestListExams(unittest.TestCase):
    """测试考试目标查询。"""

    @patch("core.agent._read_table")
    def test_list_exams_returns_exams_and_courses(self, mock_read_table):
        mock_read_table.side_effect = [
            [{"id": 1, "course_id": 2, "exam_name": "期末考试"}],
            [{"id": 2, "course_name": "数据结构"}],
        ]

        result = agent.list_exams()

        self.assertEqual(len(result["exams"]), 1)
        self.assertEqual(result["exams"][0]["id"], 1)
        self.assertEqual(result["courses"][0]["course_name"], "数据结构")
        self.assertIn("note", result)
        self.assertEqual(mock_read_table.call_count, 2)

    @patch("core.agent._read_table")
    def test_list_exams_when_database_is_empty(self, mock_read_table):
        mock_read_table.return_value = []

        result = agent.list_exams()

        self.assertEqual(result["exams"], [])
        self.assertEqual(result["courses"], [])


class TestGetExamDetails(unittest.TestCase):
    """测试考试详情和考纲关联。"""

    @patch("core.agent._read_table")
    def test_returns_exam_and_related_syllabus(self, mock_read_table):
        mock_read_table.side_effect = [
            [
                {"id": 1, "exam_name": "期末考试"},
                {"id": 2, "exam_name": "补考"},
            ],
            [
                {"id": 10, "exam_id": 1, "topic": "线性表"},
                {"id": 11, "exam_id": 2, "topic": "树"},
                {"id": 12, "exam_id": 1, "topic": "图"},
            ],
        ]

        result = agent.get_exam_details(1)

        self.assertEqual(result["exam"]["id"], 1)
        self.assertEqual(
            [item["topic"] for item in result["syllabus_items"]],
            ["线性表", "图"],
        )

    def test_invalid_exam_id(self):
        for exam_id in [0, -1, "1", 1.0, True, None]:
            with self.subTest(exam_id=exam_id):
                with self.assertRaises(ValueError):
                    agent.get_exam_details(exam_id)

    @patch("core.agent._read_table")
    def test_exam_not_found(self, mock_read_table):
        mock_read_table.return_value = []

        with self.assertRaisesRegex(ValueError, "没有找到考试"):
            agent.get_exam_details(999)


class TestGetReviewPlan(unittest.TestCase):
    """测试当前生效的复习计划查询。"""

    @patch("core.agent.get_current_review_plan")
    def test_plan_not_found(self, mock_get_plan):
        mock_get_plan.return_value = None

        result = agent.get_review_plan(1)

        self.assertTrue(result["success"])
        self.assertFalse(result["found"])
        self.assertIn("没有生效的复习计划", result["message"])
        mock_get_plan.assert_called_once_with(1)

    @patch("core.agent._json_safe")
    @patch("core.agent.get_current_review_plan")
    def test_plan_found(self, mock_get_plan, mock_json_safe):
        plan = {
            "id": 10,
            "status": "active",
            "tasks": [{"id": 101, "status": "pending"}],
        }
        mock_get_plan.return_value = plan
        mock_json_safe.return_value = plan

        result = agent.get_review_plan(1)

        self.assertTrue(result["success"])
        self.assertTrue(result["found"])
        self.assertEqual(result["plan"]["id"], 10)
        mock_get_plan.assert_called_once_with(1)
        mock_json_safe.assert_called_once_with(plan)

    def test_invalid_exam_id(self):
        for exam_id in [0, -1, "1", 1.0, True, None]:
            with self.subTest(exam_id=exam_id):
                with self.assertRaises(ValueError):
                    agent.get_review_plan(exam_id)


class TestUpdateTaskStatus(unittest.TestCase):
    """测试复习任务状态更新。"""

    @patch("core.agent.update_review_task_status")
    def test_update_task_success(self, mock_update):
        mock_update.return_value = True

        result = agent.update_task_status(
            task_id=101,
            status="completed",
            plan_id=10,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["task_id"], 101)
        self.assertEqual(result["plan_id"], 10)
        self.assertEqual(result["status"], "completed")
        mock_update.assert_called_once_with(
            task_id=101,
            status="completed",
            plan_id=10,
        )

    @patch("core.agent.update_review_task_status")
    def test_update_task_not_found(self, mock_update):
        mock_update.return_value = False

        result = agent.update_task_status(
            task_id=999,
            status="completed",
            plan_id=10,
        )

        self.assertFalse(result["success"])
        self.assertIn("任务状态未更新", result["error"])

    def test_invalid_task_id_and_plan_id(self):
        invalid_ids = [0, -1, "1", 1.0, True, None]

        for invalid_id in invalid_ids:
            with self.subTest(task_id=invalid_id):
                with self.assertRaises(ValueError):
                    agent.update_task_status(
                        task_id=invalid_id,
                        status="completed",
                        plan_id=10,
                    )

            with self.subTest(plan_id=invalid_id):
                with self.assertRaises(ValueError):
                    agent.update_task_status(
                        task_id=101,
                        status="completed",
                        plan_id=invalid_id,
                    )

    def test_invalid_status(self):
        for status in ["done", "in_progress", "", None]:
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    agent.update_task_status(
                        task_id=101,
                        status=status,
                        plan_id=10,
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
