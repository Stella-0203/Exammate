import tempfile
import unittest
from pathlib import Path

from services.material_service import import_material
from storage.db import get_connection, init_db


class TestMaterialService(unittest.TestCase):

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
                """
                INSERT INTO exam_goals (
                    course_id, name, raw_syllabus_text
                )
                VALUES (?, ?, ?)
                """,
                (self.course_id, "期末考试", "线性表与树"),
            )
            self.exam_id = cursor.lastrowid

            cursor = connection.execute(
                "INSERT INTO courses (name) VALUES (?)",
                ("操作系统",),
            )
            self.other_course_id = cursor.lastrowid

            connection.commit()
        finally:
            connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_txt(self, name="lecture.txt", content="线性表\n栈和队列"):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_import_material_success(self):
        source = self.create_txt()

        result = import_material(
            source,
            course_id=self.course_id,
            exam_id=self.exam_id,
            db_path=self.db_path,
            materials_dir=self.materials_dir,
        )

        self.assertEqual(result["original_name"], "lecture.txt")
        self.assertEqual(result["extracted_text"], "线性表\n栈和队列")
        self.assertEqual(result["parse_status"], "success")
        self.assertTrue(Path(result["stored_path"]).is_file())

        # 导入不应移动或删除用户原文件。
        self.assertTrue(source.is_file())

        connection = get_connection(self.db_path)
        try:
            row = connection.execute(
                "SELECT * FROM materials WHERE id = ?",
                (result["id"],),
            ).fetchone()

            self.assertIsNotNone(row)
            self.assertEqual(row["course_id"], self.course_id)
            self.assertEqual(row["exam_id"], self.exam_id)
            self.assertEqual(row["extracted_text"], "线性表\n栈和队列")
        finally:
            connection.close()

    def test_exam_only_infers_course(self):
        source = self.create_txt()

        result = import_material(
            source,
            exam_id=self.exam_id,
            db_path=self.db_path,
            materials_dir=self.materials_dir,
        )

        self.assertEqual(result["course_id"], self.course_id)

    def test_reject_mismatched_course_and_exam(self):
        source = self.create_txt()

        with self.assertRaises(ValueError):
            import_material(
                source,
                course_id=self.other_course_id,
                exam_id=self.exam_id,
                db_path=self.db_path,
                materials_dir=self.materials_dir,
            )

        # 关联校验失败时，不应复制文件。
        if self.materials_dir.exists():
            self.assertEqual(list(self.materials_dir.iterdir()), [])

    def test_reject_empty_material(self):
        source = self.create_txt(content="   \n  ")

        with self.assertRaises(ValueError):
            import_material(
                source,
                db_path=self.db_path,
                materials_dir=self.materials_dir,
            )

        self.assertFalse(self.materials_dir.exists())

    def test_database_failure_cleans_up_copied_file(self):
        source = self.create_txt()

        # 模拟数据库写入失败。
        connection = get_connection(self.db_path)
        try:
            connection.execute("DROP TABLE materials")
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(Exception):
            import_material(
                source,
                db_path=self.db_path,
                materials_dir=self.materials_dir,
            )

        # 数据库写入失败后，复制的文件也应被清理。
        if self.materials_dir.exists():
            self.assertEqual(list(self.materials_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()