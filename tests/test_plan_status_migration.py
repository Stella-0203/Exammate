
import sqlite3
import tempfile
import unittest
from pathlib import Path

from storage.db import get_connection, init_db


class TestPlanStatusMigration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fresh_database_supports_stale(self):
        init_db(self.db_path)

        connection = get_connection(self.db_path)
        try:
            connection.execute(
                """
                INSERT INTO courses (name)
                VALUES ('数据结构')
                """
            )
            course_id = connection.execute(
                "SELECT id FROM courses"
            ).fetchone()["id"]

            cursor = connection.execute(
                """
                INSERT INTO exam_goals (
                    course_id, name, exam_date, status
                )
                VALUES (?, ?, ?, ?)
                """,
                (course_id, "期末考试", "2099-12-31", "confirmed"),
            )
            exam_id = cursor.lastrowid

            cursor = connection.execute(
                """
                INSERT INTO review_plans (
                    exam_id, exam_date,
                    daily_available_minutes, status
                )
                VALUES (?, ?, ?, ?)
                """,
                (exam_id, "2099-12-31", 60, "stale"),
            )
            self.assertIsNotNone(cursor.lastrowid)
            connection.commit()
        finally:
            connection.close()

    def test_old_database_migration_preserves_plan_and_tasks(self):
        # 先创建一个模拟旧版的数据库。
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        try:
            connection.executescript(
                """
                CREATE TABLE app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE exam_goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    exam_date TEXT,
                    raw_syllabus_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (course_id)
                        REFERENCES courses(id) ON DELETE CASCADE
                );

                CREATE TABLE review_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_id INTEGER NOT NULL,
                    review_goal TEXT NOT NULL DEFAULT '',
                    exam_date TEXT NOT NULL,
                    daily_available_minutes INTEGER NOT NULL
                        CHECK (daily_available_minutes > 0),
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'archived')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (exam_id)
                        REFERENCES exam_goals(id) ON DELETE CASCADE
                );

                CREATE TABLE review_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    day_number INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    estimated_minutes INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (plan_id)
                        REFERENCES review_plans(id) ON DELETE CASCADE
                );

                INSERT INTO courses (id, name)
                VALUES (1, '数据结构');

                INSERT INTO exam_goals (
                    id, course_id, name, exam_date, status
                )
                VALUES (
                    1, 1, '期末考试', '2099-12-31', 'confirmed'
                );

                INSERT INTO review_plans (
                    id, exam_id, review_goal, exam_date,
                    daily_available_minutes, status
                )
                VALUES (
                    1, 1, '复习核心知识', '2099-12-31', 60, 'active'
                );

                INSERT INTO review_tasks (
                    id, plan_id, day_number, topic,
                    task_type, priority, estimated_minutes,
                    description
                )
                VALUES (
                    1, 1, 1, '线性表',
                    'learn', 'high', 30, '复习线性表'
                );
                """
            )
        finally:
            connection.close()

        # 正式初始化应当迁移旧表，并补齐其他缺失表和索引。
        init_db(self.db_path)

        connection = get_connection(self.db_path)
        try:
            plan = connection.execute(
                "SELECT * FROM review_plans WHERE id = 1"
            ).fetchone()
            task = connection.execute(
                "SELECT * FROM review_tasks WHERE id = 1"
            ).fetchone()

            self.assertIsNotNone(plan)
            self.assertEqual(plan["status"], "active")
            self.assertEqual(plan["review_goal"], "复习核心知识")
            self.assertIsNotNone(task)
            self.assertEqual(task["topic"], "线性表")

            connection.execute(
                "UPDATE review_plans SET status = 'stale' WHERE id = 1"
            )
            connection.commit()

            violations = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            self.assertEqual(violations, [])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
