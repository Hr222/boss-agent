"""Boss 直聘投递自动化子包。"""

from .client import BossApplyClient, BossApplyOptions
from .router import BossApplyTemplateRouter
from .strategy import BossApplyStrategy
from .types import ApplyJobResult, PreparedChatTab, TemplateType

__all__ = [
    "ApplyJobResult",
    "BossApplyClient",
    "BossApplyOptions",
    "BossApplyTemplateRouter",
    "BossApplyStrategy",
    "PreparedChatTab",
    "TemplateType",
]
