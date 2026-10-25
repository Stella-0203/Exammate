
"""真实 DeepSeek API 多考纲条目覆盖分析测试。"""

import unittest.mock
from pprint import pprint

from services.coverage_service import analyze_material_coverage


# 模拟数据库读取结果，但保留真实 DeepSeek API 调用。
context = {
    "exam": {
        "id": 1,
        "name": "多条目覆盖分析测试",
        "course_id": 1,
        "course_name": "数据结构",
        "exam_date": None,
        "status": "confirmed",
    },
    "syllabus_items": [
        {
            "id": 101,
            "content": "掌握栈的入栈和出栈操作",
            "item_type": "knowledge",
            "parent_id": None,
        },
        {
            "id": 102,
            "content": "掌握队列的入队、出队操作及其时间复杂度",
            "item_type": "knowledge",
            "parent_id": None,
        },
        {
            "id": 103,
            "content": "掌握循环队列判空和判满的条件",
            "item_type": "knowledge",
            "parent_id": None,
        },
        {
            "id": 104,
            "content": "理解本课程表达式求值所采用的数据结构",
            "item_type": "knowledge",
            "parent_id": None,
        },
    ],
    "materials": [
        {
            "id": 10,
            "original_name": "栈的基本操作.txt",
            "extracted_text": (
                "栈是一种后进先出（LIFO）的数据结构。"
                "入栈操作将元素压入栈顶，出栈操作将栈顶元素移除。"
            ),
        },
        {
            "id": 11,
            "original_name": "队列的基本操作.txt",
            "extracted_text": (
                "队列是一种先进先出（FIFO）的数据结构。"
                "入队操作将元素添加到队尾，出队操作将队头元素移除。"
            ),
        },
        {
            "id": 12,
            "original_name": "表达式求值资料A.txt",
            "extracted_text": "本课程采用栈结构进行表达式求值。",
        },
        {
            "id": 13,
            "original_name": "表达式求值资料B.txt",
            "extracted_text": "本课程不使用栈进行表达式求值，而采用队列结构。",
        },
    ],
}


def main():
    print("开始真实 DeepSeek API 多条目覆盖分析测试……")

    try:
        with unittest.mock.patch(
            "services.coverage_service.load_coverage_context",
            return_value=context,
        ):
            report = analyze_material_coverage(exam_id=1)

        print("\n完整分析报告：")
        pprint(report, sort_dicts=False)


        print("\n逐条结果字段检查：")
        for item in report["items"]:
            print(
                "ID =", item["syllabus_item_id"],
                "| status =", item["status"],
                "| reason =", repr(item["reason"]),
                "| evidence =", repr(item["evidence"]),
                "| uncertainty =", repr(item["uncertainty"]),
            )

        print("\n逐条分析结果：")
        for item in report["items"]:
            syllabus_content = next(
                s["content"]
                for s in context["syllabus_items"]
                if s["id"] == item["syllabus_item_id"]
            )

            print(f"\n考纲 ID：{item['syllabus_item_id']}")
            print(f"考纲内容：{syllabus_content}")
            print(f"覆盖状态：{item['status']}")
            print(f"判断理由：{item['reason']}")
            print(f"证据：{item['evidence']}")
            print(f"不确定原因：{item['uncertainty']}")

        print("\n测试摘要：")
        print(f"条目总数：{report['summary']['total_items']}")
        print(f"资料数量：{report['summary']['material_count']}")
        print(f"状态统计：{report['summary']['status_counts']}")

        # 自动检查：条目完整性、字段完整性、证据归属和统计一致性。
        expected_ids = {101, 102, 103, 104}
        items_by_id = {
            item["syllabus_item_id"]: item
            for item in report["items"]
        }

        actual_ids = [
            item["syllabus_item_id"]
            for item in report["items"]
        ]

        assert len(actual_ids) == len(set(actual_ids)), "存在重复条目"
        assert set(actual_ids) == expected_ids, "条目遗漏或出现未知 ID"
        assert report["summary"]["total_items"] == 4, "条目总数不正确"

        required_fields = {
            "syllabus_item_id",
            "status",
            "reason",
            "evidence",
            "uncertainty",
        }

        for item in report["items"]:
            item_id = item["syllabus_item_id"]

            assert required_fields.issubset(item.keys()), (
                f"条目 {item_id} 缺少必要字段"
            )
            assert item["status"] in {
                "covered", "partial", "uncovered", "needs_review"
            }, f"条目 {item_id} 的状态无效"

            assert isinstance(item["reason"], str) and item["reason"].strip(), (
                f"条目 {item_id} 缺少判断理由"
            )

            if item["status"] in {"covered", "partial"}:
                assert item["evidence"], (
                    f"条目 {item_id} 为 {item['status']}，却没有证据"
                )

            if item["status"] == "needs_review":
                assert item["uncertainty"].strip(), (
                    f"条目 {item_id} 需要复核，却没有说明原因"
                )

            # 检查证据引用的原文是否确实属于对应材料。
            material_by_id = {
                material["id"]: material
                for material in context["materials"]
            }

            for evidence in item["evidence"]:
                material_id = evidence["material_id"]
                assert material_id in material_by_id, (
                    f"条目 {item_id} 引用了不存在的资料 {material_id}"
                )

                source_text = material_by_id[material_id]["extracted_text"]
                quote = evidence["quote"]

                normalize = lambda text: " ".join(text.casefold().split())

                assert normalize(quote) in normalize(source_text), (
                    f"条目 {item_id} 的证据不属于资料 {material_id}"
                )

        counts = report["summary"]["status_counts"]
        assert sum(counts.values()) == 4, "状态统计总数不正确"

        print("\n自动检查通过：条目、字段、证据归属和统计均符合约束。")

    except Exception as exc:
        print("\n多条目真实 API 集成测试失败。")
        print(f"错误类型：{type(exc).__name__}")
        print(f"错误信息：{exc}")
        raise


if __name__ == "__main__":
    main()

