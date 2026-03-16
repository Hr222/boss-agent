"""Boss 直聘 legacy 模板发送逻辑。"""

import json


class BossApplyLegacyTemplate:
    """处理旧版详情页/聊天输入框发送。"""

    async def dump_page_if_needed(self, tab, prefix: str, debug: bool) -> None:
        return None

    async def find_input(self, tab):
        selectors = [
            "textarea",
            "textarea.input-area",
            "textarea.chat-input",
            "textarea[placeholder]",
            "div[contenteditable='true']",
            "div[contenteditable='plaintext-only']",
            "[contenteditable='true']",
            "[contenteditable='plaintext-only']",
            "[role='textbox']",
            ".chat-input",
            ".chat-editor",
            ".input-area",
            ".boss-editor-input",
            ".public-DraftEditor-content",
        ]
        for selector in selectors:
            try:
                el = await tab.select(selector, timeout=4)
            except Exception:
                continue
            try:
                if await el.apply(
                    "(e) => !!(e && (e.offsetParent !== null || getComputedStyle(e).position === 'fixed'))"
                ):
                    return el
            except Exception:
                return el
        try:
            fallback = await tab.evaluate(
                """
                () => {
                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') return false;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 20 && rect.height > 16;
                    };
                    const score = (el) => {
                        if (!isVisible(el)) return -1;
                        const rect = el.getBoundingClientRect();
                        let value = 0;
                        if (typeof el.value === 'string') value += 100;
                        if (el.isContentEditable) value += 120;
                        if ((el.getAttribute('role') || '') === 'textbox') value += 80;
                        const cls = `${el.className || ''} ${el.id || ''}`.toLowerCase();
                        if (cls.includes('input')) value += 25;
                        if (cls.includes('editor')) value += 25;
                        if (cls.includes('chat')) value += 20;
                        if (rect.top > window.innerHeight * 0.55) value += 35;
                        if (rect.width > window.innerWidth * 0.25) value += 20;
                        return value;
                    };
                    const candidates = Array.from(document.querySelectorAll(
                        "textarea, [contenteditable='true'], [contenteditable='plaintext-only'], [role='textbox'], input[type='text'], div, section"
                    ));
                    let best = null;
                    let bestScore = -1;
                    for (const el of candidates) {
                        const s = score(el);
                        if (s > bestScore) {
                            best = el;
                            bestScore = s;
                        }
                    }
                    if (!best || bestScore < 60) return null;
                    best.setAttribute('data-codex-chat-input', '1');
                    return {
                        score: bestScore,
                        tag: best.tagName,
                        className: best.className || '',
                        role: best.getAttribute('role') || '',
                    };
                }
                """
            )
            if fallback:
                return await tab.select("[data-codex-chat-input='1']", timeout=1)
        except Exception:
            pass
        return None

    async def is_ready(self, tab) -> bool:
        return bool(await self.find_input(tab))

    async def send_greeting(self, tab, greeting: str, *, debug: bool, dry_run: bool, fill_only: bool) -> bool:
        chat_input = await self.find_input(tab)
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
            filled = await self._fill_input(chat_input, greeting, debug=debug)
            if not filled:
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
        except Exception as error:
            if debug:
                print(f"[debug] 发送招呼语失败: {error}")
            return False

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
            except Exception as error:
                if debug:
                    print(f"[debug] 点击发送按钮「{text}」失败: {error}")

        selectors = [
            "button[type='submit']",
            ".send-btn",
            ".btn-send",
            ".chat-op button",
            ".chat-controls button",
            ".op-btn-send",
            ".message-send",
            "button",
        ]
        for selector in selectors:
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

    async def _fill_input(self, chat_input, greeting: str, debug: bool) -> bool:
        normalized_greeting = greeting.replace("\r\n", "\n").replace("\r", "\n")
        script = f"""
        (el) => {{
            const value = {json.dumps(normalized_greeting)};
            const dispatchInputEvents = () => {{
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }};
            if (!el) {{
                return false;
            }}
            if (typeof el.value === 'string') {{
                el.focus();
                el.value = value;
                dispatchInputEvents();
                return el.value === value;
            }}
            if (el.isContentEditable) {{
                el.focus();
                el.innerHTML = '';
                const lines = value.split('\\n');
                lines.forEach((line, index) => {{
                    if (index > 0) {{
                        el.appendChild(document.createElement('br'));
                    }}
                    el.appendChild(document.createTextNode(line));
                }});
                dispatchInputEvents();
                return (el.innerText || el.textContent || '').replace(/\\r\\n/g, '\\n') === value;
            }}
            return false;
        }}
        """
        try:
            filled = await chat_input.apply(script)
            return bool(filled)
        except Exception as error:
            if debug:
                print(f"[debug] DOM 填充输入框失败，回退 send_keys: {error}")
            return False
