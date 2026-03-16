"""Boss 投递模板策略接口。"""

from typing import Protocol


class BossApplyStrategy(Protocol):
    async def is_ready(self, tab) -> bool: ...

    async def send_greeting(
        self,
        tab,
        greeting: str,
        *,
        debug: bool,
        dry_run: bool,
        fill_only: bool,
    ) -> bool: ...

    async def dump_page_if_needed(self, tab, prefix: str, debug: bool) -> None: ...
