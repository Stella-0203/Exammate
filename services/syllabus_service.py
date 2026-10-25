import re

import json

from core.llm_client import chat_completion
from core.schemas import validate_suggestions

from storage.db import get_connection

from services.plan_persistence_service import (
    mark_review_plan_stale_in_transaction,
)

# 识别常见的条目开头，例如：
# 1. xxx、1、xxx、（1）xxx、(1) xxx、一、xxx、（一）xxx
# 同时支持项目符号。
ITEM_MARKER = re.compile(
    r"^\s*(?:"
    r"\d+\s*[.、．)]\s*"
    r"|[（(]\s*\d+\s*[）)]\s*"
    r"|[一二三四五六七八九十百零〇]+\s*[、.．]\s*"
    r"|[（(]\s*[一二三四五六七八九十百零〇]+\s*[）)]\s*"
    r"|[-*•]\s+"
    r")"
)


def parse_syllabus_text(text: str) -> list[dict[str, object]]:
    """
    将考纲文本拆分为原始条目。

    规则：
    1. 保留每个条目的原始编号或项目符号。
    2. 保留条目顺序。
    3. 空行不生成条目。
    4. 如果存在编号或项目符号，未标记的换行内容默认
       视为上一条的续行。
    5. 如果全文没有可识别的条目标记，则每个非空行作为一项。

    返回：
    [
        {"content": "1. 线性表的基本概念", "sort_order": 1},
        ...
    ]
    """
    if not isinstance(text, str):
        raise TypeError("考纲内容必须是字符串。")

    if not text.strip():
        raise ValueError("考纲内容不能为空。")

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:
        raise ValueError("考纲内容不能为空。")

    # 判断全文是否包含常见的条目标记
    has_markers = any(
        ITEM_MARKER.match(line)
        for line in lines
    )

    if not has_markers:
        items = lines
    else:
        items = []
        current_item = None

        for line in lines:
            if ITEM_MARKER.match(line):
                if current_item is not None:
                    items.append(current_item)

                current_item = line

            elif current_item is None:
                # 编号条目之前的说明文字也不能直接丢弃
                current_item = line

            else:
                # 将续行拼接到上一条，避免错误拆成独立条目
                current_item = f"{current_item} {line}"

        if current_item is not None:
            items.append(current_item)

    return [
        {
            "content": content,
            "sort_order": index,
        }
        for index, content in enumerate(items, start=1)
    ]



def generate_syllabus_suggestions(
    source_items: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    根据已解析的原始考纲条目生成候选展开项，
    并在返回前完成 JSON 解析与 Python 校验。
    """
    if not source_items:
        raise ValueError("没有可供展开的原始考纲条目。")

    prompt_items = [
        {
            "sort_order": item["sort_order"],
            "content": item["content"],
        }
        for item in source_items
    ]

    messages = [
        {
            "role": "system",
            "content": """
你是 ExamMate 的考纲分析助手。

你的任务是针对给定的每一条原始考纲，提出适量的候选知识点、
学习能力或题型要求，供用户审核。

规则：
1. 原始考纲是老师给出的依据，不得改写或覆盖。
2. 只生成有助于理解考试要求的候选项，不要无限细分。
3. 原文已经足够具体时，可以返回空 suggestions 数组。
4. 必须为输入中的每个 source_sort_order 返回且只返回一组结果。
5. source_sort_order 必须原样保留，不得自行编号。
6. 每个候选项都必须提供 content、item_type、rationale。
7. item_type 只能是 knowledge、skill、question_type、other。
8. rationale 说明推断依据，并区分原文明示内容与合理推断。
9. 不要声称推断出来的内容是老师明确要求的。
10. 不要回答输入数据以外的问题。

只返回符合 JSON 格式的对象：
{
  "items": [
    {
      "source_sort_order": 1,
      "suggestions": [
        {
          "content": "候选项内容",
          "item_type": "knowledge",
          "rationale": "提出该建议的依据"
        }
      ]
    }
  ]
}
""",
        },
        {
            "role": "user",
            "content": json.dumps(
                {"items": prompt_items},
                ensure_ascii=False,
            ),
        },
    ]

    raw_result = chat_completion(
        messages=messages,
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    try:
        parsed_result = json.loads(raw_result)
    except json.JSONDecodeError as exc:
        raise ValueError("模型返回的内容不是合法 JSON。") from exc

    return validate_suggestions(parsed_result, source_items)



def create_exam_with_syllabus(
    course_name: str,
    exam_name: str,
    raw_syllabus_text: str,
    exam_date: str | None = None,
    db_path=None,
) -> dict[str, object]:
    """
    创建考试目标，并保存原始考纲条目与模型候选展开项。

    先完成解析、模型生成和校验，再执行数据库事务。
    db_path 仅用于测试时指定临时数据库。
    """
    if not course_name.strip():
        raise ValueError("课程名称不能为空。")

    if not exam_name.strip():
        raise ValueError("考试名称不能为空。")

    # 第一步：解析原文并生成候选项。
    # 在这一步失败时，数据库不会新增课程或考试。
    source_items = parse_syllabus_text(raw_syllabus_text)
    suggestions = generate_syllabus_suggestions(source_items)

    connection = get_connection(db_path)

    try:
        with connection:
            # 第二步：查找已有课程；不存在时才创建。
            course = connection.execute(
                """
                SELECT id
                FROM courses
                WHERE name = ?
                ORDER BY id
                LIMIT 1
                """,
                (course_name.strip(),),
            ).fetchone()

            if course is None:
                cursor = connection.execute(
                    "INSERT INTO courses (name) VALUES (?)",
                    (course_name.strip(),),
                )
                course_id = cursor.lastrowid
            else:
                course_id = course["id"]

            # 第三步：创建本次考试。
            cursor = connection.execute(
                """
                INSERT INTO exam_goals (
                    course_id,
                    name,
                    exam_date,
                    raw_syllabus_text,
                    status
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    exam_name.strip(),
                    exam_date,
                    raw_syllabus_text,
                    "needs_review",
                ),
            )
            exam_id = cursor.lastrowid

            # 第四步：保存原始考纲条目，并记录条目序号到数据库 ID 的映射。
            original_ids = {}

            for item in source_items:
                cursor = connection.execute(
                    """
                    INSERT INTO syllabus_items (
                        exam_id,
                        parent_id,
                        content,
                        item_type,
                        origin,
                        review_status,
                        sort_order
                    )
                    VALUES (?, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        exam_id,
                        item["content"],
                        "other",
                        "original",
                        "pending",
                        item["sort_order"],
                    ),
                )

                original_ids[item["sort_order"]] = cursor.lastrowid

            # 第五步：保存模型生成的候选项。
            # 每个原始考纲条目下，候选项的排序从 1 开始。
            suggestion_orders = {}

            for item in suggestions:
                source_order = item["source_sort_order"]
                parent_id = original_ids[source_order]

                # 记录当前原始条目下的候选项数量。
                suggestion_orders[source_order] = (
                        suggestion_orders.get(source_order, 0) + 1
                )
                suggestion_order = suggestion_orders[source_order]

                connection.execute(
                    """
                    INSERT INTO syllabus_items (
                        exam_id,
                        parent_id,
                        content,
                        item_type,
                        origin,
                        review_status,
                        rationale,
                        sort_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        exam_id,
                        parent_id,
                        item["content"],
                        item["item_type"],
                        "inferred",
                        "pending",
                        item["rationale"],
                        suggestion_order,
                    ),
                )

        # 离开 with 块后，事务已成功提交。
        return {
            "course_id": course_id,
            "exam_id": exam_id,
            "original_count": len(source_items),
            "suggestion_count": len(suggestions),
            "status": "needs_review",
        }

    finally:
        connection.close()



def _refresh_exam_review_status(connection, exam_id: int) -> str:
    """根据考试下全部考纲条目的审核状态，重新计算考试目标状态。"""
    exam = connection.execute(
        "SELECT id FROM exam_goals WHERE id = ?",
        (exam_id,),
    ).fetchone()

    if exam is None:
        raise ValueError(f"考试目标不存在：{exam_id}")

    stats = connection.execute(
        """
        SELECT
            COUNT(*) AS total_count,
            SUM(
                CASE WHEN review_status = 'pending'
                THEN 1 ELSE 0 END
            ) AS pending_count
        FROM syllabus_items
        WHERE exam_id = ?
        """,
        (exam_id,),
    ).fetchone()

    total_count = stats["total_count"]
    pending_count = stats["pending_count"] or 0

    if total_count > 0 and pending_count == 0:
        status = "confirmed"
    else:
        status = "needs_review"

    connection.execute(
        """
        UPDATE exam_goals
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, exam_id),
    )

    return status


def _get_suggestion(connection, suggestion_id: int):
    """获取候选项，并确保它确实是模型生成的候选项。"""
    row = connection.execute(
        """
        SELECT id, exam_id, origin, content, review_status
        FROM syllabus_items
        WHERE id = ?
        """,
        (suggestion_id,),
    ).fetchone()

    if row is None:
        raise ValueError("考纲条目不存在")

    if row["origin"] != "inferred":
        raise ValueError("该条目不是可审核的候选条目")

    return row




def confirm_suggestion(
    suggestion_id: int,
    db_path=None,
) -> str:
    """确认保留候选项，并同步考试目标状态。"""
    connection = get_connection(db_path)

    try:
        with connection:
            suggestion = _get_suggestion(connection, suggestion_id)

            if suggestion["review_status"] != "confirmed":
                connection.execute(
                    """
                    UPDATE syllabus_items
                    SET review_status = 'confirmed',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (suggestion_id,),
                )

                mark_review_plan_stale_in_transaction(
                    connection,
                    suggestion["exam_id"],
                )

            status = _refresh_exam_review_status(
                connection,
                suggestion["exam_id"],
            )

        return status

    finally:
        connection.close()




def edit_suggestion(
    suggestion_id: int,
    new_content: str,
    db_path=None,
) -> str:
    """修改候选项内容，并同步考试目标审核状态。"""
    if not isinstance(new_content, str) or not new_content.strip():
        raise ValueError("候选项内容不能为空。")

    new_content = new_content.strip()

    if len(new_content) > 500:
        raise ValueError("候选项内容不能超过 500 字符。")

    connection = get_connection(db_path)

    try:
        with connection:
            suggestion = _get_suggestion(
                connection,
                suggestion_id,
            )

            content_changed = suggestion["content"] != new_content
            status_changed = suggestion["review_status"] != "edited"

            if content_changed or status_changed:
                connection.execute(
                    """
                    UPDATE syllabus_items
                    SET content = ?,
                        review_status = 'edited',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (new_content, suggestion_id),
                )

                mark_review_plan_stale_in_transaction(
                    connection,
                    suggestion["exam_id"],
                )

            status = _refresh_exam_review_status(
                connection,
                suggestion["exam_id"],
            )

        return status

    finally:
        connection.close()




def exclude_suggestion(
    suggestion_id: int,
    db_path=None,
) -> str:
    """排除候选项，但保留记录，并同步考试目标状态。"""
    connection = get_connection(db_path)

    try:
        with connection:
            suggestion = _get_suggestion(
                connection,
                suggestion_id,
            )

            if suggestion["review_status"] != "excluded":
                connection.execute(
                    """
                    UPDATE syllabus_items
                    SET review_status = 'excluded',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (suggestion_id,),
                )

                mark_review_plan_stale_in_transaction(
                    connection,
                    suggestion["exam_id"],
                )

            status = _refresh_exam_review_status(
                connection,
                suggestion["exam_id"],
            )

        return status

    finally:
        connection.close()


def add_syllabus_suggestion(
    exam_id: int,
    parent_id: int,
    content: str,
    item_type: str = "knowledge",
    rationale: str = "用户手动补充",
    db_path=None,
) -> dict[str, object]:
    """手动新增候选项，并同步考试目标审核状态。"""
    from core.schemas import ALLOWED_ITEM_TYPES

    # 1. 校验输入
    if not isinstance(content, str) or not content.strip():
        raise ValueError("候选项内容不能为空。")

    content = content.strip()
    if len(content) > 500:
        raise ValueError("候选项内容不能超过 500 字符。")

    if item_type not in ALLOWED_ITEM_TYPES:
        raise ValueError(f"不支持的候选项类型：{item_type}")

    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("新增依据不能为空。")

    rationale = rationale.strip()
    if len(rationale) > 1000:
        raise ValueError("新增依据不能超过 1000 字符。")

    connection = get_connection(db_path)

    try:
        with connection:
            # 2. 确认考试目标存在
            exam = connection.execute(
                "SELECT id FROM exam_goals WHERE id = ?",
                (exam_id,),
            ).fetchone()

            if exam is None:
                raise ValueError(f"考试目标不存在：{exam_id}")

            # 3. 确认父条目属于这份考试，且是原始考纲条目
            parent = connection.execute(
                """
                SELECT id
                FROM syllabus_items
                WHERE id = ?
                  AND exam_id = ?
                  AND origin = 'original'
                """,
                (parent_id, exam_id),
            ).fetchone()

            if parent is None:
                raise ValueError(
                    "关联的父条目不存在，或不属于该考试的原始考纲。"
                )

            # 4. 新增候选项，强制从 pending 开始
            cursor = connection.execute(
                """
                INSERT INTO syllabus_items (
                    exam_id,
                    parent_id,
                    content,
                    item_type,
                    origin,
                    review_status,
                    rationale,
                    sort_order
                )
                VALUES (?, ?, ?, ?, 'inferred', 'pending', ?, ?)
                """,
                (
                    exam_id,
                    parent_id,
                    content,
                    item_type,
                    rationale,
                    parent_id,
                ),
            )

            suggestion_id = cursor.lastrowid

            # 5. 考纲发生变化，使当前复习计划失效
            mark_review_plan_stale_in_transaction(
                connection,
                exam_id,
            )

            # 6. 重新计算考试目标审核状态
            exam_status = _refresh_exam_review_status(
                connection,
                exam_id,
            )

        # 事务提交成功后才返回
        return {
            "suggestion_id": suggestion_id,
            "exam_id": exam_id,
            "review_status": "pending",
            "exam_status": exam_status,
        }

    finally:
        connection.close()


def confirm_exam_syllabus(exam_id: int, db_path=None) -> str:
    """用户确认整份考纲；仍有待审核候选项时不允许完成。"""
    connection = get_connection(db_path)

    try:
        with connection:
            exam = connection.execute(
                "SELECT id FROM exam_goals WHERE id = ?",
                (exam_id,),
            ).fetchone()

            if exam is None:
                raise ValueError(f"考试目标不存在：{exam_id}")

            pending = connection.execute(
                """
                SELECT COUNT(*)
                FROM syllabus_items
                WHERE exam_id = ?
                  AND review_status = 'pending'
                """,
                (exam_id,),
            ).fetchone()[0]

            if pending > 0:
                raise ValueError(
                    "仍有待审核的考纲条目，请先完成原始考纲和候选项审核。"
                )

            connection.execute(
                """
                UPDATE exam_goals
                SET status = 'confirmed',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (exam_id,),
            )

        return "confirmed"

    finally:
        connection.close()





def confirm_original_syllabus_item(
    item_id: int,
    db_path=None,
) -> str:
    """确认一条原始考纲条目，并刷新考试目标审核状态。"""
    connection = get_connection(db_path)

    try:
        with connection:
            item = connection.execute(
                """
                SELECT id, exam_id, origin, review_status
                FROM syllabus_items
                WHERE id = ?
                """,
                (item_id,),
            ).fetchone()

            if item is None:
                raise ValueError(f"考纲条目不存在：{item_id}")

            if item["origin"] != "original":
                raise ValueError(
                    f"条目 {item_id} 不是原始考纲条目，不能通过此接口确认。"
                )

            # 只有审核状态真正改变时，才使当前计划失效
            if item["review_status"] != "confirmed":
                connection.execute(
                    """
                    UPDATE syllabus_items
                    SET review_status = 'confirmed',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (item_id,),
                )

                mark_review_plan_stale_in_transaction(
                    connection,
                    item["exam_id"],
                )

            # 刷新考试状态，并保留返回值
            status = _refresh_exam_review_status(
                connection,
                item["exam_id"],
            )

        # 必须返回状态，不能遗漏
        return status

    finally:
        connection.close()


