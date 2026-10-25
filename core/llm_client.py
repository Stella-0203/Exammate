import platform
import sys

from core.config import BASE_URL, MODEL_NAME, get_api_key


# 兼容当前 Windows 环境中已发现的 WMI 查询问题。
# 必须在导入 OpenAI SDK 之前设置。
if sys.platform == "win32":
    def skip_wmi_query(*args, **kwargs):
        raise OSError("Skip blocked Windows WMI query")

    platform._wmi_query = skip_wmi_query


from openai import OpenAI


_client = None


def get_client() -> OpenAI:
    """获取统一的 DeepSeek API 客户端，首次调用时才初始化。"""
    global _client

    if _client is None:
        _client = OpenAI(
            api_key=get_api_key(),
            base_url=BASE_URL,
            timeout=30.0,
            max_retries=1,
        )

    return _client

"""
def chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
) -> str:
"""

def chat_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.2,
    response_format: dict | None = None,
) -> str:


    """
    发送对话请求，返回模型生成的文本。

    messages 示例：
    [
        {"role": "system", "content": "你是一个学习助手。"},
        {"role": "user", "content": "请解释什么是栈。"}
    ]
    """
    client = get_client()

    try:
        request_args = {
            "model": model or MODEL_NAME,
            "messages": messages,
            "temperature": temperature,
        }

        if response_format is not None:
            request_args["response_format"] = response_format

        response = client.chat.completions.create(**request_args)
        """
        response = client.chat.completions.create(
            model=model or MODEL_NAME,
            messages=messages,
            temperature=temperature,
        )
        """
        content = response.choices[0].message.content

        if not content:
            raise RuntimeError("模型返回了空内容。")

        return content

    except RuntimeError:
        raise
    except Exception as exc:
        # 不输出 API Key 或请求头等敏感信息。
        raise RuntimeError(
            f"DeepSeek API 调用失败，错误类型：{type(exc).__name__}。"
            "请检查网络、API 配置或服务状态。"
        ) from exc