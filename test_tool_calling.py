
import os
import json
import platform

# 兼容当前电脑的 WMI 查询卡住问题。
# 必须在导入 OpenAI SDK 之前设置。
def skip_wmi_query(*args, **kwargs):
    raise OSError("Skip blocked Windows WMI query")


platform._wmi_query = skip_wmi_query

from openai import OpenAI


# 1. 定义一个供模型调用的 Python 工具
def get_course_info(course_name: str) -> dict:
    """查询课程信息。这里用本地模拟数据验证工具调用流程。"""

    course_database = {
        "数据结构": {
            "course": "数据结构",
            "topics": ["线性表", "树与二叉树", "图", "排序与查找"],
            "exam_format": "笔试",
            "suggested_review_days": 7,
        },
        "操作系统": {
            "course": "操作系统",
            "topics": ["进程管理", "内存管理", "文件系统", "设备管理"],
            "exam_format": "笔试",
            "suggested_review_days": 5,
        },
    }

    result = course_database.get(course_name)

    if result is None:
        return {
            "error": f"暂时没有找到课程“{course_name}”的信息"
        }

    return result


# 2. 向模型声明可用工具及其参数
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_course_info",
            "description": (
                "查询指定课程的考点、考试形式和建议复习天数。"
                "当用户询问课程考点或复习安排时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_name": {
                        "type": "string",
                        "description": "课程名称，例如数据结构、操作系统",
                    }
                },
                "required": ["course_name"],
                "additionalProperties": False,
            },
        },
    }
]


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
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 ExamMate 学习助手。"
                    "用户询问课程考点或复习安排时，"
                    "应先调用课程信息工具获取信息，再回答用户。"
                ),
            },
            {
                "role": "user",
                "content": "请查询数据结构的考点和建议复习天数，并帮我总结。",
            },
        ]

        # 3. 第一次请求：让模型自行判断是否调用工具
        print("第 1 步：正在请求模型判断是否需要调用工具……", flush=True)

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=300,
        )

        assistant_message = response.choices[0].message
        print("模型结束原因：", response.choices[0].finish_reason)

        # 保存模型的工具调用请求，后续需要把它发回去
        messages.append(
            assistant_message.model_dump(exclude_none=True)
        )

        if not assistant_message.tool_calls:
            print("模型没有调用工具，返回内容：")
            print(assistant_message.content)
            return

        # 4. Python 接收并执行模型选择的工具
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            print(f"\n第 2 步：模型请求调用工具 {tool_name}")

            if tool_name != "get_course_info":
                raise ValueError(f"不允许调用未知工具：{tool_name}")

            arguments = json.loads(tool_call.function.arguments)
            course_name = arguments.get("course_name")

            if not isinstance(course_name, str):
                raise ValueError("course_name 参数必须是字符串")

            print("工具参数：", arguments)

            tool_result = get_course_info(course_name)
            print("工具执行结果：")
            print(json.dumps(tool_result, ensure_ascii=False, indent=2))

            # 5. 把工具执行结果交还模型
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        tool_result, ensure_ascii=False
                    ),
                }
            )

        print("\n第 3 步：正在把工具结果交还模型……", flush=True)

        # 6. 模型根据真实工具结果生成最终回答
        final_response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="none",
            max_tokens=300,
        )

        print("\n第 4 步：模型最终回答：")
        print(final_response.choices[0].message.content)

        print("\nTool Calling 测试完成。")

    finally:
        client.close()


if __name__ == "__main__":
    main()
