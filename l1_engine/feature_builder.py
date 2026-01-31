"""
PR-ARCH-01: FeatureBuilder/MarketFeaturePipeline

特征生成管道的单一入口，确保线上/回测/测试使用相同的特征生成逻辑。

目标：
1. 特征生成单一真相：所有环境（线上/回测/测试）使用同一管道
2. 强类型输出：返回FeatureSnapshot（不是dict）
3. 口径一致：统一使用decimal格式（0.05 = 5%）
4. None-safe：缺失字段保留None，不使用0伪装
5. Coverage明确：lookback/gap/missing_windows可追溯

P0-01 DataFix增强：
- 核心字段验证返回细粒度的ReasonTag
- 区分必须字段（price）和重要字段（volume/funding_rate）
- 缺失字段显性化，禁止None→0伪中性

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
        
        # P0-01 DataFix：验证核心字段（增强版）
        is_valid, missing_tags = self._validate_core_fields(features, symbol)
        
        if not is_valid:
            logger.error(f"[{symbol}] Core fields validation failed - returning empty snapshot")
            # 返回空快照，使用第一个缺失标签（通常是DATA_MISSING_PRICE）
            from models.reason_tags import ReasonTag
            primary_tag = missing_tags[0] if missing_tags else ReasonTag.INVALID_DATA
            return create_empty_snapshot(symbol, primary_tag)
        
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
        
        # 诊断日志（INFO级别以便在生产环境看到）
        logger.info(f"[{symbol}] FeatureSnapshot built: "
                    f"short_evaluable={coverage.short_evaluable}, "
                    f"medium_evaluable={coverage.medium_evaluable}, "
                    f"missing_windows={coverage.missing_windows}")
        
        return snapshot
    
    # ========================================
    # P2-2: 异常值处理配置
    # ========================================
    
    # 异常值阈值配置（分级处理）
    OUTLIER_CONFIG = {
        'price_change': {
            'soft_limit': 0.15,   # 15%: 软限制（警告+cap）
            'hard_limit': 0.50,   # 50%: 硬限制（严重异常）
            'extreme_limit': 1.0, # 100%: 极端异常（可能数据错误）
        },
        'oi_change': {
            'soft_limit': 0.20,   # 20%: 软限制
            'hard_limit': 0.50,   # 50%: 硬限制
            'extreme_limit': 1.0, # 100%: 极端异常
        },
        'funding_rate': {
            'soft_limit': 0.01,   # 1%: 软限制（费率通常<0.1%）
            'hard_limit': 0.03,   # 3%: 硬限制（极端市场）
            'extreme_limit': 0.05,# 5%: 极端异常
        },
        'taker_imbalance': {
            'soft_limit': 0.70,   # 70%: 软限制
            'hard_limit': 0.90,   # 90%: 硬限制
            'extreme_limit': 1.0, # 100%: 极端异常
        },
    }
    
    def _validate_core_fields(self, features: MarketFeatures, symbol: str) -> Tuple[bool, List]:
        """
        验证核心必需字段（P2-2增强版：分级异常处理）
        
        三层校验：
        1. 缺失校验（None）：DATA_MISSING_*
        2. 无效值校验（<=0）：DATA_INVALID_*（阻断）
        3. 异常值校验（outlier）：DATA_OUTLIER_*（分级处理+cap）
        
        异常值分级处理：
        - soft_limit: 警告 + cap到软限制
        - hard_limit: 严重警告 + cap到硬限制 + 降级标签
        - extreme_limit: 错误 + 置信度强制降低
        
        Args:
            features: 提取的特征
            symbol: 交易对符号（用于日志）
        
        Returns:
            (is_valid, validation_tags): 是否通过验证，校验标签列表
        """
        from models.reason_tags import ReasonTag
        
        validation_tags = []
        is_valid = True
        outlier_corrections = []  # 记录异常值修正
        
        # ========== 1. Price校验 ==========
        if features.price is None or features.price.current_price is None:
            logger.error(f"[{symbol}] Missing REQUIRED field: price")
            validation_tags.append(ReasonTag.DATA_MISSING_PRICE)
            is_valid = False
        elif features.price.current_price <= 0:
            logger.error(f"[{symbol}] INVALID price: {features.price.current_price} <= 0")
            validation_tags.append(ReasonTag.DATA_INVALID_PRICE)
            is_valid = False
        
        # ========== 2. Volume校验 ==========
        if features.volume is None or features.volume.volume_24h is None:
            logger.warning(f"[{symbol}] Missing important field: volume_24h")
            validation_tags.append(ReasonTag.DATA_MISSING_VOLUME)
        elif features.volume.volume_24h <= 0:
            logger.error(f"[{symbol}] INVALID volume_24h: {features.volume.volume_24h} <= 0")
            validation_tags.append(ReasonTag.DATA_INVALID_VOLUME)
            is_valid = False
        
        # ========== 3. Open Interest校验 ==========
        if features.open_interest is None or features.open_interest.current_oi is None:
            logger.debug(f"[{symbol}] Missing auxiliary field: open_interest")
            validation_tags.append(ReasonTag.DATA_MISSING_OPEN_INTEREST)
        elif features.open_interest.current_oi <= 0:
            logger.error(f"[{symbol}] INVALID open_interest: {features.open_interest.current_oi} <= 0")
            validation_tags.append(ReasonTag.DATA_INVALID_OI)
            is_valid = False
        
        # ========== 4. Funding Rate异常值分级处理 ==========
        if features.funding is None or features.funding.funding_rate is None:
            logger.warning(f"[{symbol}] Missing important field: funding_rate")
            validation_tags.append(ReasonTag.DATA_MISSING_FUNDING_RATE)
        else:
            funding = features.funding.funding_rate
            config = self.OUTLIER_CONFIG['funding_rate']
            
            if abs(funding) > config['extreme_limit']:
                # 极端异常：cap到极端限制
                capped = config['extreme_limit'] if funding > 0 else -config['extreme_limit']
                outlier_corrections.append(f"funding_rate: {funding:.4f} → {capped:.4f} (extreme)")
                features.funding.funding_rate = capped
                validation_tags.append(ReasonTag.DATA_OUTLIER_FUNDING_RATE)
                logger.error(f"[{symbol}] EXTREME funding_rate: {funding:.4f}, capped to {capped:.4f}")
            elif abs(funding) > config['hard_limit']:
                # 硬限制：cap + 降级标签
                capped = config['hard_limit'] if funding > 0 else -config['hard_limit']
                outlier_corrections.append(f"funding_rate: {funding:.4f} → {capped:.4f} (hard)")
                features.funding.funding_rate = capped
                validation_tags.append(ReasonTag.DATA_OUTLIER_FUNDING_RATE)
                logger.warning(f"[{symbol}] HARD funding_rate: {funding:.4f}, capped to {capped:.4f}")
            elif abs(funding) > config['soft_limit']:
                # 软限制：警告但不修正
                logger.info(f"[{symbol}] SOFT funding_rate: {funding:.4f} (>{config['soft_limit']})")
        
        # ========== 5. Taker Imbalance异常值分级处理 ==========
        if features.taker_imbalance is None or features.taker_imbalance.taker_imbalance_1h is None:
            logger.debug(f"[{symbol}] Missing auxiliary field: taker_imbalance_1h")
            validation_tags.append(ReasonTag.DATA_MISSING_TAKER_IMBALANCE)
        else:
            for field_name in ['taker_imbalance_5m', 'taker_imbalance_15m', 'taker_imbalance_1h']:
                imbalance = getattr(features.taker_imbalance, field_name, None)
                if imbalance is None:
                    continue
                    
                config = self.OUTLIER_CONFIG['taker_imbalance']
                
                if abs(imbalance) > config['extreme_limit']:
                    capped = config['extreme_limit'] if imbalance > 0 else -config['extreme_limit']
                    outlier_corrections.append(f"{field_name}: {imbalance:.3f} → {capped:.3f} (extreme)")
                    setattr(features.taker_imbalance, field_name, capped)
                    if ReasonTag.DATA_OUTLIER_TAKER_IMBALANCE not in validation_tags:
                        validation_tags.append(ReasonTag.DATA_OUTLIER_TAKER_IMBALANCE)
                    logger.error(f"[{symbol}] EXTREME {field_name}: {imbalance:.3f}, capped to {capped:.3f}")
                elif abs(imbalance) > config['hard_limit']:
                    capped = config['hard_limit'] if imbalance > 0 else -config['hard_limit']
                    outlier_corrections.append(f"{field_name}: {imbalance:.3f} → {capped:.3f} (hard)")
                    setattr(features.taker_imbalance, field_name, capped)
                    if ReasonTag.DATA_OUTLIER_TAKER_IMBALANCE not in validation_tags:
                        validation_tags.append(ReasonTag.DATA_OUTLIER_TAKER_IMBALANCE)
                    logger.warning(f"[{symbol}] HARD {field_name}: {imbalance:.3f}, capped to {capped:.3f}")
        
        # ========== 6. Price Change异常值分级处理 ==========
        if features.price:
            config = self.OUTLIER_CONFIG['price_change']
            price_fields = [
                ('price_change_5m', features.price.price_change_5m),
                ('price_change_15m', features.price.price_change_15m),
                ('price_change_1h', features.price.price_change_1h),
                ('price_change_6h', features.price.price_change_6h),
                ('price_change_24h', features.price.price_change_24h),
            ]
            
            for field_name, change in price_fields:
                if change is None:
                    continue
                    
                if abs(change) > config['extreme_limit']:
                    capped = config['extreme_limit'] if change > 0 else -config['extreme_limit']
                    outlier_corrections.append(f"{field_name}: {change:.4f} → {capped:.4f} (extreme)")
                    setattr(features.price, field_name, capped)
                    if ReasonTag.DATA_OUTLIER_PRICE_CHANGE not in validation_tags:
                        validation_tags.append(ReasonTag.DATA_OUTLIER_PRICE_CHANGE)
                    logger.error(f"[{symbol}] EXTREME {field_name}: {change:.4f}, capped to {capped:.4f}")
                elif abs(change) > config['hard_limit']:
                    capped = config['hard_limit'] if change > 0 else -config['hard_limit']
                    outlier_corrections.append(f"{field_name}: {change:.4f} → {capped:.4f} (hard)")
                    setattr(features.price, field_name, capped)
                    if ReasonTag.DATA_OUTLIER_PRICE_CHANGE not in validation_tags:
                        validation_tags.append(ReasonTag.DATA_OUTLIER_PRICE_CHANGE)
                    logger.warning(f"[{symbol}] HARD {field_name}: {change:.4f}, capped to {capped:.4f}")
        
        # ========== 7. OI Change异常值分级处理 ==========
        if features.open_interest:
            config = self.OUTLIER_CONFIG['oi_change']
            oi_fields = [
                ('oi_change_15m', features.open_interest.oi_change_15m),
                ('oi_change_1h', features.open_interest.oi_change_1h),
                ('oi_change_6h', features.open_interest.oi_change_6h),
            ]
            
            for field_name, change in oi_fields:
                if change is None:
                    continue
                    
                if abs(change) > config['extreme_limit']:
                    capped = config['extreme_limit'] if change > 0 else -config['extreme_limit']
                    outlier_corrections.append(f"{field_name}: {change:.4f} → {capped:.4f} (extreme)")
                    setattr(features.open_interest, field_name, capped)
                    if ReasonTag.DATA_OUTLIER_OI_CHANGE not in validation_tags:
                        validation_tags.append(ReasonTag.DATA_OUTLIER_OI_CHANGE)
                    logger.error(f"[{symbol}] EXTREME {field_name}: {change:.4f}, capped to {capped:.4f}")
                elif abs(change) > config['hard_limit']:
                    capped = config['hard_limit'] if change > 0 else -config['hard_limit']
                    outlier_corrections.append(f"{field_name}: {change:.4f} → {capped:.4f} (hard)")
                    setattr(features.open_interest, field_name, capped)
                    if ReasonTag.DATA_OUTLIER_OI_CHANGE not in validation_tags:
                        validation_tags.append(ReasonTag.DATA_OUTLIER_OI_CHANGE)
                    logger.warning(f"[{symbol}] HARD {field_name}: {change:.4f}, capped to {capped:.4f}")
        
        # ========== 日志输出 ==========
        outlier_count = sum(1 for t in validation_tags if 'outlier' in t.value)
        missing_count = sum(1 for t in validation_tags if 'missing' in t.value)
        
        if is_valid:
            if outlier_corrections:
                logger.info(f"[{symbol}] Core fields validated with {len(outlier_corrections)} corrections: {outlier_corrections}")
            else:
                logger.debug(f"[{symbol}] Core fields validation passed (missing={missing_count}, outlier={outlier_count})")
        else:
            invalid_tags = [t.value for t in validation_tags if 'invalid' in t.value]
            logger.error(f"[{symbol}] Core fields validation FAILED (invalid={invalid_tags})")
        
        return is_valid, validation_tags
    
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
        
        # Volume features (P0-4: 添加 volume_ratio_1h)
        volume_features = VolumeFeatures(
            volume_1h=normalized_data.get('volume_1h'),
            volume_24h=normalized_data.get('volume_24h'),
            volume_ratio_5m=normalized_data.get('volume_ratio_5m'),
            volume_ratio_15m=normalized_data.get('volume_ratio_15m'),
            volume_ratio_1h=normalized_data.get('volume_ratio_1h')
        )
        
        # Funding features
        funding_features = FundingFeatures(
            funding_rate=normalized_data.get('funding_rate'),
            funding_rate_prev=None  # TODO: 从历史数据获取（如需要）
        )
        
        # Phase 2: Top Trader features (大户多空比)
        from models.feature_snapshot import TopTraderFeatures
        top_trader_features = TopTraderFeatures(
            top_long_ratio=normalized_data.get('top_long_ratio'),
            top_short_ratio=normalized_data.get('top_short_ratio'),
            retail_long_ratio=normalized_data.get('retail_long_ratio'),
            retail_short_ratio=normalized_data.get('retail_short_ratio')
        )
        
        return MarketFeatures(
            price=price_features,
            open_interest=oi_features,
            taker_imbalance=taker_features,
            volume=volume_features,
            funding=funding_features,
            top_trader=top_trader_features
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
        raw_coverage = metadata.get('lookback_coverage', {})
        
        # 统一格式：get_lookback_coverage返回 {'has_data': ..., 'windows': {...}}
        # 需要提取windows部分
        if isinstance(raw_coverage, dict) and 'windows' in raw_coverage:
            lookback_coverage = raw_coverage.get('windows', {})
        else:
            lookback_coverage = raw_coverage  # 兼容旧格式
        
        # 方式2: 如果raw_data中没有，尝试从data_cache直接查询
        if not lookback_coverage and data_cache and hasattr(data_cache, 'get_lookback_coverage'):
            try:
                result = data_cache.get_lookback_coverage(symbol)
                # get_lookback_coverage返回 {'windows': {...}}，需要提取windows
                lookback_coverage = result.get('windows', {}) if isinstance(result, dict) else {}
                logger.info(f"[{symbol}] Got coverage from data_cache: has_data={result.get('has_data')}, cache_size={result.get('cache_size')}")
            except Exception as e:
                logger.warning(f"[{symbol}] Failed to get lookback_coverage from data_cache: {e}")
                lookback_coverage = {}
        
        # 诊断：检查lookback_coverage来源
        logger.info(f"[{symbol}] lookback_coverage source: from_metadata={bool(metadata.get('lookback_coverage'))}, final_keys={list(lookback_coverage.keys())}")
        
        # 提取各窗口的lookback信息
        lookback_5m = lookback_coverage.get('5m', {})
        lookback_15m = lookback_coverage.get('15m', {})
        lookback_1h = lookback_coverage.get('1h', {})
        lookback_6h = lookback_coverage.get('6h', {})
        
        # 诊断日志
        logger.info(f"[{symbol}] Coverage windows: "
                    f"5m={lookback_5m.get('is_valid')}, "
                    f"15m={lookback_15m.get('is_valid')}, "
                    f"1h={lookback_1h.get('is_valid')}, "
                    f"6h={lookback_6h.get('is_valid')}")
        
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
    
    # Volume (P0-4: 添加 volume_ratio_1h)
    features.volume.volume_1h = features_dict.get('volume_1h')
    features.volume.volume_24h = features_dict.get('volume_24h')
    features.volume.volume_ratio_5m = features_dict.get('volume_ratio_5m')
    features.volume.volume_ratio_15m = features_dict.get('volume_ratio_15m')
    features.volume.volume_ratio_1h = features_dict.get('volume_ratio_1h')
    
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
