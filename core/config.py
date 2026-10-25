import os
from pathlib import Path


# 项目根目录：ExamMate/
BASE_DIR = Path(__file__).resolve().parent.parent

# 本地数据目录
DATA_DIR = BASE_DIR / "data"

# 学习资料原始文件存储目录
MATERIALS_DIR = DATA_DIR / "materials"

# SQLite 数据库文件
#DB_PATH = DATA_DIR / "exammate.db"
# SQLite 数据库文件。默认使用正式数据库；测试时可通过环境变量覆盖。
DB_PATH = Path(
    os.getenv("EXAMMATE_DB_PATH", str(DATA_DIR / "exammate.db"))
).resolve()

# DeepSeek API 配置
API_KEY_ENV_NAME = "DEEPSEEK_API_KEY"
BASE_URL = "https://api.deepseek.com"
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def get_api_key() -> str:
    """从系统环境变量读取 API Key，不在代码中保存密钥。"""
    api_key = os.getenv(API_KEY_ENV_NAME)

    if not api_key:
        raise RuntimeError(
            f"未找到环境变量 {API_KEY_ENV_NAME}，"
            "请检查 Windows 用户环境变量配置。"
        )

    return api_key