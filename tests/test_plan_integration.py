
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from storage.db import get_connection, init_db
from services.plan_service import generate_review_plan
from services.plan_persistence_service import (
    save_review_plan,
    get_current_review_plan,
)


class TestPlanIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")

        init_db(self.db_path)

        connection = get_connection(self.db_path)
        try:
            cursor = connection.execute(
                """
                INSERT INTO courses (name)
                VALUES (?)
                """,
                ("数据结构",),
            )
            self.course_id = cursor.lastrowid

            exam_date = (date.today() + timedelta(days=7)).isoformat()
            cursor = connection.execute(
                """
                INSERT INTO exam_goals (
                    course_id, name, exam_date,
                    raw_syllabus_text, status
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.course_id,
                    "数据结构期末考试",
                    exam_date,
                    "1. 线性表",
                    "confirmed",
                ),
            )
            self.exam_id = cursor.lastrowid

            connection.execute(
                """
                INSERT INTO syllabus_items (
                    exam_id, parent_id, content,
                    item_type, origin, review_status, sort_order
                )
                VALUES (?, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    self.exam_id,
                    "线性表",
                    "knowledge",
                    "original",
                    "confirmed",
                    1,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _mock_model_result(self):
        return json.dumps(
            {
                "tasks": [
                    {
                        "day": 1,
                        "topic": "线性表",
                        "task_type": "learn",
                        "priority": "high",
                        "estimated_minutes": 30,
                        "description": "复习线性表的逻辑结构和基本操作。",
                    },
                    {
                        "day": 2,
                        "topic": "线性表",
                        "task_type": "practice",
                        "priority": "medium",
                        "estimated_minutes": 40,
                        "description": "完成线性表相关练习并整理错题。",
                    },
                ]
            },
            ensure_ascii=False,
        )

    def test_generate_save_and_read_plan(self):
        """模型生成的计划能够保存，并从数据库完整读取。"""
        with patch(
            "services.plan_service.chat_completion",
            return_value=self._mock_model_result(),
        ) as mock_chat:
            generated_plan = generate_review_plan(
                exam_id=self.exam_id,
                daily_available_minutes=60,
                review_goal="掌握核心知识点并完成练习",
                db_path=self.db_path,
            )

        mock_chat.assert_called_once()

        # 生成服务负责生成，不应自行写入数据库。
        connection = get_connection(self.db_path)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM review_plans"
            ).fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            connection.close()

        # 生成结果不包含 review_goal，需要在保存时补上。
        plan_to_save = {
            **generated_plan,
            "review_goal": "掌握核心知识点并完成练习",
        }

        plan_id = save_review_plan(
            exam_id=self.exam_id,
            plan=plan_to_save,
            db_path=self.db_path,
        )

        self.assertIsNotNone(plan_id)

        saved_plan = get_current_review_plan(
            exam_id=self.exam_id,
            db_path=self.db_path,
        )

        self.assertIsNotNone(saved_plan)
        self.assertEqual(saved_plan["id"], plan_id)
        self.assertEqual(
            saved_plan["review_goal"],
            "掌握核心知识点并完成练习",
        )
        self.assertEqual(saved_plan["exam_date"], generated_plan["exam_date"])
        self.assertEqual(
            saved_plan["daily_available_minutes"],
            60,
        )
        self.assertEqual(len(saved_plan["tasks"]), 2)

        first_task = saved_plan["tasks"][0]
        self.assertEqual(first_task["topic"], "线性表")
        self.assertEqual(first_task["task_type"], "learn")
        self.assertEqual(first_task["estimated_minutes"], 30)

    def test_invalid_model_json_does_not_save_plan(self):
        """模型返回非法 JSON 时，数据库中不应产生复习计划。"""
        with patch(
            "services.plan_service.chat_completion",
            return_value="这不是合法 JSON",
        ):
            with self.assertRaisesRegex(ValueError, "合法 JSON"):
                generate_review_plan(
                    exam_id=self.exam_id,
                    daily_available_minutes=60,
                    db_path=self.db_path,
                )

        self.assertIsNone(
            get_current_review_plan(
                exam_id=self.exam_id,
                db_path=self.db_path,
            )
        )

        connection = get_connection(self.db_path)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM review_plans"
            ).fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            connection.close()

    def test_invalid_generated_plan_does_not_save_plan(self):
        """模型输出不符合业务规则时，不应保存计划。"""
        invalid_result = json.dumps(
            {
                "tasks": [
                    {
                        "day": 1,
                        "topic": "不在考纲中的知识点",
                        "task_type": "learn",
                        "priority": "high",
                        "estimated_minutes": 30,
                        "description": "测试无效知识点。",
                    }
                ]
            },
            ensure_ascii=False,
        )

        with patch(
            "services.plan_service.chat_completion",
            return_value=invalid_result,
        ):
            with self.assertRaisesRegex(ValueError, "不属于已审核考纲"):
                generate_review_plan(
                    exam_id=self.exam_id,
                    daily_available_minutes=60,
                    db_path=self.db_path,
                )

        self.assertIsNone(
            get_current_review_plan(
                exam_id=self.exam_id,
                db_path=self.db_path,
            )
        )


if __name__ == "__main__":
    unittest.main()
