
import json
import sqlite3
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from services.plan_service import (
    load_plan_context,
    validate_review_plan,
    generate_review_plan,
)


class TestPlanService(unittest.TestCase):
    """复习计划生成模块测试：不调用真实模型 API。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_exam_mate.db")

        # 先创建一套最小数据库。
        # 如果项目已有统一的数据库初始化函数，后续应改为复用它。
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row

        connection.executescript(
            """
            CREATE TABLE courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );

            CREATE TABLE exam_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                exam_date TEXT,
                raw_syllabus_text TEXT,
                status TEXT NOT NULL
            );

            CREATE TABLE syllabus_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id INTEGER NOT NULL,
                parent_id INTEGER,
                content TEXT NOT NULL,
                item_type TEXT,
                origin TEXT,
                review_status TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0
            );
            """
        )

        connection.execute(
            "INSERT INTO courses (name) VALUES (?)",
            ("数据结构",),
        )
        self.course_id = connection.execute(
            "SELECT id FROM courses"
        ).fetchone()["id"]

        self.exam_date = date.today() + timedelta(days=7)

        connection.execute(
            """
            INSERT INTO exam_goals
                (course_id, name, exam_date, raw_syllabus_text, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.course_id,
                "数据结构期末考试",
                self.exam_date.isoformat(),
                "线性表\n树与二叉树",
                "confirmed",
            ),
        )
        self.exam_id = connection.execute(
            "SELECT id FROM exam_goals"
        ).fetchone()["id"]

        connection.executemany(
            """
            INSERT INTO syllabus_items
                (exam_id, parent_id, content, item_type,
                 origin, review_status, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    self.exam_id, None, "线性表", "knowledge",
                    "original", "confirmed", 1,
                ),
                (
                    self.exam_id, None, "树与二叉树", "knowledge",
                    "original", "confirmed", 2,
                ),
            ],
        )

        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def valid_context(self):
        """构造校验计划所需的上下文。"""
        return {
            "exam": {
                "id": self.exam_id,
                "course_id": self.course_id,
                "course_name": "数据结构",
                "exam_name": "数据结构期末考试",
                "exam_date": self.exam_date.isoformat(),
                "status": "confirmed",
            },
            "exam_date": self.exam_date.isoformat(),
            "start_date": date.today().isoformat(),
            "total_days": (self.exam_date - date.today()).days + 1,
            "syllabus_items": [
                {
                    "id": 1,
                    "content": "线性表",
                    "item_type": "knowledge",
                    "parent_id": None,
                    "sort_order": 1,
                },
                {
                    "id": 2,
                    "content": "树与二叉树",
                    "item_type": "knowledge",
                    "parent_id": None,
                    "sort_order": 2,
                },
            ],
        }

    def valid_model_result(self):
        return {
            "tasks": [
                {
                    "day": 2,
                    "topic": "树与二叉树",
                    "task_type": "learn",
                    "priority": "high",
                    "estimated_minutes": 40,
                    "description": "复习二叉树的基本概念。",
                },
                {
                    "day": 1,
                    "topic": "线性表",
                    "task_type": "review",
                    "priority": "medium",
                    "estimated_minutes": 30,
                    "description": "回顾顺序表与链表。",
                },
            ]
        }

    # 1. 数据库上下文读取

    def test_load_plan_context_success(self):
        context = load_plan_context(self.exam_id, db_path=self.db_path)

        self.assertEqual(context["exam"]["course_name"], "数据结构")
        self.assertEqual(context["exam"]["exam_name"], "数据结构期末考试")
        self.assertGreaterEqual(context["total_days"], 1)
        self.assertEqual(len(context["syllabus_items"]), 2)


    def add_syllabus_item(
        self,
        content,
        parent_id=None,
        review_status="confirmed",
        sort_order=3,
    ):
        """向测试数据库添加考纲条目，返回新条目的 ID。"""
        connection = sqlite3.connect(self.db_path)
        cursor = connection.execute(
            """
            INSERT INTO syllabus_items
                (exam_id, parent_id, content, item_type,
                 origin, review_status, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.exam_id,
                parent_id,
                content,
                "knowledge",
                "inferred",
                review_status,
                sort_order,
            ),
        )
        item_id = cursor.lastrowid
        connection.commit()
        connection.close()
        return item_id

    def test_load_plan_context_excludes_parent_with_confirmed_children(self):
        """父级存在已审核子项时，只保留具体子项。"""
        connection = sqlite3.connect(self.db_path)
        parent = connection.execute(
            "SELECT id FROM syllabus_items WHERE content = ?",
            ("树与二叉树",),
        ).fetchone()[0]
        connection.close()

        self.add_syllabus_item(
            "二叉树的遍历",
            parent_id=parent,
            sort_order=1,
        )
        self.add_syllabus_item(
            "二叉搜索树",
            parent_id=parent,
            sort_order=2,
        )

        context = load_plan_context(
            self.exam_id,
            db_path=self.db_path,
        )
        topics = [item["content"] for item in context["syllabus_items"]]

        self.assertIn("线性表", topics)
        self.assertNotIn("树与二叉树", topics)
        self.assertIn("二叉树的遍历", topics)
        self.assertIn("二叉搜索树", topics)

    def test_load_plan_context_keeps_parent_without_children(self):
        """没有子项的父级条目仍然可以作为复习主题。"""
        context = load_plan_context(
            self.exam_id,
            db_path=self.db_path,
        )
        topics = [item["content"] for item in context["syllabus_items"]]

        self.assertIn("树与二叉树", topics)
        self.assertIn("线性表", topics)


    def test_load_plan_context_keeps_parent_when_children_excluded(self):
        """只有已排除子项时，父级仍然保留。"""
        connection = sqlite3.connect(self.db_path)
        parent = connection.execute(
            "SELECT id FROM syllabus_items WHERE content = ?",
            ("树与二叉树",),
        ).fetchone()[0]
        connection.close()

        self.add_syllabus_item(
            "二叉树的遍历",
            parent_id=parent,
            review_status="excluded",
        )

        context = load_plan_context(
            self.exam_id,
            db_path=self.db_path,
        )
        topics = [item["content"] for item in context["syllabus_items"]]

        self.assertIn("树与二叉树", topics)
        self.assertNotIn("二叉树的遍历", topics)


    def test_load_plan_context_unknown_exam(self):
        with self.assertRaises(ValueError):
            load_plan_context(999999, db_path=self.db_path)

    def test_load_plan_context_exam_not_confirmed(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "UPDATE exam_goals SET status = ? WHERE id = ?",
            ("needs_review", self.exam_id),
        )
        connection.commit()
        connection.close()

        with self.assertRaises(ValueError):
            load_plan_context(self.exam_id, db_path=self.db_path)

    def test_load_plan_context_missing_exam_date(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "UPDATE exam_goals SET exam_date = NULL WHERE id = ?",
            (self.exam_id,),
        )
        connection.commit()
        connection.close()

        with self.assertRaises(ValueError):
            load_plan_context(self.exam_id, db_path=self.db_path)

    # 2. 模型结果结构与业务规则校验

    def test_validate_valid_plan(self):
        result = validate_review_plan(
            self.valid_model_result(),
            self.valid_context(),
            daily_available_minutes=120,
        )

        self.assertEqual(len(result["tasks"]), 2)
        self.assertEqual(result["tasks"][0]["day"], 1)
        self.assertEqual(result["tasks"][1]["day"], 2)
        self.assertEqual(result["tasks"][0]["date"], date.today().isoformat())

    def test_validate_unknown_topic(self):
        result = self.valid_model_result()
        result["tasks"][0]["topic"] = "项目中不存在的知识点"

        with self.assertRaises(ValueError):
            validate_review_plan(
                result, self.valid_context(), 120
            )

    def test_validate_invalid_task_type(self):
        result = self.valid_model_result()
        result["tasks"][0]["task_type"] = "play"

        with self.assertRaises(ValueError):
            validate_review_plan(
                result, self.valid_context(), 120
            )

    def test_validate_daily_time_over_budget(self):
        result = {
            "tasks": [
                {
                    "day": 1,
                    "topic": "线性表",
                    "task_type": "learn",
                    "priority": "high",
                    "estimated_minutes": 80,
                    "description": "学习线性表。",
                },
                {
                    "day": 1,
                    "topic": "树与二叉树",
                    "task_type": "learn",
                    "priority": "high",
                    "estimated_minutes": 50,
                    "description": "学习二叉树。",
                },
            ]
        }

        with self.assertRaises(ValueError):
            validate_review_plan(
                result, self.valid_context(), 120
            )

    def test_validate_invalid_day(self):
        result = self.valid_model_result()
        result["tasks"][0]["day"] = 999

        with self.assertRaises(ValueError):
            validate_review_plan(
                result, self.valid_context(), 120
            )

    # 3. 完整生成流程：模拟模型，不发送 API 请求

    @patch("services.plan_service.chat_completion")
    def test_generate_review_plan_success(self, mock_chat):
        mock_chat.return_value = json.dumps(
            self.valid_model_result(),
            ensure_ascii=False,
        )

        result = generate_review_plan(
            exam_id=self.exam_id,
            daily_available_minutes=120,
            review_goal="优先掌握核心知识点",
            db_path=self.db_path,
        )

        self.assertEqual(result["course_name"], "数据结构")
        self.assertEqual(len(result["tasks"]), 2)
        mock_chat.assert_called_once()

    @patch("services.plan_service.chat_completion")
    def test_generate_review_plan_invalid_json(self, mock_chat):
        mock_chat.return_value = "{not valid json"

        with self.assertRaises(ValueError):
            generate_review_plan(
                exam_id=self.exam_id,
                daily_available_minutes=120,
                db_path=self.db_path,
            )

        mock_chat.assert_called_once()



    def test_load_plan_context_rejects_pending_child(self):
        """父级下存在待审核子项时，不生成不完整的计划上下文。"""
        connection = sqlite3.connect(self.db_path)
        parent = connection.execute(
            "SELECT id FROM syllabus_items WHERE content = ?",
            ("树与二叉树",),
        ).fetchone()[0]
        connection.close()

        self.add_syllabus_item(
            "二叉树的遍历",
            parent_id=parent,
            review_status="confirmed",
        )
        self.add_syllabus_item(
            "二叉搜索树",
            parent_id=parent,
            review_status="pending",
        )

        with self.assertRaisesRegex(ValueError, "二叉搜索树"):
            load_plan_context(
                self.exam_id,
                db_path=self.db_path,
            )

    def test_load_plan_context_uses_parent_when_all_children_excluded(self):
        """所有子项都被排除时，保留父级作为复习主题。"""
        connection = sqlite3.connect(self.db_path)
        parent = connection.execute(
            "SELECT id FROM syllabus_items WHERE content = ?",
            ("树与二叉树",),
        ).fetchone()[0]
        connection.close()

        self.add_syllabus_item(
            "二叉树的遍历",
            parent_id=parent,
            review_status="excluded",
        )
        self.add_syllabus_item(
            "二叉搜索树",
            parent_id=parent,
            review_status="excluded",
        )

        context = load_plan_context(
            self.exam_id,
            db_path=self.db_path,
        )
        topics = [item["content"] for item in context["syllabus_items"]]

        self.assertIn("树与二叉树", topics)
        self.assertNotIn("二叉树的遍历", topics)
        self.assertNotIn("二叉搜索树", topics)


if __name__ == "__main__":
    unittest.main(verbosity=2)
