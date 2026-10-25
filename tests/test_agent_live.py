
from core.agent import run_agent


TEST_CASES = {
    "1": {
        "name": "查询课程列表",
        "question": "请列出 ExamMate 中已有的课程，并告诉我目前有多少门。",
    },
    "2": {
        "name": "查询考试列表",
        "question": "请列出 ExamMate 中已有的考试，并说明每场考试对应的课程。",
    },
    "3": {
        "name": "查询考试详情",
        "question": "请查看 ExamMate 中现有的第一场考试，并告诉我它的考试名称、所属课程和大纲信息。",
    },
    "4": {
        "name": "查询复习计划",
        "question": "请查询 ExamMate 中现有考试的复习计划。如果有多场考试，请先列出考试让我选择。",
    },
}


def main():
    print("ExamMate Agent 真实模型测试")
    print("-" * 40)

    for key, case in TEST_CASES.items():
        print(f"{key}. {case['name']}")

    choice = input("\n请选择测试场景（输入 1-4）：").strip()

    if choice not in TEST_CASES:
        print("无效选项，请输入 1-4。")
        return

    case = TEST_CASES[choice]
    question = case["question"]

    print(f"\n测试场景：{case['name']}")
    print(f"用户：{question}")
    print("\nAgent：")

    try:
        answer = run_agent(question)
        print(answer)
    except Exception as exc:
        print(f"测试调用失败：{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
