import tempfile
import unittest
from pathlib import Path

from storage.db import get_connection, init_db
from services.coverage_service import load_coverage_context


class TestCoverageService(unittest.TestCase):

    def setUp(self):
        # 每个测试使用独立的临时数据库
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(
            Path(self.temp_dir.name) / "test_exammate.db"
        )

        init_db(self.db_path)
        self.conn = get_connection(self.db_path)

        # 创建两门课程
        self.course_id = self.conn.execute(
            "INSERT INTO courses (name) VALUES (?)",
            ("数据结构",),
        ).lastrowid

        self.other_course_id = self.conn.execute(
            "INSERT INTO courses (name) VALUES (?)",
            ("计算机网络",),
        ).lastrowid

        # 创建当前考试目标
        self.exam_id = self.conn.execute(
            """
            INSERT INTO exam_goals
                (course_id, name, status)
            VALUES (?, ?, ?)
            """,
            (self.course_id, "数据结构期末考试", "confirmed"),
        ).lastrowid

        # 创建同一课程的另一个考试目标
        self.other_exam_id = self.conn.execute(
            """
            INSERT INTO exam_goals
                (course_id, name, status)
            VALUES (?, ?, ?)
            """,
            (self.course_id, "数据结构期中考试", "confirmed"),
        ).lastrowid

        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def add_syllabus_item(
        self,
        content,
        review_status="confirmed",
        parent_id=None,
    ):
        cursor = self.conn.execute(
            """
            INSERT INTO syllabus_items
                (exam_id, parent_id, content, item_type,
                 origin, review_status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self.exam_id,
                parent_id,
                content,
                "knowledge",
                "original",
                review_status,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def add_material(
        self,
        original_name,
        course_id,
        exam_id=None,
        parse_status="success",
        extracted_text="测试资料内容",
    ):
        cursor = self.conn.execute(
            """
            INSERT INTO materials
                (course_id, exam_id, original_name,
                 stored_path, file_type, extracted_text,
                 parse_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                course_id,
                exam_id,
                original_name,
                f"/fake/path/{original_name}",
                "txt",
                extracted_text,
                parse_status,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def test_loads_exam_and_eligible_data(self):
        """正常读取考试信息、可分析考纲及相关资料。"""
        item_id = self.add_syllabus_item("栈和队列")

        exam_material_id = self.add_material(
            "期末复习资料.txt",
            self.course_id,
            self.exam_id,
        )
        generic_material_id = self.add_material(
            "课程通用笔记.txt",
            self.course_id,
        )

        result = load_coverage_context(
            self.exam_id,
            db_path=self.db_path,
        )

        self.assertEqual(result["exam"]["id"], self.exam_id)
        self.assertEqual(result["exam"]["course_name"], "数据结构")

        self.assertEqual(
            [item["id"] for item in result["syllabus_items"]],
            [item_id],
        )
        self.assertEqual(
            {material["id"] for material in result["materials"]},
            {exam_material_id, generic_material_id},
        )

    def test_includes_generic_materials_of_same_course(self):
        """纳入当前课程的通用资料。"""
        self.add_syllabus_item("栈和队列")

        material_id = self.add_material(
            "数据结构课堂笔记.txt",
            self.course_id,
            exam_id=None,
        )

        result = load_coverage_context(
            self.exam_id,
            db_path=self.db_path,
        )

        material_ids = {
            material["id"] for material in result["materials"]
        }
        self.assertIn(material_id, material_ids)

    def test_excludes_materials_from_other_exams_or_courses(self):
        """排除其他考试专属资料及其他课程资料。"""
        self.add_syllabus_item("树的遍历")
        current_material_id = self.add_material(
            "当前考试资料.txt",
            self.course_id,
            self.exam_id,
        )
        other_exam_material_id = self.add_material(
            "期中专属资料.txt",
            self.course_id,
            self.other_exam_id,
        )
        other_course_material_id = self.add_material(
            "计算机网络笔记.txt",
            self.other_course_id,
        )

        result = load_coverage_context(
            self.exam_id,
            db_path=self.db_path,
        )

        material_ids = {
            material["id"] for material in result["materials"]
        }

        self.assertIn(current_material_id, material_ids)
        self.assertNotIn(other_exam_material_id, material_ids)
        self.assertNotIn(other_course_material_id, material_ids)

    def test_excludes_unconfirmed_syllabus_items(self):
        """只纳入 confirmed 和 edited 条目。"""
        confirmed_id = self.add_syllabus_item(
            "树的遍历",
            review_status="confirmed",
        )
        edited_id = self.add_syllabus_item(
            "图的遍历",
            review_status="edited",
        )
        pending_id = self.add_syllabus_item(
            "排序算法",
            review_status="pending",
        )
        excluded_id = self.add_syllabus_item(
            "不考内容",
            review_status="excluded",
        )

        result = load_coverage_context(
            self.exam_id,
            db_path=self.db_path,
        )

        item_ids = {
            item["id"] for item in result["syllabus_items"]
        }

        self.assertEqual(item_ids, {confirmed_id, edited_id})
        self.assertNotIn(pending_id, item_ids)
        self.assertNotIn(excluded_id, item_ids)

    def test_excludes_failed_or_empty_materials(self):
        """排除解析失败或正文为空的资料。"""
        self.add_syllabus_item("排序算法")
        valid_id = self.add_material(
            "有效资料.txt",
            self.course_id,
            extracted_text="包含有效内容",
        )
        failed_id = self.add_material(
            "解析失败.txt",
            self.course_id,
            parse_status="failed",
        )
        empty_id = self.add_material(
            "空白资料.txt",
            self.course_id,
            extracted_text="   \n  ",
        )

        result = load_coverage_context(
            self.exam_id,
            db_path=self.db_path,
        )

        material_ids = {
            material["id"] for material in result["materials"]
        }

        self.assertIn(valid_id, material_ids)
        self.assertNotIn(failed_id, material_ids)
        self.assertNotIn(empty_id, material_ids)

    def test_raises_error_when_exam_does_not_exist(self):
        """考试目标不存在时给出明确错误。"""
        with self.assertRaisesRegex(ValueError, "考试目标不存在"):
            load_coverage_context(
                999999,
                db_path=self.db_path,
            )

    def test_raises_error_when_no_eligible_syllabus_items(self):
        """没有已确认或已编辑的考纲条目时给出明确错误。"""
        self.add_syllabus_item(
            "尚待审核的知识点",
            review_status="pending",
        )

        with self.assertRaisesRegex(
            ValueError,
            "没有可用于覆盖分析的考纲条目",
        ):
            load_coverage_context(
                self.exam_id,
                db_path=self.db_path,
            )


if __name__ == "__main__":
    unittest.main()
