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
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "zhipu").strip().lower() or "zhipu"

    CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "")
    BOSS_PHONE = os.getenv("BOSS_PHONE", "")
    BOSS_PASSWORD = os.getenv("BOSS_PASSWORD", "")
    CRAWL_DELAY = int(os.getenv("CRAWL_DELAY", "2"))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    BOSS_BASE_URL = "https://www.zhipin.com"

    @classmethod
    def get_browser_executable_path(cls) -> str:
        """返回显式配置的浏览器可执行文件路径。"""
        candidates = [
            os.getenv("BROWSER_EXECUTABLE_PATH", ""),
            os.getenv("CHROME_EXECUTABLE_PATH", ""),
            os.getenv("CHROMIUM_EXECUTABLE_PATH", ""),
            os.getenv("CHROMEDRIVER_PATH", ""),
        ]
        for value in candidates:
            path = (value or "").strip()
            if path:
                return str(Path(path).expanduser())
        return ""

    @classmethod
    def get_llm_api_key(cls, provider: str | None = None) -> str:
        """按提供方读取对应 API Key。"""
        normalized = (provider or cls.LLM_PROVIDER or "zhipu").strip().lower()
        if normalized == "deepseek":
            return cls.DEEPSEEK_API_KEY
        return cls.ZAI_API_KEY or cls.ZHIPUAI_API_KEY

    @classmethod
    def get_llm_provider(cls) -> str:
        """返回默认 LLM 提供方。"""
        return cls.LLM_PROVIDER if cls.LLM_PROVIDER in {"zhipu", "deepseek"} else "zhipu"

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
