
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from storage.db import get_connection, init_db
from services.plan_persistence_service import (
    save_review_plan,
    get_current_review_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestMCPServer(unittest.TestCase):

    def test_mcp_tools_and_read_call(self):
        """验证 MCP 工具发现，以及 list_courses 调用。"""
        asyncio.run(self._test_mcp_tools_and_read_call())

    async def _test_mcp_tools_and_read_call(self):
        server = StdioServerParameters(
            command=sys.executable,
            args=["mcp_server.py"],
            env=os.environ.copy(),
        )

        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                result = await session.list_tools()
                tool_names = {tool.name for tool in result.tools}

                expected_tools = {
                    "list_courses",
                    "list_exams",
                    "get_exam_details",
                    "create_and_save_review_plan",
                    "get_review_plan",
                    "update_task_status",
                }

                print("发现的工具：", sorted(tool_names))

                for tool in result.tools:
                    print(f"工具名称 repr：{tool.name!r}")

                self.assertEqual(
                    expected_tools,
                    tool_names,
                    (
                        f"工具缺失：{expected_tools - tool_names}；"
                        f"意外工具：{tool_names - expected_tools}"
                    ),
                )

                result = await session.call_tool(
                    "list_courses",
                    arguments={},
                )

                self.assertFalse(result.isError, "list_courses 调用失败")
                print("MCP 工具发现和读取测试通过。")

    def test_update_task_status_through_mcp(self):
        """通过 MCP 更新任务状态，并确认临时数据库持久化成功。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "test_exammate.db")

            # 1. 初始化隔离的测试数据库，并准备测试数据。
            init_db(db_path=db_path)

            connection = get_connection(db_path)
            try:
                with connection:
                    cursor = connection.execute(
                        "INSERT INTO courses (name) VALUES (?)",
                        ("MCP 测试课程",),
                    )
                    course_id = cursor.lastrowid

                    cursor = connection.execute(
                        """
                        INSERT INTO exam_goals
                            (course_id, name, exam_date,
                             raw_syllabus_text, status)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            course_id,
                            "MCP 测试考试",
                            "2099-12-31",
                            "1. 线性表",
                            "confirmed",
                        ),
                    )
                    exam_id = cursor.lastrowid
            finally:
                connection.close()

            plan = {
                "review_goal": "MCP 写操作测试",
                "exam_date": "2099-12-31",
                "daily_available_minutes": 120,
                "tasks": [
                    {
                        "day": 1,
                        "topic": "线性表基础",
                        "task_type": "learn",
                        "priority": "high",
                        "estimated_minutes": 30,
                        "description": "测试任务状态更新",
                    },
                ],
            }

            plan_id = save_review_plan(
                exam_id,
                plan,
                db_path=db_path,
            )

            saved_plan = get_current_review_plan(
                exam_id,
                db_path=db_path,
            )
            task_id = saved_plan["tasks"][0]["id"]

            # 2. 通过环境变量将 MCP 子进程指向临时数据库。
            server_env = os.environ.copy()
            server_env["EXAMMATE_DB_PATH"] = db_path

            server = StdioServerParameters(
                command=sys.executable,
                args=["mcp_server.py"],
                env=server_env,
            )

            async def call_mcp_tool():
                async with stdio_client(server) as (
                    read_stream,
                    write_stream,
                ):
                    async with ClientSession(
                        read_stream,
                        write_stream,
                    ) as session:
                        await session.initialize()

                        result = await session.call_tool(
                            "update_task_status",
                            arguments={
                                "task_id": task_id,
                                "status": "completed",
                                "plan_id": plan_id,
                            },
                        )

                        self.assertFalse(
                            result.isError,
                            "MCP 工具调用发生协议层错误",
                        )

                        content_text = "\n".join(
                            item.text
                            for item in result.content
                            if hasattr(item, "text")
                        )
                        print("MCP 写操作返回：", content_text)

                        payload = json.loads(content_text)
                        self.assertTrue(
                            payload.get("success"),
                            f"任务更新失败：{payload}",
                        )

            asyncio.run(call_mcp_tool())

            # 3. 重新连接同一个临时数据库，核实写入结果。
            saved_again = get_current_review_plan(
                exam_id,
                db_path=db_path,
            )

            tasks_by_id = {
                task["id"]: task for task in saved_again["tasks"]
            }

            self.assertEqual(
                tasks_by_id[task_id]["status"],
                "completed",
            )

            print("MCP 写操作及数据库持久化测试通过。")


if __name__ == "__main__":
    unittest.main(verbosity=2)

