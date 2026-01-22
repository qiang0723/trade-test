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
    """
    系统状态（简化版：L1咨询层不维护持仓状态）
    
    L1作为纯咨询层，只输出决策建议，不涉及持仓管理。
    因此移除了 LONG_ACTIVE/SHORT_ACTIVE/COOL_DOWN 等持仓语义状态。
    反抖动功能由 DecisionMemory（PR-C）实现。
    """
    INIT = "init"  # 初始化
    WAIT = "wait"  # 等待（默认状态）


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


class LTFStatus(Enum):
    """
    低时间框架（LTF）多周期触发状态（PR-005）
    
    三层触发（1h Context → 15m Confirm → 5m Trigger）的综合状态：
    - CONFIRMED: 三层全部满足，高质量信号
    - PARTIAL: Context满足，Confirm部分满足，降级执行
    - FAILED: Context满足，但Confirm或Trigger失败
    - MISSING: 数据不完整（klines历史不足）
    - NOT_APPLICABLE: Context层方向不允许
    """
    CONFIRMED = "confirmed"              # 全部确认
    PARTIAL = "partial"                  # 部分确认（降级）
    FAILED = "failed"                    # 确认失败
    MISSING = "missing"                  # 数据缺失
    NOT_APPLICABLE = "not_applicable"    # Context不允许


class Timeframe(Enum):
    """
    时间周期（PR-DUAL: 双周期独立结论）
    
    L1同时输出短期和中长期两套独立结论
    """
    SHORT_TERM = "short_term"      # 短期：5m/15m 数据驱动
    MEDIUM_TERM = "medium_term"    # 中长期：1h/6h 数据驱动


class AlignmentType(Enum):
    """
    双周期一致性类型（PR-DUAL + PATCH-P0-04）
    
    描述短期和中长期结论的关系：
    - BOTH_LONG: 两者都看多
    - BOTH_SHORT: 两者都看空
    - BOTH_NO_TRADE: 两者都不交易
    - CONFLICT_LONG_SHORT: 冲突 - 短期多/中长期空
    - CONFLICT_SHORT_LONG: 冲突 - 短期空/中长期多
    - PARTIAL_LONG: 一方看多，一方不交易
    - PARTIAL_SHORT: 一方看空，一方不交易
    - SHORT_ONLY: 仅短期可用（中期数据缺口）- PATCH-P0-04
    - MID_ONLY: 仅中期可用（短期数据缺口，罕见）- PATCH-P0-04
    - NONE_AVAILABLE: 都不可用 - PATCH-P0-04
    """
    BOTH_LONG = "both_long"                    # 一致看多
    BOTH_SHORT = "both_short"                  # 一致看空
    BOTH_NO_TRADE = "both_no_trade"            # 一致不交易
    CONFLICT_LONG_SHORT = "conflict_long_short"  # 冲突：短期多/中长期空
    CONFLICT_SHORT_LONG = "conflict_short_long"  # 冲突：短期空/中长期多
    PARTIAL_LONG = "partial_long"              # 部分看多
    PARTIAL_SHORT = "partial_short"            # 部分看空
    SHORT_ONLY = "short_only"                  # PATCH-P0-04: 仅短期可用（中期缺口）
    MID_ONLY = "mid_only"                      # PATCH-P0-04: 仅中期可用（短期缺口）
    NONE_AVAILABLE = "none_available"          # PATCH-P0-04: 都不可用


class ConflictResolution(Enum):
    """
    冲突处理策略（PR-DUAL）
    
    当短期和中长期结论冲突时的处理方式：
    - FOLLOW_MEDIUM_TERM: 跟随中长期（更稳健）
    - FOLLOW_SHORT_TERM: 跟随短期（更激进）
    - NO_TRADE: 冲突时不交易（最保守）
    - FOLLOW_HIGHER_CONFIDENCE: 跟随置信度更高的一方
    """
    FOLLOW_MEDIUM_TERM = "follow_medium_term"
    FOLLOW_SHORT_TERM = "follow_short_term"
    NO_TRADE = "no_trade"
    FOLLOW_HIGHER_CONFIDENCE = "follow_higher_confidence"
