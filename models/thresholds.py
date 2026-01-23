"""
L1 Advisory Layer - 强类型配置阈值对象 (PR-ARCH-03)

负责：
1. 将YAML配置编译为强类型dataclass对象
2. 提供类型安全的阈值访问
3. 便于IDE自动补全和重构
4. 配置版本追溯

设计原则：
- 使用dataclass（Python 3.7+标准库）
- 字段类型明确（float/int/bool/str/List）
- 嵌套结构反映YAML层次
- 不可变对象（frozen=True，防止运行时修改）
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ==========================================
# Symbol Universe（币种宇宙）
# ==========================================

@dataclass(frozen=True)
class SymbolUniverse:
    """币种宇宙配置"""
    enabled_symbols: List[str]
    default_symbol: str


# ==========================================
# 定时更新配置
# ==========================================

@dataclass(frozen=True)
class PeriodicUpdate:
    """定时更新配置"""
    enabled: bool
    interval_minutes: int
    market_type: str  # "futures" or "spot"


# ==========================================
# 数据保留策略
# ==========================================

@dataclass(frozen=True)
class DataRetention:
    """数据保留策略"""
    keep_hours: int
    cleanup_interval_hours: int


# ==========================================
# 错误处理
# ==========================================

@dataclass(frozen=True)
class ErrorHandling:
    """错误处理配置"""
    max_retries: int
    retry_delay_seconds: int
    continue_on_error: bool


# ==========================================
# 数据质量阈值
# ==========================================

@dataclass(frozen=True)
class DataQuality:
    """数据质量阈值"""
    max_staleness_seconds: int


# ==========================================
# 决策频率控制
# ==========================================

@dataclass(frozen=True)
class DecisionControl:
    """决策频率控制配置"""
    min_decision_interval_seconds: int
    flip_cooldown_seconds: int
    enable_min_interval: bool
    enable_flip_cooldown: bool


# ==========================================
# 市场环境识别阈值
# ==========================================

@dataclass(frozen=True)
class MarketRegime:
    """市场环境识别阈值"""
    extreme_price_change_1h: float
    trend_price_change_6h: float
    short_term_trend_1h: float


# ==========================================
# 风险准入阈值
# ==========================================

@dataclass(frozen=True)
class LiquidationThreshold:
    """清算阶段检测阈值"""
    price_change: float
    oi_drop: float


@dataclass(frozen=True)
class CrowdingThreshold:
    """拥挤风险检测阈值"""
    funding_abs: float
    oi_growth: float


@dataclass(frozen=True)
class ExtremeVolumeThreshold:
    """极端成交量检测阈值"""
    multiplier: float


@dataclass(frozen=True)
class RiskExposure:
    """风险准入阈值"""
    liquidation: LiquidationThreshold
    crowding: CrowdingThreshold
    extreme_volume: ExtremeVolumeThreshold


# ==========================================
# 交易质量阈值
# ==========================================

@dataclass(frozen=True)
class AbsorptionThreshold:
    """吸纳风险阈值"""
    imbalance: float
    volume_ratio: float


@dataclass(frozen=True)
class NoiseThreshold:
    """噪音市场阈值"""
    funding_volatility: float
    funding_abs: float


@dataclass(frozen=True)
class RotationThreshold:
    """轮动风险阈值"""
    price_threshold: float
    oi_threshold: float


@dataclass(frozen=True)
class RangeWeakThreshold:
    """震荡市弱信号阈值"""
    imbalance: float
    oi: float


@dataclass(frozen=True)
class TradeQuality:
    """交易质量阈值"""
    absorption: AbsorptionThreshold
    noise: NoiseThreshold
    rotation: RotationThreshold
    range_weak: RangeWeakThreshold


# ==========================================
# 方向评估阈值
# ==========================================

@dataclass(frozen=True)
class DirectionalThreshold:
    """方向阈值（LONG或SHORT）"""
    imbalance: float
    oi_change: float
    price_change: Optional[float] = None  # trend模式有，range模式可能没有


@dataclass(frozen=True)
class ShortTermOpportunityThreshold:
    """短期机会识别阈值"""
    min_price_change_1h: float
    min_oi_change_1h: float
    min_taker_imbalance: float
    min_buy_sell_imbalance: float  # 兼容旧键名
    required_signals: int


@dataclass(frozen=True)
class TrendThresholds:
    """趋势市阈值"""
    long: DirectionalThreshold
    short: DirectionalThreshold


@dataclass(frozen=True)
class RangeThresholds:
    """震荡市阈值"""
    long: DirectionalThreshold
    short: DirectionalThreshold
    short_term_opportunity: Dict[str, ShortTermOpportunityThreshold]  # {"long": ..., "short": ...}


@dataclass(frozen=True)
class Direction:
    """方向评估阈值"""
    trend: TrendThresholds
    range: RangeThresholds


# ==========================================
# 置信度配置
# ==========================================

@dataclass(frozen=True)
class ConfidenceThresholdsMap:
    """置信度档位映射"""
    ultra: int
    high: int
    medium: int


@dataclass(frozen=True)
class ConfidenceCaps:
    """置信度硬降级上限"""
    uncertain_quality_max: str  # "HIGH"/"MEDIUM"/etc.
    reduce_default_max: str
    tag_caps: Dict[str, str]


@dataclass(frozen=True)
class StrongSignalBoost:
    """强信号突破配置"""
    enabled: bool
    boost_levels: int
    required_tags: List[str]


@dataclass(frozen=True)
class ConfidenceScoring:
    """置信度配置"""
    decision_score: int
    regime_trend_score: int
    regime_range_score: int
    regime_extreme_score: int
    quality_good_score: int
    quality_uncertain_score: int
    quality_poor_score: int
    strong_signal_bonus: int
    thresholds: ConfidenceThresholdsMap
    caps: ConfidenceCaps
    strong_signal_boost: StrongSignalBoost


# ==========================================
# ReasonTag分类规则
# ==========================================

@dataclass(frozen=True)
class ReasonTagRules:
    """ReasonTag分类规则"""
    reduce_tags: List[str]
    deny_tags: List[str]


# ==========================================
# 执行控制
# ==========================================

@dataclass(frozen=True)
class ExecutableControl:
    """执行控制配置"""
    min_confidence_normal: str  # "HIGH"/"ULTRA"/etc.
    min_confidence_reduced: str  # "MEDIUM"/"HIGH"/etc.


# ==========================================
# 辅助标签阈值
# ==========================================

@dataclass(frozen=True)
class AuxiliaryTags:
    """辅助标签阈值"""
    oi_growing_threshold: float
    oi_declining_threshold: float
    funding_rate_threshold: float


# ==========================================
# 多周期三层触发配置
# ==========================================

@dataclass(frozen=True)
class ContextThreshold:
    """Context层（1h）阈值"""
    min_price_change: Optional[float] = None  # LONG用
    max_price_change: Optional[float] = None  # SHORT用
    min_taker_imbalance: Optional[float] = None  # LONG用
    max_taker_imbalance: Optional[float] = None  # SHORT用
    min_oi_change: float = 0.0
    required_signals: int = 2


@dataclass(frozen=True)
class ConfirmThreshold:
    """Confirm层（15m）阈值"""
    min_price_change: Optional[float] = None  # LONG用
    max_price_change: Optional[float] = None  # SHORT用
    min_taker_imbalance: Optional[float] = None  # LONG用
    max_taker_imbalance: Optional[float] = None  # SHORT用
    min_volume_ratio: float = 1.0
    min_oi_change: float = 0.0
    required_confirmed: int = 2
    required_partial: int = 1


@dataclass(frozen=True)
class TriggerThreshold:
    """Trigger层（5m）阈值"""
    min_price_change: Optional[float] = None  # LONG用
    max_price_change: Optional[float] = None  # SHORT用
    min_taker_imbalance: Optional[float] = None  # LONG用
    max_taker_imbalance: Optional[float] = None  # SHORT用
    min_volume_ratio: float = 1.0
    required_signals: int = 2


@dataclass(frozen=True)
class BindingPolicy:
    """绑定策略"""
    short_term_opportunity_requires_confirmed: bool
    partial_action: str  # "degrade"/"allow"/"deny"
    failed_short_term_action: str  # "cancel"/etc.
    failed_long_term_action: str  # "degrade"/etc.


@dataclass(frozen=True)
class MultiTF:
    """多周期三层触发配置"""
    enabled: bool
    context_1h: Dict[str, ContextThreshold]  # {"long": ..., "short": ...}
    confirm_15m: Dict[str, ConfirmThreshold]  # {"long": ..., "short": ...}
    trigger_5m: Dict[str, TriggerThreshold]  # {"long": ..., "short": ...}
    binding_policy: BindingPolicy


# ==========================================
# 双周期独立结论配置
# ==========================================

@dataclass(frozen=True)
class MinPriceChange15m:
    """动态阈值：15m价格变化"""
    dynamic: bool
    trend: float
    range: float
    extreme: float
    default: float


@dataclass(frozen=True)
class ShortTermThresholds:
    """短期评估（5m/15m）阈值"""
    min_price_change_15m: MinPriceChange15m
    min_taker_imbalance: float
    min_volume_ratio: float
    min_oi_change_15m: float
    required_signals: int


@dataclass(frozen=True)
class ConflictResolution:
    """冲突处理策略"""
    default_strategy: str  # "no_trade"/"follow_medium_term"/etc.


@dataclass(frozen=True)
class AlignmentBonus:
    """一致性加成"""
    confidence_boost: int
    relax_executable_threshold: bool


@dataclass(frozen=True)
class DualTimeframe:
    """双周期独立结论配置"""
    enabled: bool
    short_term: ShortTermThresholds
    conflict_resolution: ConflictResolution
    alignment_bonus: AlignmentBonus


# ==========================================
# 双周期决策频率控制
# ==========================================

@dataclass(frozen=True)
class DualDecisionControl:
    """双周期决策频率控制"""
    short_term_interval_seconds: int
    short_term_flip_cooldown_seconds: int
    medium_term_interval_seconds: int
    medium_term_flip_cooldown_seconds: int
    alignment_flip_cooldown_seconds: int


# ==========================================
# 顶层Thresholds对象
# ==========================================

@dataclass(frozen=True)
class Thresholds:
    """
    L1 Advisory Layer 配置阈值（强类型）
    
    所有配置段的强类型封装，提供：
    - 类型安全访问
    - IDE自动补全
    - 重构友好
    - 配置版本追溯
    """
    # 基础配置
    symbol_universe: SymbolUniverse
    periodic_update: PeriodicUpdate
    data_retention: DataRetention
    error_handling: ErrorHandling
    data_quality: DataQuality
    
    # 决策控制
    decision_control: DecisionControl
    dual_decision_control: DualDecisionControl
    
    # 市场评估
    market_regime: MarketRegime
    risk_exposure: RiskExposure
    trade_quality: TradeQuality
    
    # 方向评估
    direction: Direction
    
    # 置信度与执行
    confidence_scoring: ConfidenceScoring
    reason_tag_rules: ReasonTagRules
    executable_control: ExecutableControl
    
    # 辅助配置
    auxiliary_tags: AuxiliaryTags
    multi_tf: MultiTF
    dual_timeframe: DualTimeframe
    
    # 版本信息（用于追溯）
    version: str  # 配置hash或版本号
    
    def __post_init__(self):
        """初始化后验证（可选）"""
        # 可在此添加跨字段验证逻辑
        # 例如：确保 flip_cooldown >= min_interval
        pass


# ==========================================
# 工具函数
# ==========================================

def get_thresholds_version_info(thresholds: Thresholds) -> Dict[str, str]:
    """
    获取配置版本信息（用于输出/日志）
    
    Returns:
        Dict包含版本号、编译时间等信息
    """
    return {
        "thresholds_version": thresholds.version,
        "enabled_symbols": ",".join(thresholds.symbol_universe.enabled_symbols),
        "dual_timeframe_enabled": str(thresholds.dual_timeframe.enabled),
        "multi_tf_enabled": str(thresholds.multi_tf.enabled)
    }
