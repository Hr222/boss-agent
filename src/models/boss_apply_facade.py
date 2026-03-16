"""Boss 投递门面：给模型层提供统一的浏览器投递入口。"""

from src.infrastructure.browser.boss_apply import BossApplyClient, BossApplyOptions


class BossApplyFacade(BossApplyClient):
    """面向模型层的投递门面，屏蔽底层浏览器自动化细节。

    models 只依赖 facade，不直接依赖具体 chat/legacy 模板与 nodriver 页面交互。
    这样投递实现可以在 infrastructure 内部演进，而不用把变更扩散到用例层。
    """


__all__ = ["BossApplyFacade", "BossApplyOptions"]
