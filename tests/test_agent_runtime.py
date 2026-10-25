
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import agent


def make_response(
    content=None,
    tool_calls=None,
    finish_reason="stop",
):
    """构造模拟的模型响应，不请求真实 API。"""

    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        model_dump=lambda exclude_none=True: {
            "role": "assistant",
            "content": content,
            **(
                {"tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in (tool_calls or [])
                ]}
                if tool_calls
                else {}
            ),
        },
    )

    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=message,
                finish_reason=finish_reason,
            )
        ]
    )


def make_tool_call(
    name="list_courses",
    arguments="{}",
    call_id="call_test_001",
):
    """构造模拟的模型工具调用请求。"""

    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


class TestAgentRuntime(unittest.TestCase):

    def setUp(self):
        self.client = Mock()

        # 只替换模型客户端，不访问真实 DeepSeek API。
        self.client_patch = patch(
            "core.agent.get_client",
            return_value=self.client,
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def test_tool_call_then_final_answer(self):
        """模型调用工具后，应读取工具结果并生成最终回答。"""

        self.client.chat.completions.create.side_effect = [
            make_response(
                tool_calls=[make_tool_call()],
                finish_reason="tool_calls",
            ),
            make_response(
                content="系统目前有 2 门课程。",
                finish_reason="stop",
            ),
        ]

        fake_courses = {
            "count": 2,
            "courses": [
                {"id": 1, "name": "数据结构"},
                {"id": 2, "name": "操作系统"},
            ],
        }

        with patch(
            "core.agent._execute_tool",
            return_value=fake_courses,
        ) as execute_tool:
            result = agent.run_agent("请列出课程并统计数量。")

        self.assertEqual(result, "系统目前有 2 门课程。")
        execute_tool.assert_called_once_with("list_courses", {})

        # 验证模型请求了两轮。
        self.assertEqual(
            self.client.chat.completions.create.call_count,
            2,
        )

        # 第二轮请求中应包含工具返回的数据。
        second_call = (
            self.client.chat.completions.create.call_args_list[1]
        )
        messages = second_call.kwargs["messages"]

        tool_messages = [
            message for message in messages
            if message.get("role") == "tool"
        ]

        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(
            json.loads(tool_messages[0]["content"]),
            fake_courses,
        )
        self.assertEqual(
            tool_messages[0]["tool_call_id"],
            "call_test_001",
        )

    def test_direct_final_answer_without_tool(self):
        """模型不需要工具时，应直接返回最终回答。"""

        self.client.chat.completions.create.return_value = (
            make_response(content="你好，我是 ExamMate。")
        )

        result = agent.run_agent("你好")

        self.assertEqual(result, "你好，我是 ExamMate。")
        self.client.chat.completions.create.assert_called_once()

    def test_invalid_tool_arguments_return_error_to_model(self):
        """模型生成非法 JSON 参数时，应将错误反馈给模型。"""

        self.client.chat.completions.create.side_effect = [
            make_response(
                tool_calls=[
                    make_tool_call(arguments="{invalid json")
                ],
                finish_reason="tool_calls",
            ),
            make_response(content="工具参数格式有误，请重试。"),
        ]

        with patch("core.agent._execute_tool") as execute_tool:
            result = agent.run_agent("查询课程")

        self.assertEqual(result, "工具参数格式有误，请重试。")
        execute_tool.assert_not_called()

        messages = (
            self.client.chat.completions.create.call_args_list[1]
            .kwargs["messages"]
        )

        tool_messages = [
            message for message in messages
            if message.get("role") == "tool"
        ]

        self.assertEqual(len(tool_messages), 1)
        self.assertIn(
            "不是合法 JSON",
            json.loads(tool_messages[0]["content"])["error"],
        )

    def test_tool_round_limit(self):
        """持续要求调用工具时，应遵守轮数上限。"""

        self.client.chat.completions.create.return_value = (
            make_response(
                tool_calls=[make_tool_call()],
                finish_reason="tool_calls",
            )
        )

        with patch(
            "core.agent._execute_tool",
            return_value={"count": 0, "courses": []},
        ):
            result = agent.run_agent(
                "请查询课程",
                max_tool_rounds=2,
            )

        self.assertIn("轮数上限", result)
        self.assertEqual(
            self.client.chat.completions.create.call_count,
            2,
        )

    def test_model_request_exception_propagates(self):
        """模型请求失败时，当前实现应向调用方抛出异常。"""

        self.client.chat.completions.create.side_effect = (
            RuntimeError("模拟模型请求失败")
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "模拟模型请求失败",
        ):
            agent.run_agent("查询课程")


if __name__ == "__main__":
    unittest.main(verbosity=2)
