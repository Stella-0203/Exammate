
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage.db import init_db, get_connection
from services.material_service import import_material, list_materials

class FailingInsertConnection:
    """模拟数据库写入 materials 表失败的情况。"""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql, parameters=()):
        if "INSERT INTO materials" in sql:
            raise RuntimeError("模拟数据库写入失败")

        return self._connection.execute(sql, parameters)

    def rollback(self):
        return self._connection.rollback()

    def commit(self):
        return self._connection.commit()

    def close(self):
        return self._connection.close()

class TestMaterialImportErrors(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.db_path = self.root / "test.db"
        self.materials_dir = self.root / "materials"
        self.source_dir = self.root / "source"
        self.source_dir.mkdir()

        init_db(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_txt(self, name="notes.txt", content="测试学习资料"):
        path = self.source_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def _import(self, file_path):
        return import_material(
            file_path,
            db_path=self.db_path,
            materials_dir=self.materials_dir,
        )

    def _assert_no_imported_materials(self):
        self.assertEqual(
            list_materials(db_path=self.db_path),
            [],
        )

        # 如果资料目录已创建，也不应残留文件
        if self.materials_dir.exists():
            self.assertEqual(
                list(self.materials_dir.iterdir()),
                [],
            )

    def test_missing_file(self):
        """文件不存在时，不应新增记录或保存文件。"""
        path = self.source_dir / "missing.txt"

        with self.assertRaises(FileNotFoundError):
            self._import(path)

        self._assert_no_imported_materials()

    def test_unsupported_extension(self):
        """不支持的格式应明确报错。"""
        path = self.source_dir / "notes.zip"
        path.write_bytes(b"test")

        with self.assertRaisesRegex(ValueError, "支持的格式"):
            self._import(path)

        self._assert_no_imported_materials()

    def test_empty_content(self):
        """空白资料不能入库。"""
        path = self._create_txt(content=" \n\t ")

        with self.assertRaisesRegex(ValueError, "内容为空"):
            self._import(path)

        self._assert_no_imported_materials()

    def test_invalid_course_id(self):
        """关联的课程不存在时，不能保存材料。"""
        path = self._create_txt()

        with self.assertRaisesRegex(ValueError, "课程不存在"):
            import_material(
                path,
                course_id=999999,
                db_path=self.db_path,
                materials_dir=self.materials_dir,
            )

        self._assert_no_imported_materials()
    """
    def test_database_insert_failure_cleans_up_file(self):
        #数据库 INSERT 失败时，回滚记录并清理已复制的文件。
        path = self._create_txt()

        with patch(
            "services.material_service.get_connection",
        ) as mocked_get_connection:
            # 使用真实的临时数据库连接，让初始化和查询逻辑正常工作。
            mocked_get_connection.side_effect = lambda db_path=None: (
                get_connection(db_path)
            )

            # 让 INSERT 语句失败，其余 SQL 仍交给真实连接处理。
            original_get_connection = get_connection

            def connection_with_failing_insert(db_path=None):
                connection = original_get_connection(db_path)
                original_execute = connection.execute

                def execute(sql, parameters=()):
                    if "INSERT INTO materials" in sql:
                        raise RuntimeError("模拟数据库写入失败")
                    return original_execute(sql, parameters)

                connection.execute = execute
                return connection

            mocked_get_connection.side_effect = connection_with_failing_insert

            with self.assertRaisesRegex(
                RuntimeError,
                "模拟数据库写入失败",
            ):
                self._import(path)

        self._assert_no_imported_materials()
    """

    def test_database_insert_failure_cleans_up_file(self):
        path = self._create_txt()

        def connection_with_failing_insert(db_path=None):
            connection = get_connection(db_path)
            return FailingInsertConnection(connection)

        with patch(
                "services.material_service.get_connection",
                side_effect=connection_with_failing_insert,
        ):
            with self.assertRaisesRegex(
                    RuntimeError,
                    "模拟数据库写入失败",
            ):
                self._import(path)

        # 写入失败后，数据库中没有资料记录，存储目录也没有残留文件。
        self._assert_no_imported_materials()


if __name__ == "__main__":
    unittest.main()
