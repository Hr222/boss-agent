"""岗位策略工厂：统一创建与列出可选策略。"""

from __future__ import annotations

from src.models.resume_profile import ResumeProfile
from src.models.strategies.backend_ai_strategy import BackendAIStrategy
from src.models.strategies.candidate_strategy import CandidateStrategy
from src.models.strategies.frontend_strategy import FrontendStrategy
from src.models.strategies.legal_strategy import LegalStrategy
from src.models.strategies.ui_design_strategy import UIDesignStrategy


class StrategyFactory:
    """统一管理岗位策略实例。"""

    _strategy_map = {
        BackendAIStrategy.strategy_id: BackendAIStrategy,
        FrontendStrategy.strategy_id: FrontendStrategy,
        LegalStrategy.strategy_id: LegalStrategy,
        UIDesignStrategy.strategy_id: UIDesignStrategy,
    }

    @classmethod
    def create(cls, strategy_id: str) -> CandidateStrategy:
        """按策略 ID 创建实例。"""
        if strategy_id == "auto":
            raise ValueError("auto 需要通过 create_auto() 解析。")
        strategy_cls = cls._strategy_map.get(strategy_id, BackendAIStrategy)
        return strategy_cls()

    @classmethod
    def create_auto(cls, resume: ResumeProfile | None) -> CandidateStrategy:
        """根据简历内容自动选择最可能的策略。"""
        if resume is None:
            return BackendAIStrategy()
        for strategy_cls in [LegalStrategy, UIDesignStrategy, FrontendStrategy, BackendAIStrategy]:
            strategy = strategy_cls()
            if strategy.infer_from_resume(resume):
                return strategy
        return BackendAIStrategy()

    @classmethod
    def options(cls) -> list[tuple[str, str]]:
        """返回控制台展示所需的策略选项。"""
        return [
            (BackendAIStrategy.strategy_id, BackendAIStrategy.display_name),
            (FrontendStrategy.strategy_id, FrontendStrategy.display_name),
            (UIDesignStrategy.strategy_id, UIDesignStrategy.display_name),
            (LegalStrategy.strategy_id, LegalStrategy.display_name),
            ("auto", "自动识别"),
        ]


__all__ = ["StrategyFactory"]
