"""Boss 直聘 chat 模板发送逻辑。"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

from src.config.settings import Config


POLL_INTERVAL_SEC = float(os.getenv("BOSS_POLL_INTERVAL_SEC", "0.03"))
SEND_VERIFY_TIMEOUT_SEC = float(os.getenv("BOSS_CHAT_SEND_VERIFY_TIMEOUT_SEC", "5"))


class BossApplyChatTemplate:
    """处理跳转到 /web/geek/chat 后的消息发送。"""

    def __init__(self, uc, *, chat_debug_enabled) -> None:
        self.uc = uc
        self._chat_debug_enabled = chat_debug_enabled
        self._chat_dumped_urls: set[str] = set()

    async def find_input(self, tab):
        for selector in [
            "#chat-input.chat-input",
            "#chat-input",
            ".message-controls #chat-input",
            ".chat-editor #chat-input",
            ".chat-editor .chat-input",
            ".chat-editor [contenteditable='true']",
            ".message-controls [contenteditable='true']",
            "[role='textbox'][contenteditable='true']",
        ]:
            try:
                el = await tab.select(selector, timeout=2)
                if el:
                    return el
            except Exception:
                continue
        return None

    async def is_ready(self, tab) -> bool:
        for selector in [".chat-content", ".chat-record", ".message-content", ".chat-editor", ".boss-chat", "main"]:
            try:
                if await tab.select(selector, timeout=1):
                    break
            except Exception:
                continue
        return bool(await self.find_input(tab))

    async def send_greeting(self, tab, greeting: str, *, debug: bool, dry_run: bool, fill_only: bool) -> bool:
        normalized_greeting = self._normalize_greeting_for_chat_input(greeting)
        try:
            await self._log_debug_state(tab, "before_find_input", debug)
            chat_input = await self._prepare_input(tab, debug=debug)
            if not chat_input:
                return False
            await self._log_debug_state(tab, "before_send_keys", debug)
            filled = await self._ensure_message_filled(tab, chat_input, normalized_greeting, debug=debug)
            if not filled:
                return False
            if dry_run or fill_only:
                return True
            before_send_state = await self._collect_debug_state(tab)
            try:
                await self._dump_state_before_send(tab, "boss_chat_before_send", debug)
                if await self._send_message(tab, normalized_greeting, debug=debug, before_state=before_send_state):
                    return True
                if self._chat_debug_enabled(debug):
                    await self._dump_state_before_send(tab, "boss_chat_send_verify_failed", debug)
                return False
            except Exception as error:
                if debug:
                    print(f"[debug] chat-page Enter 发送失败: {error}")
                return False
        except Exception as error:
            if debug:
                print(f"[debug] chat-page DOM 发送失败: {error}")
            return False

    async def dump_page_if_needed(self, tab, prefix: str, debug: bool) -> None:
        if not self._chat_debug_enabled(debug):
            return
        current_url = str(getattr(tab, "url", "") or "")
        if not current_url or current_url in self._chat_dumped_urls:
            return
        self._chat_dumped_urls.add(current_url)
        try:
            png, html_path = await self._dump_page(tab, prefix)
            print(f"[debug] 已导出聊天页: {png} / {html_path}")
        except Exception as error:
            print(f"[debug] 导出聊天页失败: {error}")

    async def _prepare_input(self, tab, debug: bool):
        chat_input = await self.find_input(tab)
        if not chat_input:
            if debug:
                print("[debug] chat-page DOM 填充失败: input_missing")
            return None
        try:
            await chat_input.apply("(input) => { input.focus(); input.click(); }")
        except Exception:
            pass
        try:
            await chat_input.clear_input()
        except Exception:
            pass
        return chat_input

    async def _type_message(self, tab, chat_input, greeting: str, debug: bool) -> bool:
        try:
            lines = greeting.split("\n")
            for index, line in enumerate(lines):
                if line:
                    await chat_input.send_keys(line)
                if index < len(lines) - 1:
                    await self._press_ctrl_enter(tab)
            return True
        except Exception as error:
            if debug:
                print(f"[debug] chat-page send_keys 失败，回退 DOM 填充: {error}")
            return False

    async def _fill_message_via_dom(self, chat_input, greeting: str, debug: bool) -> bool:
        filled = await chat_input.apply(
            f"""
            (input) => {{
                const value = {json.dumps(greeting)};
                if (!input) {{
                    return false;
                }}
                input.focus();
                input.click();
                input.innerHTML = '';
                input.dispatchEvent(new InputEvent('beforeinput', {{
                    bubbles: true,
                    cancelable: true,
                    data: value,
                    inputType: 'insertText'
                }}));
                const lines = value.split('\\n');
                lines.forEach((line, index) => {{
                    if (index > 0) {{
                        input.appendChild(document.createElement('br'));
                    }}
                    input.appendChild(document.createTextNode(line));
                }});
                input.dispatchEvent(new InputEvent('input', {{ bubbles: true, data: value, inputType: 'insertText' }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                input.dispatchEvent(new KeyboardEvent('keydown', {{ bubbles: true, key: 'a' }}));
                input.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true, key: 'a' }}));
                return (input.innerText || input.textContent || '').replace(/\\r\\n/g, '\\n') === value;
            }}
            """
        )
        if filled:
            return True
        if debug:
            print(f"[debug] chat-page DOM 填充失败: {filled}")
        return False

    async def _ensure_message_filled(self, tab, chat_input, greeting: str, debug: bool) -> bool:
        if await self._type_message(tab, chat_input, greeting, debug=debug):
            await self._log_debug_state(tab, "after_send_keys", debug)
            return True
        if await self._fill_message_via_dom(chat_input, greeting, debug=debug):
            return True
        try:
            lines = greeting.split("\n")
            for index, line in enumerate(lines):
                if line:
                    await chat_input.send_keys(line)
                if index < len(lines) - 1:
                    await self._press_ctrl_enter(tab)
            await self._log_debug_state(tab, "after_fallback_send_keys", debug)
            return True
        except Exception as error:
            if debug:
                print(f"[debug] chat-page send_keys 回退失败: {error}")
            return False

    def _normalize_greeting_for_chat_input(self, greeting: str) -> str:
        """chat 编辑器里只保留单层逻辑换行，避免空行被放大成多次换行。"""
        text = (greeting or "").replace("\r\n", "\n").replace("\r", "\n")
        # 先按“段”收口，去掉多余空白行；chat 场景下每段之间只保留一个逻辑换行。
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
        if paragraphs:
            return "\n".join(paragraphs)
        return "\n".join(line.rstrip() for line in text.split("\n")).strip()

    async def _click_send_button(self, tab, debug: bool) -> bool:
        for text in ["发送", "发出", "立即发送"]:
            try:
                send_btn = await tab.find(text, best_match=True, timeout=1.5)
            except Exception:
                send_btn = None
            if not send_btn:
                continue
            try:
                await send_btn.apply("(btn) => { btn.focus(); btn.click(); }")
                await tab.sleep(0.25)
                return True
            except Exception as error:
                if self._chat_debug_enabled(debug):
                    print(f"[debug] 点击聊天页发送文本按钮失败({text}): {error}")
        for selector in [".chat-op .btn-send", ".message-controls .btn-send", "button.btn-send"]:
            try:
                send_btn = await tab.select(selector, timeout=1)
            except Exception:
                send_btn = None
            if not send_btn:
                continue
            try:
                enabled = await send_btn.apply(
                    """
                    (btn) => {
                        if (!btn) return false;
                        const disabled = btn.classList.contains('disabled')
                            || btn.hasAttribute('disabled')
                            || btn.getAttribute('aria-disabled') === 'true';
                        return !disabled;
                    }
                    """
                )
            except Exception:
                enabled = True
            if not enabled:
                continue
            try:
                await send_btn.apply("(btn) => { btn.focus(); btn.click(); }")
                await tab.sleep(0.2)
                return True
            except Exception as error:
                if self._chat_debug_enabled(debug):
                    print(f"[debug] 点击聊天页发送按钮失败({selector}): {error}")
                continue
        return False

    async def _send_message(self, tab, greeting: str, *, debug: bool, before_state: dict[str, object]) -> bool:
        if await self._click_send_button(tab, debug=debug):
            await self._log_debug_state(tab, "after_click_send", debug)
            if await self._verify_send_success(tab, greeting, before_state, debug):
                return True
        await self._press_enter(tab)
        await tab.sleep(0.2)
        await self._log_debug_state(tab, "after_enter", debug)
        return await self._verify_send_success(tab, greeting, before_state, debug)

    async def _press_enter(self, tab) -> None:
        await tab.send(
            self.uc.cdp.input_.dispatch_key_event(
                "rawKeyDown",
                code="Enter",
                key="Enter",
                windows_virtual_key_code=13,
                native_virtual_key_code=13,
            )
        )
        await tab.send(
            self.uc.cdp.input_.dispatch_key_event(
                "keyUp",
                code="Enter",
                key="Enter",
                windows_virtual_key_code=13,
                native_virtual_key_code=13,
            )
        )

    async def _press_ctrl_enter(self, tab) -> None:
        ctrl_modifier = 2
        await tab.send(
            self.uc.cdp.input_.dispatch_key_event(
                "rawKeyDown",
                modifiers=ctrl_modifier,
                code="ControlLeft",
                key="Control",
                windows_virtual_key_code=17,
                native_virtual_key_code=17,
            )
        )
        await tab.send(
            self.uc.cdp.input_.dispatch_key_event(
                "rawKeyDown",
                modifiers=ctrl_modifier,
                code="Enter",
                key="Enter",
                windows_virtual_key_code=13,
                native_virtual_key_code=13,
            )
        )
        await tab.send(
            self.uc.cdp.input_.dispatch_key_event(
                "keyUp",
                modifiers=ctrl_modifier,
                code="Enter",
                key="Enter",
                windows_virtual_key_code=13,
                native_virtual_key_code=13,
            )
        )
        await tab.send(
            self.uc.cdp.input_.dispatch_key_event(
                "keyUp",
                code="ControlLeft",
                key="Control",
                windows_virtual_key_code=17,
                native_virtual_key_code=17,
            )
        )

    async def _collect_debug_state(self, tab) -> dict[str, object]:
        try:
            payload = await tab.evaluate(
                """
                () => {
                    const input = document.querySelector('#chat-input.chat-input')
                        || document.querySelector('.message-controls #chat-input')
                        || document.querySelector('.chat-editor .chat-input');
                    const sendBtn = document.querySelector('.chat-op .btn-send')
                        || document.querySelector('.message-controls .btn-send')
                        || document.querySelector('button.btn-send');
                    const messages = Array.from(document.querySelectorAll('.im-list li, .chat-message li'));
                    const lastMessage = messages.length ? messages[messages.length - 1] : null;
                    return {
                        activeTag: document.activeElement ? document.activeElement.tagName : '',
                        activeId: document.activeElement ? (document.activeElement.id || '') : '',
                        activeClass: document.activeElement ? (document.activeElement.className || '') : '',
                        inputFound: !!input,
                        inputText: input ? ((input.innerText || input.textContent || '').trim()) : '',
                        inputHtmlLength: input ? ((input.innerHTML || '').length) : 0,
                        sendBtnFound: !!sendBtn,
                        sendBtnDisabled: !!(sendBtn && (sendBtn.classList.contains('disabled') || sendBtn.hasAttribute('disabled'))),
                        sendBtnText: sendBtn ? ((sendBtn.innerText || sendBtn.textContent || '').trim()) : '',
                        messageCount: messages.length,
                        lastMessageText: lastMessage ? ((lastMessage.innerText || lastMessage.textContent || '').trim().slice(0, 120)) : '',
                    };
                }
                """
            )
            return payload or {}
        except Exception:
            return await self._collect_debug_state_from_html(tab)

    async def _collect_debug_state_from_html(self, tab) -> dict[str, object]:
        """当 evaluate 失效时，从整页 HTML 做弱解析，至少保证发送校验可用。"""
        html = await self._safe_get_content(tab)
        if not html:
            return {}
        input_match = re.search(
            r'<div[^>]+id="chat-input"[^>]*class="[^"]*chat-input[^"]*"[^>]*>(.*?)</div>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        send_btn_match = re.search(
            r'<button[^>]*class="[^"]*btn-send([^"]*)"[^>]*>(.*?)</button>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        myself_blocks = re.findall(
            r'<li[^>]*class="[^"]*item-myself[^"]*"[^>]*>(.*?)</li>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        last_block = myself_blocks[-1] if myself_blocks else ""
        last_text = self._extract_text_from_html(last_block)
        input_text = self._extract_text_from_html(input_match.group(1)) if input_match else ""
        send_btn_classes = send_btn_match.group(1) if send_btn_match else ""
        send_btn_text = self._extract_text_from_html(send_btn_match.group(2)) if send_btn_match else ""
        return {
            "activeTag": "",
            "activeId": "",
            "activeClass": "",
            "inputFound": bool(input_match),
            "inputText": input_text,
            "inputHtmlLength": len(input_match.group(1)) if input_match else 0,
            "sendBtnFound": bool(send_btn_match),
            "sendBtnDisabled": "disabled" in (send_btn_classes or ""),
            "sendBtnText": send_btn_text,
            "messageCount": len(myself_blocks),
            "lastMessageText": last_text[:120],
        }

    async def _log_debug_state(self, tab, stage: str, debug: bool) -> None:
        if not self._chat_debug_enabled(debug):
            return
        state = await self._collect_debug_state(tab)
        if not state:
            print(f"[debug] chat state @{stage}: <unavailable>")
            return
        print(
            f"[debug] chat state @{stage}: "
            f"active={state.get('activeTag')}#{state.get('activeId')} "
            f"class={state.get('activeClass')} | "
            f"inputFound={state.get('inputFound')} inputTextLen={len(str(state.get('inputText') or ''))} "
            f"inputHtmlLen={state.get('inputHtmlLength')} | "
            f"sendBtnFound={state.get('sendBtnFound')} disabled={state.get('sendBtnDisabled')} "
            f"text={state.get('sendBtnText')} | "
            f"messageCount={state.get('messageCount')} lastMessage={state.get('lastMessageText')}"
        )

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _build_message_markers(self, greeting: str) -> list[str]:
        normalized = self._normalize_text(greeting)
        if not normalized:
            return []
        markers: list[str] = []
        first_line = self._normalize_text(normalized.split("\n", 1)[0])
        if first_line:
            markers.append(first_line[:40])
        markers.append(normalized[:40])
        markers.append(normalized[:24])
        deduped: list[str] = []
        for marker in markers:
            if marker and marker not in deduped:
                deduped.append(marker)
        return deduped

    def _message_matches_greeting(self, last_message: str | None, greeting: str) -> bool:
        normalized_message = self._normalize_text(last_message)
        if not normalized_message:
            return False
        for marker in self._build_message_markers(greeting):
            if marker and marker in normalized_message:
                return True
        return False

    async def _page_contains_greeting_message(self, tab, greeting: str) -> bool:
        """在 DOM 状态不可读时，从页面 HTML 中确认自己的最新消息是否已出现。"""
        html = await self._safe_get_content(tab)
        if not html:
            return False
        myself_blocks = re.findall(
            r'<li[^>]*class="[^"]*item-myself[^"]*"[^>]*>(.*?)</li>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not myself_blocks:
            return False
        last_text = self._extract_text_from_html(myself_blocks[-1])
        return self._message_matches_greeting(last_text, greeting)

    async def _verify_send_success(
        self,
        tab,
        greeting: str,
        before_state: dict[str, object] | None,
        debug: bool,
        *,
        timeout_sec: float = SEND_VERIFY_TIMEOUT_SEC,
    ) -> bool:
        before_state = before_state or {}
        before_count = int(before_state.get("messageCount") or 0)
        before_input = self._normalize_text(before_state.get("inputText"))
        deadline = asyncio.get_running_loop().time() + timeout_sec
        last_state: dict[str, object] = {}
        while asyncio.get_running_loop().time() < deadline:
            state = await self._collect_debug_state(tab)
            last_state = state or {}
            after_count = int(last_state.get("messageCount") or 0)
            after_input = self._normalize_text(last_state.get("inputText"))
            last_message = str(last_state.get("lastMessageText") or "")

            if self._message_matches_greeting(last_message, greeting):
                if self._chat_debug_enabled(debug):
                    print("[debug] chat-page send verified: matched last outgoing message")
                return True
            if await self._page_contains_greeting_message(tab, greeting):
                if self._chat_debug_enabled(debug):
                    print("[debug] chat-page send verified: matched outgoing message in page HTML")
                return True
            if after_count > before_count and before_input and len(after_input) < max(4, len(before_input) // 3):
                if self._chat_debug_enabled(debug):
                    print("[debug] chat-page send verified: message count increased and input cleared")
                return True
            await tab.sleep(POLL_INTERVAL_SEC)

        if self._chat_debug_enabled(debug):
            print(
                "[debug] chat-page send verify failed: "
                f"beforeCount={before_count} afterCount={last_state.get('messageCount')} "
                f"beforeInputLen={len(before_input)} afterInputLen={len(self._normalize_text(last_state.get('inputText')))} "
                f"lastMessage={last_state.get('lastMessageText')}"
            )
        return False

    async def _dump_state_before_send(self, tab, prefix: str, debug: bool) -> None:
        if not self._chat_debug_enabled(debug):
            return
        dump_dir = Config.resolve_project_path(os.getenv("BOSS_DUMP_DIR", "data/boss_debug"))
        dump_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = re.sub(r"[^a-zA-Z0-9_\\-]+", "_", prefix).strip("_") or "chat_before_send"
        text_path = dump_dir / f"{safe_prefix}_{ts}.txt"
        try:
            state = await self._collect_debug_state(tab)
            text_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as error:
            text_path.write_text(f"collect_chat_debug_state failed: {error}", encoding="utf-8")
        try:
            png, html_path = await self._dump_page(tab, safe_prefix)
            print(f"[debug] 已导出发送前聊天页: {png} / {html_path} / {text_path}")
        except Exception as error:
            print(f"[debug] 导出发送前聊天页失败: {error}")

    async def _safe_get_content(self, tab) -> str:
        try:
            content = await tab.get_content()
            return content or ""
        except Exception:
            return ""

    def _extract_text_from_html(self, raw_html: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", raw_html or "", flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return self._normalize_text(text)

    async def _dump_page(self, tab, prefix: str) -> tuple[Path, Path]:
        dump_dir = Config.resolve_project_path(os.getenv("BOSS_DUMP_DIR", "data/boss_debug"))
        dump_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = re.sub(r"[^a-zA-Z0-9_\\-]+", "_", prefix).strip("_") or "dump"
        png = dump_dir / f"{safe_prefix}_{ts}.png"
        html_path = dump_dir / f"{safe_prefix}_{ts}.html"
        await tab.save_screenshot(str(png), format="png", full_page=True)
        html_path.write_text(await self._safe_get_content(tab), encoding="utf-8")
        return png, html_path
