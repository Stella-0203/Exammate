
import tempfile
import unittest
from pathlib import Path

from storage.db import init_db, get_connection
from services.plan_persistence_service import (
    save_review_plan,
    get_current_review_plan,
    update_review_task_status,
)

from services.plan_persistence_service import (
    mark_review_plan_stale,
    mark_review_plan_stale_in_transaction,
)


class TestPlanPersistenceService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(
            Path(self.temp_dir.name) / "test_exam_mate.db"
        )

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

            cursor = connection.execute(
                """
                INSERT INTO exam_goals (
                    course_id,
                    name,
                    exam_date,
                    raw_syllabus_text,
                    status
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.course_id,
                    "数据结构期末考试",
                    "2099-12-20",
                    "线性表、栈和队列、树、图",
                    "confirmed",
                ),
            )
            self.exam_id = cursor.lastrowid

            connection.commit()
        finally:
            connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_plan(self, topic_prefix="线性表"):
        return {
            "review_goal": "期末复习",
            "exam_date": "2099-12-20",
            "daily_available_minutes": 120,
            "tasks": [
                {
                    "day": 1,
                    "topic": f"{topic_prefix}基础知识",
                    "task_type": "learn",
                    "priority": "high",
                    "estimated_minutes": 30,
                    "description": "复习基本概念和定义",
                },
                {
                    "day": 1,
                    "topic": f"{topic_prefix}练习",
                    "task_type": "practice",
                    "priority": "medium",
                    "estimated_minutes": 40,
                    "description": "完成基础练习题",
                },
                {
                    "day": 2,
                    "topic": f"{topic_prefix}巩固",
                    "task_type": "review",
                    "priority": "low",
                    "estimated_minutes": 20,
                    "description": "回顾前一天的学习内容",
                },
            ],
        }

    def read_plan_statuses(self):
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                """
                SELECT id, status
                FROM review_plans
                WHERE exam_id = ?
                ORDER BY id
                """,
                (self.exam_id,),
            ).fetchall()

            return [dict(row) for row in rows]
        finally:
            connection.close()

    def test_no_current_plan_returns_none(self):
        result = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertIsNone(result)

    def test_save_and_read_plan(self):
        plan_id = save_review_plan(
            self.exam_id,
            self.make_plan(),
            db_path=self.db_path,
        )

        result = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], plan_id)
        self.assertEqual(result["exam_id"], self.exam_id)
        self.assertEqual(result["review_goal"], "期末复习")
        self.assertEqual(result["exam_date"], "2099-12-20")
        self.assertEqual(
            result["daily_available_minutes"],
            120,
        )
        self.assertEqual(result["status"], "active")
        self.assertEqual(len(result["tasks"]), 3)

        # 任务按日期和顺序读取。
        self.assertEqual(
            [task["day_number"] for task in result["tasks"]],
            [1, 1, 2],
        )
        self.assertEqual(
            result["tasks"][0]["topic"],
            "线性表基础知识",
        )
        self.assertEqual(
            result["tasks"][0]["status"],
            "pending",
        )

    def test_new_plan_archives_previous_plan(self):
        old_plan_id = save_review_plan(
            self.exam_id,
            self.make_plan("旧计划"),
            db_path=self.db_path,
        )

        new_plan_id = save_review_plan(
            self.exam_id,
            self.make_plan("新计划"),
            db_path=self.db_path,
        )

        self.assertNotEqual(old_plan_id, new_plan_id)

        statuses = self.read_plan_statuses()

        self.assertEqual(
            statuses,
            [
                {"id": old_plan_id, "status": "archived"},
                {"id": new_plan_id, "status": "active"},
            ],
        )

        current_plan = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertEqual(current_plan["id"], new_plan_id)
        self.assertEqual(
            current_plan["tasks"][0]["topic"],
            "新计划基础知识",
        )

    def test_failed_save_rolls_back_new_plan_and_tasks(self):
        invalid_plan = self.make_plan()
        invalid_plan["tasks"][1]["day"] = 0

        with self.assertRaises(ValueError):
            save_review_plan(
                self.exam_id,
                invalid_plan,
                db_path=self.db_path,
            )

        connection = get_connection(self.db_path)
        try:
            plan_count = connection.execute(
                "SELECT COUNT(*) FROM review_plans"
            ).fetchone()[0]

            task_count = connection.execute(
                "SELECT COUNT(*) FROM review_tasks"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(plan_count, 0)
        self.assertEqual(task_count, 0)

    def test_failed_replacement_keeps_old_plan_active(self):
        old_plan_id = save_review_plan(
            self.exam_id,
            self.make_plan("原计划"),
            db_path=self.db_path,
        )

        invalid_plan = self.make_plan("新计划")
        invalid_plan["tasks"][1]["task_type"] = "invalid_type"

        with self.assertRaises(ValueError):
            save_review_plan(
                self.exam_id,
                invalid_plan,
                db_path=self.db_path,
            )

        current_plan = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertEqual(current_plan["id"], old_plan_id)
        self.assertEqual(current_plan["status"], "active")
        self.assertEqual(
            len(self.read_plan_statuses()),
            1,
        )

    def test_update_task_status(self):
        plan_id = save_review_plan(
            self.exam_id,
            self.make_plan(),
            db_path=self.db_path,
        )

        plan = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )
        task_id = plan["tasks"][0]["id"]

        updated = update_review_task_status(
            task_id,
            "completed",
            plan_id=plan_id,
            db_path=self.db_path,
        )

        self.assertTrue(updated)

        updated_plan = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertEqual(
            updated_plan["tasks"][0]["status"],
            "completed",
        )

        # 允许将已完成任务重新设为待完成。
        reverted = update_review_task_status(
            task_id,
            "pending",
            plan_id=plan_id,
            db_path=self.db_path,
        )

        self.assertTrue(reverted)

        reverted_plan = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertEqual(
            reverted_plan["tasks"][0]["status"],
            "pending",
        )

    def test_task_cannot_be_updated_through_wrong_plan_id(self):
        first_plan_id = save_review_plan(
            self.exam_id,
            self.make_plan("第一份计划"),
            db_path=self.db_path,
        )

        first_plan = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )
        task_id = first_plan["tasks"][0]["id"]

        second_plan_id = save_review_plan(
            self.exam_id,
            self.make_plan("第二份计划"),
            db_path=self.db_path,
        )

        self.assertNotEqual(first_plan_id, second_plan_id)

        updated = update_review_task_status(
            task_id,
            "completed",
            plan_id=second_plan_id,
            db_path=self.db_path,
        )

        self.assertFalse(updated)

        connection = get_connection(self.db_path)
        try:
            row = connection.execute(
                """
                SELECT status
                FROM review_tasks
                WHERE id = ?
                  AND plan_id = ?
                """,
                (task_id, first_plan_id),
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(row["status"], "pending")

    def test_invalid_task_status_raises_error(self):
        plan_id = save_review_plan(
            self.exam_id,
            self.make_plan(),
            db_path=self.db_path,
        )

        plan = get_current_review_plan(
            self.exam_id,
            db_path=self.db_path,
        )
        task_id = plan["tasks"][0]["id"]

        with self.assertRaises(ValueError):
            update_review_task_status(
                task_id,
                "in_progress",
                plan_id=plan_id,
                db_path=self.db_path,
            )



    def test_mark_active_plan_stale(self):
        """失效操作应使当前计划不再被当作有效计划读取。"""
        plan_id = save_review_plan(
            self.exam_id,
            {
                "review_goal": "期末复习",
                "exam_date": "2026-12-20",
                "daily_available_minutes": 60,
                "tasks": [
                    {
                        "day": 1,
                        "topic": "线性表",
                        "task_type": "learn",
                        "priority": "high",
                        "estimated_minutes": 30,
                        "description": "复习线性表",
                    }
                ],
            },
            db_path=self.db_path,
        )

        updated_count = mark_review_plan_stale(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertEqual(updated_count, 1)
        self.assertIsNone(
            get_current_review_plan(self.exam_id, db_path=self.db_path)
        )

        connection = get_connection(self.db_path)
        try:
            plan = connection.execute(
                "SELECT status FROM review_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
            self.assertEqual(plan["status"], "stale")
        finally:
            connection.close()


    def test_mark_stale_does_not_affect_other_exam(self):
        """失效指定考试的计划，不应影响其他考试。"""
        plan_a = save_review_plan(
            self.exam_id,
            {
                "review_goal": "考试 A",
                "exam_date": "2026-12-20",
                "daily_available_minutes": 60,
                "tasks": [
                    {
                        "day": 1,
                        "topic": "线性表",
                        "task_type": "learn",
                        "priority": "high",
                        "estimated_minutes": 30,
                        "description": "复习线性表",
                    }
                ],
            },
            db_path=self.db_path,
        )

        connection = get_connection(self.db_path)
        try:
            cursor = connection.execute(
                """
                INSERT INTO exam_goals (
                    course_id, name, exam_date, status
                )
                SELECT course_id, ?, ?, 'confirmed'
                FROM exam_goals
                WHERE id = ?
                """,
                ("另一场考试", "2026-12-25", self.exam_id),
            )
            other_exam_id = cursor.lastrowid
            connection.commit()
        finally:
            connection.close()

        plan_b = save_review_plan(
            other_exam_id,
            {
                "review_goal": "考试 B",
                "exam_date": "2026-12-25",
                "daily_available_minutes": 60,
                "tasks": [
                    {
                        "day": 1,
                        "topic": "线性表",
                        "task_type": "learn",
                        "priority": "high",
                        "estimated_minutes": 30,
                        "description": "复习线性表",
                    }
                ],
            },
            db_path=self.db_path,
        )

        mark_review_plan_stale(self.exam_id, db_path=self.db_path)

        connection = get_connection(self.db_path)
        try:
            statuses = connection.execute(
                """
                SELECT id, status FROM review_plans
                WHERE id IN (?, ?)
                """,
                (plan_a, plan_b),
            ).fetchall()

            status_by_id = {row["id"]: row["status"] for row in statuses}
            self.assertEqual(status_by_id[plan_a], "stale")
            self.assertEqual(status_by_id[plan_b], "active")
        finally:
            connection.close()


    def test_mark_stale_does_not_change_archived_plan(self):
        """归档历史计划不能被失效操作重新标记。"""
        plan_id = save_review_plan(
            self.exam_id,
            {
                "review_goal": "历史计划",
                "exam_date": "2026-12-20",
                "daily_available_minutes": 60,
                "tasks": [
                    {
                        "day": 1,
                        "topic": "线性表",
                        "task_type": "learn",
                        "priority": "high",
                        "estimated_minutes": 30,
                        "description": "复习线性表",
                    }
                ],
            },
            db_path=self.db_path,
        )

        connection = get_connection(self.db_path)
        try:
            connection.execute(
                "UPDATE review_plans SET status = 'archived' WHERE id = ?",
                (plan_id,),
            )
            connection.commit()
        finally:
            connection.close()

        updated_count = mark_review_plan_stale(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertEqual(updated_count, 0)

        connection = get_connection(self.db_path)
        try:
            status = connection.execute(
                "SELECT status FROM review_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()["status"]
            self.assertEqual(status, "archived")
        finally:
            connection.close()


    def test_invalid_exam_id_rejected(self):
        """无效考试 ID 应在访问数据库前被拒绝。"""
        for invalid_id in (0, -1, True, "1", None):
            with self.subTest(exam_id=invalid_id):
                with self.assertRaises(ValueError):
                    mark_review_plan_stale(
                        invalid_id,
                        db_path=self.db_path,
                    )


    def test_stale_update_can_participate_in_outer_transaction(self):
        """事务内失效函数不自行提交，外层回滚后状态应恢复。"""
        plan_id = save_review_plan(
            self.exam_id,
            {
                "review_goal": "事务测试",
                "exam_date": "2026-12-20",
                "daily_available_minutes": 60,
                "tasks": [
                    {
                        "day": 1,
                        "topic": "线性表",
                        "task_type": "learn",
                        "priority": "high",
                        "estimated_minutes": 30,
                        "description": "复习线性表",
                    }
                ],
            },
            db_path=self.db_path,
        )

        connection = get_connection(self.db_path)
        try:
            connection.execute("BEGIN")
            updated_count = mark_review_plan_stale_in_transaction(
                connection,
                self.exam_id,
            )
            self.assertEqual(updated_count, 1)

            # 模拟后续考纲更新失败，回滚整个事务。
            connection.rollback()

            status = connection.execute(
                "SELECT status FROM review_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()["status"]

            self.assertEqual(status, "active")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
