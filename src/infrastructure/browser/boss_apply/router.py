"""Boss 投递模板路由。"""

from dataclasses import dataclass

from src.infrastructure.browser.boss_apply.types import TemplateType


@dataclass(frozen=True)
class BossApplyTemplateRouter:
    """根据当前页面状态解析应使用的发送模板。"""

    def resolve(self, tab) -> TemplateType:
        current_url = str(getattr(tab, "url", "") or "")
        if "/web/geek/chat" in current_url or "/chat?" in current_url:
            return "chat"
        return "legacy"
