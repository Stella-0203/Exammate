
from services.syllabus_service import (
    parse_syllabus_text,
    generate_syllabus_suggestions,
)


def main() -> None:
    syllabus_text = """
    1. 线性表的基本概念与存储结构
    2. 掌握栈和队列的基本操作
    3. 熟悉图的遍历算法，理解 BFS 和 DFS 的区别
    """

    source_items = parse_syllabus_text(syllabus_text)

    print("原始考纲解析完成，共", len(source_items), "条。")
    print("正在调用 DeepSeek 生成候选展开项，请稍候...\n")

    suggestions = generate_syllabus_suggestions(source_items)

    print("候选项生成与校验：通过")
    print("候选展开项数量：", len(suggestions))

    for item in suggestions:
        print("-" * 50)
        print("对应原始条目序号：", item["source_sort_order"])
        print("候选内容：", item["content"])
        print("类型：", item["item_type"])
        print("来源：", item["origin"])
        print("审核状态：", item["review_status"])
        print("推断依据：", item["rationale"])


if __name__ == "__main__":
    main()
