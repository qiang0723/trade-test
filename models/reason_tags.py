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
    
    # P0-01 DataFix: 核心字段缺失的细粒度标签
    DATA_MISSING_PRICE = "data_missing_price"              # 价格缺失（必须阻断）
    DATA_MISSING_VOLUME = "data_missing_volume"            # 成交量缺失（降级）
    DATA_MISSING_FUNDING_RATE = "data_missing_funding_rate"  # 资金费率缺失（降级）
    DATA_MISSING_OPEN_INTEREST = "data_missing_open_interest"  # 持仓量缺失（降级）
    DATA_MISSING_TAKER_IMBALANCE = "data_missing_taker_imbalance"  # taker失衡缺失（降级）
    
    # P1-01 DataValidity: 无效值校验（值存在但非法）
    DATA_INVALID_PRICE = "data_invalid_price"              # 价格<=0（必须阻断）
    DATA_INVALID_VOLUME = "data_invalid_volume"            # 成交量<=0（阻断）
    DATA_INVALID_OI = "data_invalid_oi"                    # 持仓量<=0（阻断）
    
    # P1-01 DataValidity: 异常值校验（值合法但超出合理范围）
    DATA_OUTLIER_PRICE_CHANGE = "data_outlier_price_change"        # 价格变化>100%（降级+cap）
    DATA_OUTLIER_OI_CHANGE = "data_outlier_oi_change"              # 持仓量变化>100%（降级+cap）
    DATA_OUTLIER_TAKER_IMBALANCE = "data_outlier_taker_imbalance"  # taker失衡>100%（降级+cap）
    DATA_OUTLIER_FUNDING_RATE = "data_outlier_funding_rate"        # 资金费率异常（降级+cap）
    
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
    
    # P3-1 Dual Alignment仲裁
    ALIGNMENT_BONUS = "alignment_bonus"            # 双周期同向，置信度+1档
    TIMEFRAME_CONFLICT = "timeframe_conflict"      # 双周期反向，强制降级
    
    # ===== 决策频率控制类（PR-C）=====
    MIN_INTERVAL_BLOCK = "min_interval_block"
    FLIP_COOLDOWN_BLOCK = "flip_cooldown_block"
    
    # ===== 辅助信息类（非否决）=====
    HIGH_FUNDING_RATE = "high_funding_rate"
    LOW_FUNDING_RATE = "low_funding_rate"
    
    # P2-2 Funding三段式规则
    FUNDING_ELEVATED = "funding_elevated"          # |funding| 在 [f_low, f_high)，中等风险
    FUNDING_CROWDING = "funding_crowding"          # |funding| >= f_high + 顺势，高拥挤风险
    FUNDING_TAILWIND = "funding_tailwind"          # |funding| >= f_high + 逆势，逆风增益
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
    
    # ===== 三层触发状态类（PR-005新增 → P2-1语义细分）=====
    # 旧标签保留用于向后兼容
    LTF_CONFIRMED = "ltf_confirmed"                      # [Deprecated] 使用MTF_FULL
    LTF_PARTIAL_CONFIRM = "ltf_partial_confirm"          # [Deprecated] 使用MTF_PARTIAL_CONFIRM
    LTF_FAILED_CONFIRM = "ltf_failed_confirm"            # [Deprecated] 使用MTF_NO_TRIGGER
    LTF_CONTEXT_DENIED = "ltf_context_denied"            # [Deprecated] 使用MTF_DENIED
    
    # P2-1 MultiTF语义细分（新标签）
    MTF_FULL = "mtf_full"                          # 全确认：context✅ confirm✅ trigger✅
    MTF_NO_TRIGGER = "mtf_no_trigger"              # 无触发：context✅ confirm✅ trigger❌
    MTF_PARTIAL_CONFIRM = "mtf_partial_confirm"    # 部分确认：context✅ confirm部分
    MTF_DENIED = "mtf_denied"                      # 拒绝：context❌
    
    # ===== 数据增强信号类（Phase 1/2）=====
    # Phase 1.1: 资金费率极端反转
    FUNDING_EXTREME_REVERSAL = "funding_extreme_reversal"  # 资金费率极端+逆势→反转信号
    FUNDING_EXTREME_LONG = "funding_extreme_long"          # 极端负费率→做多潜力
    FUNDING_EXTREME_SHORT = "funding_extreme_short"        # 极端正费率→做空潜力
    
    # Phase 1.2: OI与价格背离
    OI_PRICE_DIVERGENCE_BULL = "oi_price_divergence_bull"  # 价格跌+OI涨→看涨背离（空头入场）
    OI_PRICE_DIVERGENCE_BEAR = "oi_price_divergence_bear"  # 价格涨+OI跌→看跌背离（多头出场）
    HEALTHY_UPTREND = "healthy_uptrend"                    # 健康上涨：price↑+OI↑
    HEALTHY_DOWNTREND = "healthy_downtrend"                # 健康下跌：price↓+OI↑
    
    # Phase 1.3: 多周期一致性
    TIMEFRAME_FULL_ALIGNMENT = "timeframe_full_alignment"  # 5m/15m/1h方向完全一致
    TIMEFRAME_PARTIAL_ALIGNMENT = "timeframe_partial_alignment"  # 部分周期一致
    
    # Phase 2: 大户多空比（预留）
    TOP_TRADER_LONG_BIAS = "top_trader_long_bias"          # 大户偏多（>55%）
    TOP_TRADER_SHORT_BIAS = "top_trader_short_bias"        # 大户偏空（>55%）
    TOP_TRADER_EXTREME_LONG = "top_trader_extreme_long"    # 大户极端偏多（>70%）→警惕反转
    TOP_TRADER_EXTREME_SHORT = "top_trader_extreme_short"  # 大户极端偏空（>70%）→警惕反转
    SMART_MONEY_DIVERGENCE = "smart_money_divergence"      # 大户与散户方向相反→跟随大户
    
    # ===== 第一批优化新增标签 =====
    # P0-1: 24h长期趋势
    LONG_TERM_UPTREND = "long_term_uptrend"                # 24h强势上涨（>5%）
    LONG_TERM_DOWNTREND = "long_term_downtrend"            # 24h强势下跌（<-5%）
    LONG_TERM_RANGE = "long_term_range"                    # 24h震荡（<2%）
    
    # P0-4: 1h放量确认
    VOLUME_SURGE_1H = "volume_surge_1h"                    # 1h大幅放量（>2x）
    VOLUME_MODERATE_1H = "volume_moderate_1h"              # 1h中度放量（>1.5x）
    VOLUME_LOW_1H = "volume_low_1h"                        # 1h缩量（<0.5x）


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
    
    # P0-01 DataFix: 核心字段缺失
    "data_missing_price": "❌ 价格缺失：无法获取当前价格，决策阻断",
    "data_missing_volume": "📊 成交量缺失：volume_24h字段缺失，信号质量降级",
    "data_missing_funding_rate": "💸 资金费率缺失：funding_rate字段缺失，信号质量降级",
    "data_missing_open_interest": "📈 持仓量缺失：open_interest字段缺失，信号质量降级",
    "data_missing_taker_imbalance": "⚖️ taker失衡缺失：taker_imbalance字段缺失，信号质量降级",
    
    # P1-01 DataValidity: 无效值
    "data_invalid_price": "🚫 价格无效：价格<=0，数据异常，决策阻断",
    "data_invalid_volume": "🚫 成交量无效：成交量<=0，数据异常，决策阻断",
    "data_invalid_oi": "🚫 持仓量无效：持仓量<=0，数据异常，决策阻断",
    
    # P1-01 DataValidity: 异常值
    "data_outlier_price_change": "⚠️ 价格变化异常：变化幅度>100%，可能为脏数据，置信度受限",
    "data_outlier_oi_change": "⚠️ 持仓量变化异常：变化幅度>100%，可能为脏数据，置信度受限",
    "data_outlier_taker_imbalance": "⚠️ taker失衡异常：失衡比例>100%，可能为脏数据，置信度受限",
    "data_outlier_funding_rate": "⚠️ 资金费率异常：费率超出合理范围，置信度受限",
    
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
    
    # P3-1 Dual Alignment仲裁
    "alignment_bonus": "✅ 双周期同向：短期与中期方向一致，信号质量增强",
    "timeframe_conflict": "⚠️ 周期冲突：短期与中期方向相反，降级执行",
    
    # 决策频率控制类（PR-C）
    "min_interval_block": "⏱️ 间隔过短：距离上次决策时间过短，防止频繁输出",
    "flip_cooldown_block": "🔄 翻转冷却：方向翻转冷却期内，防止频繁切换",
    
    # 辅助信息类
    "high_funding_rate": "💸 高资金费率：当前资金费率较高（辅助参考）",
    "low_funding_rate": "💰 低资金费率：当前资金费率较低（辅助参考）",
    
    # P2-2 Funding三段式
    "funding_elevated": "⚠️ 资金费率升高：费率在警戒区间，信号质量降级",
    "funding_crowding": "🚨 资金费率拥挤：费率极端且顺势开仓，高风险拥挤",
    "funding_tailwind": "🎯 资金费率逆风：费率极端但逆势开仓，潜在质量增益",
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
    
    # 三层触发状态类（PR-005新增 → P2-1语义细分）
    # 旧标签（向后兼容）
    "ltf_confirmed": "✅ [旧]三层确认：请使用mtf_full",
    "ltf_partial_confirm": "⚠️ [旧]部分确认：请使用mtf_partial_confirm",
    "ltf_failed_confirm": "❌ [旧]确认失败：请使用mtf_no_trigger",
    "ltf_context_denied": "🚫 [旧]Context拒绝：请使用mtf_denied",
    
    # P2-1 新标签
    "mtf_full": "✅ MultiTF全确认：1h方向+15m确认+5m触发全部满足（高质量信号）",
    "mtf_no_trigger": "⏸️ MultiTF无触发：1h方向+15m确认满足，但5m入场信号不足（等待时机）",
    "mtf_partial_confirm": "⚠️ MultiTF部分确认：1h方向满足，15m确认信号较弱（降级执行）",
    "mtf_denied": "🚫 MultiTF拒绝：1h方向不符（Context层否决）",
    
    # Phase 1.1: 资金费率极端反转
    "funding_extreme_reversal": "🔄 资金费率极端反转：费率极端+逆势开仓，高概率反转信号",
    "funding_extreme_long": "💰 极端负费率：空头拥挤，做多成本低，潜在做多机会",
    "funding_extreme_short": "💸 极端正费率：多头拥挤，做空收益高，潜在做空机会",
    
    # Phase 1.2: OI与价格背离
    "oi_price_divergence_bull": "📈 看涨背离：价格下跌但OI增长，新空头入场，可能反弹",
    "oi_price_divergence_bear": "📉 看跌背离：价格上涨但OI下降，多头获利出场，可能回调",
    "healthy_uptrend": "💚 健康上涨：价格上涨+OI增长，新资金入场确认趋势",
    "healthy_downtrend": "💔 健康下跌：价格下跌+OI增长，新空头入场确认趋势",
    
    # Phase 1.3: 多周期一致性
    "timeframe_full_alignment": "🎯 全周期一致：5m/15m/1h方向完全一致，高质量信号",
    "timeframe_partial_alignment": "⚡ 部分周期一致：多数周期方向一致，信号可参考",
    
    # Phase 2: 大户多空比
    "top_trader_long_bias": "🐋 大户偏多：前20%大户多单占比>55%，聪明钱看涨",
    "top_trader_short_bias": "🐋 大户偏空：前20%大户空单占比>55%，聪明钱看跌",
    "top_trader_extreme_long": "⚠️ 大户极端偏多：多单占比>70%，市场可能过热",
    "top_trader_extreme_short": "⚠️ 大户极端偏空：空单占比>70%，市场可能超卖",
    "smart_money_divergence": "🎯 聪明钱背离：大户与散户方向相反，跟随大户信号",
    
    # 第一批优化新增标签
    # P0-1: 24h长期趋势
    "long_term_uptrend": "📈 24h强势上涨：24小时涨幅>5%，中期趋势向上",
    "long_term_downtrend": "📉 24h强势下跌：24小时跌幅>5%，中期趋势向下",
    "long_term_range": "➡️ 24h震荡：24小时波动<2%，无明显中期方向",
    
    # P0-4: 1h放量确认
    "volume_surge_1h": "🔥 1h大幅放量：1小时成交量>2倍均值，资金强势进场",
    "volume_moderate_1h": "📊 1h中度放量：1小时成交量>1.5倍均值，资金有所增加",
    "volume_low_1h": "📉 1h缩量：1小时成交量<0.5倍均值，市场交投清淡",
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
    
    # P0-01 DataFix: 核心字段缺失
    ReasonTag.DATA_MISSING_PRICE: ExecutabilityLevel.BLOCK,           # 价格缺失必须阻断
    ReasonTag.DATA_MISSING_VOLUME: ExecutabilityLevel.DEGRADE,        # 成交量缺失降级
    ReasonTag.DATA_MISSING_FUNDING_RATE: ExecutabilityLevel.DEGRADE,  # 资金费率缺失降级
    ReasonTag.DATA_MISSING_OPEN_INTEREST: ExecutabilityLevel.DEGRADE, # 持仓量缺失降级
    ReasonTag.DATA_MISSING_TAKER_IMBALANCE: ExecutabilityLevel.DEGRADE,  # taker失衡缺失降级
    
    # P1-01 DataValidity: 无效值（必须阻断）
    ReasonTag.DATA_INVALID_PRICE: ExecutabilityLevel.BLOCK,   # 价格无效必须阻断
    ReasonTag.DATA_INVALID_VOLUME: ExecutabilityLevel.BLOCK,  # 成交量无效阻断
    ReasonTag.DATA_INVALID_OI: ExecutabilityLevel.BLOCK,      # 持仓量无效阻断
    
    # P1-01 DataValidity: 异常值（降级）
    ReasonTag.DATA_OUTLIER_PRICE_CHANGE: ExecutabilityLevel.DEGRADE,      # 价格变化异常降级
    ReasonTag.DATA_OUTLIER_OI_CHANGE: ExecutabilityLevel.DEGRADE,         # 持仓量变化异常降级
    ReasonTag.DATA_OUTLIER_TAKER_IMBALANCE: ExecutabilityLevel.DEGRADE,   # taker失衡异常降级
    ReasonTag.DATA_OUTLIER_FUNDING_RATE: ExecutabilityLevel.DEGRADE,      # 资金费率异常降级
    
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
    
    # P3-1 Dual Alignment仲裁
    ReasonTag.ALIGNMENT_BONUS: ExecutabilityLevel.ALLOW,     # 同向增益→不降级
    ReasonTag.TIMEFRAME_CONFLICT: ExecutabilityLevel.DEGRADE,  # 冲突→降级
    
    # 决策频率控制类（PR-C）- 阻断
    ReasonTag.MIN_INTERVAL_BLOCK: ExecutabilityLevel.BLOCK,
    ReasonTag.FLIP_COOLDOWN_BLOCK: ExecutabilityLevel.BLOCK,
    
    # 辅助信息类 - 不影响
    ReasonTag.HIGH_FUNDING_RATE: ExecutabilityLevel.ALLOW,
    ReasonTag.LOW_FUNDING_RATE: ExecutabilityLevel.ALLOW,
    
    # P2-2 Funding三段式
    ReasonTag.FUNDING_ELEVATED: ExecutabilityLevel.DEGRADE,   # 中等风险→降级
    ReasonTag.FUNDING_CROWDING: ExecutabilityLevel.DEGRADE,   # 高拥挤→降级（可配置为BLOCK）
    ReasonTag.FUNDING_TAILWIND: ExecutabilityLevel.ALLOW,     # 逆风增益→不降级
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
    
    # 三层触发状态类（PR-005新增 → P2-1语义细分）
    # 旧标签（向后兼容，但不推荐使用）
    ReasonTag.LTF_CONFIRMED: ExecutabilityLevel.ALLOW,         # [旧]三层确认
    ReasonTag.LTF_PARTIAL_CONFIRM: ExecutabilityLevel.DEGRADE, # [旧]部分确认
    ReasonTag.LTF_FAILED_CONFIRM: ExecutabilityLevel.BLOCK,    # [旧]确认失败
    ReasonTag.LTF_CONTEXT_DENIED: ExecutabilityLevel.BLOCK,    # [旧]Context拒绝
    
    # P2-1 新标签
    ReasonTag.MTF_FULL: ExecutabilityLevel.ALLOW,              # 全确认→正常执行
    ReasonTag.MTF_NO_TRIGGER: ExecutabilityLevel.DEGRADE,      # 无触发→降级（等待时机）
    ReasonTag.MTF_PARTIAL_CONFIRM: ExecutabilityLevel.DEGRADE, # 部分确认→降级
    ReasonTag.MTF_DENIED: ExecutabilityLevel.ALLOW,            # 拒绝→由decision=NO_TRADE自然DENY
    
    # ===== 数据增强信号类（Phase 1/2）=====
    # Phase 1.1: 资金费率极端反转 - 全部为正面信号
    ReasonTag.FUNDING_EXTREME_REVERSAL: ExecutabilityLevel.ALLOW,  # 反转信号→正面
    ReasonTag.FUNDING_EXTREME_LONG: ExecutabilityLevel.ALLOW,      # 极端负费率→做多潜力
    ReasonTag.FUNDING_EXTREME_SHORT: ExecutabilityLevel.ALLOW,     # 极端正费率→做空潜力
    
    # Phase 1.2: OI与价格背离 - 背离可能需要谨慎处理
    ReasonTag.OI_PRICE_DIVERGENCE_BULL: ExecutabilityLevel.ALLOW,  # 看涨背离→正面信号
    ReasonTag.OI_PRICE_DIVERGENCE_BEAR: ExecutabilityLevel.DEGRADE, # 看跌背离→降级（逆势风险）
    ReasonTag.HEALTHY_UPTREND: ExecutabilityLevel.ALLOW,           # 健康上涨→正面
    ReasonTag.HEALTHY_DOWNTREND: ExecutabilityLevel.ALLOW,         # 健康下跌→正面
    
    # Phase 1.3: 多周期一致性 - 全部为正面信号
    ReasonTag.TIMEFRAME_FULL_ALIGNMENT: ExecutabilityLevel.ALLOW,   # 全周期一致→正面
    ReasonTag.TIMEFRAME_PARTIAL_ALIGNMENT: ExecutabilityLevel.ALLOW, # 部分一致→正面
    
    # Phase 2: 大户多空比
    ReasonTag.TOP_TRADER_LONG_BIAS: ExecutabilityLevel.ALLOW,       # 大户偏多→正面
    ReasonTag.TOP_TRADER_SHORT_BIAS: ExecutabilityLevel.ALLOW,      # 大户偏空→正面
    ReasonTag.TOP_TRADER_EXTREME_LONG: ExecutabilityLevel.DEGRADE,  # 大户极端偏多→警惕反转
    ReasonTag.TOP_TRADER_EXTREME_SHORT: ExecutabilityLevel.DEGRADE, # 大户极端偏空→警惕反转
    ReasonTag.SMART_MONEY_DIVERGENCE: ExecutabilityLevel.ALLOW,     # 聪明钱背离→高质量信号
    
    # 第一批优化新增标签
    # P0-1: 24h长期趋势
    ReasonTag.LONG_TERM_UPTREND: ExecutabilityLevel.ALLOW,         # 24h上涨→正面信号
    ReasonTag.LONG_TERM_DOWNTREND: ExecutabilityLevel.ALLOW,       # 24h下跌→正面信号
    ReasonTag.LONG_TERM_RANGE: ExecutabilityLevel.ALLOW,           # 24h震荡→中性
    
    # P0-4: 1h放量确认
    ReasonTag.VOLUME_SURGE_1H: ExecutabilityLevel.ALLOW,           # 大幅放量→正面信号
    ReasonTag.VOLUME_MODERATE_1H: ExecutabilityLevel.ALLOW,        # 中度放量→正面信号
    ReasonTag.VOLUME_LOW_1H: ExecutabilityLevel.DEGRADE,           # 缩量→降级警告
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
