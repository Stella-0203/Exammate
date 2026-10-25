
import os
import tempfile
import unittest

from storage.db import get_connection, init_db
from services.plan_persistence_service import (
    save_review_plan,
    get_current_review_plan,
    update_review_task_status,
)


class TestReviewPlanIntegration(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(
            self.temp_dir.name,
            "test_exammate.db",
        )
        init_db(db_path=self.db_path)

        # 创建一门课程和一场已确认考纲的考试。
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
                        (course_id, name, exam_date,
                         raw_syllabus_text, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        self.course_id,
                        "期末考试",
                        "2099-12-31",
                        "1. 线性表",
                        "confirmed",
                    ),
                )
                self.exam_id = cursor.lastrowid
        finally:
            connection.close()

        self.plan = {
            "review_goal": "期末复习",
            "exam_date": "2099-12-31",
            "daily_available_minutes": 120,
            "tasks": [
                {
                    "day": 1,
                    "topic": "线性表基础",
                    "task_type": "learn",
                    "priority": "high",
                    "estimated_minutes": 30,
                    "description": "复习线性表的基本概念",
                },
                {
                    "day": 2,
                    "topic": "线性表练习",
                    "task_type": "practice",
                    "priority": "medium",
                    "estimated_minutes": 40,
                    "description": "完成线性表相关练习",
                },
            ],
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_read_plan(self):
        # 1. 保存计划。
        plan_id = save_review_plan(
            self.exam_id,
            self.plan,
            db_path=self.db_path,
        )
        self.assertGreater(plan_id, 0)

        # 2. 重新读取，确认计划和任务都已保存。
        saved = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertIsNotNone(saved)
        self.assertEqual(saved["id"], plan_id)
        self.assertEqual(saved["status"], "active")
        self.assertEqual(saved["review_goal"], "期末复习")
        self.assertEqual(len(saved["tasks"]), 2)
        self.assertEqual(
            [task["topic"] for task in saved["tasks"]],
            ["线性表基础", "线性表练习"],
        )
        self.assertTrue(
            all(task["status"] == "pending" for task in saved["tasks"])
        )

    def test_update_task_status_persists(self):
        # 保存计划后，把第一项任务标记为完成。
        plan_id = save_review_plan(
            self.exam_id,
            self.plan,
            db_path=self.db_path,
        )
        saved = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )
        task_id = saved["tasks"][0]["id"]

        updated = update_review_task_status(
            task_id,
            "completed",
            plan_id=plan_id,
            db_path=self.db_path,
        )
        self.assertTrue(updated)

        # 再次读取，确认完成状态真正写入数据库。
        saved_again = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )
        tasks_by_id = {
            task["id"]: task for task in saved_again["tasks"]
        }
        self.assertEqual(tasks_by_id[task_id]["status"], "completed")
        self.assertEqual(
            tasks_by_id[saved["tasks"][1]["id"]]["status"],
            "pending",
        )

    def test_invalid_update_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "status 只能是"):
            update_review_task_status(
                1,
                "finished",
                db_path=self.db_path,
            )

        # 不存在的任务不能被误报为更新成功。
        updated = update_review_task_status(
            999999,
            "completed",
            db_path=self.db_path,
        )
        self.assertFalse(updated)

    def test_failed_new_plan_preserves_old_active_plan(self):
        # 先保存一份有效计划。
        old_plan_id = save_review_plan(
            self.exam_id,
            self.plan,
            db_path=self.db_path,
        )

        # 新计划的任务类型无效，保存过程应该失败。
        invalid_plan = {
            **self.plan,
            "review_goal": "新的复习计划",
            "tasks": [
                {
                    **self.plan["tasks"][0],
                    "task_type": "invalid_type",
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "task_type 无效"):
            save_review_plan(
                self.exam_id,
                invalid_plan,
                db_path=self.db_path,
            )

        # 旧计划仍然有效，新计划不应留下残余记录。
        current = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )
        self.assertEqual(current["id"], old_plan_id)

        connection = get_connection(self.db_path)
        try:
            plan_count = connection.execute(
                "SELECT COUNT(*) FROM review_plans WHERE exam_id = ?",
                (self.exam_id,),
            ).fetchone()[0]
            task_count = connection.execute(
                "SELECT COUNT(*) FROM review_tasks WHERE plan_id = ?",
                (old_plan_id,),
            ).fetchone()[0]

            self.assertEqual(plan_count, 1)
            self.assertEqual(task_count, 2)
        finally:
            connection.close()

    def test_no_plan_returns_none(self):
        current = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )
        self.assertIsNone(current)


if __name__ == "__main__":
    unittest.main(verbosity=2)
