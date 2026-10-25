
import tempfile
import unittest
from pathlib import Path

from services.material_service import (
    get_material,
    import_material,
    list_materials,
)
from storage.db import get_connection, init_db


class TestMaterialQueries(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "test.db"
        self.materials_dir = self.root / "materials"

        init_db(self.db_path)

        connection = get_connection(self.db_path)
        try:
            cursor = connection.execute(
                "INSERT INTO courses (name) VALUES (?)",
                ("数据结构",),
            )
            self.course_id = cursor.lastrowid

            cursor = connection.execute(
                "INSERT INTO courses (name) VALUES (?)",
                ("操作系统",),
            )
            self.other_course_id = cursor.lastrowid

            cursor = connection.execute(
                """
                INSERT INTO exam_goals (
                    course_id, name, raw_syllabus_text
                )
                VALUES (?, ?, ?)
                """,
                (self.course_id, "期末考试", "线性表与树"),
            )
            self.exam_id = cursor.lastrowid

            connection.commit()
        finally:
            connection.close()

        self.source = self.root / "lecture.txt"
        self.source.write_text(
            "线性表\n栈和队列",
            encoding="utf-8",
        )

        self.imported = import_material(
            self.source,
            course_id=self.course_id,
            exam_id=self.exam_id,
            db_path=self.db_path,
            materials_dir=self.materials_dir,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_materials(self):
        results = list_materials(db_path=self.db_path)

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["original_name"],
            "lecture.txt",
        )
        self.assertNotIn("extracted_text", results[0])
        self.assertNotIn("stored_path", results[0])

    def test_filter_by_course(self):
        results = list_materials(
            course_id=self.course_id,
            db_path=self.db_path,
        )
        self.assertEqual(len(results), 1)

        results = list_materials(
            course_id=self.other_course_id,
            db_path=self.db_path,
        )
        self.assertEqual(results, [])

    def test_filter_by_exam(self):
        results = list_materials(
            exam_id=self.exam_id,
            db_path=self.db_path,
        )
        self.assertEqual(len(results), 1)

        results = list_materials(
            exam_id=999999,
            db_path=self.db_path,
        )
        self.assertEqual(results, [])

    def test_get_material_detail(self):
        material_id = self.imported["id"]
        result = get_material(
            material_id,
            db_path=self.db_path,
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result["extracted_text"],
            "线性表\n栈和队列",
        )
        self.assertTrue(Path(result["stored_path"]).is_file())

    def test_get_missing_material(self):
        result = get_material(
            999999,
            db_path=self.db_path,
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
