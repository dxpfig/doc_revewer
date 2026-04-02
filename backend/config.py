import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
STANDARDS_DIR = DATA_DIR / "standards"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
STANDARDS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/doc_revewer.db"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_EMB_PROVIDER = "openai"

# Kimi OCR 配置 (从环境变量读取)
KIMI_API_KEY = os.getenv("KIMI_API_KEY")
if not KIMI_API_KEY:
    raise ValueError("环境变量 KIMI_API_KEY 未设置，请设置后再运行")

KIMI_VISION_MODEL = os.getenv("KIMI_VISION_MODEL", "moonshot-v1-8k-vision-preview")
KIMI_TEXT_MODEL = os.getenv("KIMI_TEXT_MODEL", "moonshot-v1-8k")