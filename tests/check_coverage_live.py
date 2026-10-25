import unittest.mock
from pprint import pprint

from services.coverage_service import analyze_material_coverage


def main():
    # 构造最小化的测试上下文，不读写正式数据库
    context = {
        "exam": {
            "id": 1,
            "name": "覆盖分析测试",
            "course_id": 1,
            "course_name": "数据结构",
            "exam_date": None,
            "status": "confirmed",
        },
        "syllabus_items": [
            {
                "id": 101,
                "exam_id": 1,
                "parent_id": None,
                "content": "掌握栈的入栈和出栈操作",
                "item_type": "knowledge",
                "origin": "original",
                "review_status": "confirmed",
                "rationale": None,
                "sort_order": 1,
            }
        ],
        "materials": [
            {
                "id": 10,
                "course_id": 1,
                "exam_id": None,
                "original_name": "数据结构测试讲义.txt",
                "stored_path": "/fake/test_lecture.txt",
                "file_type": "txt",
                "extracted_text": (
                    "栈是一种后进先出（LIFO）的数据结构。"
                    "入栈操作将元素压入栈顶，"
                    "出栈操作将栈顶元素移除。"
                ),
                "parse_status": "success",
            }
        ],
    }

    print("开始真实 DeepSeek API 覆盖分析测试……")

    try:
        # 只替换数据库读取，不替换模型调用。
        # chat_completion 仍然会真正请求 DeepSeek。
        with unittest.mock.patch(
            "services.coverage_service.load_coverage_context",
            return_value=context,
        ):
            report = analyze_material_coverage(exam_id=1)

        print("\n分析成功！结构化报告如下：")
        pprint(report, sort_dicts=False)

        print("\n检查 items 的实际字段：")
        print(report["items"][0].keys())
        print("\n检查第一条结果的完整内容：")
        print(repr(report["items"][0]))

        print("\n测试摘要：")
        print(f"考纲条目数：{report['summary']['total_items']}")
        print(f"资料数量：{report['summary']['material_count']}")
        print(f"状态统计：{report['summary']['status_counts']}")

        for item in report["items"]:
            print(f"\n考纲条目 ID：{item['syllabus_item_id']}")
            print(f"覆盖状态：{item['status']}")
            print(f"判断理由：{item['reason']}")
            print(f"证据：{item['evidence']}")
            print(f"不确定原因：{item['uncertainty']}")

        print("\n真实 API 集成测试通过。")

    except Exception as exc:
        print("\n真实 API 集成测试失败。")
        print(f"错误类型：{type(exc).__name__}")
        print(f"错误信息：{exc}")
        raise


if __name__ == "__main__":
    main()
