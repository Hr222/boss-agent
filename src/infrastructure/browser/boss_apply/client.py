"""Boss 直聘投递客户端：封装 nodriver 页面交互。"""

import asyncio
import html
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from src.config.settings import Config
from src.infrastructure.browser.boss_apply.chat_template import BossApplyChatTemplate
from src.infrastructure.browser.boss_apply.legacy_template import BossApplyLegacyTemplate
from src.infrastructure.browser.boss_apply.router import BossApplyTemplateRouter
from src.infrastructure.browser.boss_apply.strategy import BossApplyStrategy
from src.infrastructure.browser.boss_apply.types import (
    ApplyJobResult,
    CHAT_READY_TIMEOUT_SEC,
    CHAT_TARGET_TIMEOUT_SEC,
    DETAIL_READY_TIMEOUT_SEC,
    PreparedChatTab,
    TemplateType,
)
from src.infrastructure.browser.nodriver_runtime import _env_bool, _import_nodriver
from src.models.greeting_archive_model import GreetingArchiveModel


ORIGIN = "https://www.zhipin.com"
CHAT_NOT_READY_EXTRA_WAIT_SEC = float(os.getenv("BOSS_CHAT_NOT_READY_EXTRA_WAIT_SEC", "3"))


@dataclass(frozen=True)
class BossApplyOptions:
    require_login: bool = False
    dry_run: bool = False
    fill_only: bool = False
    no_close_tab: bool = False
    greetings_dir: str = "data/greetings"
    job_url: str | None = None
    greeting_file: str | None = None
    greeting_text: str | None = None
    debug: bool = False
    target_apply_count: int | None = None
    apply_retries: int = 2
    max_apply_failures: int = 3


class BossApplyClient:
    """负责打开岗位详情页并发送招呼语。"""

    def __init__(self) -> None:
        self.uc = _import_nodriver()
        self.archive_model = GreetingArchiveModel()
        self.template_router = BossApplyTemplateRouter()
        self.template_strategies: dict[TemplateType, BossApplyStrategy] = {
            "chat": BossApplyChatTemplate(self.uc, chat_debug_enabled=self._chat_debug_enabled),
            "legacy": BossApplyLegacyTemplate(),
        }

    @staticmethod
    def _chat_debug_enabled(debug: bool) -> bool:
        """聊天页专项调试开关，避免普通 debug 时输出过多细节。"""
        return bool(debug) and _env_bool("BOSS_CHAT_DEBUG", False)

    async def apply_jobs(
        self,
        queue: list[dict],
        *,
        mark_applied,
        mark_apply_skipped=None,
        mark_apply_failed=None,
        options: BossApplyOptions,
        browser=None,
    ) -> list[ApplyJobResult]:
        """执行岗位投递或预览填充。"""
        # 这里只负责浏览器自动化，不做岗位是否适合的业务判断。
        owns_browser = browser is None
        if owns_browser:
            browser = await self._start_browser()
            bootstrap_tab = await browser.get(ORIGIN, new_window=_env_bool("BOSS_NEW_WINDOW", False))
            await bootstrap_tab
            print(f"✓ 已打开: {bootstrap_tab.url}")

            if options.require_login:
                print(">>> 浏览器已打开，请先手动完成登录。")
                await self._ensure_manual_login(bootstrap_tab, debug=options.debug)

        results: list[ApplyJobResult] = []
        greetings_dir = Config.resolve_project_path(options.greetings_dir)
        sent_count = 0
        target_apply_count = options.target_apply_count

        if not queue:
            print("No jobs to apply (need is_suitable=1 and is_applied is NULL/0).")
        else:
            for row in queue:
                result = await self._apply_single_job(
                    browser,
                    row,
                    greetings_dir=greetings_dir,
                    mark_applied=mark_applied,
                    mark_apply_skipped=mark_apply_skipped,
                    mark_apply_failed=mark_apply_failed,
                    options=options,
                )
                results.append(result)
                if result.status == "ok":
                    sent_count += 1
                if target_apply_count and sent_count >= target_apply_count:
                    print(f">>> 已达到本轮目标：实际发送 {sent_count} 个岗位。")
                    break

        # 主线路批量投递完成后直接结束，避免一直挂起等待人工中断。
        processed_count = len(results)
        success_count = sum(1 for item in results if item.status == "ok")
        already_contacted_count = sum(1 for item in results if item.reason == "already_contacted")
        skipped_count = sum(
            1 for item in results if item.status == "skipped" and item.reason != "already_contacted"
        )
        failed_count = sum(1 for item in results if item.status == "failed")
        print(
            f">>> 本轮处理结束，共处理 {processed_count} 个岗位："
            f"成功处理 {success_count}，其中实际发送 {sent_count}，"
            f"继续沟通/已沟通 {already_contacted_count}，跳过 {skipped_count}，失败 {failed_count}。"
        )

        keep_browser_open = bool(options.job_url or options.fill_only or options.dry_run or options.no_close_tab)
        if not owns_browser:
            return results
        if keep_browser_open:
            print(">>> 当前为调试/单岗位模式，浏览器保持打开。")
            try:
                while True:
                    proc = getattr(browser, "_process", None)
                    if proc is not None and getattr(proc, "returncode", None) is not None:
                        break
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                pass
            return results

        await self._safe_close_browser(browser, debug=options.debug)
        return results

    async def _apply_single_job(
        self,
        browser,
        row: dict,
        *,
        greetings_dir: Path,
        mark_applied,
        mark_apply_skipped,
        mark_apply_failed,
        options: BossApplyOptions,
    ) -> ApplyJobResult:
        """处理单个岗位的详情打开、沟通按钮点击和消息发送。"""
        job_url = str(row.get("job_url") or "").strip()
        if not job_url:
            return ApplyJobResult(status="skipped", reason="missing_job_url", job_url="")

        open_url = job_url if job_url.startswith("http") else urljoin(ORIGIN, job_url)
        if not open_url:
            return ApplyJobResult(status="skipped", reason="invalid_job_url", job_url=job_url)

        raw_json = row.get("raw_json")
        greeting = self._resolve_greeting(open_url, raw_json, greetings_dir, options)
        if not greeting:
            print(f"跳过（无招呼语）: {open_url}")
            if callable(mark_apply_skipped) and not options.dry_run and not options.fill_only and not options.job_url:
                mark_apply_skipped(job_url, "missing_greeting")
            return ApplyJobResult(status="skipped", reason="missing_greeting", job_url=open_url)

        print(f"\n[apply] {open_url}")
        # 记录当前已有 target，便于识别“立即沟通”后是否新开了聊天 target。
        known_target_ids = {
            str(getattr(candidate, "target_id", "") or "")
            for candidate in getattr(browser, "tabs", [])
        }
        job_tab = await self._open_job_tab(browser, open_url, debug=options.debug)

        # 已沟通过的岗位直接跳过，避免重复触达。
        already_contacted = await self._detect_existing_contact(job_tab, debug=options.debug)
        if already_contacted and not options.job_url:
            print("跳过发送（检测到已沟通/继续沟通状态），已标记为已处理")
            if not options.dry_run:
                mark_applied(job_url)
            if not options.no_close_tab:
                await self._safe_close_tab(job_tab)
            return ApplyJobResult(status="skipped", reason="already_contacted", job_url=open_url)

        # 详情页和聊天页之间可能会跳 target，这里统一做收敛。
        prepared_chat = await self._prepare_chat_tab(browser, job_tab, known_target_ids, debug=options.debug)
        job_tab = prepared_chat.tab
        if prepared_chat.template_type == "chat" and not prepared_chat.ready:
            if options.debug:
                print(
                    f"[debug] chat 页首次未 ready，追加等待 {CHAT_NOT_READY_EXTRA_WAIT_SEC:.1f}s 后再尝试进入输入态"
                )
            try:
                await job_tab.sleep(CHAT_NOT_READY_EXTRA_WAIT_SEC)
            except Exception:
                pass
            extra_ready = await self._wait_for_chat_ready(
                job_tab,
                debug=options.debug,
                timeout_sec=max(CHAT_NOT_READY_EXTRA_WAIT_SEC, 2.0),
            )
            prepared_chat = PreparedChatTab(
                tab=job_tab,
                template_type=self._resolve_chat_template_type(job_tab),
                ready=extra_ready,
            )
        # chat 页一旦触发发送动作，重复重试更容易造成重复消息，因此只做单次尝试。
        retry_attempts = 1 if prepared_chat.template_type == "chat" else (max(int(options.apply_retries), 0) + 1)
        ok = False
        failure_reason = "send_failed"
        for attempt_index in range(retry_attempts):
            ok = await self._send_greeting(
                job_tab,
                greeting,
                template_type=prepared_chat.template_type,
                debug=options.debug,
                dry_run=options.dry_run,
                fill_only=options.fill_only,
            )
            if ok:
                break
            if options.debug:
                print(f"[debug] 第 {attempt_index + 1}/{retry_attempts} 次发送失败。")
            if attempt_index >= retry_attempts - 1:
                break
            try:
                await job_tab.sleep(0.6)
            except Exception:
                pass

        if ok:
            if options.dry_run:
                print("✓ dry-run OK")
            elif options.fill_only:
                print("✓ 已填充到输入框（未发送）")
            else:
                print("✓ 已发送")
                try:
                    archive_path = self.archive_model.write_archive(greetings_dir, row, greeting)
                    if options.debug:
                        print(f"[debug] 已归档发送记录: {archive_path}")
                except Exception as error:
                    if options.debug:
                        print(f"[debug] 归档发送记录失败: {error}")
            if not options.dry_run and not options.fill_only and not options.job_url:
                mark_applied(job_url)
            status = "ok"
        else:
            print("✗ 发送失败（或未找到输入框）")
            failure_count = 0
            if callable(mark_apply_failed) and not options.dry_run and not options.fill_only:
                failure_count = mark_apply_failed(job_url, failure_reason)
                if failure_count >= max(int(options.max_apply_failures), 1):
                    print(
                        f"[apply] 岗位累计失败 {failure_count} 次，"
                        f"已达到上限，后续自动投递将跳过该岗位。"
                    )
            status = "failed"

        if not options.no_close_tab:
            await self._safe_close_tab(job_tab)
        return ApplyJobResult(status=status, job_url=open_url)

    async def _start_browser(self):
        """按项目约定启动带用户数据目录的 Chrome 实例。"""
        user_data_dir = os.getenv("BOSS_USER_DATA_DIR", ".nodriver_user_data/boss")
        headless = _env_bool("BOSS_HEADLESS", False)
        disable_extensions = _env_bool("BOSS_DISABLE_EXTENSIONS", True)

        profile_dir = Config.resolve_project_path(user_data_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)

        browser_args = ["--disable-dev-shm-usage", "--no-first-run", "--no-default-browser-check"]
        if disable_extensions:
            browser_args += ["--disable-extensions", "--disable-component-extensions-with-background-pages"]
        browser_executable_path = Config.get_browser_executable_path()

        return await self.uc.start(
            headless=headless,
            user_data_dir=str(profile_dir),
            browser_args=browser_args,
            browser_executable_path=browser_executable_path or None,
        )

    def _resolve_greeting(
        self,
        job_url: str,
        raw_json: str | None,
        greetings_dir: Path,
        options: BossApplyOptions,
    ) -> str:
        """按优先级解析招呼语来源：直接文本 > 文件 > DB raw_json > 本地目录文件。"""
        greeting = (options.greeting_text or "").strip()
        if greeting:
            return greeting
        if options.greeting_file:
            try:
                return Config.resolve_project_path(options.greeting_file).read_text(encoding="utf-8").strip()
            except Exception:
                return ""
        greeting = self._load_greeting_from_raw(raw_json)
        if greeting:
            return greeting
        return self._load_greeting_from_file(greetings_dir, job_url)

    @staticmethod
    def _parse_job_id(job_url: str) -> str:
        match = re.search(r"/job_detail/([^/?]+)\.html", job_url)
        return match.group(1) if match else re.sub(r"[^a-zA-Z0-9_\-]+", "_", job_url)[:80]

    def _load_greeting_from_raw(self, raw_json: str | None) -> str:
        if not raw_json:
            return ""
        try:
            data = json.loads(raw_json) or {}
        except Exception:
            return ""
        value = data.get("greeting_message")
        return (str(value) if value is not None else "").strip()

    def _load_greeting_from_file(self, greetings_dir: Path, job_url: str) -> str:
        job_id = self._parse_job_id(job_url)
        for candidate in [greetings_dir / f"{job_id}.txt", greetings_dir / f"{job_id}.md"]:
            if candidate.exists():
                try:
                    return candidate.read_text(encoding="utf-8").strip()
                except Exception:
                    return ""
        return ""

    async def _click_start_chat(self, tab, debug: bool) -> bool:
        """优先按文本查找“立即沟通”，再回退到通用选择器。"""
        for text in ["立即沟通", "继续沟通", "去沟通", "聊一聊"]:
            try:
                el = await tab.find(text, best_match=True, timeout=6)
                if el:
                    try:
                        await el.apply("(e) => e.scrollIntoView({block: 'center'})")
                    except Exception:
                        pass
                    try:
                        await el.click()
                    except Exception:
                        await el.apply("(e) => e.click()")
                    await tab.sleep(0.25)
                    return True
            except Exception as e:
                if debug:
                    print(f"[debug] 点击「{text}」失败: {e}")

        for selector in ["a[href*='chat']", "button", "a", ".op-btn", ".btn"]:
            try:
                el = await tab.select(selector, timeout=2)
                if not el:
                    continue
                text = await el.apply("(e) => (e.innerText || e.textContent || '').trim()")
                if any(keyword in str(text) for keyword in ["立即沟通", "继续沟通", "去沟通", "聊一聊"]):
                    try:
                        await el.apply("(e) => e.scrollIntoView({block: 'center'})")
                    except Exception:
                        pass
                    try:
                        await el.click()
                    except Exception:
                        await el.apply("(e) => e.click()")
                    await tab.sleep(0.25)
                    return True
            except Exception:
                continue
        return False

    async def _detect_existing_contact(self, tab, debug: bool) -> bool:
        """检测岗位是否已经处于已沟通/继续沟通状态。"""
        for text in ["继续沟通", "已沟通", "继续聊天"]:
            try:
                el = await tab.find(text, best_match=True, timeout=2)
                if el:
                    if debug:
                        print(f"[debug] 检测到已沟通状态文案: {text}")
                    return True
            except Exception:
                continue
        return False

    def _resolve_chat_template_type(self, tab) -> TemplateType:
        """通过模板路由器解析当前页面应使用的发送模板。"""
        return self.template_router.resolve(tab)

    async def _wait_for_detail_ready(self, tab, debug: bool, timeout_sec: float = DETAIL_READY_TIMEOUT_SEC) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout_sec
        selectors = [".job-detail-box", ".job-detail", ".job-banner", ".job-info", "main"]
        while asyncio.get_running_loop().time() < deadline:
            current_url = str(getattr(tab, "url", "") or "")
            if debug and current_url:
                print(f"[debug] detail wait url -> {current_url}")
            for selector in selectors:
                try:
                    if await tab.select(selector, timeout=1):
                        return True
                except Exception:
                    continue
            await tab.sleep(POLL_INTERVAL_SEC)
        return False

    async def _open_job_tab(self, browser, open_url: str, debug: bool):
        job_tab = await browser.get(open_url, new_tab=True, new_window=False)
        await job_tab
        try:
            await job_tab.get(open_url)
            await job_tab
        except Exception as e:
            if debug:
                print(f"[debug] 新标签页二次导航失败: {e}")
        return job_tab

    async def _wait_for_chat_ready(self, tab, debug: bool, timeout_sec: float = CHAT_READY_TIMEOUT_SEC) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout_sec
        last_url = ""
        while asyncio.get_running_loop().time() < deadline:
            try:
                await tab
            except Exception:
                pass
            current_url = str(getattr(tab, "url", "") or "")
            if debug and current_url and current_url != last_url:
                print(f"[debug] chat wait url -> {current_url}")
                last_url = current_url
            template_type = self._resolve_chat_template_type(tab)
            strategy = self.template_strategies[template_type]
            if await strategy.is_ready(tab):
                return True
            await tab.sleep(float(os.getenv("BOSS_POLL_INTERVAL_SEC", "0.03")))
        return False

    async def _wait_for_same_tab_chat_redirect(self, tab, debug: bool, timeout_sec: float = CHAT_TARGET_TIMEOUT_SEC) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            try:
                await tab
            except Exception:
                pass
            current_url = str(getattr(tab, "url", "") or "")
            if self.template_router.resolve(tab) == "chat":
                if self._chat_debug_enabled(debug):
                    print(f"[debug] current tab redirected to chat -> {current_url}")
                await self.template_strategies["chat"].dump_page_if_needed(
                    tab,
                    prefix="boss_chat_same_tab",
                    debug=debug,
                )
                return True
            await asyncio.sleep(float(os.getenv("BOSS_POLL_INTERVAL_SEC", "0.03")))
        return False

    async def _wait_for_chat_target(self, browser, known_target_ids: set[str], debug: bool, timeout_sec: float = CHAT_TARGET_TIMEOUT_SEC):
        deadline = asyncio.get_running_loop().time() + timeout_sec
        while asyncio.get_running_loop().time() < deadline:
            try:
                await browser
            except Exception:
                pass
            for candidate in getattr(browser, "tabs", []):
                target_id = str(getattr(candidate, "target_id", "") or "")
                if not target_id or target_id in known_target_ids:
                    continue
                candidate_url = str(getattr(candidate, "url", "") or "")
                if self._chat_debug_enabled(debug):
                    print(f"[debug] new target detected -> {candidate_url or target_id}")
                await self.template_strategies["chat"].dump_page_if_needed(
                    candidate,
                    prefix="boss_chat_new_target",
                    debug=debug,
                )
                return candidate
            await asyncio.sleep(float(os.getenv("BOSS_POLL_INTERVAL_SEC", "0.03")))
        return None
    @staticmethod
    def _normalize_greeting_for_chat(greeting: str) -> str:
        """把易被聊天富文本错误展示的 ASCII 箭头替换成稳定字符。"""
        normalized = html.unescape(greeting or "")
        replacements = {
            "->": "→",
            "<-": "←",
            "=>": "⇒",
            "<=": "⇐",
        }
        for raw, target in replacements.items():
            normalized = normalized.replace(raw, target)
        return normalized

    async def _send_greeting(
        self,
        tab,
        greeting: str,
        *,
        template_type: TemplateType | None = None,
        debug: bool,
        dry_run: bool,
        fill_only: bool,
    ) -> bool:
        greeting = self._normalize_greeting_for_chat(greeting)
        if not greeting.strip():
            return False
        resolved_template_type = template_type or self._resolve_chat_template_type(tab)
        if self._chat_debug_enabled(debug):
            print(f"[debug] 当前发送模板: {resolved_template_type}")
        strategy = self.template_strategies[resolved_template_type]
        return await strategy.send_greeting(
            tab,
            greeting,
            debug=debug,
            dry_run=dry_run,
            fill_only=fill_only,
        )

    async def _prepare_chat_tab(self, browser, job_tab, known_target_ids: set[str], debug: bool) -> PreparedChatTab:
        clicked = await self._click_start_chat(job_tab, debug=debug)
        if not clicked:
            detail_ready = await self._wait_for_detail_ready(job_tab, debug=debug, timeout_sec=DETAIL_READY_TIMEOUT_SEC)
            if debug and not detail_ready:
                print("[debug] 在等待时间内未检测到岗位详情主体区域")
            clicked = await self._click_start_chat(job_tab, debug=debug)
        if not clicked:
            if debug:
                print("[debug] 未点击到「立即沟通/继续沟通」按钮，仍尝试寻找输入框")
            return PreparedChatTab(
                tab=job_tab,
                template_type=self._resolve_chat_template_type(job_tab),
                ready=False,
            )
        same_tab_redirected = await self._wait_for_same_tab_chat_redirect(
            job_tab,
            debug=debug,
            timeout_sec=max(CHAT_TARGET_TIMEOUT_SEC, 2.0),
        )
        if same_tab_redirected:
            ready = await self._wait_for_chat_ready(job_tab, debug=debug, timeout_sec=max(CHAT_READY_TIMEOUT_SEC, 3.0))
            if debug and not ready:
                print("[debug] 当前 tab 已跳转聊天页，但在等待时间内未进入聊天输入态")
            return PreparedChatTab(
                tab=job_tab,
                template_type=self._resolve_chat_template_type(job_tab),
                ready=ready,
            )
        redirected_tab = await self._wait_for_chat_target(browser, known_target_ids, debug=debug, timeout_sec=CHAT_TARGET_TIMEOUT_SEC)
        if redirected_tab:
            job_tab = redirected_tab
            await job_tab
        ready = await self._wait_for_chat_ready(job_tab, debug=debug, timeout_sec=max(CHAT_READY_TIMEOUT_SEC, 3.0))
        if debug and not ready:
            print("[debug] 已点击沟通按钮，但在等待时间内未进入聊天输入态")
        template_type = self._resolve_chat_template_type(job_tab)
        if self._chat_debug_enabled(debug):
            print(f"[debug] 当前页面模板判定: {template_type}")
        return PreparedChatTab(
            tab=job_tab,
            template_type=template_type,
            ready=ready,
        )

    async def _ensure_manual_login(self, tab, debug: bool) -> None:
        input(">>> 请在浏览器完成登录后按回车继续: ")
        await tab
        if debug:
            print(f"[debug] 当前 URL: {getattr(tab, 'url', '')}")

    async def _safe_close_tab(self, tab) -> None:
        try:
            await tab.close()
        except Exception:
            pass

    async def _safe_close_browser(self, browser, debug: bool) -> None:
        """批量投递结束后尽量优雅关闭浏览器，保证程序退出。"""
        close_methods = ["stop", "close", "quit"]
        for method_name in close_methods:
            method = getattr(browser, method_name, None)
            if method is None:
                continue
            try:
                result = method()
                if asyncio.iscoroutine(result):
                    await result
                return
            except Exception as exc:
                if debug:
                    print(f"[debug] 关闭浏览器失败({method_name}): {exc}")
