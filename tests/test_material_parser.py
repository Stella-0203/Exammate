import tempfile
import unittest
from pathlib import Path

from parsers.material_parser import extract_txt_text


class TestMaterialParser(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_read_utf8(self):
        path = self.test_dir / "utf8.txt"
        expected = "线性表的基本概念\n掌握栈和队列"

        path.write_text(expected, encoding="utf-8")

        self.assertEqual(extract_txt_text(path), expected)

    def test_read_utf8_with_bom(self):
        path = self.test_dir / "utf8_bom.txt"
        expected = "数据结构与算法"

        path.write_text(expected, encoding="utf-8-sig")

        self.assertEqual(extract_txt_text(path), expected)

    def test_read_gb18030(self):
        path = self.test_dir / "gb18030.txt"
        expected = "计算机组成原理与操作系统"

        path.write_bytes(expected.encode("gb18030"))

        self.assertEqual(extract_txt_text(path), expected)

    def test_read_empty_file(self):
        path = self.test_dir / "empty.txt"
        path.write_text("", encoding="utf-8")

        self.assertEqual(extract_txt_text(path), "")

    def test_missing_file(self):
        path = self.test_dir / "missing.txt"

        with self.assertRaises(FileNotFoundError):
            extract_txt_text(path)

    def test_unsupported_extension(self):
        path = self.test_dir / "notes.pdf"
        path.write_text("暂不解析 PDF", encoding="utf-8")

        with self.assertRaises(ValueError):
            extract_txt_text(path)


if __name__ == "__main__":
    unittest.main()