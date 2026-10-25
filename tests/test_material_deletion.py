
import tempfile
import unittest
from pathlib import Path

from services.material_service import (
    delete_material,
    get_material,
    import_material,
)
from storage.db import get_connection, init_db


class TestMaterialDeletion(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.db_path = self.root / "test.db"
        self.materials_dir = self.root / "materials"
        self.source_dir = self.root / "source"

        self.source_dir.mkdir()
        init_db(self.db_path)

        connection = get_connection(self.db_path)
        try:
            cursor = connection.execute(
                "INSERT INTO courses (name) VALUES (?)",
                ("数据结构",),
            )
            self.course_id = cursor.lastrowid
            connection.commit()
        finally:
            connection.close()

        self.source = self.source_dir / "lecture.txt"
        self.source.write_text(
            "线性表与栈",
            encoding="utf-8",
        )

        self.imported = import_material(
            self.source,
            course_id=self.course_id,
            db_path=self.db_path,
            materials_dir=self.materials_dir,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_delete_material_success(self):
        stored_file = Path(self.imported["stored_path"])

        result = delete_material(
            self.imported["id"],
            db_path=self.db_path,
            materials_dir=self.materials_dir,
        )

        self.assertTrue(result)
        self.assertFalse(stored_file.exists())
        self.assertTrue(self.source.exists())
        self.assertIsNone(
            get_material(
                self.imported["id"],
                db_path=self.db_path,
            )
        )

    def test_delete_missing_material(self):
        result = delete_material(
            999999,
            db_path=self.db_path,
            materials_dir=self.materials_dir,
        )

        self.assertFalse(result)
        self.assertTrue(
            Path(self.imported["stored_path"]).exists()
        )

    def test_reject_path_outside_materials_directory(self):
        outside_file = self.root / "important.txt"
        outside_file.write_text("不能删除我", encoding="utf-8")

        connection = get_connection(self.db_path)
        try:
            connection.execute(
                "UPDATE materials SET stored_path = ? WHERE id = ?",
                (str(outside_file), self.imported["id"]),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaises(ValueError):
            delete_material(
                self.imported["id"],
                db_path=self.db_path,
                materials_dir=self.materials_dir,
            )

        self.assertTrue(outside_file.exists())
        self.assertIsNotNone(
            get_material(
                self.imported["id"],
                db_path=self.db_path,
            )
        )

    def test_delete_record_when_stored_file_is_missing(self):
        stored_file = Path(self.imported["stored_path"])
        stored_file.unlink()

        result = delete_material(
            self.imported["id"],
            db_path=self.db_path,
            materials_dir=self.materials_dir,
        )

        self.assertTrue(result)
        self.assertIsNone(
            get_material(
                self.imported["id"],
                db_path=self.db_path,
            )
        )
        self.assertTrue(self.source.exists())


if __name__ == "__main__":
    unittest.main()
