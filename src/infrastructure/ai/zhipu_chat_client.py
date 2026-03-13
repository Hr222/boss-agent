"""智谱AI客户端模块"""
import json

from typing import Any, Optional
from zai import ZaiClient

from src.config.settings import Config


class ZhipuChatClient:
    """智谱AI客户端"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化客户端

        Args:
            api_key: API密钥，如果不传则从配置读取
        """
        self.api_key = api_key or Config.get_llm_api_key()
        if not self.api_key:
            raise ValueError("请设置 ZAI_API_KEY 环境变量")

        self.client = ZaiClient(
            api_key=self.api_key,
            base_url=Config.ZAI_BASE_URL,
        )

    def chat(
        self,
        messages: list,
        model: str = "glm-5",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        调用聊天API

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            模型回复
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                thinking={"type": "disabled"},
            )
            return self._extract_response_text(response)
        except Exception as e:
            raise Exception(f"智谱AI调用失败: {e}")

    def _extract_response_text(self, response: Any) -> str:
        """兼容不同响应结构，尽量稳定提取模型文本。"""
        try:
            message = response.choices[0].message
        except Exception as e:
            raise Exception(f"响应结构异常，无法读取 message: {e}")

        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str) and item.strip():
                    text_parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    if item.get("type") == "text" and item.get("text"):
                        text_parts.append(str(item["text"]).strip())
                    elif item.get("content"):
                        text_parts.append(str(item["content"]).strip())
                    continue
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if text:
                    text_parts.append(str(text).strip())
            merged = "\n".join(part for part in text_parts if part)
            if merged.strip():
                return merged.strip()

        raise Exception(f"模型返回为空，finish_reason={getattr(response.choices[0], 'finish_reason', None)}")

    def analyze_jd_match(
        self,
        jd_text: str,
        resume_text: str,
        rule_precheck: dict | None = None,
    ) -> str:
        """
        分析JD与简历的匹配度

        Args:
            jd_text: 职位描述文本
            resume_text: 简历文本

        Returns:
            分析结果（JSON格式）
        """
        rule_precheck = rule_precheck or {}
        hard_gaps = rule_precheck.get("hard_gaps", [])
        hard_gap_text = "；".join(hard_gaps) if hard_gaps else "无明显硬性缺口"
        prompt = f"""你是一个严格、审慎的技术招聘顾问。请分析以下职位描述(JD)与简历的匹配度。

职位描述(JD):
{jd_text}

简历:
{resume_text}

规则预筛结果（这是必须遵守的硬约束，不允许忽略）:
- JD要求语言: {', '.join(rule_precheck.get("required_languages", [])) or '未识别'}
- 已匹配语言: {', '.join(rule_precheck.get("matched_languages", [])) or '暂无'}
- 缺失语言: {', '.join(rule_precheck.get("missing_languages", [])) or '无'}
- 语言深度硬缺口: {', '.join(rule_precheck.get("hard_language_gaps", [])) or '无'}
- 普通语言差异: {', '.join(rule_precheck.get("soft_language_gaps", [])) or '无'}
- JD要求框架: {', '.join(rule_precheck.get("required_frameworks", [])) or '未识别'}
- 缺失框架: {', '.join(rule_precheck.get("missing_frameworks", [])) or '无'}
- JD最低年限: {rule_precheck.get("required_years", 0)} 年
- 简历年限: {rule_precheck.get("resume_years", 0)} 年
- 年限差距: {rule_precheck.get("years_gap", 0)} 年
- 硬性缺口: {hard_gap_text}
- 分数上限: {rule_precheck.get("cap_score", 100)}
- 是否禁止推荐: {"是" if rule_precheck.get("must_not_recommend") else "否"}

请以JSON格式返回分析结果，包含以下字段：
{{
    "match_score": 匹配度分数(0-100),
    "match_level": "高"或"中"或"低",
    "matched_skills": ["匹配的技能1", "匹配的技能2", ...],
    "missing_skills": ["缺失的技能1", "缺失的技能2", ...],
    "matched_experience": ["匹配的经验1", "匹配的经验2", ...],
    "advantages": ["个人优势匹配点1", "个人优势匹配点2", ...],
    "analysis": "详细匹配分析(3-5句话)",
    "suggestions": ["求职建议1", "求职建议2", ...],
    "is_recommended": true/false
}}

请严格遵守以下评分与推荐规则：

1. 总体原则
- 宁可保守，不要默认高分。
- 如果JD信息不完整，可以说明不确定性，但不能因此直接给高分。
- 只有“核心技能、核心经验、业务场景”三者都较匹配时，才能给高分。

2. 分数区间解释
- 90-100：高度匹配。JD中的核心技术栈、关键经验、业务场景基本都能在简历中直接对应。
- 75-89：较匹配。具备大部分核心要求，但仍有少量非关键缺口。
- 60-74：部分匹配。只有部分核心要求匹配，存在明显缺口，需要转岗学习成本。
- 40-59：较低匹配。只匹配到少量通用技能，JD要求与简历主体不一致。
- 0-39：不匹配。核心技术栈或核心经历明显不符。

2.1 `match_level` 输出规则
- 只能输出 `"高"`、`"中"`、`"低"` 三个值，绝不允许输出其他词。
- 当 `match_score >= 80` 时，`match_level` 必须为 `"高"`。
- 当 `60 <= match_score < 80` 时，`match_level` 必须为 `"中"`。
- 当 `match_score < 60` 时，`match_level` 必须为 `"低"`。

3. 必须降分的情况
- JD明确要求某些硬性技术，而简历中没有直接证据支持。
- JD强调特定语言/框架/领域经验，而候选人只有泛化能力，没有直接项目证明。
- JD要求年限、行业背景、业务场景经验，简历无法支撑。
- JD偏多语言岗位（如 C/C++/Java 为主），而候选人只匹配其中次要部分。

3.1 硬约束打分规则
- 如果缺少JD中的语言，但只是“语言差异”且没有体现出精通/熟练/底层原理/关键生态要求，可以保守降分，但不要直接判定为硬性不匹配。
- 如果缺少JD中的关键语言能力，且 JD 明确要求精通、熟练、底层原理、语言特性、源码、虚拟机、关键生态/框架经验，则 `match_score` 不得高于 70。
- 如果缺少JD中的关键框架或关键平台能力，`match_score` 不得高于 75。
- 如果年限要求明确高于候选人实际年限，且差距 >= 1 年，`match_score` 不得高于 75。
- 如果同时存在两个及以上硬性缺口，`match_score` 不得高于 65。
- 如果岗位主体并不是 Python 后端，而候选人只是部分沾边，`match_score` 应落在 40-65 区间。

4. `matched_skills` 与 `missing_skills` 规则
- `matched_skills` 只能写“JD中明确提到，且简历中也明确出现”的技能。
- 不要把简历里有、但JD没要求的技能写进 `matched_skills`。
- `missing_skills` 只写JD中的核心缺口，不要泛滥罗列。

5. `matched_experience` 与 `advantages` 规则
- 必须基于简历中的真实内容，不要虚构经历。
- 如果JD提到高并发、团队管理、某行业场景，只有简历里明确提到才能算匹配。

6. `is_recommended` 判定规则
- 只有在 `match_score >= 75` 且不存在明显硬性门槛缺失时，才允许为 `true`。
- 如果缺少JD中的关键语言能力、关键框架、关键行业经验、关键年限要求，则必须为 `false`。
- 如果只是普通语言差异，但候选人其余核心能力明显匹配，可以继续结合整体证据判断是否推荐。
- 不要因为候选人“学习能力强”就直接推荐。
- 如果同时存在两个及以上硬性缺口，则 `is_recommended` 必须为 `false`。
- 如果 `match_score < 75`，则 `is_recommended` 必须为 `false`。

7. 输出要求
- `analysis` 要解释为什么得这个分，重点说明“匹配点”和“硬伤”。
- `suggestions` 要有针对性，说明候选人下一步该如何补强或面试中该如何应对。
- 如果判定为推荐，必须说明“为什么关键要求已满足”。
- 如果判定为不推荐，必须明确指出“哪几个硬性门槛不满足”。
- 你的 `match_score` 不允许超过“规则预筛结果”里的“分数上限”。
- 如果“是否禁止推荐”为“是”，则 `is_recommended` 必须为 `false`。

请确保返回的是有效的JSON格式，不要包含其他内容，不要使用 Markdown 代码块。"""

        messages = [
            {
                "role": "system",
                "content": "你是一个严格的技术招聘顾问。你不会默认给高分，只有在证据充分时才会判断高匹配和推荐投递。"
            },
            {"role": "user", "content": prompt}
        ]

        return self.chat(messages, temperature=0.3)
