"""Boss 直聘投递客户端：封装 nodriver 页面交互。"""

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from src.config.settings import Config
from src.infrastructure.browser.nodriver_runtime import _env_bool, _import_nodriver
from src.models.greeting_archive_model import GreetingArchiveModel


ORIGIN = "https://www.zhipin.com"
DETAIL_READY_TIMEOUT_SEC = float(os.getenv("BOSS_DETAIL_READY_TIMEOUT_SEC", "1"))
CHAT_READY_TIMEOUT_SEC = float(os.getenv("BOSS_CHAT_READY_TIMEOUT_SEC", "1"))
CHAT_TARGET_TIMEOUT_SEC = float(os.getenv("BOSS_CHAT_TARGET_TIMEOUT_SEC", "1"))
POLL_INTERVAL_SEC = float(os.getenv("BOSS_POLL_INTERVAL_SEC", "0.03"))


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


class BossApplyClient:
    """负责打开岗位详情页并发送招呼语。"""

    def __init__(self) -> None:
        self.uc = _import_nodriver()
        self.archive_model = GreetingArchiveModel()

    async def apply_jobs(
        self,
        queue: list[dict],
        *,
        mark_applied,
        options: BossApplyOptions,
        browser=None,
    ) -> list[dict]:
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

        results: list[dict] = []
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
                    options=options,
                )
                results.append(result)
                if result.get("status") == "ok":
                    sent_count += 1
                if target_apply_count and sent_count >= target_apply_count:
                    print(f">>> 已达到本轮目标：实际发送 {sent_count} 个岗位。")
                    break

        # 主线路批量投递完成后直接结束，避免一直挂起等待人工中断。
        processed_count = len(results)
        success_count = sum(1 for item in results if item.get("status") == "ok")
        already_contacted_count = sum(1 for item in results if item.get("reason") == "already_contacted")
        skipped_count = sum(
            1 for item in results if item.get("status") == "skipped" and item.get("reason") != "already_contacted"
        )
        failed_count = sum(1 for item in results if item.get("status") == "failed")
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
        options: BossApplyOptions,
    ) -> dict:
        """处理单个岗位的详情打开、沟通按钮点击和消息发送。"""
        job_url = str(row.get("job_url") or "").strip()
        if not job_url:
            return {"status": "skipped", "reason": "missing_job_url"}

        open_url = job_url if job_url.startswith("http") else urljoin(ORIGIN, job_url)
        if not open_url:
            return {"status": "skipped", "reason": "invalid_job_url", "job_url": job_url}

        raw_json = row.get("raw_json")
        greeting = self._resolve_greeting(open_url, raw_json, greetings_dir, options)
        if not greeting:
            print(f"跳过（无招呼语）: {open_url}")
            return {"status": "skipped", "reason": "missing_greeting", "job_url": open_url}

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
            return {"status": "skipped", "reason": "already_contacted", "job_url": open_url}

        # 详情页和聊天页之间可能会跳 target，这里统一做收敛。
        job_tab = await self._prepare_chat_tab(browser, job_tab, known_target_ids, debug=options.debug)
        ok = await self._send_greeting(
            job_tab,
            greeting,
            debug=options.debug,
            dry_run=options.dry_run,
            fill_only=options.fill_only,
        )

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
            status = "failed"

        if not options.no_close_tab:
            await self._safe_close_tab(job_tab)
        return {"status": status, "job_url": open_url}

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

        return await self.uc.start(
            headless=headless,
            user_data_dir=str(profile_dir),
            browser_args=browser_args,
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

    async def _find_chat_input(self, tab):
        for selector in ["textarea", "textarea.input-area", "textarea.chat-input", "div[contenteditable='true']", "[contenteditable='true']"]:
            try:
                el = await tab.select(selector, timeout=4)
            except Exception:
                continue
            try:
                if await el.apply("(e) => !!(e && e.offsetParent !== null)"):
                    return el
            except Exception:
                return el
        return None

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

    async def _click_send_button(self, tab, debug: bool) -> bool:
        text_candidates = ["发送", "发出", "立即发送"]
        for text in text_candidates:
            try:
                el = await tab.find(text, best_match=True, timeout=2)
                if not el:
                    continue
                try:
                    visible = await el.apply("(e) => !!(e && e.offsetParent !== null)")
                    if not visible:
                        continue
                except Exception:
                    pass
                try:
                    await el.apply("(e) => e.scrollIntoView({block: 'center'})")
                except Exception:
                    pass
                try:
                    await el.click()
                except Exception:
                    await el.apply("(e) => e.click()")
                await tab.sleep(0.35)
                return True
            except Exception as e:
                if debug:
                    print(f"[debug] 点击发送按钮「{text}」失败: {e}")

        for selector in ["button[type='submit']", ".send-btn", ".btn-send", ".chat-op button", ".chat-controls button", "button"]:
            try:
                el = await tab.select(selector, timeout=2)
                if not el:
                    continue
                text = await el.apply("(e) => (e.innerText || e.textContent || '').trim()")
                if selector != "button" and not any(keyword in str(text) for keyword in text_candidates):
                    pass
                elif selector == "button" and not any(keyword in str(text) for keyword in text_candidates):
                    continue
                try:
                    await el.apply("(e) => e.scrollIntoView({block: 'center'})")
                except Exception:
                    pass
                try:
                    await el.click()
                except Exception:
                    await el.apply("(e) => e.click()")
                await tab.sleep(0.35)
                return True
            except Exception:
                continue
        return False

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
            if await self._find_chat_input(tab):
                return True
            await tab.sleep(POLL_INTERVAL_SEC)
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
                if debug:
                    print(f"[debug] new target detected -> {candidate_url or target_id}")
                return candidate
            await asyncio.sleep(POLL_INTERVAL_SEC)
        return None

    async def _send_greeting(self, tab, greeting: str, debug: bool, dry_run: bool, fill_only: bool) -> bool:
        if not greeting.strip():
            return False
        chat_input = await self._find_chat_input(tab)
        if not chat_input:
            if debug:
                print("[debug] 未找到聊天输入框")
            return False
        try:
            await chat_input.apply("(e) => e.focus()")
        except Exception:
            pass
        if dry_run:
            if debug:
                print("[debug] dry-run: 已定位输入框，未发送")
            return True
        try:
            try:
                await chat_input.clear_input()
            except Exception:
                pass
            await chat_input.send_keys(greeting)
            if fill_only:
                await tab.sleep(0.15)
                return True
            if await self._click_send_button(tab, debug=debug):
                return True
            if debug:
                print("[debug] 未找到发送按钮，回退到回车发送")
            await chat_input.send_keys("\n")
            await tab.sleep(0.35)
            return True
        except Exception as e:
            if debug:
                print(f"[debug] 发送招呼语失败: {e}")
            return False

    async def _prepare_chat_tab(self, browser, job_tab, known_target_ids: set[str], debug: bool):
        clicked = await self._click_start_chat(job_tab, debug=debug)
        if not clicked:
            detail_ready = await self._wait_for_detail_ready(job_tab, debug=debug, timeout_sec=DETAIL_READY_TIMEOUT_SEC)
            if debug and not detail_ready:
                print("[debug] 在等待时间内未检测到岗位详情主体区域")
            clicked = await self._click_start_chat(job_tab, debug=debug)
        if not clicked:
            if debug:
                print("[debug] 未点击到「立即沟通/继续沟通」按钮，仍尝试寻找输入框")
            return job_tab
        redirected_tab = await self._wait_for_chat_target(browser, known_target_ids, debug=debug, timeout_sec=CHAT_TARGET_TIMEOUT_SEC)
        if redirected_tab:
            job_tab = redirected_tab
            await job_tab
        ready = await self._wait_for_chat_ready(job_tab, debug=debug, timeout_sec=CHAT_READY_TIMEOUT_SEC)
        if debug and not ready:
            print("[debug] 已点击沟通按钮，但在等待时间内未进入聊天输入态")
        return job_tab

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
