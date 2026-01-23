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
    DATA_INCOMPLETE = "data_incomplete"        # PR-003: 数据不完整（启动期或历史不足）
    DATA_INCOMPLETE_LTF = "data_incomplete_ltf"  # PATCH-P0-3: 短期关键字段缺失（5m/15m）
    DATA_INCOMPLETE_MTF = "data_incomplete_mtf"  # PATCH-P0-3: 中期关键字段缺失（1h/6h）
    DATA_GAP_5M = "data_gap_5m"                # PATCH-2: 5分钟窗口数据缺口过大
    DATA_GAP_15M = "data_gap_15m"              # PATCH-2: 15分钟窗口数据缺口过大
    DATA_GAP_1H = "data_gap_1h"                # PATCH-2: 1小时窗口数据缺口过大
    DATA_GAP_6H = "data_gap_6h"                # PATCH-2: 6小时窗口数据缺口过大
    MTF_DEGRADED_TO_1H = "mtf_degraded_to_1h"  # P0-CodeFix-2: 中期降级为1h-only评估（6h缺失）
    
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
    
    # ===== 短期机会识别类（v3.2新增）=====
    SHORT_TERM_TREND = "short_term_trend"                # 短期趋势（1h>2%）
    RANGE_SHORT_TERM_LONG = "range_short_term_long"      # RANGE短期做多机会
    RANGE_SHORT_TERM_SHORT = "range_short_term_short"    # RANGE短期做空机会
    SHORT_TERM_PRICE_SURGE = "short_term_price_surge"    # 短期价格上涨
    SHORT_TERM_PRICE_DROP = "short_term_price_drop"      # 短期价格下跌
    SHORT_TERM_STRONG_BUY = "short_term_strong_buy"      # 短期强买压
    SHORT_TERM_STRONG_SELL = "short_term_strong_sell"    # 短期强卖压
    
    # ===== 三层触发状态类（PR-005新增）=====
    LTF_CONFIRMED = "ltf_confirmed"                      # 低时间框架确认（1h+15m+5m）
    LTF_PARTIAL_CONFIRM = "ltf_partial_confirm"          # 部分确认（Confirm弱）
    LTF_FAILED_CONFIRM = "ltf_failed_confirm"            # 确认失败
    LTF_CONTEXT_DENIED = "ltf_context_denied"            # Context层不允许该方向


# 中文解释映射
REASON_TAG_EXPLANATIONS = {
    # 数据验证
    "invalid_data": "❌ 数据无效：输入数据缺失或异常",
    "data_stale": "⏰ 数据过期：市场数据不够新鲜，可能缓存过期或API异常",
    "data_incomplete": "📊 数据不完整：历史数据不足（启动初期或缓存清空），无法准确计算",
    "data_incomplete_ltf": "📊 短期数据不完整：5m/15m关键字段缺失，短期决策无法进行",
    "data_incomplete_mtf": "📊 中期数据不完整：1h/6h关键字段缺失，中期信号质量下降",
    "data_gap_5m": "⏳ 5分钟数据缺口：历史点与目标时间gap过大，lookback失败",
    "data_gap_15m": "⏳ 15分钟数据缺口：历史点与目标时间gap过大，lookback失败",
    "data_gap_1h": "⏳ 1小时数据缺口：历史点与目标时间gap过大，lookback失败",
    "data_gap_6h": "⏳ 6小时数据缺口：历史点与目标时间gap过大，lookback失败",
    "mtf_degraded_to_1h": "⚠️ 中期降级：6h数据缺失，降级为1h-only评估（置信度受限）",
    
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
    
    # 短期机会识别类（v3.2新增）
    "short_term_trend": "⚡ 短期趋势：1小时快速走势（>2%），捕获短期机会",
    "range_short_term_long": "🎯 震荡短期做多：综合信号强势做多机会（3选2确认）",
    "range_short_term_short": "🎯 震荡短期做空：综合信号强势做空机会（3选2确认）",
    "short_term_price_surge": "💨 短期价格上涨：1小时涨幅>1.5%",
    "short_term_price_drop": "💨 短期价格下跌：1小时跌幅>1.5%",
    "short_term_strong_buy": "🔥 短期强买压：买卖失衡>65%",
    "short_term_strong_sell": "🔥 短期强卖压：买卖失衡<-65%",
    
    # 三层触发状态类（PR-005新增）
    "ltf_confirmed": "✅ 三层确认：1h方向+15m确认+5m触发全部满足（高质量信号）",
    "ltf_partial_confirm": "⚠️ 部分确认：Context满足但Confirm信号较弱（降级执行）",
    "ltf_failed_confirm": "❌ 确认失败：Context满足但15m/5m信号不足（短期机会取消）",
    "ltf_context_denied": "🚫 Context拒绝：1h方向与信号不符（方向冲突）",
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
    ReasonTag.DATA_INCOMPLETE_LTF: ExecutabilityLevel.BLOCK,    # PATCH-P0-3: 短期关键字段缺失，阻断
    ReasonTag.DATA_INCOMPLETE_MTF: ExecutabilityLevel.DEGRADE,  # PATCH-P0-3: 中期关键字段缺失，降级
    ReasonTag.DATA_GAP_5M: ExecutabilityLevel.BLOCK,      # PATCH-2: 5分钟数据缺口阻断短期决策
    ReasonTag.DATA_GAP_15M: ExecutabilityLevel.BLOCK,     # PATCH-2: 15分钟数据缺口阻断短期决策
    ReasonTag.DATA_GAP_1H: ExecutabilityLevel.DEGRADE,    # PATCH-2: 1小时数据缺口降级（不完全阻断）
    ReasonTag.DATA_GAP_6H: ExecutabilityLevel.DEGRADE,    # PATCH-2: 6小时数据缺口降级
    ReasonTag.MTF_DEGRADED_TO_1H: ExecutabilityLevel.DEGRADE,  # P0-CodeFix-2: 中期降级为1h-only
    
    # 风险否决类 - 全部阻断
    ReasonTag.EXTREME_REGIME: ExecutabilityLevel.BLOCK,
    ReasonTag.LIQUIDATION_PHASE: ExecutabilityLevel.BLOCK,
    ReasonTag.CROWDING_RISK: ExecutabilityLevel.BLOCK,
    ReasonTag.EXTREME_VOLUME: ExecutabilityLevel.DEGRADE,  # PR-007: 改为DEGRADE，联立时才DENY
    
    # 质量否决类 - POOR阻断，UNCERTAIN降级
    # 注意：ABSORPTION_RISK 和 ROTATION_RISK 被设置为 BLOCK（更保守，等价于风险否决类）
    # 双重保护机制：POOR硬短路 + BLOCK标签 → DENY → 即使强信号也无法绕过
    ReasonTag.ABSORPTION_RISK: ExecutabilityLevel.BLOCK,   # deny_tags等价物
    ReasonTag.ROTATION_RISK: ExecutabilityLevel.BLOCK,     # deny_tags等价物
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
    
    # 数据质量类（补充）
    ReasonTag.DATA_INCOMPLETE: ExecutabilityLevel.DEGRADE,     # 数据不完整，降级执行（不完全阻断）
    
    # 短期机会识别类（v3.2）- 全部为正面信号，不影响执行
    ReasonTag.SHORT_TERM_TREND: ExecutabilityLevel.ALLOW,          # 短期趋势信号
    ReasonTag.RANGE_SHORT_TERM_LONG: ExecutabilityLevel.ALLOW,     # 震荡短期做多
    ReasonTag.RANGE_SHORT_TERM_SHORT: ExecutabilityLevel.ALLOW,    # 震荡短期做空
    ReasonTag.SHORT_TERM_PRICE_SURGE: ExecutabilityLevel.ALLOW,    # 短期价格上涨
    ReasonTag.SHORT_TERM_PRICE_DROP: ExecutabilityLevel.ALLOW,     # 短期价格下跌
    ReasonTag.SHORT_TERM_STRONG_BUY: ExecutabilityLevel.ALLOW,     # 短期强买压
    ReasonTag.SHORT_TERM_STRONG_SELL: ExecutabilityLevel.ALLOW,    # 短期强卖压
    
    # 三层触发状态类（PR-005新增）
    ReasonTag.LTF_CONFIRMED: ExecutabilityLevel.ALLOW,         # 三层确认，正常执行
    ReasonTag.LTF_PARTIAL_CONFIRM: ExecutabilityLevel.DEGRADE, # 部分确认，降级执行
    ReasonTag.LTF_FAILED_CONFIRM: ExecutabilityLevel.BLOCK,    # 确认失败，阻断执行
    ReasonTag.LTF_CONTEXT_DENIED: ExecutabilityLevel.BLOCK,    # Context拒绝，阻断执行
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
