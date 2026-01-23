"""
PR-ARCH-01: FeatureSnapshot DTO

强类型市场特征快照，统一线上/回测/测试的特征表示。

目标：
1. 特征单一真相：所有特征生成走同一管道，确保口径一致
2. 强类型：IDE自动补全，编译时检查
3. 覆盖度可见：lookback实际值、gap、缺失窗口明确标注
4. 可追溯：保留转换记录、数据源时间戳、特征版本

设计原则：
- 所有百分比字段统一为小数格式（如0.05 = 5%）
- None表示字段不可用（不使用0伪装）
- 窗口明确：5m/15m/1h/6h/24h
- evaluable标志：short_evaluable/medium_evaluable
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


class FeatureVersion(str, Enum):
    """特征版本枚举（追溯演进）"""
    V1_BASELINE = "v1_baseline"          # 基础版本
    V2_P0_CODEFIX = "v2_p0_codefix"      # P0-CodeFix增强版
    V3_ARCH01 = "v3_arch01"              # PR-ARCH-01版本（当前）


@dataclass
class PriceFeatures:
    """价格变化特征（小数格式）"""
    # 短周期
    price_change_5m: Optional[float] = None      # 5分钟价格变化率
    price_change_15m: Optional[float] = None     # 15分钟价格变化率
    price_change_1h: Optional[float] = None      # 1小时价格变化率
    
    # 中周期
    price_change_6h: Optional[float] = None      # 6小时价格变化率
    
    # 长周期
    price_change_24h: Optional[float] = None     # 24小时价格变化率
    
    # 当前价格
    current_price: Optional[float] = None        # 当前价格


@dataclass
class OpenInterestFeatures:
    """持仓量变化特征（小数格式）"""
    oi_change_15m: Optional[float] = None        # 15分钟持仓量变化率
    oi_change_1h: Optional[float] = None         # 1小时持仓量变化率
    oi_change_6h: Optional[float] = None         # 6小时持仓量变化率
    
    current_oi: Optional[float] = None           # 当前持仓量


@dataclass
class TakerImbalanceFeatures:
    """主动买卖失衡特征（无量纲，范围[-1, 1]）"""
    taker_imbalance_5m: Optional[float] = None   # 5分钟主动买卖失衡
    taker_imbalance_15m: Optional[float] = None  # 15分钟主动买卖失衡
    taker_imbalance_1h: Optional[float] = None   # 1小时主动买卖失衡


@dataclass
class VolumeFeatures:
    """成交量特征"""
    volume_1h: Optional[float] = None            # 1小时成交量
    volume_24h: Optional[float] = None           # 24小时成交量
    volume_ratio_5m: Optional[float] = None      # 5分钟成交量比率
    volume_ratio_15m: Optional[float] = None     # 15分钟成交量比率


@dataclass
class FundingFeatures:
    """资金费率特征（小数格式）"""
    funding_rate: Optional[float] = None         # 当前资金费率
    funding_rate_prev: Optional[float] = None    # 上一周期资金费率（用于计算波动）


@dataclass
class MarketFeatures:
    """市场特征集合（包含所有特征子集）"""
    price: PriceFeatures = field(default_factory=PriceFeatures)
    open_interest: OpenInterestFeatures = field(default_factory=OpenInterestFeatures)
    taker_imbalance: TakerImbalanceFeatures = field(default_factory=TakerImbalanceFeatures)
    volume: VolumeFeatures = field(default_factory=VolumeFeatures)
    funding: FundingFeatures = field(default_factory=FundingFeatures)
    
    def to_flat_dict(self) -> Dict[str, Optional[float]]:
        """
        转换为扁平字典（兼容旧代码）
        
        Returns:
            扁平化的特征字典，键名与旧版本一致
        """
        flat = {}
        
        # Price features
        if self.price.price_change_5m is not None:
            flat['price_change_5m'] = self.price.price_change_5m
        if self.price.price_change_15m is not None:
            flat['price_change_15m'] = self.price.price_change_15m
        if self.price.price_change_1h is not None:
            flat['price_change_1h'] = self.price.price_change_1h
        if self.price.price_change_6h is not None:
            flat['price_change_6h'] = self.price.price_change_6h
        if self.price.price_change_24h is not None:
            flat['price_change_24h'] = self.price.price_change_24h
        if self.price.current_price is not None:
            flat['price'] = self.price.current_price
        
        # OI features
        if self.open_interest.oi_change_15m is not None:
            flat['oi_change_15m'] = self.open_interest.oi_change_15m
        if self.open_interest.oi_change_1h is not None:
            flat['oi_change_1h'] = self.open_interest.oi_change_1h
        if self.open_interest.oi_change_6h is not None:
            flat['oi_change_6h'] = self.open_interest.oi_change_6h
        if self.open_interest.current_oi is not None:
            flat['open_interest'] = self.open_interest.current_oi
        
        # Taker imbalance features
        if self.taker_imbalance.taker_imbalance_5m is not None:
            flat['taker_imbalance_5m'] = self.taker_imbalance.taker_imbalance_5m
        if self.taker_imbalance.taker_imbalance_15m is not None:
            flat['taker_imbalance_15m'] = self.taker_imbalance.taker_imbalance_15m
        if self.taker_imbalance.taker_imbalance_1h is not None:
            flat['taker_imbalance_1h'] = self.taker_imbalance.taker_imbalance_1h
        
        # Volume features
        if self.volume.volume_1h is not None:
            flat['volume_1h'] = self.volume.volume_1h
        if self.volume.volume_24h is not None:
            flat['volume_24h'] = self.volume.volume_24h
        if self.volume.volume_ratio_5m is not None:
            flat['volume_ratio_5m'] = self.volume.volume_ratio_5m
        if self.volume.volume_ratio_15m is not None:
            flat['volume_ratio_15m'] = self.volume.volume_ratio_15m
        
        # Funding features
        if self.funding.funding_rate is not None:
            flat['funding_rate'] = self.funding.funding_rate
        
        return flat


@dataclass
class CoverageInfo:
    """
    数据覆盖度信息（P0-CodeFix增强）
    
    记录实际lookback、gap、缺失窗口，支持降级决策
    """
    # 短周期覆盖度
    lookback_actual_seconds_5m: Optional[float] = None     # 5分钟实际回溯秒数
    lookback_gap_seconds_5m: Optional[float] = None        # 5分钟gap秒数
    
    lookback_actual_seconds_15m: Optional[float] = None    # 15分钟实际回溯秒数
    lookback_gap_seconds_15m: Optional[float] = None       # 15分钟gap秒数
    
    lookback_actual_seconds_1h: Optional[float] = None     # 1小时实际回溯秒数
    lookback_gap_seconds_1h: Optional[float] = None        # 1小时gap秒数
    
    # 中周期覆盖度
    lookback_actual_seconds_6h: Optional[float] = None     # 6小时实际回溯秒数
    lookback_gap_seconds_6h: Optional[float] = None        # 6小时gap秒数
    
    # 缺失窗口列表
    missing_windows: List[str] = field(default_factory=list)  # 缺失的窗口（如["6h", "24h"]）
    
    # 可评估性标志（P0-CodeFix核心）
    short_evaluable: bool = True      # 短周期是否可评估（5m/15m/1h至少一个可用）
    medium_evaluable: bool = True     # 中周期是否可评估（6h可用 或 允许1h降级）
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'lookback_actual_seconds_5m': self.lookback_actual_seconds_5m,
            'lookback_gap_seconds_5m': self.lookback_gap_seconds_5m,
            'lookback_actual_seconds_15m': self.lookback_actual_seconds_15m,
            'lookback_gap_seconds_15m': self.lookback_gap_seconds_15m,
            'lookback_actual_seconds_1h': self.lookback_actual_seconds_1h,
            'lookback_gap_seconds_1h': self.lookback_gap_seconds_1h,
            'lookback_actual_seconds_6h': self.lookback_actual_seconds_6h,
            'lookback_gap_seconds_6h': self.lookback_gap_seconds_6h,
            'missing_windows': self.missing_windows,
            'short_evaluable': self.short_evaluable,
            'medium_evaluable': self.medium_evaluable,
        }


@dataclass
class FeatureMetadata:
    """特征元数据"""
    feature_version: FeatureVersion = FeatureVersion.V3_ARCH01  # 特征版本
    percentage_format: str = "decimal"                          # 百分比格式（decimal/percent_point）
    
    # 数据源时间戳
    source_timestamp: Optional[datetime] = None                 # 数据源时间戳
    generated_at: datetime = field(default_factory=datetime.now)  # 生成时间
    
    # 数据源标识
    symbol: str = ""                                           # 交易对符号
    exchange: str = "binance"                                  # 交易所
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'feature_version': self.feature_version.value,
            'percentage_format': self.percentage_format,
            'source_timestamp': self.source_timestamp.isoformat() if self.source_timestamp else None,
            'generated_at': self.generated_at.isoformat(),
            'symbol': self.symbol,
            'exchange': self.exchange,
        }


@dataclass
class FeatureTrace:
    """
    特征生成追溯信息（可选）
    
    用于调试、审计、问题定位
    """
    # 规范化追溯
    normalization_trace: Optional[Dict] = None     # 来自MetricsNormalizer的trace
    
    # 数据查询追溯
    lookback_queries: Dict[str, Dict] = field(default_factory=dict)  # 各窗口的lookback查询结果
    
    # 范围校验
    range_validation: Dict[str, bool] = field(default_factory=dict)  # 字段范围校验结果
    
    # 警告/错误
    warnings: List[str] = field(default_factory=list)          # 警告信息
    errors: List[str] = field(default_factory=list)            # 错误信息
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'normalization_trace': self.normalization_trace,
            'lookback_queries': self.lookback_queries,
            'range_validation': self.range_validation,
            'warnings': self.warnings,
            'errors': self.errors,
        }


@dataclass
class FeatureSnapshot:
    """
    市场特征快照（PR-ARCH-01核心DTO）
    
    统一线上/回测/测试的特征表示，确保口径一致。
    
    特性：
    1. 强类型：所有字段类型明确，IDE自动补全
    2. None-safe：缺失字段用None表示，不使用0伪装
    3. 覆盖度可见：lookback/gap/missing_windows明确
    4. 可追溯：保留转换/查询/校验记录
    5. 向后兼容：to_flat_dict()转换为旧格式
    """
    features: MarketFeatures = field(default_factory=MarketFeatures)
    coverage: CoverageInfo = field(default_factory=CoverageInfo)
    metadata: FeatureMetadata = field(default_factory=FeatureMetadata)
    trace: Optional[FeatureTrace] = None  # 可选追溯信息
    
    def to_dict(self) -> Dict:
        """
        转换为完整字典（用于输出/日志）
        
        Returns:
            包含所有信息的字典
        """
        result = {
            'features': self.features.to_flat_dict(),
            'coverage': self.coverage.to_dict(),
            'metadata': self.metadata.to_dict(),
        }
        
        if self.trace:
            result['trace'] = self.trace.to_dict()
        
        return result
    
    def to_legacy_format(self) -> Dict:
        """
        转换为旧版格式（完全兼容旧代码）
        
        Returns:
            扁平化字典 + coverage字段
        """
        result = self.features.to_flat_dict()
        
        # 添加coverage信息（旧代码使用）
        result['_coverage'] = self.coverage.to_dict()
        result['_metadata'] = self.metadata.to_dict()
        
        return result


# ============================================
# 便捷构造函数
# ============================================

def create_empty_snapshot(symbol: str) -> FeatureSnapshot:
    """
    创建空快照（所有特征为None）
    
    用途：数据完全不可用时的占位符
    
    Args:
        symbol: 交易对符号
        
    Returns:
        空特征快照
    """
    metadata = FeatureMetadata(symbol=symbol)
    coverage = CoverageInfo(
        short_evaluable=False,
        medium_evaluable=False,
        missing_windows=['5m', '15m', '1h', '6h', '24h']
    )
    
    return FeatureSnapshot(
        features=MarketFeatures(),
        coverage=coverage,
        metadata=metadata,
    )


def create_degraded_snapshot(
    symbol: str,
    available_features: Dict[str, float],
    missing_windows: List[str]
) -> FeatureSnapshot:
    """
    创建降级快照（部分特征可用）
    
    用途：数据部分缺失时的降级表示
    
    Args:
        symbol: 交易对符号
        available_features: 可用的特征字典
        missing_windows: 缺失的窗口列表
        
    Returns:
        降级特征快照
    """
    # 构建特征对象
    features = MarketFeatures()
    
    # Price features
    if 'price_change_5m' in available_features:
        features.price.price_change_5m = available_features['price_change_5m']
    if 'price_change_15m' in available_features:
        features.price.price_change_15m = available_features['price_change_15m']
    if 'price_change_1h' in available_features:
        features.price.price_change_1h = available_features['price_change_1h']
    if 'price_change_6h' in available_features:
        features.price.price_change_6h = available_features['price_change_6h']
    if 'price' in available_features:
        features.price.current_price = available_features['price']
    
    # OI features
    if 'oi_change_15m' in available_features:
        features.open_interest.oi_change_15m = available_features['oi_change_15m']
    if 'oi_change_1h' in available_features:
        features.open_interest.oi_change_1h = available_features['oi_change_1h']
    if 'oi_change_6h' in available_features:
        features.open_interest.oi_change_6h = available_features['oi_change_6h']
    if 'open_interest' in available_features:
        features.open_interest.current_oi = available_features['open_interest']
    
    # Taker imbalance
    if 'taker_imbalance_5m' in available_features:
        features.taker_imbalance.taker_imbalance_5m = available_features['taker_imbalance_5m']
    if 'taker_imbalance_15m' in available_features:
        features.taker_imbalance.taker_imbalance_15m = available_features['taker_imbalance_15m']
    if 'taker_imbalance_1h' in available_features:
        features.taker_imbalance.taker_imbalance_1h = available_features['taker_imbalance_1h']
    
    # Volume
    if 'volume_1h' in available_features:
        features.volume.volume_1h = available_features['volume_1h']
    if 'volume_24h' in available_features:
        features.volume.volume_24h = available_features['volume_24h']
    if 'volume_ratio_5m' in available_features:
        features.volume.volume_ratio_5m = available_features['volume_ratio_5m']
    if 'volume_ratio_15m' in available_features:
        features.volume.volume_ratio_15m = available_features['volume_ratio_15m']
    
    # Funding
    if 'funding_rate' in available_features:
        features.funding.funding_rate = available_features['funding_rate']
    
    # 构建覆盖度信息
    coverage = CoverageInfo(
        missing_windows=missing_windows,
        short_evaluable='5m' not in missing_windows or '15m' not in missing_windows or '1h' not in missing_windows,
        medium_evaluable='6h' not in missing_windows or ('1h' not in missing_windows and '6h_degraded' in available_features)
    )
    
    # 构建元数据
    metadata = FeatureMetadata(symbol=symbol)
    
    return FeatureSnapshot(
        features=features,
        coverage=coverage,
        metadata=metadata,
    )
