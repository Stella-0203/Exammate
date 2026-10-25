
import sys
from pathlib import Path

from storage.db import get_connection, init_db
from services.syllabus_service import (
    create_exam_with_syllabus,
    confirm_suggestion,
)
from services.material_service import import_material
from services.coverage_service import analyze_material_coverage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "exammate_test.db"
MATERIAL_DIR = PROJECT_ROOT / "data" / "test_materials"
TXT_PATH = MATERIAL_DIR / "coverage_e2e_demo.txt"


def check_database_is_empty():
    """只检查，不清空已有数据。"""
    init_db(DB_PATH)
    connection = get_connection(DB_PATH)

    try:
        for table in ("courses", "exam_goals", "syllabus_items", "materials"):
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            if count > 0:
                raise RuntimeError(
                    f"测试数据库中的 {table} 已有 {count} 条记录。"
                    "为避免覆盖旧数据，请先确认是否可以使用另一份测试数据库。"
                )
    finally:
        connection.close()


def main():
    print("=== ExamMate 覆盖分析端到端测试 ===")
    print(f"测试数据库：{DB_PATH}")

    check_database_is_empty()

    MATERIAL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 创建一份小型考纲。
    raw_syllabus = """
    1. 栈的基本概念与入栈、出栈操作
    2. 队列的基本概念与先进先出特性
    """

    print("\n[1/4] 创建考试目标与考纲……")

    exam = create_exam_with_syllabus(
        course_name="端到端测试-数据结构",
        exam_name="端到端测试-覆盖分析",
        raw_syllabus_text=raw_syllabus,
        db_path=DB_PATH,
    )

    exam_id = exam["exam_id"]
    print(f"考试目标创建成功，exam_id={exam_id}")
    print(f"原始条目数：{exam['original_count']}")
    print(f"候选项数：{exam['suggestion_count']}")

    # 2. 审核所有模型生成的候选项。
    connection = get_connection(DB_PATH)
    try:
        suggestions = connection.execute(
            """
            SELECT id
            FROM syllabus_items
            WHERE exam_id = ?
              AND origin = 'inferred'
              AND review_status = 'pending'
            ORDER BY id
            """,
            (exam_id,),
        ).fetchall()
    finally:
        connection.close()

    for suggestion in suggestions:
        confirm_suggestion(suggestion["id"], db_path=DB_PATH)

    if not suggestions:
        print("模型没有生成候选项，将使用下面的原始考纲条目补充测试条目。")

        connection = get_connection(DB_PATH)
        try:
            with connection:
                original_items = connection.execute(
                    """
                    SELECT id
                    FROM syllabus_items
                    WHERE exam_id = ? AND origin = 'original'
                    ORDER BY sort_order
                    """,
                    (exam_id,),
                ).fetchall()

                for item in original_items:
                    connection.execute(
                        """
                        UPDATE syllabus_items
                        SET review_status = 'confirmed'
                        WHERE id = ?
                        """,
                        (item["id"],),
                    )
        finally:
            connection.close()

    # 3. 生成并导入真实 TXT 资料。
    print("\n[2/4] 创建并导入 TXT 资料……")

    TXT_PATH.write_text(
        """
        栈是一种后进先出的数据结构。
        入栈操作将元素放入栈顶，出栈操作移除栈顶元素。

        队列是一种先进先出的数据结构。
        入队操作将元素加入队尾，出队操作移除队头元素。
        """.strip(),
        encoding="utf-8",
    )

    material = import_material(
        file_path=TXT_PATH,
        course_id=exam["course_id"],
        exam_id=exam_id,
        db_path=DB_PATH,
        materials_dir=MATERIAL_DIR,
    )

    print(f"资料导入成功，material_id={material['id']}")
    print(f"文件类型：{material['file_type']}")
    print(f"解析状态：{material['parse_status']}")

    # 4. 使用真实数据库上下文和真实模型执行覆盖分析。
    print("\n[3/4] 调用真实模型执行覆盖分析……")

    report = analyze_material_coverage(
        exam_id=exam_id,
        db_path=DB_PATH,
    )

    print("\n[4/4] 检查分析报告……")
    print(f"课程：{report['exam']['course_name']}")
    print(f"考试：{report['exam']['name']}")
    print(f"分析条目数：{report['summary']['total_items']}")
    print(f"参与分析的资料数：{report['summary']['material_count']}")
    print(f"状态统计：{report['summary']['status_counts']}")

    for item in report["items"]:
        print("\n------------------------------")
        print(f"知识点 ID：{item['syllabus_item_id']}")
        print(f"状态：{item['status']}")
        print(f"原因：{item['reason']}")

        for evidence in item["evidence"]:
            print(f"证据资料 ID：{evidence['material_id']}")
            print(f"原文引用：{evidence['quote']}")

    # 基础断言
    assert report["summary"]["total_items"] > 0
    assert report["summary"]["material_count"] == 1

    valid_statuses = {
        "covered", "partial", "uncovered", "needs_review"
    }
    assert all(item["status"] in valid_statuses for item in report["items"])

    print("\n测试通过：真实资料读取与覆盖分析已跑通。")
    print("注意：本脚本尚未验证分析报告的持久化。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n测试失败：{type(exc).__name__}: {exc}")
        raise
