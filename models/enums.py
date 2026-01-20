"""
L1 Advisory Layer - 枚举定义

定义所有L1决策层使用的枚举类型
"""

from enum import Enum


class Decision(Enum):
    """交易决策"""
    LONG = "long"
    SHORT = "short"
    NO_TRADE = "no_trade"


class Confidence(Enum):
    """置信度（PR-005: 升级为4层）"""
    ULTRA = "ultra"      # 极高：TREND + GOOD + 强信号
    HIGH = "high"        # 高：TREND + GOOD，或 RANGE + GOOD + 强信号
    MEDIUM = "medium"    # 中：TREND + POOR，或 RANGE + GOOD
    LOW = "low"          # 低：其他情况


class TradeQuality(Enum):
    """交易质量（PR-004: 升级为3层）"""
    GOOD = "good"           # 质量好：明确的交易机会
    UNCERTAIN = "uncertain"  # 不确定：噪声市场，方向不明
    POOR = "poor"           # 质量差：明确的风险（吸纳、轮动等）


class MarketRegime(Enum):
    """市场环境"""
    TREND = "trend"      # 趋势市
    RANGE = "range"      # 震荡市
    EXTREME = "extreme"  # 极端行情


class SystemState(Enum):
    """系统状态"""
    INIT = "init"                  # 初始化
    WAIT = "wait"                  # 等待
    LONG_ACTIVE = "long_active"    # 做多激活
    SHORT_ACTIVE = "short_active"  # 做空激活
    COOL_DOWN = "cool_down"        # 冷却期
