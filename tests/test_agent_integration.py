
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from core.agent import run_agent


class FakeMessage:
    """模拟模型返回的消息，避免真实 API 调用。"""

    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        result = {
            "role": "assistant",
            "content": self.content,
        }

        if self.tool_calls:
            result["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ]

        if exclude_none and result["content"] is None:
            result.pop("content")

        return result


def make_tool_call(name, arguments="{}"):
    return SimpleNamespace(
        id="call_test_001",
        type="function",
        function=SimpleNamespace(
            name=name,
            arguments=arguments,
        ),
    )


class FakeCompletions:
    """按顺序返回预设的模型响应，并记录请求。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        if not self.responses:
            raise AssertionError("Agent 请求了超出预期次数的模型响应")

        message = self.responses.pop(0)

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=message,
                    finish_reason=(
                        "tool_calls"
                        if message.tool_calls
                        else "stop"
                    ),
                )
            ]
        )


def test_agent_tool_call_reads_real_data_from_temp_db(tmp_path):
    # 1. 准备独立的临时数据库，不触碰正式数据库
    db_path = tmp_path / "agent_integration.db"

    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE courses (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO courses (id, name, created_at)
        VALUES (?, ?, ?)
        """,
        (1, "数据结构", "2026-10-25 10:00:00"),
    )
    connection.commit()
    connection.close()

    # 2. 模拟模型：先调用 list_courses，再返回最终回答
    first_message = FakeMessage(
        tool_calls=[make_tool_call("list_courses")]
    )
    final_message = FakeMessage(
        content="当前课程有：数据结构。"
    )

    completions = FakeCompletions(
        [first_message, final_message]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )

    # 3. 将 Agent 的数据库连接指向临时数据库
    def connect_temp_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    with (
        patch("core.agent.get_client", return_value=fake_client),
        patch("core.agent.get_connection", side_effect=connect_temp_db),
    ):
        result = run_agent("我有哪些课程？")

    # 4. 验证模型调用、真实工具执行和结果回传
    assert result == "当前课程有：数据结构。"
    assert len(completions.calls) == 2

    second_messages = completions.calls[1]["messages"]

    tool_messages = [
        message
        for message in second_messages
        if message.get("role") == "tool"
    ]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "call_test_001"


    tool_result = json.loads(tool_messages[0]["content"])

    assert tool_result["count"] == 1
    assert any(
        course["name"] == "数据结构"
        for course in tool_result["courses"]
    )

