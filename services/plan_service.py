
import json
from datetime import date, datetime

from core.llm_client import chat_completion
from storage.db import get_connection


ALLOWED_TASK_TYPES = {"learn", "review", "practice"}
ALLOWED_PRIORITIES = {"high", "medium", "low"}


def load_plan_context(exam_id: int, db_path=None) -> dict:
    """读取指定考试的基本信息和已审核考纲。"""
    connection = get_connection(db_path)

    try:
        exam = connection.execute(
            """
            SELECT
                eg.id,
                eg.course_id,
                eg.name AS exam_name,
                eg.exam_date,
                eg.status,
                c.name AS course_name
            FROM exam_goals AS eg
            JOIN courses AS c ON c.id = eg.course_id
            WHERE eg.id = ?
            """,
            (exam_id,),
        ).fetchone()

        if exam is None:
            raise ValueError(f"考试目标不存在：exam_id={exam_id}")

        if exam["status"] != "confirmed":
            raise ValueError("请先完成考纲审核，再生成复习计划。")

        if not exam["exam_date"]:
            raise ValueError("请先设置考试日期。")

        try:
            exam_date = date.fromisoformat(exam["exam_date"])
        except (TypeError, ValueError) as exc:
            raise ValueError("考试日期格式无效，应为 YYYY-MM-DD。") from exc

        today = date.today()
        if exam_date < today:
            raise ValueError("考试日期已过去，无法生成当前复习计划。")


        # 检查已确认父级下是否仍存在待审核的子项。
        pending_child = connection.execute(
            """
            SELECT parent.content AS parent_content,
                   child.content AS child_content
            FROM syllabus_items AS parent
            JOIN syllabus_items AS child
              ON child.parent_id = parent.id
             AND child.exam_id = parent.exam_id
            WHERE parent.exam_id = ?
              AND parent.parent_id IS NULL
              AND parent.review_status IN ('confirmed', 'edited')
              AND child.review_status = 'pending'
            LIMIT 1
            """,
            (exam_id,),
        ).fetchone()

        if pending_child is not None:
            raise ValueError(
                f"考纲尚未审核完成："
                f"「{pending_child['parent_content']}」下的"
                f"「{pending_child['child_content']}」仍待审核。"
            )

        # 选择可用于计划生成的考纲条目。
        rows = connection.execute(
            """
            SELECT
                si.id,
                si.content,
                si.item_type,
                si.parent_id,
                si.sort_order
            FROM syllabus_items AS si
            WHERE si.exam_id = ?
              AND si.review_status IN ('confirmed', 'edited')
              AND NOT EXISTS (
                  SELECT 1
                  FROM syllabus_items AS child
                  WHERE child.exam_id = si.exam_id
                    AND child.parent_id = si.id
                    AND child.review_status IN ('confirmed', 'edited')
              )
            ORDER BY
                CASE WHEN si.parent_id IS NULL THEN si.id
                     ELSE si.parent_id END,
                CASE WHEN si.parent_id IS NULL THEN 0 ELSE 1 END,
                si.sort_order,
                si.id
            """,
            (exam_id,),
        ).fetchall()


        if not rows:
            raise ValueError("没有已确认的考纲条目，无法生成复习计划。")

        return {
            "exam": dict(exam),
            "exam_date": exam_date.isoformat(),
            "start_date": today.isoformat(),
            "total_days": (exam_date - today).days + 1,
            "syllabus_items": [dict(row) for row in rows],
        }

    finally:
        connection.close()


def validate_review_plan(
    result: object,
    context: dict,
    daily_available_minutes: int,
) -> dict:
    """校验模型生成的计划结构、日期和每日时间上限。"""
    if not isinstance(result, dict):
        raise ValueError("模型返回的计划必须是 JSON 对象。")

    tasks = result.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("计划必须包含至少一项复习任务。")

    total_days = context["total_days"]
    start_date = date.fromisoformat(context["start_date"])
    exam_date = date.fromisoformat(context["exam_date"])

    topic_names = {
        item["content"].strip()
        for item in context["syllabus_items"]
    }

    daily_totals = {}
    validated_tasks = []

    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise ValueError(f"第 {index} 项任务格式错误。")

        day_number = task.get("day")
        topic = task.get("topic")
        task_type = task.get("task_type")
        priority = task.get("priority")
        minutes = task.get("estimated_minutes")
        description = task.get("description", "")

        if (
            isinstance(day_number, bool)
            or not isinstance(day_number, int)
            or not 1 <= day_number <= total_days
        ):
            raise ValueError(f"第 {index} 项任务的 day 超出有效范围。")

        if not isinstance(topic, str) or not topic.strip():
            raise ValueError(f"第 {index} 项任务缺少知识点。")

        if topic.strip() not in topic_names:
            raise ValueError(
                f"任务知识点不属于已审核考纲：{topic}"
            )

        if task_type not in ALLOWED_TASK_TYPES:
            raise ValueError(f"不支持的任务类型：{task_type}")

        if priority not in ALLOWED_PRIORITIES:
            raise ValueError(f"不支持的优先级：{priority}")

        if (
            isinstance(minutes, bool)
            or not isinstance(minutes, int)
            or minutes <= 0
        ):
            raise ValueError(f"第 {index} 项任务的预计时长必须为正整数。")

        if not isinstance(description, str):
            raise ValueError(f"第 {index} 项任务的说明格式错误。")

        task_date = start_date.fromordinal(
            start_date.toordinal() + day_number - 1
        )

        if task_date > exam_date:
            raise ValueError("任务日期不能晚于考试日期。")

        daily_totals[day_number] = (
            daily_totals.get(day_number, 0) + minutes
        )

        if daily_totals[day_number] > daily_available_minutes:
            raise ValueError(
                f"第 {day_number} 天的任务总时长超过每日可用时间。"
            )

        validated_tasks.append({
            "day": day_number,
            "date": task_date.isoformat(),
            "topic": topic.strip(),
            "task_type": task_type,
            "priority": priority,
            "estimated_minutes": minutes,
            "description": description.strip(),
        })

    return {
        "exam_id": context["exam"]["id"],
        "course_name": context["exam"]["course_name"],
        "exam_name": context["exam"]["exam_name"],
        "exam_date": context["exam_date"],
        "start_date": context["start_date"],
        "total_days": total_days,
        "daily_available_minutes": daily_available_minutes,
        "tasks": sorted(
            validated_tasks,
            key=lambda task: (task["day"], task["topic"]),
        ),
    }


def generate_review_plan(
    exam_id: int,
    daily_available_minutes: int,
    review_goal: str = "",
    db_path=None,
) -> dict:
    """根据已审核考纲生成并校验复习计划，不写入数据库。"""
    if (
        isinstance(daily_available_minutes, bool)
        or not isinstance(daily_available_minutes, int)
        or daily_available_minutes <= 0
    ):
        raise ValueError("每日可用复习时间必须是正整数。")

    if not isinstance(review_goal, str):
        raise ValueError("复习目标必须是字符串。")

    review_goal = review_goal.strip()
    if len(review_goal) > 1000:
        raise ValueError("复习目标不能超过 1000 字符。")

    context = load_plan_context(exam_id, db_path)

    user_payload = {
        "course_name": context["exam"]["course_name"],
        "exam_name": context["exam"]["exam_name"],
        "start_date": context["start_date"],
        "exam_date": context["exam_date"],
        "total_days": context["total_days"],
        "daily_available_minutes": daily_available_minutes,
        "review_goal": review_goal,
        "syllabus_items": [
            {
                "id": item["id"],
                "content": item["content"],
                "item_type": item["item_type"],
            }
            for item in context["syllabus_items"]
        ],
    }

    messages = [
        {
            "role": "system",
            "content": """
你是 ExamMate 的复习计划生成助手。

根据已审核的考纲和用户条件，生成具体、可执行的复习任务。

规则：
1. 只能使用输入中提供的考纲知识点，不得自行添加新的考纲知识点。
2. day 从 1 开始，表示从 start_date 起的第几天。
3. 所有任务必须安排在考试日期当天或之前。
4. 同一天所有任务的 estimated_minutes 总和不得超过
   daily_available_minutes。
5. task_type 只能是 learn、review、practice。
6. priority 只能是 high、medium、low。
7. 尽量覆盖所有考纲知识点，并合理安排学习、复习和练习。
8. 不要将每日可用时间全部填满作为硬性要求，应保留合理弹性。
9. description 应说明任务具体做什么，避免只有空泛的标题。
10. 只返回合法 JSON，不要使用 Markdown 代码块。

输出格式：
{
  "tasks": [
    {
      "day": 1,
      "topic": "必须与某个已审核考纲条目完全一致",
      "task_type": "learn",
      "priority": "high",
      "estimated_minutes": 40,
      "description": "具体复习任务"
    }
  ]
}
""",
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False),
        },
    ]

    raw_result = chat_completion(
        messages=messages,
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    try:
        parsed_result = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("模型返回的内容不是合法 JSON。") from exc

    return validate_review_plan(
        parsed_result,
        context,
        daily_available_minutes,
    )
