import sqlite3
from datetime import date

from storage.db import get_connection


def save_review_plan(exam_id, plan, db_path=None):
    """
    保存一份复习计划及其任务。

    plan 格式：
    {
        "review_goal": "期末复习",
        "exam_date": "2026-12-20",
        "daily_available_minutes": 120,
        "tasks": [
            {
                "day": 1,
                "topic": "线性表",
                "task_type": "learn",
                "priority": "high",
                "estimated_minutes": 30,
                "description": "复习线性表的基本概念"
            }
        ]
    }

    新计划及其任务全部保存成功后，才归档旧计划。
    返回新计划的 ID。
    """
    if not isinstance(exam_id, int) or isinstance(exam_id, bool) or exam_id <= 0:
        raise ValueError("exam_id 必须是正整数")

    if not isinstance(plan, dict):
        raise ValueError("plan 必须是字典")

    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("复习计划必须包含至少一项任务")

    review_goal = plan.get("review_goal", "")
    exam_date = plan.get("exam_date")
    daily_minutes = plan.get("daily_available_minutes")

    if not isinstance(review_goal, str):
        raise ValueError("review_goal 必须是字符串")

    if not isinstance(exam_date, str) or not exam_date:
        raise ValueError("exam_date 必须是非空日期字符串")

    try:
        parsed_exam_date = date.fromisoformat(exam_date)
    except ValueError as exc:
        raise ValueError(
            "exam_date 格式无效，应为 YYYY-MM-DD"
        ) from exc

    if parsed_exam_date.isoformat() != exam_date:
        raise ValueError(
            "exam_date 格式无效，应为 YYYY-MM-DD"
        )

    if (
        not isinstance(daily_minutes, int)
        or isinstance(daily_minutes, bool)
        or daily_minutes <= 0
    ):
        raise ValueError("daily_available_minutes 必须是正整数")

    connection = get_connection(db_path)

    try:
        # 显式开启事务，确保新计划、任务及旧计划状态变更原子完成。
        connection.execute("BEGIN")

        exam = connection.execute(
            """
            SELECT id
            FROM exam_goals
            WHERE id = ?
            """,
            (exam_id,),
        ).fetchone()

        if exam is None:
            raise ValueError(f"考试目标不存在：{exam_id}")

        cursor = connection.execute(
            """
            INSERT INTO review_plans (
                exam_id,
                review_goal,
                exam_date,
                daily_available_minutes,
                status
            )
            VALUES (?, ?, ?, ?, 'archived')
            """,
            (exam_id, review_goal, exam_date, daily_minutes),
        )
        plan_id = cursor.lastrowid

        for index, task in enumerate(tasks):
            if not isinstance(task, dict):
                raise ValueError(f"第 {index + 1} 项任务必须是字典")

            day = task.get("day")
            topic = task.get("topic")
            task_type = task.get("task_type")
            priority = task.get("priority")
            minutes = task.get("estimated_minutes")
            description = task.get("description")

            if (
                not isinstance(day, int)
                or isinstance(day, bool)
                or day < 1
            ):
                raise ValueError(f"第 {index + 1} 项任务的 day 无效")

            if not isinstance(topic, str) or not topic.strip():
                raise ValueError(f"第 {index + 1} 项任务的 topic 无效")

            if task_type not in {"learn", "review", "practice"}:
                raise ValueError(f"第 {index + 1} 项任务的 task_type 无效")

            if priority not in {"high", "medium", "low"}:
                raise ValueError(f"第 {index + 1} 项任务的 priority 无效")

            if (
                not isinstance(minutes, int)
                or isinstance(minutes, bool)
                or minutes <= 0
            ):
                raise ValueError(
                    f"第 {index + 1} 项任务的 estimated_minutes 无效"
                )

            if not isinstance(description, str):
                raise ValueError(
                    f"第 {index + 1} 项任务的 description 必须是字符串"
                )

            connection.execute(
                """
                INSERT INTO review_tasks (
                    plan_id,
                    day_number,
                    topic,
                    task_type,
                    priority,
                    estimated_minutes,
                    description,
                    status,
                    sort_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    plan_id,
                    day,
                    topic.strip(),
                    task_type,
                    priority,
                    minutes,
                    description,
                    index,
                ),
            )

        # 新计划和所有任务都插入成功后，再归档旧计划。
        connection.execute(
            """
            UPDATE review_plans
            SET status = 'archived',
                updated_at = CURRENT_TIMESTAMP
            WHERE exam_id = ?
              AND id != ?
              AND status = 'active'
            """,
            (exam_id, plan_id),
        )

        connection.execute(
            """
            UPDATE review_plans
            SET status = 'active',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (plan_id,),
        )

        connection.commit()
        return plan_id

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def mark_review_plan_stale_in_transaction(
    connection: sqlite3.Connection,
    exam_id: int,
) -> int:
    """在当前事务中，将指定考试的有效复习计划标记为失效。"""
    if isinstance(exam_id, bool) or not isinstance(exam_id, int) or exam_id <= 0:
        raise ValueError("exam_id 必须是正整数")

    cursor = connection.execute(
        """
        UPDATE review_plans
        SET status = 'stale',
            updated_at = CURRENT_TIMESTAMP
        WHERE exam_id = ?
          AND status = 'active'
        """,
        (exam_id,),
    )
    return cursor.rowcount


def get_current_review_plan(exam_id, db_path=None):
    """
    获取考试目标当前的有效计划及其任务。
    没有当前计划时返回 None。
    """
    connection = get_connection(db_path)

    try:
        plan = connection.execute(
            """
            SELECT *
            FROM review_plans
            WHERE exam_id = ?
              AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (exam_id,),
        ).fetchone()

        if plan is None:
            return None

        tasks = connection.execute(
            """
            SELECT *
            FROM review_tasks
            WHERE plan_id = ?
            ORDER BY day_number, sort_order, id
            """,
            (plan["id"],),
        ).fetchall()

        result = dict(plan)
        result["tasks"] = [dict(task) for task in tasks]

        return result

    finally:
        connection.close()


def update_review_task_status(
    task_id,
    status,
    plan_id=None,
    db_path=None,
):
    """
    更新任务状态。

    status 只能是 pending 或 completed。
    如果传入 plan_id，则同时检查任务是否属于指定计划。
    返回 True 表示更新成功，False 表示任务不存在或不属于指定计划。
    """
    if status not in {"pending", "completed"}:
        raise ValueError("status 只能是 pending 或 completed")

    connection = get_connection(db_path)

    try:
        if plan_id is None:
            cursor = connection.execute(
                """
                UPDATE review_tasks
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, task_id),
            )
        else:
            cursor = connection.execute(
                """
                UPDATE review_tasks
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND plan_id = ?
                """,
                (status, task_id, plan_id),
            )

        connection.commit()
        return cursor.rowcount > 0

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()



def mark_review_plan_stale_in_transaction(
    connection: sqlite3.Connection,
    exam_id: int,
) -> int:
    """
    在调用方现有事务中，将指定考试的当前有效计划标记为 stale。

    不提交、不回滚、不关闭连接。
    返回被更新的计划数量。
    """
    if (
        isinstance(exam_id, bool)
        or not isinstance(exam_id, int)
        or exam_id <= 0
    ):
        raise ValueError("exam_id 必须是正整数")

    cursor = connection.execute(
        """
        UPDATE review_plans
        SET status = 'stale',
            updated_at = CURRENT_TIMESTAMP
        WHERE exam_id = ?
          AND status = 'active'
        """,
        (exam_id,),
    )
    return cursor.rowcount


def mark_review_plan_stale(exam_id, db_path=None) -> int:
    """
    独立地将指定考试的当前有效计划标记为 stale。

    返回被更新的计划数量；没有 active 计划时返回 0。
    """
    if (
        isinstance(exam_id, bool)
        or not isinstance(exam_id, int)
        or exam_id <= 0
    ):
        raise ValueError("exam_id 必须是正整数")

    connection = get_connection(db_path)

    try:
        connection.execute("BEGIN")

        updated_count = mark_review_plan_stale_in_transaction(
            connection,
            exam_id,
        )

        connection.commit()
        return updated_count

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
