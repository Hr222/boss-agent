"""MVC model export: Boss browser automation."""

from src.infrastructure.browser.boss_apply_client import BossApplyClient, BossApplyOptions


class BossApplyBrowserModel(BossApplyClient):
    """MVC-friendly alias for Boss browser automation."""


__all__ = ["BossApplyBrowserModel", "BossApplyOptions"]
