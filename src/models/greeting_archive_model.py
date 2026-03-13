"""招呼语归档模型：只在真实发送成功后输出复盘文件。"""

import json
import re
from pathlib import Path
from typing import Any


class GreetingArchiveModel:
    """负责把已发送的岗位信息、JD 和招呼语归档到本地文件。"""

    def write_archive(self, out_dir: Path, row: dict[str, Any], greeting: str) -> Path:
        """按“公司 - 岗位”写入已发送招呼语归档文件。"""
        out_dir.mkdir(parents=True, exist_ok=True)
        merged = self._merge_row_with_raw_json(row)
        filename = self._build_archive_filename(
            company_name=str(merged.get("company") or ""),
            job_title=str(merged.get("title") or ""),
        )
        path = out_dir / f"{filename}.txt"
        path.write_text(self._build_archive_content(merged, greeting), encoding="utf-8")
        return path

    def _merge_row_with_raw_json(self, row: dict[str, Any]) -> dict[str, Any]:
        """把数据库字段与 raw_json 做轻量合并，保证归档内容尽可能完整。"""
        merged = dict(row)
        raw_json = row.get("raw_json")
        if not raw_json:
            return merged
        try:
            raw_data = json.loads(raw_json) or {}
        except Exception:
            return merged
        for key in ["title", "company", "salary", "city", "jd", "job_url", "greeting_message"]:
            if not merged.get(key) and raw_data.get(key):
                merged[key] = raw_data.get(key)
        return merged

    def _build_archive_filename(self, company_name: str, job_title: str) -> str:
        """生成适合人工查看的归档文件名。"""
        company = (company_name or "未知公司").strip()
        title = (job_title or "未知岗位").strip()
        raw_name = f"{company} - {title}"
        safe_name = re.sub(r'[<>:"/\\\\|?*\\r\\n]+', "_", raw_name)
        safe_name = re.sub(r"\s+", " ", safe_name).strip(" .")
        return safe_name[:120] or "未命名岗位"

    def _build_archive_content(self, row: dict[str, Any], greeting: str) -> str:
        """构建归档文件正文，方便后续人工复盘优化。"""
        cleaned_jd = self._clean_jd_text(str(row.get("jd") or ""))
        lines = [
            "=" * 60,
            "岗位信息",
            "=" * 60,
            f"公司: {row.get('company', '')}",
            f"岗位: {row.get('title', '')}",
            f"城市: {row.get('city', '')}",
            f"链接: {row.get('job_url', '')}",
            "",
            "=" * 60,
            "JD内容",
            "=" * 60,
            cleaned_jd,
            "",
            "=" * 60,
            "打招呼语",
            "=" * 60,
            (greeting or "").strip(),
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _clean_jd_text(text: str) -> str:
        """清洗归档 JD 中的样式片段、站点注水词和多余空白。"""
        cleaned = text or ""
        cleaned = re.sub(r"<style[^>]*>.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\.[A-Za-z0-9_-]+\{[^}]*\}", " ", cleaned)
        cleaned = re.sub(r"[A-Za-z0-9_-]+\{[^}]*\}", " ", cleaned)
        cleaned = re.sub(r"(BOSS直聘|直聘|boss|kanzhun|来自BOSS直聘)", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[\uE000-\uF8FF]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s*([：:；;，,。])\s*", r"\1", cleaned)
        return cleaned.strip()


__all__ = ["GreetingArchiveModel"]
