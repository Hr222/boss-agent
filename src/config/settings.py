"""项目配置定义。"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    """集中维护项目运行时配置。"""

    BASE_DIR = Path(__file__).resolve().parents[2]
    DATA_DIR = BASE_DIR / "data"
    RESUME_FILE = DATA_DIR / "resume.json"

    ZAI_API_KEY = os.getenv("ZAI_API_KEY", "")
    ZHIPUAI_API_KEY = os.getenv("ZHIPUAI_API_KEY", "")
    ZAI_BASE_URL = os.getenv("ZAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")

    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "")
    BOSS_PHONE = os.getenv("BOSS_PHONE", "")
    BOSS_PASSWORD = os.getenv("BOSS_PASSWORD", "")
    CRAWL_DELAY = int(os.getenv("CRAWL_DELAY", "2"))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    BOSS_BASE_URL = "https://www.zhipin.com"

    @classmethod
    def get_llm_api_key(cls) -> str:
        """优先读取新变量名，兼容旧变量名。"""
        return cls.ZAI_API_KEY or cls.ZHIPUAI_API_KEY

    @classmethod
    def ensure_dirs(cls) -> None:
        """保证运行过程中需要的数据目录存在。"""
        cls.DATA_DIR.mkdir(exist_ok=True)

    @classmethod
    def resolve_project_path(cls, path: str | Path) -> Path:
        """把相对路径统一解析到项目根目录，避免从 src 启动时写到 src/ 下。"""
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (cls.BASE_DIR / candidate).resolve()
