from typing import Any

from mcp.server.fastmcp import FastMCP

from core import agent as agent_tools


mcp = FastMCP("ExamMate")


def _call_tool(tool_name: str, **arguments: Any) -> dict:
    """复用现有 Agent 业务函数，统一处理工具调用错误。"""
    function = agent_tools.TOOL_FUNCTIONS.get(tool_name)

    if function is None:
        return {
            "success": False,
            "error": f"未知工具：{tool_name}",
        }

    try:
        result = function(**arguments)

        if isinstance(result, dict):
            return result

        return {
            "success": True,
            "result": result,
        }

    except (ValueError, TypeError) as exc:
        return {
            "success": False,
            "error": str(exc),
        }

    except Exception as exc:
        return {
            "success": False,
            "error": (
                "工具执行失败。"
                f"错误类型：{type(exc).__name__}。"
                "请检查业务数据或服务配置。"
            ),
        }


@mcp.tool()
def list_courses() -> dict:
    """查询 ExamMate 中已经创建的课程。"""
    return _call_tool("list_courses")


@mcp.tool()
def list_exams() -> dict:
    """查询考试列表及课程关联信息。"""
    return _call_tool("list_exams")


@mcp.tool()
def get_exam_details(exam_id: int) -> dict:
    """查询指定考试的详细信息及原始、展开考纲条目。"""
    return _call_tool(
        "get_exam_details",
        exam_id=exam_id,
    )


@mcp.tool()
def create_and_save_review_plan(
    exam_id: int,
    daily_available_minutes: int,
    review_goal: str = "",
) -> dict:
    """为指定考试生成复习计划，并保存到数据库。"""
    return _call_tool(
        "create_and_save_review_plan",
        exam_id=exam_id,
        daily_available_minutes=daily_available_minutes,
        review_goal=review_goal,
    )


@mcp.tool()
def get_review_plan(exam_id: int) -> dict:
    """查询指定考试当前生效的复习计划。"""
    return _call_tool(
        "get_review_plan",
        exam_id=exam_id,
    )


@mcp.tool()
def update_task_status(
    task_id: int,
    status: str,
    plan_id: int,
) -> dict:
    """更新指定复习计划中任务的状态，状态只能为 pending 或 completed。"""
    return _call_tool(
        "update_task_status",
        task_id=task_id,
        status=status,
        plan_id=plan_id,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")