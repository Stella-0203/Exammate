
import unittest

from core.schemas import validate_coverage_results


class TestCoverageSchema(unittest.TestCase):

    def setUp(self):
        self.syllabus_items = [
            {"id": 1, "content": "栈的入栈和出栈"},
            {"id": 2, "content": "队列的基本操作"},
        ]

        self.materials = [
            {
                "id": 10,
                "original_name": "数据结构讲义.txt",
                "extracted_text": (
                    "栈支持入栈和出栈操作。"
                    "队列支持先进先出。"
                ),
            },
            {
                "id": 20,
                "original_name": "课程补充资料.txt",
                "extracted_text": "树的遍历包括先序、中序和后序遍历。",
            },
        ]

        self.valid_result = {
            "items": [
                {
                    "syllabus_item_id": 1,
                    "status": "covered",
                    "reason": "资料明确介绍了栈的入栈和出栈操作。",
                    "evidence": [
                        {
                            "material_id": 10,
                            "quote": "栈支持入栈和出栈操作。",
                        }
                    ],
                    "uncertainty": "",
                },
                {
                    "syllabus_item_id": 2,
                    "status": "partial",
                    "reason": "资料提及队列的先进先出特性，但操作细节不足。",
                    "evidence": [
                        {
                            "material_id": 10,
                            "quote": "队列支持先进先出。",
                        }
                    ],
                    "uncertainty": "",
                },
            ]
        }

    def test_valid_result(self):
        """合法的完整结果可以通过校验。"""
        result = validate_coverage_results(
            self.valid_result,
            self.syllabus_items,
            self.materials,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["status"], "covered")
        self.assertEqual(result[1]["status"], "partial")

    def test_rejects_non_dict_result(self):
        """顶层结果必须是对象。"""
        with self.assertRaisesRegex(ValueError, "JSON 对象"):
            validate_coverage_results(
                [],
                self.syllabus_items,
                self.materials,
            )

    def test_rejects_invalid_status(self):
        """拒绝未定义的覆盖状态。"""
        result = {
            "items": [
                dict(self.valid_result["items"][0], status="excellent"),
                self.valid_result["items"][1],
            ]
        }

        with self.assertRaisesRegex(ValueError, "不支持的覆盖状态"):
            validate_coverage_results(
                result,
                self.syllabus_items,
                self.materials,
            )

    def test_rejects_duplicate_syllabus_item(self):
        """同一考纲条目不能重复出现。"""
        first = self.valid_result["items"][0]
        duplicate = dict(first)

        result = {
            "items": [
                first,
                duplicate,
                self.valid_result["items"][1],
            ]
        }

        with self.assertRaisesRegex(ValueError, "重复分析"):
            validate_coverage_results(
                result,
                self.syllabus_items,
                self.materials,
            )

    def test_rejects_missing_syllabus_item(self):
        """不能遗漏任何需要分析的考纲条目。"""
        result = {
            "items": [self.valid_result["items"][0]]
        }

        with self.assertRaisesRegex(ValueError, "遗漏了考纲条目"):
            validate_coverage_results(
                result,
                self.syllabus_items,
                self.materials,
            )

    def test_rejects_unknown_material_id(self):
        """不能引用未参与分析的资料。"""
        first = dict(self.valid_result["items"][0])
        first["evidence"] = [
            {
                "material_id": 999,
                "quote": "栈支持入栈和出栈操作。",
            }
        ]

        result = {
            "items": [
                first,
                self.valid_result["items"][1],
            ]
        }

        with self.assertRaisesRegex(
            ValueError,
            "未参与本次分析的资料",
        ):
            validate_coverage_results(
                result,
                self.syllabus_items,
                self.materials,
            )

    def test_rejects_fabricated_quote(self):
        """证据摘录必须能在指定资料原文中找到。"""
        first = dict(self.valid_result["items"][0])
        first["evidence"] = [
            {
                "material_id": 10,
                "quote": "栈支持随机访问操作。",
            }
        ]

        result = {
            "items": [
                first,
                self.valid_result["items"][1],
            ]
        }

        with self.assertRaisesRegex(ValueError, "无法在资料"):
            validate_coverage_results(
                result,
                self.syllabus_items,
                self.materials,
            )

    def test_rejects_covered_without_evidence(self):
        """覆盖充分或覆盖不足时必须提供证据。"""
        first = dict(self.valid_result["items"][0])
        first["evidence"] = []

        result = {
            "items": [
                first,
                self.valid_result["items"][1],
            ]
        }

        with self.assertRaisesRegex(ValueError, "没有提供支持证据"):
            validate_coverage_results(
                result,
                self.syllabus_items,
                self.materials,
            )

    def test_needs_review_requires_uncertainty(self):
        """待确认结果必须说明不确定原因。"""
        first = dict(self.valid_result["items"][0])
        first["status"] = "needs_review"
        first["uncertainty"] = ""

        result = {
            "items": [
                first,
                self.valid_result["items"][1],
            ]
        }

        with self.assertRaisesRegex(ValueError, "没有说明不确定原因"):
            validate_coverage_results(
                result,
                self.syllabus_items,
                self.materials,
            )

    def test_rejects_evidence_from_wrong_material(self):
        """摘录不能来自其他资料，却标记成当前资料的证据。"""
        first = dict(self.valid_result["items"][0])
        first["evidence"] = [
            {
                "material_id": 10,
                "quote": "树的遍历包括先序、中序和后序遍历。",
            }
        ]

        result = {
            "items": [
                first,
                self.valid_result["items"][1],
            ]
        }

        with self.assertRaisesRegex(ValueError, "无法在资料"):
            validate_coverage_results(
                result,
                self.syllabus_items,
                self.materials,
            )


if __name__ == "__main__":
    unittest.main()
