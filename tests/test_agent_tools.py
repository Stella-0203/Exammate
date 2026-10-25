import unittest
from core import agent
from unittest.mock import patch

from core import agent


class TestAgentTools(unittest.TestCase):

    def test_tool_dispatch(self):
        """工具分发：能否找到并执行指定工具。"""
        with patch.dict(
            agent.TOOL_FUNCTIONS,
            {"test_echo": lambda message: {"echo": message}},
        ):
            result = agent._execute_tool(
                "test_echo",
                {"message": "hello"},
            )

        self.assertEqual(result, {"echo": "hello"})

    def test_unknown_tool(self):
        """不存在的工具应返回错误。"""
        result = agent._execute_tool(
            "this_tool_does_not_exist",
            {},
        )

        self.assertIn("error", result)

    def test_invalid_arguments(self):
        """非法参数不能被当作成功执行。"""
        result = agent._execute_tool(
            "update_task_status",
            {
                "task_id": 0,
                "status": "completed",
                "plan_id": 1,
            },
        )

        self.assertIn("error", result)

    def test_task_update_failure(self):
        """业务服务更新失败时，Agent 工具必须如实返回失败。"""
        with patch(
            "core.agent.update_review_task_status",
            return_value=False,
        ):
            result = agent._execute_tool(
                "update_task_status",
                {
                    "task_id": 999,
                    "status": "completed",
                    "plan_id": 1,
                },
            )

        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_non_dict_arguments(self):
        """工具参数不是字典时，应安全返回错误。"""
        result = agent._execute_tool(
            "list_courses",
            [],
        )

        self.assertIn("error", result)



import unittest
from unittest.mock import patch

from core import agent


class TestAgentTools(unittest.TestCase):

    def test_tool_dispatch(self):
        """工具分发：能否找到并执行指定工具。"""
        with patch.dict(
            agent.TOOL_FUNCTIONS,
            {"test_echo": lambda message: {"echo": message}},
        ):
            result = agent._execute_tool(
                "test_echo",
                {"message": "hello"},
            )

        self.assertEqual(result, {"echo": "hello"})

    def test_unknown_tool(self):
        """不存在的工具应返回错误。"""
        result = agent._execute_tool(
            "this_tool_does_not_exist",
            {},
        )

        self.assertIn("error", result)

    def test_invalid_arguments(self):
        """非法参数不能被当作成功执行。"""
        result = agent._execute_tool(
            "update_task_status",
            {
                "task_id": 0,
                "status": "completed",
                "plan_id": 1,
            },
        )

        self.assertIn("error", result)

    def test_task_update_failure(self):
        """业务服务更新失败时，Agent 工具必须如实返回失败。"""
        with patch(
            "core.agent.update_review_task_status",
            return_value=False,
        ):
            result = agent._execute_tool(
                "update_task_status",
                {
                    "task_id": 999,
                    "status": "completed",
                    "plan_id": 1,
                },
            )

        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_non_dict_arguments(self):
        """工具参数不是字典时，应安全返回错误。"""
        result = agent._execute_tool(
            "list_courses",
            [],
        )

        self.assertIn("error", result)

    def test_tool_execution_exception(self):
        """工具执行过程中发生异常时，应返回错误而不是向外抛出。"""

        def raise_error():
            raise RuntimeError("模拟工具内部异常")

        with patch.dict(
            agent.TOOL_FUNCTIONS,
            {"test_failure": raise_error},
        ):
            result = agent._execute_tool("test_failure", {})

        self.assertIn("error", result)

    def test_json_safe_datetime(self):
        """日期时间等对象应转换为可序列化的数据。"""
        from datetime import date, datetime

        result = agent._json_safe({
            "date": date(2026, 10, 25),
            "datetime": datetime(2026, 10, 25, 12, 30),
        })

        self.assertEqual(result["date"], "2026-10-25")
        self.assertEqual(result["datetime"], "2026-10-25T12:30:00")

    def test_tool_result_json_serializable(self):
        """工具结果应能序列化为 JSON。"""
        import json

        result = agent._execute_tool(
            "list_courses",
            {},
        )

        serialized = json.dumps(
            result,
            ensure_ascii=False,
        )

        self.assertIsInstance(serialized, str)

        def test_json_safe_preserves_list_structure(self):
            value = {
                "count": 0,
                "courses": [],
                "nested": [
                    {"name": "数据结构", "topics": ["线性表", "树"]},
                ],
            }

            result = agent._json_safe(value)

            self.assertEqual(result["courses"], [])
            self.assertIsInstance(result["courses"], list)
            self.assertEqual(
                result["nested"][0]["topics"],
                ["线性表", "树"],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)