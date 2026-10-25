
import os

api_key = os.getenv("DEEPSEEK_API_KEY")

if api_key:
    print("API Key 环境变量读取成功！")
else:
    print("没有读取到 API Key，请检查环境变量设置。")
