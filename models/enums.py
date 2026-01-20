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


class ExecutionPermission(Enum):
    """
    执行许可级别（方案D：三级执行许可）
    
    用于区分不同风险等级的交易建议，对应 ReasonTag 的 ExecutabilityLevel：
    - ALLOW: 正常执行（无降级标签，无阻断标签）
    - ALLOW_REDUCED: 降级执行（有 DEGRADE 级别标签，如 NOISY_MARKET，使用更严格门槛）
    - DENY: 拒绝执行（有 BLOCK 级别标签，如 EXTREME_VOLUME，永远不可执行）
    
    双门槛机制：
    - ALLOW: 要求 min_confidence_normal (默认 HIGH/ULTRA)
    - ALLOW_REDUCED: 要求 min_confidence_reduced (默认 MEDIUM 及以上)
    - DENY: 永远 executable=False
    """
    ALLOW = "allow"                    # 正常执行
    ALLOW_REDUCED = "allow_reduced"    # 降级执行（更严格门槛）
    DENY = "deny"                      # 拒绝执行
