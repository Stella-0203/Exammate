
import os
import json
import platform

# 兼容当前 Windows WMI 查询卡住的问题
# 必须在导入 OpenAI SDK 之前设置
def skip_wmi_query(*args, **kwargs):
    raise OSError("Skip blocked Windows WMI query")


platform._wmi_query = skip_wmi_query

from openai import OpenAI


# 1. 定义我们期望模型生成的数据结构
def validate_study_plan(data: dict) -> None:
    """检查复习计划的必要字段、类型和基本约束。"""

    if not isinstance(data, dict):
        raise ValueError("输出必须是 JSON 对象")

    required_fields = {"course", "total_days", "tasks"}
    missing_fields = required_fields - data.keys()

    if missing_fields:
        raise ValueError(f"缺少必要字段：{missing_fields}")

    if not isinstance(data["course"], str) or not data["course"].strip():
        raise ValueError("course 必须是非空字符串")

    if type(data["total_days"]) is not int or data["total_days"] <= 0:
        raise ValueError("total_days 必须是正整数")

    if not isinstance(data["tasks"], list) or not data["tasks"]:
        raise ValueError("tasks 必须是非空列表")

    for index, task in enumerate(data["tasks"], start=1):
        if not isinstance(task, dict):
            raise ValueError(f"第 {index} 项任务必须是对象")

        required_task_fields = {
            "day",
            "topic",
            "priority",
            "estimated_minutes",
        }
        missing = required_task_fields - task.keys()

        if missing:
            raise ValueError(f"第 {index} 项任务缺少字段：{missing}")

        if type(task["day"]) is not int:
            raise ValueError(f"第 {index} 项任务的 day 必须是整数")

        if not 1 <= task["day"] <= data["total_days"]:
            raise ValueError(f"第 {index} 项任务的 day 超出复习天数范围")

        if not isinstance(task["topic"], str) or not task["topic"].strip():
            raise ValueError(f"第 {index} 项任务的 topic 必须是非空字符串")

        if task["priority"] not in {"high", "medium", "low"}:
            raise ValueError(f"第 {index} 项任务的 priority 不合法")

        if (
            type(task["estimated_minutes"]) is not int
            or task["estimated_minutes"] <= 0
        ):
            raise ValueError(
                f"第 {index} 项任务的 estimated_minutes 必须是正整数"
            )


def main():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("没有读取到 DEEPSEEK_API_KEY")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=30.0,
        max_retries=0,
    )

    try:
        print("第 1 步：请求模型生成复习计划……", flush=True)

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
            {
                    "role": "system",
                    "content": (
                        "你是 ExamMate 的复习计划生成模块。"
                        "请根据用户要求生成合理的复习计划。"
                        "只输出 JSON 对象，不要输出 Markdown 代码块或额外解释。"
                        "顶层字段必须是 course、total_days、tasks。"
                        "每项 task 必须包含 day、topic、priority、estimated_minutes。"
                        "priority 只能是 high、medium、low。"
                        "所有字段类型必须正确，任务天数不能超过 total_days。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "为数据结构课程制定一个 7 天复习计划。"
                        "覆盖线性表、树与二叉树、图、排序与查找。"
                        "每天安排 1 到 3 项任务，预计每项任务耗时 20 到 90 分钟。"
                        "优先级请根据复习重要程度合理设置。"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=1200,
        )

        content = response.choices[0].message.content

        if not content:
            raise ValueError("模型没有返回内容")

        print("\n第 2 步：模型原始输出：")
        print(content)

        print("\n第 3 步：解析 JSON……")
        data = json.loads(content)

        print("JSON 解析成功！")

        print("\n第 4 步：检查数据结构……")
        validate_study_plan(data)

        print("结构校验成功！")

        print("\n第 5 步：展示解析后的结果")
        print(f"课程：{data['course']}")
        print(f"总复习天数：{data['total_days']}")

        for task in data["tasks"]:
            print(
                f"第 {task['day']} 天 | "
                f"{task['topic']} | "
                f"优先级：{task['priority']} | "
                f"预计：{task['estimated_minutes']} 分钟"
            )

        print("\n结构化输出测试通过！")

    except json.JSONDecodeError as e:
        print("\n测试失败：模型返回的内容不是合法 JSON。")
        print("错误信息：", e)

    except ValueError as e:
        print("\n测试失败：JSON 数据不符合预期结构。")
        print("错误信息：", e)

    finally:
        client.close()


if __name__ == "__main__":
    main()
