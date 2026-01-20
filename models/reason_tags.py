"""
L1 Advisory Layer - 决策原因标签

定义决策的所有可能原因标签及其中文解释
"""

from enum import Enum
from typing import Dict


class ExecutabilityLevel(Enum):
    """
    ReasonTag的执行阻断等级（PR-B）
    
    - ALLOW: 不影响执行
    - DEGRADE: 降级但允许执行（如NOISY_MARKET）
    - BLOCK: 阻断执行（如LIQUIDATION_PHASE）
    """
    ALLOW = "allow"
    DEGRADE = "degrade"
    BLOCK = "block"


class ReasonTag(Enum):
    """决策原因标签"""
    
    # ===== 数据验证 =====
    INVALID_DATA = "invalid_data"
    DATA_STALE = "data_stale"
    
    # ===== 风险否决类 =====
    EXTREME_REGIME = "extreme_regime"
    LIQUIDATION_PHASE = "liquidation_phase"
    CROWDING_RISK = "crowding_risk"
    EXTREME_VOLUME = "extreme_volume"
    
    # ===== 质量否决类 =====
    ABSORPTION_RISK = "absorption_risk"
    NOISY_MARKET = "noisy_market"
    ROTATION_RISK = "rotation_risk"
    WEAK_SIGNAL_IN_RANGE = "weak_signal_in_range"
    
    # ===== 方向冲突类 =====
    CONFLICTING_SIGNALS = "conflicting_signals"
    NO_CLEAR_DIRECTION = "no_clear_direction"
    
    # ===== 决策频率控制类（PR-C）=====
    MIN_INTERVAL_BLOCK = "min_interval_block"
    FLIP_COOLDOWN_BLOCK = "flip_cooldown_block"
    
    # ===== 辅助信息类（非否决）=====
    HIGH_FUNDING_RATE = "high_funding_rate"
    LOW_FUNDING_RATE = "low_funding_rate"
    STRONG_BUY_PRESSURE = "strong_buy_pressure"
    STRONG_SELL_PRESSURE = "strong_sell_pressure"
    OI_GROWING = "oi_growing"
    OI_DECLINING = "oi_declining"


# 中文解释映射
REASON_TAG_EXPLANATIONS = {
    # 数据验证
    "invalid_data": "❌ 数据无效：输入数据缺失或异常",
    "data_stale": "⏰ 数据过期：市场数据不够新鲜，可能缓存过期或API异常",
    
    # 风险否决类
    "extreme_regime": "🚨 极端行情：市场波动超过安全阈值，暂停交易",
    "liquidation_phase": "⚡ 清算阶段：价格急变且持仓量骤降，疑似大规模清算",
    "crowding_risk": "📊 拥挤风险：资金费率极端且持仓量快速增长，市场过度拥挤",
    "extreme_volume": "💥 极端成交量：成交量异常放大，可能存在异常波动",
    
    # 质量否决类
    "absorption_risk": "🎣 吸纳风险：买卖失衡严重但成交量低，可能是诱导性挂单",
    "noisy_market": "📡 噪音市场：资金费率波动大但无明确方向，市场信号混乱",
    "rotation_risk": "🔄 轮动风险：持仓量与价格走势背离，可能是资金轮动而非趋势",
    "weak_signal_in_range": "📉 震荡弱信号：震荡市中信号强度不足，不宜交易",
    
    # 方向冲突类
    "conflicting_signals": "⚠️ 信号冲突：做多做空信号同时出现，保守选择观望",
    "no_clear_direction": "🤷 方向不明：未检测到明确的做多或做空信号",
    
    # 决策频率控制类（PR-C）
    "min_interval_block": "⏱️ 间隔过短：距离上次决策时间过短，防止频繁输出",
    "flip_cooldown_block": "🔄 翻转冷却：方向翻转冷却期内，防止频繁切换",
    
    # 辅助信息类
    "high_funding_rate": "💸 高资金费率：当前资金费率较高（辅助参考）",
    "low_funding_rate": "💰 低资金费率：当前资金费率较低（辅助参考）",
    "strong_buy_pressure": "🟢 强买压：检测到强烈的买方力量",
    "strong_sell_pressure": "🔴 强卖压：检测到强烈的卖方力量",
    "oi_growing": "📈 持仓增长：持仓量持续增长",
    "oi_declining": "📉 持仓下降：持仓量持续下降",
}


def get_reason_tag_explanation(tag: ReasonTag) -> str:
    """
    获取reason tag的中文解释
    
    Args:
        tag: ReasonTag枚举值
    
    Returns:
        中文解释字符串
    """
    return REASON_TAG_EXPLANATIONS.get(tag.value, tag.value)


# ==========================================
# PR-B: ReasonTag的执行阻断等级映射
# ==========================================

REASON_TAG_EXECUTABILITY: Dict[ReasonTag, ExecutabilityLevel] = {
    # 数据验证 - 阻断
    ReasonTag.INVALID_DATA: ExecutabilityLevel.BLOCK,
    ReasonTag.DATA_STALE: ExecutabilityLevel.BLOCK,
    
    # 风险否决类 - 全部阻断
    ReasonTag.EXTREME_REGIME: ExecutabilityLevel.BLOCK,
    ReasonTag.LIQUIDATION_PHASE: ExecutabilityLevel.BLOCK,
    ReasonTag.CROWDING_RISK: ExecutabilityLevel.BLOCK,
    ReasonTag.EXTREME_VOLUME: ExecutabilityLevel.BLOCK,
    
    # 质量否决类 - POOR阻断，UNCERTAIN降级
    ReasonTag.ABSORPTION_RISK: ExecutabilityLevel.BLOCK,
    ReasonTag.ROTATION_RISK: ExecutabilityLevel.BLOCK,
    ReasonTag.NOISY_MARKET: ExecutabilityLevel.DEGRADE,      # 可降级
    ReasonTag.WEAK_SIGNAL_IN_RANGE: ExecutabilityLevel.DEGRADE,  # 可降级
    
    # 方向冲突类 - 阻断
    ReasonTag.CONFLICTING_SIGNALS: ExecutabilityLevel.BLOCK,
    ReasonTag.NO_CLEAR_DIRECTION: ExecutabilityLevel.BLOCK,
    
    # 决策频率控制类（PR-C）- 阻断
    ReasonTag.MIN_INTERVAL_BLOCK: ExecutabilityLevel.BLOCK,
    ReasonTag.FLIP_COOLDOWN_BLOCK: ExecutabilityLevel.BLOCK,
    
    # 辅助信息类 - 不影响
    ReasonTag.HIGH_FUNDING_RATE: ExecutabilityLevel.ALLOW,
    ReasonTag.LOW_FUNDING_RATE: ExecutabilityLevel.ALLOW,
    ReasonTag.STRONG_BUY_PRESSURE: ExecutabilityLevel.ALLOW,
    ReasonTag.STRONG_SELL_PRESSURE: ExecutabilityLevel.ALLOW,
    ReasonTag.OI_GROWING: ExecutabilityLevel.ALLOW,
    ReasonTag.OI_DECLINING: ExecutabilityLevel.ALLOW,
}


def has_blocking_tags(reason_tags: list) -> bool:
    """
    检查是否有阻断性标签（PR-B）
    
    Args:
        reason_tags: ReasonTag列表
    
    Returns:
        bool: 是否存在BLOCK级别的标签
    """
    return any(
        REASON_TAG_EXECUTABILITY.get(tag, ExecutabilityLevel.ALLOW) == ExecutabilityLevel.BLOCK
        for tag in reason_tags
    )


def has_degrading_tags(reason_tags: list) -> bool:
    """
    检查是否有降级标签（PR-B）
    
    Args:
        reason_tags: ReasonTag列表
    
    Returns:
        bool: 是否存在DEGRADE级别的标签
    """
    return any(
        REASON_TAG_EXECUTABILITY.get(tag, ExecutabilityLevel.ALLOW) == ExecutabilityLevel.DEGRADE
        for tag in reason_tags
    )


def get_reason_tag_category(tag: ReasonTag) -> str:
    """
    获取reason tag的分类（用于前端染色）
    
    Args:
        tag: ReasonTag枚举值
    
    Returns:
        分类名称: risk-deny, quality-deny, conflict, state-constraint, info, positive
    """
    risk_deny_tags = [
        ReasonTag.EXTREME_REGIME,
        ReasonTag.LIQUIDATION_PHASE,
        ReasonTag.CROWDING_RISK,
        ReasonTag.EXTREME_VOLUME,
        ReasonTag.INVALID_DATA,
        ReasonTag.DATA_STALE
    ]
    
    quality_deny_tags = [
        ReasonTag.ABSORPTION_RISK,
        ReasonTag.NOISY_MARKET,
        ReasonTag.ROTATION_RISK,
        ReasonTag.WEAK_SIGNAL_IN_RANGE
    ]
    
    conflict_tags = [
        ReasonTag.CONFLICTING_SIGNALS,
        ReasonTag.NO_CLEAR_DIRECTION
    ]
    
    frequency_control_tags = [
        ReasonTag.MIN_INTERVAL_BLOCK,
        ReasonTag.FLIP_COOLDOWN_BLOCK
    ]
    
    positive_tags = [
        ReasonTag.STRONG_BUY_PRESSURE,
        ReasonTag.STRONG_SELL_PRESSURE,
        ReasonTag.OI_GROWING
    ]
    
    if tag in risk_deny_tags:
        return "risk-deny"
    elif tag in quality_deny_tags:
        return "quality-deny"
    elif tag in conflict_tags:
        return "conflict"
    elif tag in frequency_control_tags:
        return "frequency-control"
    elif tag in positive_tags:
        return "positive"
    else:
        return "info"
