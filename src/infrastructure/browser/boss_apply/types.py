"""Boss 投递流程共享类型与常量。"""

import os
from dataclasses import dataclass
from typing import Literal


DETAIL_READY_TIMEOUT_SEC = float(os.getenv("BOSS_DETAIL_READY_TIMEOUT_SEC", "1"))
CHAT_READY_TIMEOUT_SEC = float(os.getenv("BOSS_CHAT_READY_TIMEOUT_SEC", "1"))
CHAT_TARGET_TIMEOUT_SEC = float(os.getenv("BOSS_CHAT_TARGET_TIMEOUT_SEC", "1"))
TemplateType = Literal["chat", "legacy"]


@dataclass(frozen=True)
class PreparedChatTab:
    tab: object
    template_type: TemplateType
    ready: bool


@dataclass(frozen=True)
class ApplyJobResult:
    """单个岗位投递结果。"""

    status: str
    job_url: str
    reason: str | None = None
