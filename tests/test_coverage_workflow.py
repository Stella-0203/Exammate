import json
import unittest
from unittest.mock import patch

from services.coverage_service import analyze_material_coverage


class TestCoverageWorkflow(unittest.TestCase):

    def setUp(self):
        self.context = {
            "exam": {
                "id": 1,
                "name": "数据结构期末考试",
                "course_id": 1,
                "course_name": "数据结构",
                "exam_date": None,
                "status": "confirmed",
            },
            "syllabus_items": [
                {
                    "id": 101,
                    "exam_id": 1,
                    "parent_id": None,
                    "content": "栈的入栈和出栈操作",
                    "item_type": "knowledge",
                    "origin": "original",
                    "review_status": "confirmed",
                    "rationale": None,
                    "sort_order": 1,
                },
                {
                    "id": 102,
                    "exam_id": 1,
                    "parent_id": None,
                    "content": "队列的基本操作",
                    "item_type": "knowledge",
                    "origin": "original",
                    "review_status": "edited",
                    "rationale": None,
                    "sort_order": 2,
                },
            ],
            "materials": [
                {
                    "id": 10,
                    "course_id": 1,
                    "exam_id": None,
                    "original_name": "数据结构讲义.txt",
                    "stored_path": "/fake/lecture.txt",
                    "file_type": "txt",
                    "extracted_text": (
                        "栈支持入栈和出栈操作。"
                        "队列支持先进先出。"
                    ),
                    "parse_status": "success",
                }
            ],
        }

        self.valid_model_result = {
            "items": [
                {
                    "syllabus_item_id": 101,
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
                    "syllabus_item_id": 102,
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

    @patch("services.coverage_service.chat_completion")
    @patch("services.coverage_service.load_coverage_context")
    def test_successful_analysis(
        self,
        mock_load_context,
        mock_chat_completion,
    ):
        """合法模型结果可以生成报告和统计信息。"""
        mock_load_context.return_value = self.context
        mock_chat_completion.return_value = json.dumps(
            self.valid_model_result,
            ensure_ascii=False,
        )

        report = analyze_material_coverage(exam_id=1)

        self.assertEqual(report["exam"]["id"], 1)
        self.assertEqual(report["summary"]["total_items"], 2)
        self.assertEqual(report["summary"]["material_count"], 1)
        self.assertEqual(
            report["summary"]["status_counts"],
            {
                "covered": 1,
                "partial": 1,
                "uncovered": 0,
                "needs_review": 0,
            },
        )
        self.assertEqual(len(report["items"]), 2)

        mock_load_context.assert_called_once_with(
            exam_id=1,
            db_path=None,
        )
        mock_chat_completion.assert_called_once()

        # 确认使用 JSON 模式请求模型
        call_kwargs = mock_chat_completion.call_args.kwargs
        self.assertEqual(
            call_kwargs["response_format"],
            {"type": "json_object"},
        )

    @patch("services.coverage_service.chat_completion")
    @patch("services.coverage_service.load_coverage_context")
    def test_rejects_invalid_json(
        self,
        mock_load_context,
        mock_chat_completion,
    ):
        """模型返回非法 JSON 时明确报错。"""
        mock_load_context.return_value = self.context
        mock_chat_completion.return_value = (
            '{"items": [invalid json]}'
        )

        with self.assertRaisesRegex(ValueError, "不是合法 JSON"):
            analyze_material_coverage(exam_id=1)

    @patch("services.coverage_service.chat_completion")
    @patch("services.coverage_service.load_coverage_context")
    def test_rejects_invalid_evidence(
        self,
        mock_load_context,
        mock_chat_completion,
    ):
        """模型返回无法在原文中找到的证据时拒绝报告。"""
        mock_load_context.return_value = self.context

        invalid_result = {
            "items": [
                dict(
                    self.valid_model_result["items"][0],
                    evidence=[
                        {
                            "material_id": 10,
                            "quote": "栈支持随机访问操作。",
                        }
                    ],
                ),
                self.valid_model_result["items"][1],
            ]
        }

        mock_chat_completion.return_value = json.dumps(
            invalid_result,
            ensure_ascii=False,
        )

        with self.assertRaisesRegex(
            ValueError,
            "未通过校验",
        ):
            analyze_material_coverage(exam_id=1)

    @patch("services.coverage_service.chat_completion")
    @patch("services.coverage_service.load_coverage_context")
    def test_propagates_api_failure(
        self,
        mock_load_context,
        mock_chat_completion,
    ):
        """API 调用失败时不生成虚假的报告。"""
        mock_load_context.return_value = self.context
        mock_chat_completion.side_effect = RuntimeError(
            "模拟 API 调用失败"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "模拟 API 调用失败",
        ):
            analyze_material_coverage(exam_id=1)


if __name__ == "__main__":
    unittest.main()
