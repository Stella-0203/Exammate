
from services.syllabus_service import parse_syllabus_text


def test_numbered_items():
    text = """
    1. 线性表的基本概念与存储结构
    2. 掌握栈和队列的基本操作
    3. 熟悉图的遍历算法
    """

    items = parse_syllabus_text(text)

    assert len(items) == 3
    assert items[0]["content"].startswith("1.")
    assert items[1]["content"].startswith("2.")
    assert items[2]["content"].startswith("3.")
    assert [item["sort_order"] for item in items] == [1, 2, 3]


def test_chinese_numbering():
    text = """
    一、线性表
    二、栈和队列
    三、图的遍历
    """

    items = parse_syllabus_text(text)

    assert len(items) == 3
    assert items[0]["content"] == "一、线性表"
    assert items[2]["content"] == "三、图的遍历"


def test_wrapped_item():
    text = """
    1. 熟悉图的遍历算法
       理解 BFS 和 DFS 的区别
    2. 掌握最短路径算法
    """

    items = parse_syllabus_text(text)

    assert len(items) == 2
    assert "理解 BFS 和 DFS 的区别" in items[0]["content"]


def test_unmarked_lines():
    text = """
    线性表的基本概念
    栈和队列的基本操作
    图的遍历算法
    """

    items = parse_syllabus_text(text)

    assert len(items) == 3
    assert items[1]["content"] == "栈和队列的基本操作"


def test_empty_input():
    try:
        parse_syllabus_text("  \n  ")
    except ValueError:
        pass
    else:
        raise AssertionError("空考纲应该触发 ValueError")


def main():
    test_numbered_items()
    test_chinese_numbering()
    test_wrapped_item()
    test_unmarked_lines()
    test_empty_input()

    print("数字编号解析：通过")
    print("中文编号解析：通过")
    print("续行合并：通过")
    print("无编号文本解析：通过")
    print("空输入校验：通过")


if __name__ == "__main__":
    main()
