
import tempfile
import unittest
from pathlib import Path

from storage.db import init_db, get_connection


class TestPlanSchema(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(
            Path(self.temp_dir.name) / "test_exam_mate.db"
        )
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_review_tables_created(self):
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        finally:
            connection.close()

        table_names = {row["name"] for row in rows}

        self.assertIn("review_plans", table_names)
        self.assertIn("review_tasks", table_names)

    def test_review_plan_columns(self):
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                "PRAGMA table_info(review_plans)"
            ).fetchall()
        finally:
            connection.close()

        columns = {row["name"] for row in rows}

        expected_columns = {
            "id",
            "exam_id",
            "review_goal",
            "exam_date",
            "daily_available_minutes",
            "status",
            "created_at",
            "updated_at",
        }

        self.assertTrue(expected_columns.issubset(columns))

    def test_review_task_columns(self):
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                "PRAGMA table_info(review_tasks)"
            ).fetchall()
        finally:
            connection.close()

        columns = {row["name"] for row in rows}

        expected_columns = {
            "id",
            "plan_id",
            "day_number",
            "topic",
            "task_type",
            "priority",
            "estimated_minutes",
            "description",
            "status",
            "sort_order",
            "created_at",
            "updated_at",
        }

        self.assertTrue(expected_columns.issubset(columns))


if __name__ == "__main__":
    unittest.main()

