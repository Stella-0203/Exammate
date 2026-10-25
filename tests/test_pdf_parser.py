
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from parsers.material_parser import (
    extract_material_text,
    extract_pdf_text,
)


class TestPdfParser(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_pdf_placeholder(self):
        path = self.root / "lecture.pdf"
        path.write_bytes(b"PDF test placeholder")
        return path

    @patch("parsers.material_parser.PdfReader")
    def test_extract_pdf_text(self, mock_reader_class):
        path = self.create_pdf_placeholder()

        first_page = Mock()
        first_page.extract_text.return_value = "第一章 线性表"

        second_page = Mock()
        second_page.extract_text.return_value = "第二章 栈和队列"

        mock_reader = Mock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [first_page, second_page]
        mock_reader_class.return_value = mock_reader

        result = extract_pdf_text(path)

        self.assertEqual(
            result,
            "第一章 线性表\n\n第二章 栈和队列",
        )

    @patch("parsers.material_parser.PdfReader")
    def test_extract_pdf_skips_empty_pages(self, mock_reader_class):
        path = self.create_pdf_placeholder()

        first_page = Mock()
        first_page.extract_text.return_value = None

        second_page = Mock()
        second_page.extract_text.return_value = "有效正文"

        mock_reader = Mock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [first_page, second_page]
        mock_reader_class.return_value = mock_reader

        self.assertEqual(extract_pdf_text(path), "有效正文")

    @patch("parsers.material_parser.PdfReader")
    def test_reject_encrypted_pdf(self, mock_reader_class):
        path = self.create_pdf_placeholder()

        mock_reader = Mock()
        mock_reader.is_encrypted = True
        mock_reader_class.return_value = mock_reader

        with self.assertRaises(ValueError):
            extract_pdf_text(path)

    def test_unified_entry_dispatches_pdf(self):
        path = self.create_pdf_placeholder()

        with patch(
            "parsers.material_parser.extract_pdf_text",
            return_value="PDF 正文",
        ) as mock_extract:
            result = extract_material_text(path)

        self.assertEqual(result, "PDF 正文")
        mock_extract.assert_called_once_with(path)

    def test_unsupported_extension(self):
        path = self.root / "notes.zip"
        path.write_text("测试文件", encoding="utf-8")

        with self.assertRaises(ValueError):
            extract_material_text(path)

    def test_missing_pdf(self):
        path = self.root / "missing.pdf"

        with self.assertRaises(FileNotFoundError):
            extract_material_text(path)


if __name__ == "__main__":
    unittest.main()
