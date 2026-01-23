"""
L1 Advisory Layer - 配置编译器 (PR-ARCH-03)

负责：
1. 读取YAML配置文件
2. 键名迁移（旧键→新键兼容）
3. 类型/范围校验
4. 生成配置版本hash
5. 编译为强类型Thresholds对象

设计原则：
- 启动时编译一次（fail-fast）
- 集中处理键名迁移（不在业务逻辑层处理）
- 详细错误信息（便于调试）
- 配置版本可追溯
"""

import yaml
import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from models.thresholds import (
    Thresholds, SymbolUniverse, PeriodicUpdate, DataRetention, ErrorHandling,
    DataQuality, DecisionControl, MarketRegime, RiskExposure, TradeQuality,
    Direction, ConfidenceScoring, ReasonTagRules, ExecutableControl,
    AuxiliaryTags, MultiTF, DualTimeframe, DualDecisionControl,
    # 嵌套对象
    LiquidationThreshold, CrowdingThreshold, ExtremeVolumeThreshold,
    AbsorptionThreshold, NoiseThreshold, RotationThreshold, RangeWeakThreshold,
    DirectionalThreshold, ShortTermOpportunityThreshold, TrendThresholds, RangeThresholds,
    ConfidenceThresholdsMap, ConfidenceCaps, StrongSignalBoost,
    MinPriceChange15m, ShortTermThresholds, ConflictResolution, AlignmentBonus,
    ContextThreshold, ConfirmThreshold, TriggerThreshold, BindingPolicy
)

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """配置校验失败异常"""
    pass


class ThresholdCompiler:
    """
    配置编译器
    
    将YAML配置编译为强类型Thresholds对象
    """
    
    # ==========================================
    # 键名迁移映射（旧键 → 新键）
    # ==========================================
    
    KEY_MIGRATIONS = {
        # 例如：buy_sell_imbalance → taker_imbalance
        # 实际迁移会在_migrate_keys方法中处理
    }
    
    def __init__(self):
        self._migration_warnings: List[str] = []
    
    def compile(self, config_path: str) -> Thresholds:
        """
        编译配置文件
        
        Args:
            config_path: YAML配置文件路径
        
        Returns:
            Thresholds: 强类型配置对象
        
        Raises:
            ConfigValidationError: 配置校验失败
        """
        logger.info(f"Compiling config from: {config_path}")
        
        # 1. 读取YAML
        raw = self._load_yaml(config_path)
        
        # 2. 键名迁移
        self._migrate_keys(raw)
        
        # 3. 类型/范围校验
        self._validate_config(raw)
        
        # 4. 计算版本hash
        version = self._compute_version(raw)
        
        # 5. 构建强类型对象
        thresholds = self._build_thresholds(raw, version)
        
        # 6. 输出迁移警告
        if self._migration_warnings:
            logger.warning("Config key migrations detected:")
            for warning in self._migration_warnings:
                logger.warning(f"  - {warning}")
            logger.warning("Please update your config file to use new keys.")
        
        logger.info(f"✅ Config compiled successfully (version: {version[:8]}...)")
        return thresholds
    
    def _load_yaml(self, config_path: str) -> Dict[str, Any]:
        """读取YAML文件"""
        try:
            path = Path(config_path)
            if not path.exists():
                raise ConfigValidationError(f"Config file not found: {config_path}")
            
            with open(path, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f)
            
            if not isinstance(raw, dict):
                raise ConfigValidationError("Config file must contain a YAML dictionary")
            
            return raw
        
        except yaml.YAMLError as e:
            raise ConfigValidationError(f"Invalid YAML syntax: {e}")
        except Exception as e:
            raise ConfigValidationError(f"Failed to load config: {e}")
    
    def _migrate_keys(self, raw: Dict[str, Any]) -> None:
        """
        键名迁移（旧键 → 新键）
        
        修改raw字典（in-place），触发警告
        """
        # 示例：direction.range.short_term_opportunity 中的键名迁移
        # buy_sell_imbalance → taker_imbalance
        
        if 'direction' in raw and 'range' in raw['direction']:
            range_config = raw['direction']['range']
            
            if 'short_term_opportunity' in range_config:
                sto = range_config['short_term_opportunity']
                
                # LONG方向
                if 'long' in sto:
                    long_config = sto['long']
                    if 'min_buy_sell_imbalance' in long_config and 'min_taker_imbalance' not in long_config:
                        # 旧键存在，新键不存在 → 迁移
                        old_value = long_config['min_buy_sell_imbalance']
                        long_config['min_taker_imbalance'] = old_value
                        self._migration_warnings.append(
                            "direction.range.short_term_opportunity.long.min_buy_sell_imbalance "
                            "→ min_taker_imbalance (auto-migrated)"
                        )
                
                # SHORT方向
                if 'short' in sto:
                    short_config = sto['short']
                    if 'max_buy_sell_imbalance' in short_config and 'max_taker_imbalance' not in short_config:
                        old_value = short_config['max_buy_sell_imbalance']
                        short_config['max_taker_imbalance'] = old_value
                        self._migration_warnings.append(
                            "direction.range.short_term_opportunity.short.max_buy_sell_imbalance "
                            "→ max_taker_imbalance (auto-migrated)"
                        )
    
    def _validate_config(self, raw: Dict[str, Any]) -> None:
        """
        配置校验
        
        检查：
        - 必需字段存在
        - 类型正确
        - 范围合理
        """
        # 检查顶层必需字段
        required_sections = [
            'symbol_universe', 'market_regime', 'risk_exposure',
            'trade_quality', 'direction', 'confidence_scoring'
        ]
        
        for section in required_sections:
            if section not in raw:
                raise ConfigValidationError(f"Missing required config section: {section}")
        
        # 范围校验示例
        # 检查百分比字段在合理范围内
        market_regime = raw.get('market_regime', {})
        
        if 'extreme_price_change_1h' in market_regime:
            value = market_regime['extreme_price_change_1h']
            if not (0.0 < value < 1.0):
                raise ConfigValidationError(
                    f"market_regime.extreme_price_change_1h must be in (0, 1), got {value}"
                )
        
        # 检查required_signals合理性
        direction_range = raw.get('direction', {}).get('range', {})
        if 'short_term_opportunity' in direction_range:
            for side in ['long', 'short']:
                if side in direction_range['short_term_opportunity']:
                    sto = direction_range['short_term_opportunity'][side]
                    required_signals = sto.get('required_signals', 1)
                    if not (1 <= required_signals <= 3):
                        raise ConfigValidationError(
                            f"direction.range.short_term_opportunity.{side}.required_signals "
                            f"must be in [1, 3], got {required_signals}"
                        )
        
        # 更多校验规则可以逐步添加...
        logger.debug("Config validation passed")
    
    def _compute_version(self, raw: Dict[str, Any]) -> str:
        """
        计算配置版本hash
        
        使用SHA256对配置内容生成唯一版本号
        """
        # 将配置序列化为字符串
        config_str = yaml.dump(raw, sort_keys=True)
        
        # 计算hash
        hash_obj = hashlib.sha256(config_str.encode('utf-8'))
        version = hash_obj.hexdigest()
        
        return version
    
    def _build_thresholds(self, raw: Dict[str, Any], version: str) -> Thresholds:
        """
        构建强类型Thresholds对象
        
        从raw字典构建所有嵌套的dataclass对象
        """
        # 1. Symbol Universe
        symbol_universe = self._build_symbol_universe(raw['symbol_universe'])
        
        # 2. 基础配置
        periodic_update = self._build_periodic_update(raw.get('periodic_update', {}))
        data_retention = self._build_data_retention(raw.get('data_retention', {}))
        error_handling = self._build_error_handling(raw.get('error_handling', {}))
        data_quality = self._build_data_quality(raw.get('data_quality', {}))
        
        # 3. 决策控制
        decision_control = self._build_decision_control(raw.get('decision_control', {}))
        dual_decision_control = self._build_dual_decision_control(raw.get('dual_decision_control', {}))
        
        # 4. 市场评估
        market_regime = self._build_market_regime(raw['market_regime'])
        risk_exposure = self._build_risk_exposure(raw['risk_exposure'])
        trade_quality = self._build_trade_quality(raw['trade_quality'])
        
        # 5. 方向评估
        direction = self._build_direction(raw['direction'])
        
        # 6. 置信度与执行
        confidence_scoring = self._build_confidence_scoring(raw['confidence_scoring'])
        reason_tag_rules = self._build_reason_tag_rules(raw['reason_tag_rules'])
        executable_control = self._build_executable_control(raw['executable_control'])
        
        # 7. 辅助配置
        auxiliary_tags = self._build_auxiliary_tags(raw.get('auxiliary_tags', {}))
        multi_tf = self._build_multi_tf(raw.get('multi_tf', {}))
        dual_timeframe = self._build_dual_timeframe(raw.get('dual_timeframe', {}))
        
        # 8. 构建顶层对象
        return Thresholds(
            symbol_universe=symbol_universe,
            periodic_update=periodic_update,
            data_retention=data_retention,
            error_handling=error_handling,
            data_quality=data_quality,
            decision_control=decision_control,
            dual_decision_control=dual_decision_control,
            market_regime=market_regime,
            risk_exposure=risk_exposure,
            trade_quality=trade_quality,
            direction=direction,
            confidence_scoring=confidence_scoring,
            reason_tag_rules=reason_tag_rules,
            executable_control=executable_control,
            auxiliary_tags=auxiliary_tags,
            multi_tf=multi_tf,
            dual_timeframe=dual_timeframe,
            version=version
        )
    
    # ==========================================
    # 构建各配置段的辅助方法
    # ==========================================
    
    def _build_symbol_universe(self, raw: Dict) -> SymbolUniverse:
        return SymbolUniverse(
            enabled_symbols=raw['enabled_symbols'],
            default_symbol=raw.get('default_symbol', 'BTC')
        )
    
    def _build_periodic_update(self, raw: Dict) -> PeriodicUpdate:
        return PeriodicUpdate(
            enabled=raw.get('enabled', True),
            interval_minutes=raw.get('interval_minutes', 1),
            market_type=raw.get('market_type', 'futures')
        )
    
    def _build_data_retention(self, raw: Dict) -> DataRetention:
        return DataRetention(
            keep_hours=raw.get('keep_hours', 24),
            cleanup_interval_hours=raw.get('cleanup_interval_hours', 6)
        )
    
    def _build_error_handling(self, raw: Dict) -> ErrorHandling:
        return ErrorHandling(
            max_retries=raw.get('max_retries', 3),
            retry_delay_seconds=raw.get('retry_delay_seconds', 5),
            continue_on_error=raw.get('continue_on_error', True)
        )
    
    def _build_data_quality(self, raw: Dict) -> DataQuality:
        return DataQuality(
            max_staleness_seconds=raw.get('max_staleness_seconds', 120)
        )
    
    def _build_decision_control(self, raw: Dict) -> DecisionControl:
        return DecisionControl(
            min_decision_interval_seconds=raw.get('min_decision_interval_seconds', 300),
            flip_cooldown_seconds=raw.get('flip_cooldown_seconds', 600),
            enable_min_interval=raw.get('enable_min_interval', True),
            enable_flip_cooldown=raw.get('enable_flip_cooldown', True)
        )
    
    def _build_dual_decision_control(self, raw: Dict) -> DualDecisionControl:
        return DualDecisionControl(
            short_term_interval_seconds=raw.get('short_term_interval_seconds', 300),
            short_term_flip_cooldown_seconds=raw.get('short_term_flip_cooldown_seconds', 450),
            medium_term_interval_seconds=raw.get('medium_term_interval_seconds', 1800),
            medium_term_flip_cooldown_seconds=raw.get('medium_term_flip_cooldown_seconds', 900),
            alignment_flip_cooldown_seconds=raw.get('alignment_flip_cooldown_seconds', 900)
        )
    
    def _build_market_regime(self, raw: Dict) -> MarketRegime:
        return MarketRegime(
            extreme_price_change_1h=raw['extreme_price_change_1h'],
            trend_price_change_6h=raw['trend_price_change_6h'],
            short_term_trend_1h=raw['short_term_trend_1h']
        )
    
    def _build_risk_exposure(self, raw: Dict) -> RiskExposure:
        liquidation = LiquidationThreshold(
            price_change=raw['liquidation']['price_change'],
            oi_drop=raw['liquidation']['oi_drop']
        )
        
        crowding = CrowdingThreshold(
            funding_abs=raw['crowding']['funding_abs'],
            oi_growth=raw['crowding']['oi_growth']
        )
        
        extreme_volume = ExtremeVolumeThreshold(
            multiplier=raw['extreme_volume']['multiplier']
        )
        
        return RiskExposure(
            liquidation=liquidation,
            crowding=crowding,
            extreme_volume=extreme_volume
        )
    
    def _build_trade_quality(self, raw: Dict) -> TradeQuality:
        absorption = AbsorptionThreshold(
            imbalance=raw['absorption']['imbalance'],
            volume_ratio=raw['absorption']['volume_ratio']
        )
        
        noise = NoiseThreshold(
            funding_volatility=raw['noise']['funding_volatility'],
            funding_abs=raw['noise']['funding_abs']
        )
        
        rotation = RotationThreshold(
            price_threshold=raw['rotation']['price_threshold'],
            oi_threshold=raw['rotation']['oi_threshold']
        )
        
        range_weak = RangeWeakThreshold(
            imbalance=raw['range_weak']['imbalance'],
            oi=raw['range_weak']['oi']
        )
        
        return TradeQuality(
            absorption=absorption,
            noise=noise,
            rotation=rotation,
            range_weak=range_weak
        )
    
    def _build_direction(self, raw: Dict) -> Direction:
        # Trend阈值
        trend_long = DirectionalThreshold(
            imbalance=raw['trend']['long']['imbalance'],
            oi_change=raw['trend']['long']['oi_change'],
            price_change=raw['trend']['long']['price_change']
        )
        
        trend_short = DirectionalThreshold(
            imbalance=raw['trend']['short']['imbalance'],
            oi_change=raw['trend']['short']['oi_change'],
            price_change=raw['trend']['short']['price_change']
        )
        
        trend = TrendThresholds(long=trend_long, short=trend_short)
        
        # Range阈值
        range_long = DirectionalThreshold(
            imbalance=raw['range']['long']['imbalance'],
            oi_change=raw['range']['long']['oi_change']
        )
        
        range_short = DirectionalThreshold(
            imbalance=raw['range']['short']['imbalance'],
            oi_change=raw['range']['short']['oi_change']
        )
        
        # 短期机会
        sto_raw = raw['range']['short_term_opportunity']
        sto_long = ShortTermOpportunityThreshold(
            min_price_change_1h=sto_raw['long']['min_price_change_1h'],
            min_oi_change_1h=sto_raw['long']['min_oi_change_1h'],
            min_taker_imbalance=sto_raw['long']['min_taker_imbalance'],
            min_buy_sell_imbalance=sto_raw['long'].get('min_buy_sell_imbalance', 
                                                        sto_raw['long']['min_taker_imbalance']),
            required_signals=sto_raw['long']['required_signals']
        )
        
        sto_short = ShortTermOpportunityThreshold(
            min_price_change_1h=sto_raw['short']['max_price_change_1h'],
            min_oi_change_1h=sto_raw['short']['min_oi_change_1h'],
            min_taker_imbalance=sto_raw['short']['max_taker_imbalance'],
            min_buy_sell_imbalance=sto_raw['short'].get('max_buy_sell_imbalance',
                                                         sto_raw['short']['max_taker_imbalance']),
            required_signals=sto_raw['short']['required_signals']
        )
        
        range_config = RangeThresholds(
            long=range_long,
            short=range_short,
            short_term_opportunity={'long': sto_long, 'short': sto_short}
        )
        
        return Direction(trend=trend, range=range_config)
    
    def _build_confidence_scoring(self, raw: Dict) -> ConfidenceScoring:
        thresholds_map = ConfidenceThresholdsMap(
            ultra=raw['thresholds']['ultra'],
            high=raw['thresholds']['high'],
            medium=raw['thresholds']['medium']
        )
        
        caps = ConfidenceCaps(
            uncertain_quality_max=raw['caps']['uncertain_quality_max'],
            reduce_default_max=raw['caps'].get('reduce_default_max', 
                                               raw['caps']['uncertain_quality_max']),
            tag_caps=raw['caps'].get('tag_caps', {})
        )
        
        strong_boost = StrongSignalBoost(
            enabled=raw['strong_signal_boost']['enabled'],
            boost_levels=raw['strong_signal_boost']['boost_levels'],
            required_tags=raw['strong_signal_boost']['required_tags']
        )
        
        return ConfidenceScoring(
            decision_score=raw['decision_score'],
            regime_trend_score=raw['regime_trend_score'],
            regime_range_score=raw['regime_range_score'],
            regime_extreme_score=raw['regime_extreme_score'],
            quality_good_score=raw['quality_good_score'],
            quality_uncertain_score=raw['quality_uncertain_score'],
            quality_poor_score=raw['quality_poor_score'],
            strong_signal_bonus=raw['strong_signal_bonus'],
            thresholds=thresholds_map,
            caps=caps,
            strong_signal_boost=strong_boost
        )
    
    def _build_reason_tag_rules(self, raw: Dict) -> ReasonTagRules:
        return ReasonTagRules(
            reduce_tags=raw.get('reduce_tags', []),
            deny_tags=raw.get('deny_tags', [])
        )
    
    def _build_executable_control(self, raw: Dict) -> ExecutableControl:
        return ExecutableControl(
            min_confidence_normal=raw['min_confidence_normal'],
            min_confidence_reduced=raw['min_confidence_reduced']
        )
    
    def _build_auxiliary_tags(self, raw: Dict) -> AuxiliaryTags:
        return AuxiliaryTags(
            oi_growing_threshold=raw.get('oi_growing_threshold', 0.05),
            oi_declining_threshold=raw.get('oi_declining_threshold', -0.05),
            funding_rate_threshold=raw.get('funding_rate_threshold', 0.0005)
        )
    
    def _build_multi_tf(self, raw: Dict) -> MultiTF:
        # 简化实现：使用Dict存储（因为结构复杂）
        # 完整实现可以进一步细化为强类型
        
        context_1h = {}
        if 'context_1h' in raw:
            for side in ['long', 'short']:
                if side in raw['context_1h']:
                    ctx = raw['context_1h'][side]
                    context_1h[side] = ContextThreshold(
                        min_price_change=ctx.get('min_price_change'),
                        max_price_change=ctx.get('max_price_change'),
                        min_taker_imbalance=ctx.get('min_taker_imbalance'),
                        max_taker_imbalance=ctx.get('max_taker_imbalance'),
                        min_oi_change=ctx.get('min_oi_change', 0.0),
                        required_signals=ctx.get('required_signals', 2)
                    )
        
        confirm_15m = {}
        if 'confirm_15m' in raw:
            for side in ['long', 'short']:
                if side in raw['confirm_15m']:
                    conf = raw['confirm_15m'][side]
                    confirm_15m[side] = ConfirmThreshold(
                        min_price_change=conf.get('min_price_change'),
                        max_price_change=conf.get('max_price_change'),
                        min_taker_imbalance=conf.get('min_taker_imbalance'),
                        max_taker_imbalance=conf.get('max_taker_imbalance'),
                        min_volume_ratio=conf.get('min_volume_ratio', 1.0),
                        min_oi_change=conf.get('min_oi_change', 0.0),
                        required_confirmed=conf.get('required_confirmed', 2),
                        required_partial=conf.get('required_partial', 1)
                    )
        
        trigger_5m = {}
        if 'trigger_5m' in raw:
            for side in ['long', 'short']:
                if side in raw['trigger_5m']:
                    trig = raw['trigger_5m'][side]
                    trigger_5m[side] = TriggerThreshold(
                        min_price_change=trig.get('min_price_change'),
                        max_price_change=trig.get('max_price_change'),
                        min_taker_imbalance=trig.get('min_taker_imbalance'),
                        max_taker_imbalance=trig.get('max_taker_imbalance'),
                        min_volume_ratio=trig.get('min_volume_ratio', 1.0),
                        required_signals=trig.get('required_signals', 2)
                    )
        
        binding_policy = BindingPolicy(
            short_term_opportunity_requires_confirmed=raw.get('binding_policy', {}).get(
                'short_term_opportunity_requires_confirmed', True),
            partial_action=raw.get('binding_policy', {}).get('partial_action', 'degrade'),
            failed_short_term_action=raw.get('binding_policy', {}).get('failed_short_term_action', 'cancel'),
            failed_long_term_action=raw.get('binding_policy', {}).get('failed_long_term_action', 'degrade')
        )
        
        return MultiTF(
            enabled=raw.get('enabled', False),
            context_1h=context_1h,
            confirm_15m=confirm_15m,
            trigger_5m=trigger_5m,
            binding_policy=binding_policy
        )
    
    def _build_dual_timeframe(self, raw: Dict) -> DualTimeframe:
        # 短期阈值
        short_term_raw = raw.get('short_term', {})
        
        min_price_15m = MinPriceChange15m(
            dynamic=short_term_raw.get('min_price_change_15m', {}).get('dynamic', True),
            trend=short_term_raw.get('min_price_change_15m', {}).get('trend', 0.003),
            range=short_term_raw.get('min_price_change_15m', {}).get('range', 0.006),
            extreme=short_term_raw.get('min_price_change_15m', {}).get('extreme', 0.012),
            default=short_term_raw.get('min_price_change_15m', {}).get('default', 0.004)
        )
        
        short_term = ShortTermThresholds(
            min_price_change_15m=min_price_15m,
            min_taker_imbalance=short_term_raw.get('min_taker_imbalance', 0.30),
            min_volume_ratio=short_term_raw.get('min_volume_ratio', 1.3),
            min_oi_change_15m=short_term_raw.get('min_oi_change_15m', 0.02),
            required_signals=short_term_raw.get('required_signals', 3)
        )
        
        # 冲突处理
        conflict_resolution = ConflictResolution(
            default_strategy=raw.get('conflict_resolution', {}).get('default_strategy', 'no_trade')
        )
        
        # 一致性加成
        alignment_bonus = AlignmentBonus(
            confidence_boost=raw.get('alignment_bonus', {}).get('confidence_boost', 1),
            relax_executable_threshold=raw.get('alignment_bonus', {}).get('relax_executable_threshold', False)
        )
        
        return DualTimeframe(
            enabled=raw.get('enabled', False),
            short_term=short_term,
            conflict_resolution=conflict_resolution,
            alignment_bonus=alignment_bonus
        )


# ==========================================
# 便捷函数
# ==========================================

def compile_thresholds(config_path: str = None) -> Thresholds:
    """
    便捷函数：编译配置
    
    Args:
        config_path: 配置文件路径（默认：config/l1_thresholds.yaml）
    
    Returns:
        Thresholds: 强类型配置对象
    """
    if config_path is None:
        # 默认路径
        import os
        config_path = os.path.join(
            os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml'
        )
    
    compiler = ThresholdCompiler()
    return compiler.compile(config_path)
