"""岗位策略集合。"""

from src.models.strategies.backend_ai_strategy import BackendAIStrategy
from src.models.strategies.frontend_strategy import FrontendStrategy
from src.models.strategies.legal_strategy import LegalStrategy
from src.models.strategies.strategy_factory import StrategyFactory
from src.models.strategies.ui_design_strategy import UIDesignStrategy

__all__ = ["BackendAIStrategy", "FrontendStrategy", "LegalStrategy", "UIDesignStrategy", "StrategyFactory"]
