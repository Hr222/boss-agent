"""Boss 搜索客户端：负责打开搜索页并抓取岗位。"""

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config.settings import Config
from src.infrastructure.browser.nodriver_runtime import _env_bool, _import_nodriver
from src.infrastructure.persistence.sqlite_job_store import JobRecord


CITY_CODES = {
    "北京": "100010000",
    "上海": "101020100",
    "深圳": "101280600",
    "广州": "101280100",
    "杭州": "101210100",
    "成都": "101270100",
    "南京": "101190100",
    "武汉": "101200100",
    "西安": "101110100",
}


@dataclass(frozen=True)
class BossSearchOptions:
    keyword: str = ""
    city: str = ""
    city_code: str = ""
    limit: int = 20
    require_login: bool = True
    no_collect: bool = False
    debug: bool = False
    exclude_company_names: tuple[str, ...] = ()


class BossSearchClient:
    """打开 Boss 搜索页，并通过仓储层持久化抓取结果。"""

    def __init__(self) -> None:
        self.uc = _import_nodriver()
        # 按 tab 维度维护列表消费游标，保证续抓时从上次结束下标继续。
        self._tab_card_cursors: dict[str, int] = {}

    async def collect_jobs(self, *, repository, options: BossSearchOptions) -> dict[str, Any]:
        """执行完整抓取流程：打开页面、等待登录、提取链接、补全 JD、写库。"""
        user_data_dir = os.getenv("BOSS_USER_DATA_DIR", ".nodriver_user_data/boss")
        headless = _env_bool("BOSS_HEADLESS", False)
        disable_extensions = _env_bool("BOSS_DISABLE_EXTENSIONS", True)

        profile_dir = Config.resolve_project_path(user_data_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)

        browser_args = ["--disable-dev-shm-usage", "--no-first-run", "--no-default-browser-check"]
        if disable_extensions:
            browser_args += ["--disable-extensions", "--disable-component-extensions-with-background-pages"]

        browser = await self.uc.start(
            headless=headless,
            user_data_dir=str(profile_dir),
            browser_args=browser_args,
        )

        tab = await self.prepare_search_tab(browser, options)
        print(">>> 浏览器将保持打开：你可以手动操作；关闭浏览器窗口结束程序（或 Ctrl+C）")

        # 返回基础统计，便于后续 CLI 或主流程直接打印结果。
        stats = {"stored_links": 0, "jobs_written": 0, "links_found": 0}

        if not options.no_collect:
            batch_stats = await self.collect_jobs_from_tab(
                tab,
                repository=repository,
                options=options,
                session_seen_urls=set(),
                target_new_jobs=max(options.limit, 0),
            )
            stats.update(batch_stats)

        try:
            while True:
                proc = getattr(browser, "_process", None)
                if proc is not None and getattr(proc, "returncode", None) is not None:
                    break
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                browser.stop()
            except Exception:
                pass

        return stats

    async def prepare_search_tab(self, browser, options: BossSearchOptions):
        """在既有浏览器里打开搜索页，并完成登录前置检查。"""
        keyword = (options.keyword or "").strip()
        city = (options.city or "").strip()
        city_code = (options.city_code or "").strip() or CITY_CODES.get(city, "")
        url = self._build_search_url(keyword, city_code)
        dump_dir = None
        if options.debug:
            dump_dir = Config.resolve_project_path(os.getenv("BOSS_DUMP_DIR", "data/boss_debug"))
            dump_dir.mkdir(parents=True, exist_ok=True)
        # 搜索主流程默认复用当前浏览器窗口，避免每次启动多开一个新窗口。
        new_window = _env_bool("BOSS_NEW_WINDOW", False)

        tab = await browser.get(url, new_window=new_window)
        await tab
        print(f"✓ 已打开搜索页: {tab.url}")

        if options.require_login:
            print(">>> 请先在浏览器完成登录，确认搜索条件无误后按回车开始抓取。")
            if _env_bool("BOSS_AUTO_CLICK_LOGIN", True):
                try:
                    btn = await tab.select(".guide-login-btn", timeout=3)
                    await btn.click()
                except Exception:
                    pass
            input(">>> 登录并确认页面后按回车开始抓取: ")

            while self._looks_like_login_url(getattr(tab, "url", None)):
                if options.debug:
                    print(f"[debug] 仍在登录页，等待跳转... 当前 URL: {getattr(tab, 'url', '')}")
                await tab.sleep(1.0)
                await tab

            if options.debug and dump_dir is not None and _env_bool("BOSS_DUMP_AFTER_LOGIN", True):
                try:
                    png, html = await self._dump_page(tab, dump_dir, "boss_after_login")
                    print(f"[debug] 已导出登录后页面: {png} / {html}")
                except Exception as error:
                    if options.debug:
                        print(f"[debug] 导出登录后页面失败: {error}")

        await tab
        if self._looks_like_login_url(getattr(tab, "url", None)):
            raise RuntimeError("当前仍处于登录页，无法开始抓取。请重新运行并完成登录。")

        if _env_bool("BOSS_WAIT_FOR_ENTER", False):
            input(">>> 如需手动调整搜索条件，请操作完成后按回车继续: ")

        return tab

    async def collect_jobs_from_tab(
        self,
        tab,
        *,
        repository,
        options: BossSearchOptions,
        session_seen_urls: set[str],
        target_new_jobs: int,
    ) -> dict[str, Any]:
        """从已打开的搜索页继续滚动抓取，直到拿到一批新的岗位。"""
        dump_dir = None
        if options.debug:
            dump_dir = Config.resolve_project_path(os.getenv("BOSS_DUMP_DIR", "data/boss_debug"))
            dump_dir.mkdir(parents=True, exist_ok=True)
        scroll_rounds = int(os.getenv("BOSS_AGENT_SCROLL_ROUNDS", "6"))
        scroll_amount = int(os.getenv("BOSS_AGENT_SCROLL_AMOUNT", os.getenv("BOSS_SCROLL_AMOUNT", "400")))
        scroll_pause_seconds = float(os.getenv("BOSS_AGENT_SCROLL_PAUSE_SECONDS", "0.6"))
        detail_wait_seconds = float(os.getenv("BOSS_CARD_DETAIL_WAIT_SECONDS", "0.45"))
        keyword = (options.keyword or "").strip() or "Python开发"
        city = (options.city or "").strip() or "深圳"

        stats = {
            "stored_links": 0,
            "jobs_written": 0,
            "links_found": 0,
            "new_links_found": 0,
            "new_jobs_written": 0,
        }
        unique_new_links: list[str] = []
        unique_new_jobs: list[JobRecord] = []
        is_followup_round = bool(session_seen_urls)
        tab_cursor_key = self._get_tab_cursor_key(tab)
        start_card_index = self._tab_card_cursors.get(tab_cursor_key, 0)

        try:
            await tab.select(".job-card-wrapper", timeout=4)
        except Exception:
            if options.debug:
                print("[debug] 未在 4s 内等到 .job-card-wrapper，继续尝试抓取。")

        # 如果本会话里已经抓过一批岗位，说明当前是“续抓”而不是首抓。
        # 这时先主动下滚一小段，避免下一轮又从上一轮已经看过的卡片顶部开始重复读取。
        if is_followup_round:
            try:
                pre_scroll_amount = max(scroll_amount, 500)
                print(f"[search] 进入续抓模式，先预滚动页面 {pre_scroll_amount}px。")
                await tab.scroll_down(pre_scroll_amount)
                await tab.sleep(max(0.2, scroll_pause_seconds))
            except Exception:
                if options.debug:
                    print("[debug] 续抓预滚动失败，继续按当前视图尝试抓取。")

        for round_index in range(max(scroll_rounds, 1)):
            print(
                f"[search] 抓取轮次 {round_index + 1}/{max(scroll_rounds, 1)}："
                f"开始读取当前可见岗位（起始下标 {start_card_index}）。"
            )
            # 抓取阶段遵循“最少原则”：本轮只围绕目标缺口数量收集，不吞掉当前页全部可见岗位。
            visible_limit = max(target_new_jobs, 1)
            current_jobs, next_card_index, total_cards = await self._collect_jobs_via_card_clicks(
                tab,
                limit=visible_limit,
                detail_wait_seconds=max(detail_wait_seconds, 0.0),
                start_index=start_card_index,
                debug=options.debug,
            )
            stats["links_found"] = max(stats["links_found"], total_cards)
            if options.debug:
                print(
                    f"[debug] 当前卡片扫描策略: 游标续抓，"
                    f"起始下标 {start_card_index}，结束下标 {next_card_index}，"
                    f"候选卡片数 {len(current_jobs)}，当前列表总卡片数 {total_cards}。"
                )
            start_card_index = max(start_card_index, next_card_index)
            self._tab_card_cursors[tab_cursor_key] = start_card_index
            new_jobs = [
                job
                for job in current_jobs
                if job.job_url
                and job.job_url not in session_seen_urls
                and not self._is_excluded_company(job.company, options.exclude_company_names)
            ]
            new_links = [
                job.job_url
                for job in new_jobs
                if job.job_url and job.job_url not in session_seen_urls
            ][: max(target_new_jobs, 1)]

            for link in new_links:
                if link not in unique_new_links:
                    unique_new_links.append(link)
                if len(unique_new_links) >= target_new_jobs:
                    break
            for job in new_jobs:
                if job.job_url not in session_seen_urls and all(item.job_url != job.job_url for item in unique_new_jobs):
                    unique_new_jobs.append(job)
                if len(unique_new_jobs) >= target_new_jobs:
                    break

            if len(unique_new_jobs) >= target_new_jobs:
                print(f"[search] 已收集到目标数量的新增岗位：{len(unique_new_jobs)}/{target_new_jobs}。")
                break

            try:
                print(
                    f"[search] 当前新增岗位 {len(unique_new_jobs)}/{target_new_jobs}，"
                    f"继续下滚 {scroll_amount}px 搜索更多岗位。"
                )
                await tab.scroll_down(scroll_amount)
                await tab.sleep(scroll_pause_seconds)
            except Exception:
                if options.debug:
                    print(f"[debug] 第 {round_index + 1} 轮滚动失败，提前结束本轮抓取。")
                break

        unique_new_jobs = unique_new_jobs[: max(target_new_jobs, 1)]
        filtered_job_urls = {job.job_url for job in unique_new_jobs if job.job_url}
        unique_new_links = [link for link in unique_new_links if link in filtered_job_urls][: max(target_new_jobs, 1)]

        if unique_new_links:
            stats["stored_links"] = repository.save_links(unique_new_links, keyword=keyword, city=city)
            stats["new_links_found"] = len(unique_new_links)
        if unique_new_jobs:
            stats["jobs_written"] = repository.save_jobs(unique_new_jobs)
            stats["new_jobs_written"] = stats["jobs_written"]
            session_seen_urls.update(job.job_url for job in unique_new_jobs if job.job_url)

        if not unique_new_jobs and options.debug and dump_dir is not None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            png = dump_dir / f"boss_search_round_empty_{ts}.png"
            html = dump_dir / f"boss_search_round_empty_{ts}.html"
            try:
                await tab.save_screenshot(str(png), format="png", full_page=True)
                html.write_text(await tab.get_content(), encoding="utf-8")
                print(f"[debug] 本轮未抓到新岗位，已导出: {png} / {html}")
            except Exception:
                pass

        return stats

    def _is_excluded_company(self, company_name: str, excluded_company_names: tuple[str, ...]) -> bool:
        """如果岗位公司与过往任职公司名称相近，则直接过滤掉。"""
        candidate = self._normalize_company_name(company_name)
        if not candidate:
            return False
        for excluded in excluded_company_names:
            normalized_excluded = self._normalize_company_name(excluded)
            if not normalized_excluded:
                continue
            if candidate == normalized_excluded:
                return True
            if candidate in normalized_excluded or normalized_excluded in candidate:
                return True
        return False

    def _normalize_company_name(self, company_name: str) -> str:
        """对公司名做轻量归一化，便于判断“同一家公司不同写法”。"""
        normalized = self._clean_text(company_name or "")
        normalized = re.sub(r"[()（）\\-·,.，。\\s]", "", normalized)
        suffixes = [
            "股份有限公司",
            "有限责任公司",
            "科技有限公司",
            "技术有限公司",
            "实业有限公司",
            "集团有限公司",
            "有限公司",
            "股份公司",
            "集团",
            "控股",
            "科技",
            "技术",
            "实业",
        ]
        changed = True
        while changed and normalized:
            changed = False
            for suffix in suffixes:
                if normalized.endswith(suffix):
                    normalized = normalized[: -len(suffix)]
                    changed = True
        return normalized

    def _build_search_url(self, keyword: str, city_code: str) -> str:
        from urllib.parse import quote_plus

        path = os.getenv("BOSS_SEARCH_PATH", "/web/geek/job").strip() or "/web/geek/job"
        if not path.startswith("/"):
            path = "/" + path
        if not keyword and not city_code:
            return f"https://www.zhipin.com{path}"
        params: list[str] = []
        if keyword:
            params.append(f"query={quote_plus(keyword)}")
        if city_code:
            params.append(f"city={city_code}")
        query = "&".join(params)
        return f"https://www.zhipin.com{path}?{query}" if query else f"https://www.zhipin.com{path}"

    def _extract_job_links_from_html(self, html: str) -> list[str]:
        if not html:
            return []
        hrefs = set(re.findall(r'href="([^"]*?/job_detail/[^"]+)"', html))
        return [h.strip() for h in hrefs if isinstance(h, str) and h.strip()]

    def _normalize_job_url(self, job_url: str) -> str:
        from urllib.parse import urlsplit, urlunsplit

        raw = (job_url or "").strip()
        if not raw:
            return ""
        parts = urlsplit(raw)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    async def _collect_job_links(self, tab) -> list[str]:
        """优先从 DOM 抓链接，失败时再回退到 HTML 正则提取。"""
        from urllib.parse import urljoin

        origin = "https://www.zhipin.com"
        links: list[str] = []

        try:
            anchors = await tab.query_selector_all("a[href*='/job_detail/']")
        except Exception:
            anchors = []

        for anchor in anchors:
            try:
                href = await anchor.apply("(el) => el.href || el.getAttribute('href') || ''")
                href = self._normalize_job_url((href or "").strip())
                if not href:
                    continue
                if not href.startswith("http"):
                    href = urljoin(origin, href)
                links.append(href)
            except Exception:
                continue

        links = list(dict.fromkeys(links))
        if links:
            return links

        try:
            content = await tab.get_content()
        except Exception:
            content = ""

        for href in self._extract_job_links_from_html(content):
            if not href.startswith("http"):
                href = urljoin(origin, href)
            links.append(self._normalize_job_url(href))

        return list(dict.fromkeys(links))

    def _clean_text(self, text: str) -> str:
        return (
            (text or "")
            .replace("\u200b", "")
            .replace("\u200c", "")
            .replace("\u200d", "")
            .replace("\ufeff", "")
            .strip()
        )

    async def _extract_current_job(self, tab) -> JobRecord | None:
        """从右侧详情区读取当前选中岗位的完整信息。"""
        try:
            box = await tab.select(".job-detail-box", timeout=3)
        except Exception:
            return None

        title = salary = city = experience = education = jd = job_url = company = ""
        tags: list[str] = []

        try:
            title_el = await box.query_selector(".job-name")
            title = self._clean_text(title_el.text_all if title_el else "")
        except Exception:
            pass
        try:
            salary_el = await box.query_selector(".job-salary")
            salary = self._clean_text(salary_el.text_all if salary_el else "")
        except Exception:
            pass
        try:
            tag_items = await box.query_selector_all(".tag-list li")
            parts = [self._clean_text(item.text_all) for item in tag_items if self._clean_text(item.text_all)]
            if parts:
                city = parts[0]
            if len(parts) >= 2:
                experience = parts[1]
            if len(parts) >= 3:
                education = parts[2]
        except Exception:
            pass
        try:
            tag_els = await box.query_selector_all(".job-label-list li")
            tags = [self._clean_text(item.text_all) for item in tag_els if self._clean_text(item.text_all)]
        except Exception:
            pass

        for selector in [".company-name", ".company-info a", ".company-info", ".boss-name"]:
            try:
                company_el = await box.query_selector(selector)
                company = self._clean_text(company_el.text_all if company_el else "")
            except Exception:
                company = ""
            if company:
                break

        try:
            desc_el = await box.query_selector("p.desc")
            jd = self._clean_text(desc_el.text_all if desc_el else "")
        except Exception:
            pass
        try:
            more_el = await box.query_selector("a[href*='/job_detail/']")
            if more_el:
                job_url = (await more_el.apply("(el) => el.href || el.getAttribute('href') || ''")) or ""
                job_url = self._normalize_job_url(job_url.strip())
        except Exception:
            pass

        if not job_url:
            try:
                links = await self._collect_job_links(tab)
                job_url = links[0] if links else ""
            except Exception:
                job_url = ""
        if not job_url:
            return None

        return JobRecord(
            job_url=job_url,
            title=title,
            salary=salary,
            city=city,
            experience=experience,
            education=education,
            company=company,
            tags=tuple(tags),
            jd=jd,
            source="nodriver",
            raw={"page_url": getattr(tab, "url", "")},
        )

    async def _extract_job_card_summary(self, card, page_url: str) -> JobRecord | None:
        """从单张列表卡片读取岗位摘要信息，避免每轮扫描整页所有卡片。"""
        try:
            anchor = await card.query_selector("a.job-name[href*='/job_detail/']")
            if not anchor:
                return None
            href = await anchor.apply("(el) => el.href || el.getAttribute('href') || ''")
            href = self._normalize_job_url((href or "").strip())
            if not href:
                return None
            title = self._clean_text(anchor.text_all)
            salary_el = await card.query_selector(".job-salary")
            salary = self._clean_text(salary_el.text_all if salary_el else "")
            tag_items = await card.query_selector_all(".tag-list li")
            parts = [self._clean_text(item.text_all) for item in tag_items if self._clean_text(item.text_all)]
            experience = parts[0] if len(parts) >= 1 else ""
            education = parts[1] if len(parts) >= 2 else ""
            company_el = await card.query_selector(".boss-name")
            company = self._clean_text(company_el.text_all if company_el else "")
            loc_el = await card.query_selector(".company-location")
            city = self._clean_text(loc_el.text_all if loc_el else "")
            desc_el = await card.query_selector("p.desc")
            jd = self._clean_text(desc_el.text_all if desc_el else "")
            return JobRecord(
                job_url=href,
                title=title,
                salary=salary,
                city=city,
                experience=experience,
                education=education,
                company=company,
                tags=(),
                jd=jd,
                source="nodriver",
                raw={"page_url": page_url},
            )
        except Exception:
            return None

    async def _collect_jobs_via_card_clicks(
        self,
        tab,
        *,
        limit: int,
        detail_wait_seconds: float,
        start_index: int,
        debug: bool,
    ) -> tuple[list[JobRecord], int, int]:
        """依次点击列表卡片，用详情区内容补齐落库数据，并返回下一次续抓下标。"""
        records: list[JobRecord] = []
        seen_urls: set[str] = set()
        try:
            cards = await tab.query_selector_all(".job-card-box")
        except Exception:
            cards = []

        total_cards = len(cards)
        target_count = max(int(limit), 0) if limit > 0 else total_cards
        if total_cards <= 0:
            return records, max(start_index, 0), 0

        safe_start_index = max(0, min(int(start_index), total_cards))
        end_index = min(safe_start_index + target_count, total_cards)
        candidate_indices = list(range(safe_start_index, end_index))
        next_cursor = end_index
        if debug:
            print(
                f"[debug] 开始逐卡读取详情："
                f"列表下标 {safe_start_index} -> {max(safe_start_index, end_index - 1)}，"
                f"预计处理 {len(candidate_indices)} 张卡片，单卡等待 {detail_wait_seconds:.2f}s。"
            )

        total_candidates = len(candidate_indices)
        page_url = getattr(tab, "url", "")
        for position, index in enumerate(candidate_indices, 1):
            if debug:
                print(f"[debug] 读取卡片详情进度 {position}/{total_candidates}（列表下标 {index}）。")
            if index >= len(cards):
                break

            card = cards[index]
            try:
                anchor = await card.query_selector("a.job-name[href*='/job_detail/']")
                if not anchor:
                    continue
                href = await anchor.apply("(el) => el.href || el.getAttribute('href') || ''")
                href = self._normalize_job_url((href or "").strip())
                if not href or href in seen_urls:
                    continue

                try:
                    await card.scroll_into_view_if_needed()
                except Exception:
                    pass

                clicked = False
                for candidate in [anchor, card]:
                    try:
                        await candidate.click()
                        clicked = True
                        break
                    except Exception:
                        continue
                if not clicked:
                    continue

                if detail_wait_seconds > 0:
                    await tab.sleep(detail_wait_seconds)
                await tab

                current = await self._extract_current_job(tab)
                if current is None:
                    summary = await self._extract_job_card_summary(card, page_url)
                    if summary is None:
                        continue
                    current = summary

                summary = await self._extract_job_card_summary(card, page_url)
                if summary:
                    current = JobRecord(
                        job_url=current.job_url,
                        title=current.title or summary.title,
                        salary=current.salary or summary.salary,
                        city=current.city or summary.city,
                        experience=current.experience or summary.experience,
                        education=current.education or summary.education,
                        company=current.company or summary.company,
                        tags=current.tags or summary.tags,
                        jd=current.jd or summary.jd,
                        source=current.source,
                        raw=current.raw,
                    )

                seen_urls.add(current.job_url)
                records.append(current)
            except Exception:
                continue

        return records, next_cursor, total_cards

    def _get_tab_cursor_key(self, tab) -> str:
        """为当前搜索页生成稳定的游标键。"""
        target_id = str(getattr(tab, "target_id", "") or "")
        if target_id:
            return target_id
        return str(getattr(tab, "url", "") or "default")

    async def _safe_get_content(self, tab) -> str:
        try:
            content = await tab.get_content()
            return content or ""
        except Exception:
            return ""

    async def _dump_page(self, tab, dump_dir: Path, prefix: str) -> tuple[Path, Path]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_prefix = re.sub(r"[^a-zA-Z0-9_\\-]+", "_", prefix).strip("_") or "dump"
        png = dump_dir / f"{safe_prefix}_{ts}.png"
        html = dump_dir / f"{safe_prefix}_{ts}.html"
        await tab.save_screenshot(str(png), format="png", full_page=True)
        html.write_text(await self._safe_get_content(tab), encoding="utf-8")
        return png, html

    def _looks_like_login_url(self, url: str | None) -> bool:
        if not url:
            return False
        lowered = url.lower()
        return "/web/user" in lowered or "ka=header-login" in lowered
