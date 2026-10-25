import os
import platform


def skip_wmi_query(*args, **kwargs):
    raise OSError("Skip blocked Windows WMI query")


platform._wmi_query = skip_wmi_query

from openai import OpenAI

print("第 1 步：正在读取环境变量……", flush=True)
api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise RuntimeError("没有读取到 DEEPSEEK_API_KEY")

print("第 2 步：环境变量已读取，准备请求 API……", flush=True)

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
    timeout=15.0,
    max_retries=0,
)

print("第 3 步：正在等待 DeepSeek 返回……", flush=True)

try:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "请回复：API测试成功"}],
        max_tokens=30,
    )
    print("第 4 步：模型回复：", response.choices[0].message.content)

except Exception as e:
    print("请求失败：", type(e).__name__)
    print("错误信息：", str(e))