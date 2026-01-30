"""
P3-2: DecisionTrace - 统一决策追溯结构

用途：日志/测试/回放使用同一格式

包含：
- inputs_digest: 输入摘要（symbol+tf+coverage+关键指标hash）
- stage_tags: 按阶段分组的标签
- permission/confidence/executable
- key_metrics: 触发相关的关键指标
- thresholds_version: 配置版本
"""

import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from models.enums import Decision, Confidence, ExecutionPermission, MarketRegime
from models.reason_tags import ReasonTag


# ==========================================
# key_metrics 白名单定义
# ==========================================

KEY_METRICS_WHITELIST = [
    # 价格变化
    'price_change_5m',
    'price_change_15m',
    'price_change_1h',
    'price_change_6h',
    
    # Taker失衡
    'taker_imbalance_5m',
    'taker_imbalance_15m',
    'taker_imbalance_1h',
    
    # OI变化
    'oi_change_15m',
    'oi_change_1h',
    'oi_change_6h',
    
    # 成交量比率
    'volume_ratio_5m',
    'volume_ratio_15m',
    'volume_ratio_1h',
    
    # 资金费率
    'funding_rate',
    
    # 覆盖度
    'short_evaluable',
    'medium_evaluable',
]


@dataclass
class StageTagGroup:
    """按阶段分组的标签"""
    regime: List[str] = field(default_factory=list)       # 市场环境相关
    risk: List[str] = field(default_factory=list)         # 风险准入相关
    quality: List[str] = field(default_factory=list)      # 交易质量相关
    direction: List[str] = field(default_factory=list)    # 方向评估相关
    funding: List[str] = field(default_factory=list)      # 资金费率相关
    mtf: List[str] = field(default_factory=list)          # MultiTF相关
    alignment: List[str] = field(default_factory=list)    # Alignment相关
    gate: List[str] = field(default_factory=list)         # 频率控制相关
    data: List[str] = field(default_factory=list)         # 数据质量相关
    
    def to_dict(self) -> Dict[str, List[str]]:
        return {
            'regime': self.regime,
            'risk': self.risk,
            'quality': self.quality,
            'direction': self.direction,
            'funding': self.funding,
            'mtf': self.mtf,
            'alignment': self.alignment,
            'gate': self.gate,
            'data': self.data,
        }


@dataclass
class DecisionTrace:
    """
    决策追溯结构（P3-2）
    
    用于：
    - 线上日志输出
    - 测试断言
    - 异常信号回放定位
    """
    
    # 输入摘要
    symbol: str
    timeframe: str                          # 'SHORT_TERM' / 'MEDIUM_TERM'
    inputs_digest: str                       # 关键输入的hash摘要
    
    # 按阶段分组的标签
    stage_tags: StageTagGroup = field(default_factory=StageTagGroup)
    
    # 决策输出
    decision: str = 'no_trade'
    permission: str = 'DENY'
    confidence: str = 'LOW'
    executable: bool = False
    
    # 关键指标（白名单过滤后）
    key_metrics: Dict[str, Any] = field(default_factory=dict)
    
    # 配置版本
    thresholds_version: str = 'unknown'
    
    # 时间戳
    timestamp: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """转换为字典（用于JSON输出）"""
        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'inputs_digest': self.inputs_digest,
            'stage_tags': self.stage_tags.to_dict(),
            'decision': self.decision,
            'permission': self.permission,
            'confidence': self.confidence,
            'executable': self.executable,
            'key_metrics': self.key_metrics,
            'thresholds_version': self.thresholds_version,
            'timestamp': self.timestamp or datetime.now().isoformat(),
        }


def classify_tags_by_stage(tags: List[ReasonTag]) -> StageTagGroup:
    """
    按阶段分类标签
    
    Args:
        tags: ReasonTag列表
    
    Returns:
        StageTagGroup
    """
    stage_tags = StageTagGroup()
    
    # 标签分类规则
    regime_prefixes = ['extreme_regime', 'trend', 'range']
    risk_prefixes = ['liquidation', 'crowding_risk', 'extreme_volume']
    quality_prefixes = ['absorption', 'noisy', 'rotation', 'weak_signal']
    direction_prefixes = ['strong_buy', 'strong_sell', 'conflicting', 'no_clear']
    funding_prefixes = ['funding', 'high_funding', 'low_funding']
    mtf_prefixes = ['mtf_', 'ltf_']
    alignment_prefixes = ['alignment', 'timeframe_conflict']
    gate_prefixes = ['min_interval', 'flip_cooldown']
    data_prefixes = ['data_', 'invalid_data']
    
    for tag in tags:
        tag_value = tag.value if hasattr(tag, 'value') else str(tag)
        
        # 按前缀分类
        if any(tag_value.startswith(p) for p in data_prefixes):
            stage_tags.data.append(tag_value)
        elif any(tag_value.startswith(p) for p in regime_prefixes):
            stage_tags.regime.append(tag_value)
        elif any(tag_value.startswith(p) for p in risk_prefixes):
            stage_tags.risk.append(tag_value)
        elif any(tag_value.startswith(p) for p in quality_prefixes):
            stage_tags.quality.append(tag_value)
        elif any(tag_value.startswith(p) for p in direction_prefixes):
            stage_tags.direction.append(tag_value)
        elif any(tag_value.startswith(p) for p in funding_prefixes):
            stage_tags.funding.append(tag_value)
        elif any(tag_value.startswith(p) for p in mtf_prefixes):
            stage_tags.mtf.append(tag_value)
        elif any(tag_value.startswith(p) for p in alignment_prefixes):
            stage_tags.alignment.append(tag_value)
        elif any(tag_value.startswith(p) for p in gate_prefixes):
            stage_tags.gate.append(tag_value)
        else:
            # 默认归类到direction
            stage_tags.direction.append(tag_value)
    
    return stage_tags


def extract_key_metrics(features, coverage=None) -> Dict[str, Any]:
    """
    从features中提取key_metrics（白名单过滤）
    
    Args:
        features: MarketFeatures对象
        coverage: CoverageInfo对象（可选）
    
    Returns:
        key_metrics字典
    """
    metrics = {}
    
    # 价格变化
    if features.price:
        if features.price.price_change_5m is not None:
            metrics['price_change_5m'] = round(features.price.price_change_5m, 4)
        if features.price.price_change_15m is not None:
            metrics['price_change_15m'] = round(features.price.price_change_15m, 4)
        if features.price.price_change_1h is not None:
            metrics['price_change_1h'] = round(features.price.price_change_1h, 4)
        if features.price.price_change_6h is not None:
            metrics['price_change_6h'] = round(features.price.price_change_6h, 4)
    
    # Taker失衡
    if features.taker_imbalance:
        if features.taker_imbalance.taker_imbalance_5m is not None:
            metrics['taker_imbalance_5m'] = round(features.taker_imbalance.taker_imbalance_5m, 4)
        if features.taker_imbalance.taker_imbalance_15m is not None:
            metrics['taker_imbalance_15m'] = round(features.taker_imbalance.taker_imbalance_15m, 4)
        if features.taker_imbalance.taker_imbalance_1h is not None:
            metrics['taker_imbalance_1h'] = round(features.taker_imbalance.taker_imbalance_1h, 4)
    
    # OI变化
    if features.open_interest:
        if features.open_interest.oi_change_15m is not None:
            metrics['oi_change_15m'] = round(features.open_interest.oi_change_15m, 4)
        if features.open_interest.oi_change_1h is not None:
            metrics['oi_change_1h'] = round(features.open_interest.oi_change_1h, 4)
        if features.open_interest.oi_change_6h is not None:
            metrics['oi_change_6h'] = round(features.open_interest.oi_change_6h, 4)
    
    # 成交量比率
    if features.volume:
        if features.volume.volume_ratio_5m is not None:
            metrics['volume_ratio_5m'] = round(features.volume.volume_ratio_5m, 4)
        if features.volume.volume_ratio_15m is not None:
            metrics['volume_ratio_15m'] = round(features.volume.volume_ratio_15m, 4)
    
    # 资金费率
    if features.funding and features.funding.funding_rate is not None:
        metrics['funding_rate'] = round(features.funding.funding_rate, 6)
    
    # 覆盖度
    if coverage:
        metrics['short_evaluable'] = coverage.short_evaluable
        metrics['medium_evaluable'] = coverage.medium_evaluable
    
    return metrics


def compute_inputs_digest(symbol: str, timeframe: str, key_metrics: Dict) -> str:
    """
    计算输入摘要的hash
    
    Args:
        symbol: 交易对符号
        timeframe: 时间框架
        key_metrics: 关键指标
    
    Returns:
        8位hash摘要
    """
    import json
    digest_input = f"{symbol}|{timeframe}|{json.dumps(key_metrics, sort_keys=True)}"
    return hashlib.sha256(digest_input.encode()).hexdigest()[:8]


def create_decision_trace(
    symbol: str,
    timeframe: str,
    features,
    coverage,
    decision: Decision,
    permission: ExecutionPermission,
    confidence: Confidence,
    executable: bool,
    reason_tags: List[ReasonTag],
    thresholds_version: str = 'unknown'
) -> DecisionTrace:
    """
    创建DecisionTrace（便捷函数）
    
    Args:
        symbol: 交易对符号
        timeframe: 时间框架
        features: MarketFeatures
        coverage: CoverageInfo
        decision: 决策
        permission: 执行权限
        confidence: 置信度
        executable: 是否可执行
        reason_tags: 原因标签
        thresholds_version: 配置版本
    
    Returns:
        DecisionTrace
    """
    # 提取key_metrics
    key_metrics = extract_key_metrics(features, coverage)
    
    # 计算inputs_digest
    inputs_digest = compute_inputs_digest(symbol, timeframe, key_metrics)
    
    # 分类标签
    stage_tags = classify_tags_by_stage(reason_tags)
    
    return DecisionTrace(
        symbol=symbol,
        timeframe=timeframe,
        inputs_digest=inputs_digest,
        stage_tags=stage_tags,
        decision=decision.value if hasattr(decision, 'value') else str(decision),
        permission=permission.value if hasattr(permission, 'value') else str(permission),
        confidence=confidence.value if hasattr(confidence, 'value') else str(confidence),
        executable=executable,
        key_metrics=key_metrics,
        thresholds_version=thresholds_version,
        timestamp=datetime.now().isoformat()
    )
