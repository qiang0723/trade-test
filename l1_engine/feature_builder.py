"""
PR-ARCH-01: FeatureBuilder/MarketFeaturePipeline

特征生成管道的单一入口，确保线上/回测/测试使用相同的特征生成逻辑。

目标：
1. 特征生成单一真相：所有环境（线上/回测/测试）使用同一管道
2. 强类型输出：返回FeatureSnapshot（不是dict）
3. 口径一致：统一使用decimal格式（0.05 = 5%）
4. None-safe：缺失字段保留None，不使用0伪装
5. Coverage明确：lookback/gap/missing_windows可追溯

职责边界：
- FeatureBuilder：特征生成的唯一入口
- DataCache：提供历史数据查询
- MetricsNormalizer：规范化百分比格式
- FeatureSnapshot：强类型输出DTO
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

# PR-ARCH-01导入
from models.feature_snapshot import (
    FeatureSnapshot, MarketFeatures, CoverageInfo, FeatureMetadata,
    FeatureTrace, FeatureVersion,
    PriceFeatures, OpenInterestFeatures, TakerImbalanceFeatures,
    VolumeFeatures, FundingFeatures,
    create_empty_snapshot
)
from metrics_normalizer import MetricsNormalizer, MetadataPolicy

logger = logging.getLogger(__name__)


class FeatureBuilder:
    """
    特征生成器（PR-ARCH-01核心模块）
    
    输入：raw market data（从data_cache获取的增强数据）
    输出：FeatureSnapshot（强类型）
    
    特性：
    - 单一真相：所有特征生成走同一管道
    - 口径统一：所有百分比统一为decimal格式
    - None-safe：缺失字段保留None
    - Coverage明确：lookback/gap/missing_windows可追溯
    """
    
    def __init__(self, enable_trace: bool = False):
        """
        初始化FeatureBuilder
        
        Args:
            enable_trace: 是否启用追溯（调试模式）
        """
        self.enable_trace = enable_trace
        self.normalizer = MetricsNormalizer(metadata_policy=MetadataPolicy.WARN)
        logger.info("FeatureBuilder initialized (PR-ARCH-01 v3)")
    
    def build(
        self,
        symbol: str,
        raw_data: Dict,
        data_cache: Optional[object] = None  # MarketDataCache instance
    ) -> FeatureSnapshot:
        """
        构建特征快照（主入口）
        
        Args:
            symbol: 交易对符号
            raw_data: 原始市场数据（来自data_cache.get_enhanced_market_data）
            data_cache: MarketDataCache实例（可选，用于获取coverage）
        
        Returns:
            FeatureSnapshot对象
        """
        # Step 1: 规范化百分比格式（percent_point → decimal）
        normalized_data, norm_trace = self._normalize_data(raw_data)
        
        # Step 2: 提取特征
        features = self._extract_features(normalized_data)
        
        # P0-2修复：验证核心必需字段
        if not self._validate_core_fields(features, symbol):
            logger.error(f"[{symbol}] Core fields validation failed")
            # 返回空快照，标记数据无效
            from models.reason_tags import ReasonTag
            return create_empty_snapshot(symbol, ReasonTag.INVALID_DATA)
        
        # Step 3: 计算覆盖度信息
        coverage = self._extract_coverage(raw_data, data_cache, symbol)
        
        # Step 4: 构建元数据
        metadata = self._build_metadata(symbol, raw_data)
        
        # Step 5: 构建追溯信息（可选）
        trace = None
        if self.enable_trace:
            trace = self._build_trace(norm_trace, raw_data)
        
        # 构造快照
        snapshot = FeatureSnapshot(
            features=features,
            coverage=coverage,
            metadata=metadata,
            trace=trace
        )
        
        logger.debug(f"[{symbol}] FeatureSnapshot built: "
                    f"short_evaluable={coverage.short_evaluable}, "
                    f"medium_evaluable={coverage.medium_evaluable}")
        
        return snapshot
    
    def _validate_core_fields(self, features: MarketFeatures, symbol: str) -> bool:
        """
        验证核心必需字段（P0-2修复）
        
        核心必需字段（最小不可缺集合）：
        - price: 当前价格
        - volume_24h: 24小时成交量
        - funding_rate: 资金费率
        
        Args:
            features: 提取的特征
            symbol: 交易对符号（用于日志）
        
        Returns:
            bool: 是否通过验证
        """
        # 检查price
        if features.price is None or features.price.current_price is None:
            logger.error(f"[{symbol}] Missing core field: price")
            return False
        
        # 检查volume_24h
        if features.volume is None or features.volume.volume_24h is None:
            logger.error(f"[{symbol}] Missing core field: volume_24h")
            return False
        
        # 检查funding_rate
        if features.funding is None or features.funding.funding_rate is None:
            logger.error(f"[{symbol}] Missing core field: funding_rate")
            return False
        
        # 所有核心字段验证通过
        logger.debug(f"[{symbol}] Core fields validation passed")
        return True
    
    def _normalize_data(self, raw_data: Dict) -> Tuple[Dict, Optional[Dict]]:
        """
        规范化百分比格式
        
        Args:
            raw_data: 原始数据（可能包含percent_point格式的百分比）
        
        Returns:
            (规范化后的数据, 追溯信息)
        """
        # 调用MetricsNormalizer的normalize方法
        normalized_data, is_valid, fail_reason, norm_trace_obj = self.normalizer.normalize(raw_data)
        
        # 转换trace为dict
        norm_trace = norm_trace_obj.to_dict() if norm_trace_obj else None
        
        # 如果规范化失败，记录警告但仍返回数据（使用旧流程fallback）
        if not is_valid:
            logger.warning(f"Normalization validation failed: {fail_reason}")
        
        return normalized_data, norm_trace
    
    def _extract_features(self, normalized_data: Dict) -> MarketFeatures:
        """
        从规范化数据中提取特征
        
        Args:
            normalized_data: 规范化后的数据（decimal格式）
        
        Returns:
            MarketFeatures对象
        """
        # Price features
        price_features = PriceFeatures(
            price_change_5m=normalized_data.get('price_change_5m'),
            price_change_15m=normalized_data.get('price_change_15m'),
            price_change_1h=normalized_data.get('price_change_1h'),
            price_change_6h=normalized_data.get('price_change_6h'),
            price_change_24h=normalized_data.get('price_change_24h'),
            current_price=normalized_data.get('price')
        )
        
        # Open Interest features
        oi_features = OpenInterestFeatures(
            oi_change_15m=normalized_data.get('oi_change_15m'),
            oi_change_1h=normalized_data.get('oi_change_1h'),
            oi_change_6h=normalized_data.get('oi_change_6h'),
            current_oi=normalized_data.get('open_interest')
        )
        
        # Taker Imbalance features
        # PATCH-P0-2: 优先使用taker_imbalance_*，fallback到buy_sell_imbalance
        taker_imbalance_1h = normalized_data.get('taker_imbalance_1h')
        if taker_imbalance_1h is None:
            # Fallback: 旧代码使用buy_sell_imbalance
            taker_imbalance_1h = normalized_data.get('buy_sell_imbalance')
        
        taker_features = TakerImbalanceFeatures(
            taker_imbalance_5m=normalized_data.get('taker_imbalance_5m'),
            taker_imbalance_15m=normalized_data.get('taker_imbalance_15m'),
            taker_imbalance_1h=taker_imbalance_1h
        )
        
        # Volume features
        volume_features = VolumeFeatures(
            volume_1h=normalized_data.get('volume_1h'),
            volume_24h=normalized_data.get('volume_24h'),
            volume_ratio_5m=normalized_data.get('volume_ratio_5m'),
            volume_ratio_15m=normalized_data.get('volume_ratio_15m')
        )
        
        # Funding features
        funding_features = FundingFeatures(
            funding_rate=normalized_data.get('funding_rate'),
            funding_rate_prev=None  # TODO: 从历史数据获取（如需要）
        )
        
        return MarketFeatures(
            price=price_features,
            open_interest=oi_features,
            taker_imbalance=taker_features,
            volume=volume_features,
            funding=funding_features
        )
    
    def _extract_coverage(
        self,
        raw_data: Dict,
        data_cache: Optional[object],
        symbol: str
    ) -> CoverageInfo:
        """
        提取覆盖度信息
        
        Args:
            raw_data: 原始数据（可能包含_metadata.lookback_coverage）
            data_cache: MarketDataCache实例
            symbol: 交易对符号
        
        Returns:
            CoverageInfo对象
        """
        # 方式1: 从raw_data的_metadata中获取（PATCH-2增强）
        metadata = raw_data.get('_metadata', {})
        lookback_coverage = metadata.get('lookback_coverage', {})
        
        # 方式2: 如果raw_data中没有，尝试从data_cache直接查询
        if not lookback_coverage and data_cache and hasattr(data_cache, 'get_lookback_coverage'):
            try:
                lookback_coverage = data_cache.get_lookback_coverage(symbol)
            except Exception as e:
                logger.warning(f"[{symbol}] Failed to get lookback_coverage from data_cache: {e}")
                lookback_coverage = {}
        
        # 提取各窗口的lookback信息
        lookback_5m = lookback_coverage.get('5m', {})
        lookback_15m = lookback_coverage.get('15m', {})
        lookback_1h = lookback_coverage.get('1h', {})
        lookback_6h = lookback_coverage.get('6h', {})
        
        # 缺失窗口列表
        missing_windows = []
        for window_key in ['5m', '15m', '1h', '6h']:
            window_info = lookback_coverage.get(window_key, {})
            if not window_info.get('is_valid', False):
                missing_windows.append(window_key)
        
        # 可评估性判断（P0-CodeFix逻辑）
        # 短周期：5m/15m/1h至少一个可用
        short_evaluable = (
            lookback_5m.get('is_valid', False) or
            lookback_15m.get('is_valid', False) or
            lookback_1h.get('is_valid', False)
        )
        
        # 中周期：6h可用 或 允许1h降级
        medium_evaluable = (
            lookback_6h.get('is_valid', False) or
            lookback_1h.get('is_valid', False)  # 允许降级
        )
        
        return CoverageInfo(
            lookback_actual_seconds_5m=lookback_5m.get('actual_seconds'),
            lookback_gap_seconds_5m=lookback_5m.get('gap_seconds'),
            lookback_actual_seconds_15m=lookback_15m.get('actual_seconds'),
            lookback_gap_seconds_15m=lookback_15m.get('gap_seconds'),
            lookback_actual_seconds_1h=lookback_1h.get('actual_seconds'),
            lookback_gap_seconds_1h=lookback_1h.get('gap_seconds'),
            lookback_actual_seconds_6h=lookback_6h.get('actual_seconds'),
            lookback_gap_seconds_6h=lookback_6h.get('gap_seconds'),
            missing_windows=missing_windows,
            short_evaluable=short_evaluable,
            medium_evaluable=medium_evaluable
        )
    
    def _build_metadata(self, symbol: str, raw_data: Dict) -> FeatureMetadata:
        """
        构建元数据
        
        Args:
            symbol: 交易对符号
            raw_data: 原始数据
        
        Returns:
            FeatureMetadata对象
        """
        # 提取源时间戳
        source_timestamp = raw_data.get('source_timestamp')
        if isinstance(source_timestamp, str):
            try:
                source_timestamp = datetime.fromisoformat(source_timestamp)
            except Exception:
                source_timestamp = None
        
        return FeatureMetadata(
            feature_version=FeatureVersion.V3_ARCH01,
            percentage_format='decimal',  # FeatureBuilder输出统一为decimal
            source_timestamp=source_timestamp,
            generated_at=datetime.now(),
            symbol=symbol,
            exchange='binance'
        )
    
    def _build_trace(self, norm_trace: Optional[Dict], raw_data: Dict) -> FeatureTrace:
        """
        构建追溯信息
        
        Args:
            norm_trace: 规范化追溯
            raw_data: 原始数据
        
        Returns:
            FeatureTrace对象
        """
        return FeatureTrace(
            normalization_trace=norm_trace,
            lookback_queries={},  # TODO: 添加lookback查询详情
            range_validation={},  # TODO: 添加范围校验结果
            warnings=[],
            errors=[]
        )


class FeatureBuilderFactory:
    """
    FeatureBuilder工厂（单例模式）
    
    用途：确保整个应用使用同一个FeatureBuilder实例
    """
    _instance: Optional[FeatureBuilder] = None
    
    @classmethod
    def get_instance(cls, enable_trace: bool = False) -> FeatureBuilder:
        """
        获取FeatureBuilder实例（单例）
        
        Args:
            enable_trace: 是否启用追溯
        
        Returns:
            FeatureBuilder实例
        """
        if cls._instance is None:
            cls._instance = FeatureBuilder(enable_trace=enable_trace)
            logger.info("FeatureBuilder singleton instance created")
        return cls._instance
    
    @classmethod
    def reset(cls):
        """重置单例（用于测试）"""
        cls._instance = None


# ============================================
# 便捷函数
# ============================================

def build_features_from_cache(
    symbol: str,
    raw_data: Dict,
    data_cache: Optional[object] = None,
    enable_trace: bool = False
) -> FeatureSnapshot:
    """
    从缓存数据构建特征快照（便捷函数）
    
    Args:
        symbol: 交易对符号
        raw_data: 来自data_cache.get_enhanced_market_data的原始数据
        data_cache: MarketDataCache实例
        enable_trace: 是否启用追溯
    
    Returns:
        FeatureSnapshot对象
    """
    builder = FeatureBuilderFactory.get_instance(enable_trace=enable_trace)
    return builder.build(symbol, raw_data, data_cache)


def build_features_from_dict(
    symbol: str,
    features_dict: Dict,
    coverage_dict: Optional[Dict] = None
) -> FeatureSnapshot:
    """
    从字典构建特征快照（用于回测/测试）
    
    Args:
        symbol: 交易对符号
        features_dict: 特征字典（已规范化为decimal格式）
        coverage_dict: 覆盖度字典（可选）
    
    Returns:
        FeatureSnapshot对象
    """
    # 构建特征对象
    features = MarketFeatures()
    
    # Price features
    features.price.price_change_5m = features_dict.get('price_change_5m')
    features.price.price_change_15m = features_dict.get('price_change_15m')
    features.price.price_change_1h = features_dict.get('price_change_1h')
    features.price.price_change_6h = features_dict.get('price_change_6h')
    features.price.price_change_24h = features_dict.get('price_change_24h')
    features.price.current_price = features_dict.get('price')
    
    # OI features
    features.open_interest.oi_change_15m = features_dict.get('oi_change_15m')
    features.open_interest.oi_change_1h = features_dict.get('oi_change_1h')
    features.open_interest.oi_change_6h = features_dict.get('oi_change_6h')
    features.open_interest.current_oi = features_dict.get('open_interest')
    
    # Taker imbalance
    features.taker_imbalance.taker_imbalance_5m = features_dict.get('taker_imbalance_5m')
    features.taker_imbalance.taker_imbalance_15m = features_dict.get('taker_imbalance_15m')
    features.taker_imbalance.taker_imbalance_1h = features_dict.get('taker_imbalance_1h')
    
    # Volume
    features.volume.volume_1h = features_dict.get('volume_1h')
    features.volume.volume_24h = features_dict.get('volume_24h')
    features.volume.volume_ratio_5m = features_dict.get('volume_ratio_5m')
    features.volume.volume_ratio_15m = features_dict.get('volume_ratio_15m')
    
    # Funding
    features.funding.funding_rate = features_dict.get('funding_rate')
    
    # 构建覆盖度
    coverage = CoverageInfo()
    if coverage_dict:
        coverage.lookback_actual_seconds_5m = coverage_dict.get('lookback_actual_seconds_5m')
        coverage.lookback_gap_seconds_5m = coverage_dict.get('lookback_gap_seconds_5m')
        coverage.lookback_actual_seconds_15m = coverage_dict.get('lookback_actual_seconds_15m')
        coverage.lookback_gap_seconds_15m = coverage_dict.get('lookback_gap_seconds_15m')
        coverage.lookback_actual_seconds_1h = coverage_dict.get('lookback_actual_seconds_1h')
        coverage.lookback_gap_seconds_1h = coverage_dict.get('lookback_gap_seconds_1h')
        coverage.lookback_actual_seconds_6h = coverage_dict.get('lookback_actual_seconds_6h')
        coverage.lookback_gap_seconds_6h = coverage_dict.get('lookback_gap_seconds_6h')
        coverage.missing_windows = coverage_dict.get('missing_windows', [])
        coverage.short_evaluable = coverage_dict.get('short_evaluable', True)
        coverage.medium_evaluable = coverage_dict.get('medium_evaluable', True)
    
    # 构建元数据
    metadata = FeatureMetadata(
        symbol=symbol,
        feature_version=FeatureVersion.V3_ARCH01,
        percentage_format='decimal'
    )
    
    return FeatureSnapshot(
        features=features,
        coverage=coverage,
        metadata=metadata
    )
