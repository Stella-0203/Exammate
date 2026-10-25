
import json
from typing import Any

from core.config import MODEL_NAME
from core.llm_client import get_client
from storage.db import get_connection
from services.plan_service import (
    generate_review_plan,
    load_plan_context,
)
from services.plan_persistence_service import (
    save_review_plan,
    get_current_review_plan,
    update_review_task_status,
)

from datetime import date, datetime


SYSTEM_PROMPT = """
你是 ExamMate，一个基于学生真实课程资料的考试复习助手。

工作原则：
1. 优先调用工具获取真实数据，不得编造课程、考纲、考试日期或计划状态。
2. 用户没有提供考试 ID 时，先查询考试列表，再根据结果确定目标。
3. 生成复习计划时，必须使用系统中的已确认考纲。
4. 生成计划后，应明确告知用户计划是否已保存，以及对应的考试和计划 ID。
5. 更新任务状态前，先确认目标任务属于当前考试的复习计划。
6. 如果缺少必要信息、存在多个可能的目标，先向用户询问。
7. 不要声称执行了实际没有成功执行的操作。
8. 用清楚、自然的中文回答，优先给出可执行的建议。
"""



def _json_safe(value: Any) -> Any:
    """将 SQLite 查询结果等对象转换为可序列化的数据。"""
    if isinstance(value, dict):
        return {
            str(k): _json_safe(v)
            for k, v in value.items()
        }

    # 必须保留列表结构，不能将列表转换成字符串。
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    # 兼容 sqlite3.Row 等具有 keys() 方法的对象。
    if hasattr(value, "keys"):
        return {
            str(k): _json_safe(value[k])
            for k in value.keys()
        }

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)



def _read_table(table_name: str) -> list[dict]:
    """读取 ExamMate 的基础数据表，只允许访问指定白名单。"""
    allowed_tables = {
        "courses",
        "exam_goals",
        "syllabus_items",
    }

    if table_name not in allowed_tables:
        raise ValueError("不允许读取该数据表。")

    connection = get_connection()

    try:
        rows = connection.execute(
            f"SELECT * FROM {table_name}"
        ).fetchall()

        return [_json_safe(row) for row in rows]
    finally:
        connection.close()


def list_courses() -> dict:
    """查询系统中已经创建的课程。"""
    courses = _read_table("courses")

    return {
        "count": len(courses),
        "courses": courses,
    }


def list_exams() -> dict:
    """查询考试目标及其关联课程 ID。"""
    exams = _read_table("exam_goals")
    courses = _read_table("courses")

    return {
        "exams": exams,
        "courses": courses,
        "note": (
            "请根据 exam_goals 中的课程外键与 courses 记录关联。"
            "考试 ID 用于后续查询或生成复习计划。"
        ),
    }


def get_exam_details(exam_id: int) -> dict:
    """查询指定考试及其考纲条目。"""
    if type(exam_id) is not int or exam_id <= 0:
        raise ValueError("exam_id 必须是正整数。")

    exams = _read_table("exam_goals")
    matching_exams = [
        exam for exam in exams
        if exam.get("id") == exam_id
    ]

    if not matching_exams:
        raise ValueError(f"没有找到考试 ID 为 {exam_id} 的记录。")

    syllabus_items = _read_table("syllabus_items")
    related_items = [
        item for item in syllabus_items
        if item.get("exam_id") == exam_id
    ]

    return {
        "exam": matching_exams[0],
        "syllabus_items": related_items,
    }



def create_and_save_review_plan(
    exam_id: int,
    daily_available_minutes: int,
    review_goal: str = "",
) -> dict:
    """生成复习计划，并保存到数据库中。"""
    if type(exam_id) is not int or exam_id <= 0:
        raise ValueError("exam_id 必须是正整数。")

    if (
        type(daily_available_minutes) is not int
        or not 1 <= daily_available_minutes <= 1440
    ):
        raise ValueError(
            "daily_available_minutes 必须是 1 到 1440 之间的整数。"
        )

    if not isinstance(review_goal, str):
        raise ValueError("review_goal 必须是字符串。")

    review_goal = review_goal.strip()

    # 生成服务内部会读取考试信息、审核状态和已确认考纲，
    # 并校验模型生成的任务。
    plan = generate_review_plan(
        exam_id=exam_id,
        daily_available_minutes=daily_available_minutes,
        review_goal=review_goal,
    )

    # generate_review_plan 已经返回保存服务需要的日期、时间和任务。
    plan_to_save = {
        **plan,
        "review_goal": review_goal,
    }

    # 只有保存服务成功返回后，才向模型报告成功。
    plan_id = save_review_plan(
        exam_id=exam_id,
        plan=plan_to_save,
    )

    return {
        "success": True,
        "exam_id": exam_id,
        "plan_id": plan_id,
        "exam_date": plan_to_save["exam_date"],
        "daily_available_minutes": daily_available_minutes,
        "task_count": len(plan_to_save["tasks"]),
        "message": "复习计划已生成并保存。",
    }



def get_review_plan(exam_id: int) -> dict:
    """获取指定考试当前生效的复习计划。"""
    if type(exam_id) is not int or exam_id <= 0:
        raise ValueError("exam_id 必须是正整数。")

    plan = get_current_review_plan(exam_id)

    if plan is None:
        return {
            "success": True,
            "found": False,
            "message": "该考试目前没有生效的复习计划。",
        }

    return {
        "success": True,
        "found": True,
        "plan": _json_safe(plan),
    }



def update_task_status(
    task_id: int,
    status: str,
    plan_id: int,
) -> dict:
    """更新指定复习计划中的任务状态。"""
    if type(task_id) is not int or task_id <= 0:
        raise ValueError("task_id 必须是正整数。")

    if type(plan_id) is not int or plan_id <= 0:
        raise ValueError("plan_id 必须是正整数。")

    if status not in {"pending", "completed"}:
        raise ValueError("status 只能是 pending 或 completed。")

    updated = update_review_task_status(
        task_id=task_id,
        status=status,
        plan_id=plan_id,
    )

    if not updated:
        return {
            "success": False,
            "error": (
                f"没有找到属于计划 {plan_id} 的任务 {task_id}，"
                "任务状态未更新。"
            ),
        }

    return {
        "success": True,
        "task_id": task_id,
        "plan_id": plan_id,
        "status": status,
        "message": "任务状态更新成功。",
    }



# 模型能够调用的工具定义。
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_courses",
            "description": "查询系统中已经创建的课程。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_exams",
            "description": (
                "查询考试列表及课程关联信息。"
                "当用户没有提供考试 ID，或询问有哪些考试时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exam_details",
            "description": "查询指定考试的详细信息及原始、展开考纲条目。",
            "parameters": {
                "type": "object",
                "properties": {
                    "exam_id": {
                        "type": "integer",
                        "description": "数据库中的考试 ID。",
                    },
                },
                "required": ["exam_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_and_save_review_plan",
            "description": (
                "为指定考试生成复习计划，并保存到数据库。"
                "仅在用户明确要求生成或制定计划时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exam_id": {
                        "type": "integer",
                        "description": "目标考试 ID。",
                    },
                    "daily_available_minutes": {
                        "type": "integer",
                        "description": "每天可用于复习的分钟数。",
                    },
                    "review_goal": {
                        "type": "string",
                        "description": "复习目标或用户补充要求。",
                    },
                },
                "required": [
                    "exam_id",
                    "daily_available_minutes",
                    #"review_goal",
                ],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_review_plan",
            "description": "查询指定考试当前生效的复习计划。",
            "parameters": {
                "type": "object",
                "properties": {
                    "exam_id": {
                        "type": "integer",
                        "description": "目标考试 ID。",
                    },
                },
                "required": ["exam_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task_status",
            "description": (
                "将指定复习计划中的任务标记为已完成或待复习。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "复习任务 ID。",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "completed"],
                    },
                    "plan_id": {
                        "type": "integer",
                        "description": "该任务所属的计划 ID。",
                    },
                },
                "required": ["task_id", "status", "plan_id"],
                "additionalProperties": False,
            },
        },
    },
]


TOOL_FUNCTIONS = {
    "list_courses": list_courses,
    "list_exams": list_exams,
    "get_exam_details": get_exam_details,
    "create_and_save_review_plan": create_and_save_review_plan,
    "get_review_plan": get_review_plan,
    "update_task_status": update_task_status,
}


def _execute_tool(tool_name: str, arguments: dict) -> dict:
    """只执行白名单中的业务工具，并将错误转换为工具结果。"""
    function = TOOL_FUNCTIONS.get(tool_name)

    if function is None:
        return {
            "success": False,
            "error": f"不允许调用未知工具：{tool_name}",
        }

    if not isinstance(arguments, dict):
        return {
            "success": False,
            "error": "工具参数必须是 JSON 对象。",
        }

    try:
        result = function(**arguments)
        return _json_safe(result)
    except (ValueError, TypeError) as exc:
        return {
            "success": False,
            "error": str(exc),
        }
    except Exception as exc:
        # 不向模型或用户暴露环境变量、请求头等敏感信息。
        return {
            "success": False,
            "error": (
                "工具执行失败。"
                f"错误类型：{type(exc).__name__}。"
                "请检查相关业务数据或服务配置。"
            ),
        }



def run_agent(
    user_message: str,
    max_tool_rounds: int = 5,
) -> str:
    """运行 Agent：模型决策 -> 执行工具 -> 返回结果 -> 模型总结。"""
    if not isinstance(user_message, str) or not user_message.strip():
        raise ValueError("请输入非空消息。")

    if type(max_tool_rounds) is not int or not 1 <= max_tool_rounds <= 10:
        raise ValueError("max_tool_rounds 必须是 1 到 10 之间的整数。")

    client = get_client()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message.strip()},
    ]

    for round_index in range(max_tool_rounds):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.2,
        )

        # 调试信息 1：检查模型是否决定调用工具。
        assistant_message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        print(f"\n[Agent 调试] 第 {round_index + 1} 轮")
        print(f"[Agent 调试] finish_reason: {finish_reason}")
        print(
            "[Agent 调试] 模型返回工具调用数:",
            len(assistant_message.tool_calls or []),
        )

        # 保存模型完整的工具调用请求，以便后续正确续接对话。
        messages.append(
            assistant_message.model_dump(exclude_none=True)
        )

        tool_calls = assistant_message.tool_calls

        if not tool_calls:
            if assistant_message.content:
                print("[Agent 调试] 模型直接返回最终回答。")
                return assistant_message.content

            print("[Agent 调试] 模型没有返回文本或工具调用。")
            return "模型没有返回可用的回答，请重试。"

        # 执行模型提出的工具调用。
        for tool_call in tool_calls:
            tool_name = tool_call.function.name

            print(f"[Agent 调试] 准备调用工具: {tool_name}")
            print(
                f"[Agent 调试] 原始参数: "
                f"{tool_call.function.arguments}"
            )

            try:
                arguments = json.loads(
                    tool_call.function.arguments or "{}"
                )
            except json.JSONDecodeError:
                tool_result = {
                    "success": False,
                    "error": "模型生成的工具参数不是合法 JSON。",
                }
            else:
                tool_result = _execute_tool(
                    tool_name,
                    arguments,
                )

            # 调试信息 2：检查工具是否执行，以及实际返回了什么。
            print(f"[Agent 调试] 工具执行结果: {tool_result}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(
                    tool_result,
                    ensure_ascii=False,
                ),
            })

    print("[Agent 调试] 已达到工具调用轮数上限。")
    return (
        "本次处理触发了工具调用轮数上限，"
        "尚未生成最终回答。请缩小请求范围后重试。"
    )
