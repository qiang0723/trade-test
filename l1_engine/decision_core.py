"""
PR-ARCH-02: DecisionCore纯函数（骨架版本 v0.1）

核心决策逻辑的纯函数实现。

目标：
1. 纯函数：相同输入→相同输出
2. 无时间：不依赖datetime.now()
3. 无状态：不依赖历史决策（频控交给DecisionGate）
4. 无IO：不读取数据库/Redis
5. 可测试：确定性单测

职责边界：
- DecisionCore：策略逻辑（市场环境、风险、质量、方向、置信度）
- DecisionGate：频控逻辑（冷却期、最小间隔、阻断）

注：当前为骨架版本，展示架构设计。完整实现需要：
1. 从market_state_machine_l1.py提取决策方法
2. 转换为纯函数（移除self依赖）
3. 适配FeatureSnapshot输入
4. 保持None-safe逻辑
"""

import logging
from typing import Tuple, List, Dict, Optional
from models.feature_snapshot import FeatureSnapshot
from models.thresholds import Thresholds
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, ExecutionPermission
from models.reason_tags import ReasonTag
from models.decision_core_dto import (
    TimeframeDecisionDraft, DualTimeframeDecisionDraft,
    create_no_trade_draft, create_dual_no_trade_draft
)

logger = logging.getLogger(__name__)


class DecisionCore:
    """
    决策核心（纯函数集合）
    
    设计原则：
    - 所有方法都是静态方法或类方法
    - 不持有状态
    - 不依赖时间
    - 输入：FeatureSnapshot + Thresholds
    - 输出：DecisionDraft
    """
    
    # ========================================
    # 主入口：单周期评估
    # ========================================
    
    @staticmethod
    def evaluate_single(
        features: FeatureSnapshot,
        thresholds: Thresholds,
        symbol: str = "UNKNOWN"
    ) -> TimeframeDecisionDraft:
        """
        单周期决策评估（纯函数，主入口）
        
        10步决策管道：
        1. 数据验证 ✅
        2. 市场环境识别 ✅
        3. 风险准入评估 ✅（第一道闸门）
        4. 交易质量评估 ✅（第二道闸门）
        5. 方向评估 ✅
        6. 决策优先级 ✅
        7. 资金费率降级 ✅
        8. 执行权限 ✅
        9. 置信度计算 ✅
        10. 输出标准化 ✅
        
        Args:
            features: 特征快照（FeatureSnapshot）
            thresholds: 强类型阈值配置
            symbol: 交易对符号（用于日志）
        
        Returns:
            TimeframeDecisionDraft: 决策草稿
        """
        # Step 1: 数据验证（简化版本，TODO：添加更完善的coverage检查）
        # 检查features.coverage.short_evaluable或medium_evaluable
        # if not features.coverage.short_evaluable and not features.coverage.medium_evaluable:
        #     return create_no_trade_draft([ReasonTag.DATA_INCOMPLETE], MarketRegime.RANGE)
        
        # Step 2: 市场环境识别 ✅
        regime, regime_tags = DecisionCore._detect_market_regime(features, thresholds)
        
        # Step 3: 风险准入评估（第一道闸门） ✅
        risk_ok, risk_tags = DecisionCore._eval_risk_exposure(features, regime, thresholds)
        if not risk_ok:
            return create_no_trade_draft(risk_tags, regime)
        
        # Step 4: 交易质量评估（第二道闸门） ✅
        quality, quality_tags = DecisionCore._eval_trade_quality(features, regime, thresholds, symbol)
        if quality == TradeQuality.POOR:
            return create_no_trade_draft(quality_tags, regime)
        
        # Step 5: 方向评估 ✅（简化版本，TODO：完善短期机会识别）
        allow_long, long_tags = DecisionCore._eval_long_direction(features, regime, thresholds)
        allow_short, short_tags = DecisionCore._eval_short_direction(features, regime, thresholds)
        
        # Step 6: 决策优先级 ✅
        decision, direction_tags = DecisionCore._decide_priority(allow_short, allow_long)
        
        # Step 7: 资金费率降级（TODO：实现完整逻辑）
        decision, funding_tags = DecisionCore._apply_funding_rate_downgrade(
            decision, features, thresholds
        )
        
        # Step 8: 执行权限判断（策略层） ✅（简化版本）
        execution_permission = DecisionCore._determine_execution_permission(
            regime, quality, decision, thresholds
        )
        
        # Step 9: 置信度计算（TODO：实现PR-D混合模式）
        all_tags = regime_tags + risk_tags + quality_tags + long_tags + short_tags + direction_tags + funding_tags
        confidence = DecisionCore._compute_confidence(
            decision, regime, quality, all_tags, thresholds
        )
        
        # Step 10: 组装DecisionDraft ✅
        return TimeframeDecisionDraft(
            decision=decision,
            confidence=confidence,
            market_regime=regime,
            trade_quality=quality,
            execution_permission=execution_permission,
            reason_tags=all_tags,
            key_metrics={}  # TODO: 添加关键指标（price_change_1h等）
        )
    
    # ========================================
    # 主入口：双周期评估
    # ========================================
    
    @staticmethod
    def evaluate_dual(
        features: FeatureSnapshot,
        thresholds: Thresholds,
        symbol: str = "UNKNOWN"
    ) -> DualTimeframeDecisionDraft:
        """
        双周期决策评估（纯函数）
        
        分别评估短期（5m/15m）和中期（1h/6h）
        
        Args:
            features: 特征快照
            thresholds: 强类型阈值配置
            symbol: 交易对符号
        
        Returns:
            DualTimeframeDecisionDraft: 双周期决策草稿
        """
        # TODO: 检查short_evaluable和medium_evaluable
        # TODO: 分别调用evaluate_single（使用不同的特征子集）
        # TODO: 识别全局风险标签
        
        # 骨架实现
        short_draft = DecisionCore.evaluate_single(features, thresholds, symbol)
        medium_draft = DecisionCore.evaluate_single(features, thresholds, symbol)
        
        return DualTimeframeDecisionDraft(
            short_term=short_draft,
            medium_term=medium_draft,
            global_risk_tags=[]
        )
    
    # ========================================
    # Step 2: 市场环境识别
    # ========================================
    
    @staticmethod
    def _detect_market_regime(
        features: FeatureSnapshot,
        thresholds: Thresholds
    ) -> Tuple[MarketRegime, List[ReasonTag]]:
        """
        识别市场环境（纯函数）
        
        提取自: market_state_machine_l1.py._detect_market_regime() (PR-ARCH-02 M3-Step1)
        
        逻辑：
        1. EXTREME: price_change_1h > extreme_threshold（优先级最高）
        2. TREND: 
           - 中期趋势：price_change_6h > trend_threshold
           - 退化判定：缺6h时使用15m（更保守阈值）
           - 短期趋势：price_change_1h > short_term_trend_threshold
        3. RANGE: 默认（保守）
        
        None-safe: 关键字段缺失时使用退化逻辑或默认RANGE
        
        Args:
            features: 特征快照
            thresholds: 阈值配置
        
        Returns:
            (MarketRegime, 原因标签列表)
        """
        regime_tags = []
        
        # 提取price features（None-safe）
        price_change_1h = features.features.price.price_change_1h
        price_change_6h = features.features.price.price_change_6h
        price_change_15m = features.features.price.price_change_15m  # fallback
        
        # 获取阈值配置
        regime_thresholds = thresholds.market_regime
        
        # 1. EXTREME: 极端波动（优先级最高）
        if price_change_1h is not None:
            price_change_1h_abs = abs(price_change_1h)
            if price_change_1h_abs > regime_thresholds.extreme_price_change_1h:
                return MarketRegime.EXTREME, regime_tags
        
        # 2. TREND: 趋势市
        # 2.1 中期趋势（6小时）
        if price_change_6h is not None:
            price_change_6h_abs = abs(price_change_6h)
            if price_change_6h_abs > regime_thresholds.trend_price_change_6h:
                return MarketRegime.TREND, regime_tags
        elif price_change_15m is not None:
            # PATCH-P0-02: 缺6h时使用15m退化判定（更保守阈值）
            price_change_15m_abs = abs(price_change_15m)
            fallback_threshold = regime_thresholds.trend_price_change_6h * 0.5  # 15m用更低阈值
            if price_change_15m_abs > fallback_threshold:
                regime_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)  # 标记退化
                logger.debug("Regime detection using 15m fallback (6h missing)")
                return MarketRegime.TREND, regime_tags
        
        # 2.2 短期趋势（1小时）- 方案1: 捕获短期机会
        if price_change_1h is not None:
            price_change_1h_abs = abs(price_change_1h)
            if price_change_1h_abs > regime_thresholds.short_term_trend_1h:
                regime_tags.append(ReasonTag.SHORT_TERM_TREND)
                return MarketRegime.TREND, regime_tags
        
        # 3. RANGE: 震荡市（默认）
        # PATCH-P0-02: 如果关键字段全缺失，标记但仍返回RANGE（保守）
        if price_change_1h is None and price_change_6h is None:
            regime_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)
            logger.debug("Regime defaults to RANGE (price_change data missing)")
        
        return MarketRegime.RANGE, regime_tags
    
    # ========================================
    # Step 3: 风险准入评估
    # ========================================
    
    @staticmethod
    def _eval_risk_exposure(
        features: FeatureSnapshot,
        regime: MarketRegime,
        thresholds: Thresholds
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        风险准入评估（纯函数）
        
        提取自: market_state_machine_l1.py._eval_risk_exposure_allowed() (PR-ARCH-02 M3-Step2)
        
        检查项：
        1. 极端行情（EXTREME regime）- 最高优先级
        2. 清算阶段（price急变 + OI急降）
        3. 拥挤风险（极端费率 + 高OI增长）
        4. 极端成交量（1h成交量 > 24h平均 * 倍数）
        
        None-safe: 关键字段缺失时跳过规则（不误DENY）
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
        
        Returns:
            (是否允许风险敞口, 原因标签列表)
        """
        tags = []
        
        # 获取阈值配置
        risk_thresholds = thresholds.risk_exposure
        
        # 1. 极端行情
        if regime == MarketRegime.EXTREME:
            tags.append(ReasonTag.EXTREME_REGIME)
            return False, tags
        
        # 2. 清算阶段（PATCH-P0-02: None-safe）
        price_change_1h = features.features.price.price_change_1h
        oi_change_1h = features.features.open_interest.oi_change_1h
        
        if price_change_1h is not None and oi_change_1h is not None:
            if (abs(price_change_1h) > risk_thresholds.liquidation.price_change and 
                oi_change_1h < risk_thresholds.liquidation.oi_drop):
                tags.append(ReasonTag.LIQUIDATION_PHASE)
                return False, tags
        else:
            # 关键字段缺失，跳过此规则但记录
            if price_change_1h is None or oi_change_1h is None:
                logger.debug("Liquidation check skipped (price_change_1h or oi_change_1h missing)")
        
        # 3. 拥挤风险（PATCH-P0-02: None-safe）
        funding_rate_value = features.features.funding.funding_rate
        oi_change_6h = features.features.open_interest.oi_change_6h
        
        if funding_rate_value is not None and oi_change_6h is not None:
            funding_rate_abs = abs(funding_rate_value)
            if (funding_rate_abs > risk_thresholds.crowding.funding_abs and 
                oi_change_6h > risk_thresholds.crowding.oi_growth):
                tags.append(ReasonTag.CROWDING_RISK)
                return False, tags
        else:
            # 关键字段缺失，跳过此规则
            if funding_rate_value is None or oi_change_6h is None:
                logger.debug("Crowding check skipped (funding_rate or oi_change_6h missing)")
        
        # 4. 极端成交量（PATCH-P0-02: None-safe）
        volume_1h = features.features.volume.volume_1h
        volume_24h = features.features.volume.volume_24h
        
        if volume_1h is not None and volume_24h is not None and volume_24h > 0:
            volume_avg = volume_24h / 24
            if volume_1h > volume_avg * risk_thresholds.extreme_volume.multiplier:
                tags.append(ReasonTag.EXTREME_VOLUME)
                return False, tags
        else:
            # 成交量数据缺失，跳过此规则
            logger.debug("Extreme volume check skipped (volume data missing)")
        
        # 通过所有风险检查
        return True, []
    
    # ========================================
    # Step 4: 交易质量评估
    # ========================================
    
    @staticmethod
    def _eval_trade_quality(
        features: FeatureSnapshot,
        regime: MarketRegime,
        thresholds: Thresholds,
        symbol: str
    ) -> Tuple[TradeQuality, List[ReasonTag]]:
        """
        交易质量评估（纯函数）
        
        提取自: market_state_machine_l1.py._eval_trade_quality() (PR-ARCH-02 M3-Step3)
        
        检查项：
        1. 吸纳风险（高失衡 + 低成交量）→ POOR
        2. 噪音市（费率波动大但无方向）→ UNCERTAIN
        3. 轮动风险（OI和价格背离）→ POOR
        4. 震荡市弱信号（imbalance弱 + OI变化小）→ UNCERTAIN
        
        None-safe: 关键字段缺失时降级到UNCERTAIN（不直接POOR）
        
        纯函数改造: 噪音市检测使用features.funding.funding_rate_prev（由FeatureBuilder提供）
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
            symbol: 交易对符号（用于日志）
        
        Returns:
            (TradeQuality, 原因标签列表)
        """
        tags = []
        
        # 获取阈值配置
        quality_thresholds = thresholds.trade_quality
        
        # 1. 吸纳风险（PATCH-P0-02: None-safe）
        imbalance_value = features.features.taker_imbalance.taker_imbalance_1h
        volume_1h = features.features.volume.volume_1h
        volume_24h = features.features.volume.volume_24h
        
        if imbalance_value is not None and volume_1h is not None and volume_24h is not None and volume_24h > 0:
            imbalance_abs = abs(imbalance_value)
            volume_avg = volume_24h / 24
            if (imbalance_abs > quality_thresholds.absorption.imbalance and 
                volume_1h < volume_avg * quality_thresholds.absorption.volume_ratio):
                tags.append(ReasonTag.ABSORPTION_RISK)
                return TradeQuality.POOR, tags
        elif imbalance_value is None or volume_1h is None or volume_24h is None:
            # PATCH-P0-02: 关键字段缺失 → 降级到UNCERTAIN（不直接POOR）
            logger.debug(f"[{symbol}] Absorption check skipped (imbalance/volume missing)")
            tags.append(ReasonTag.DATA_INCOMPLETE_MTF)
            return TradeQuality.UNCERTAIN, tags
        
        # 2. 噪音市（PATCH-P0-02: None-safe）
        # PR-ARCH-02: 使用FeatureSnapshot提供的funding_rate_prev（纯函数改造）
        funding_rate = features.features.funding.funding_rate
        funding_rate_prev = features.features.funding.funding_rate_prev
        
        if funding_rate is not None and funding_rate_prev is not None:
            funding_volatility = abs(funding_rate - funding_rate_prev)
            
            if (funding_volatility > quality_thresholds.noise.funding_volatility and 
                abs(funding_rate) < quality_thresholds.noise.funding_abs):
                tags.append(ReasonTag.NOISY_MARKET)
                return TradeQuality.UNCERTAIN, tags
        else:
            logger.debug(f"[{symbol}] Noise check skipped (funding_rate or funding_rate_prev missing)")
        
        # 3. 轮动风险（PATCH-P0-02: None-safe）
        price_change_1h = features.features.price.price_change_1h
        oi_change_1h = features.features.open_interest.oi_change_1h
        
        if price_change_1h is not None and oi_change_1h is not None:
            if ((price_change_1h > quality_thresholds.rotation.price_threshold and 
                 oi_change_1h < -quality_thresholds.rotation.oi_threshold) or
                (price_change_1h < -quality_thresholds.rotation.price_threshold and 
                 oi_change_1h > quality_thresholds.rotation.oi_threshold)):
                tags.append(ReasonTag.ROTATION_RISK)
                return TradeQuality.POOR, tags
        else:
            # PATCH-P0-02: 关键字段缺失 → 跳过规则
            logger.debug(f"[{symbol}] Rotation check skipped (price_change_1h or oi_change_1h missing)")
        
        # 4. 震荡市弱信号（PATCH-P0-02: None-safe）
        if regime == MarketRegime.RANGE:
            # 重新计算绝对值（前面已读取imbalance_value和oi_change_1h）
            imbalance_abs = abs(imbalance_value) if imbalance_value is not None else None
            oi_change_1h_abs = abs(oi_change_1h) if oi_change_1h is not None else None
            
            if imbalance_abs is not None and oi_change_1h_abs is not None:
                if (imbalance_abs < quality_thresholds.range_weak.imbalance and 
                    oi_change_1h_abs < quality_thresholds.range_weak.oi):
                    tags.append(ReasonTag.WEAK_SIGNAL_IN_RANGE)
                    return TradeQuality.UNCERTAIN, tags
            else:
                logger.debug(f"[{symbol}] Range weak signal check skipped (imbalance or oi_change missing)")
        
        # 通过所有质量检查
        return TradeQuality.GOOD, []
    
    # ========================================
    # Step 5: 方向评估
    # ========================================
    
    @staticmethod
    def _eval_long_direction(
        features: FeatureSnapshot,
        regime: MarketRegime,
        thresholds: Thresholds
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        做多方向评估（纯函数）
        
        提取自: market_state_machine_l1.py._eval_long_direction() (PR-ARCH-02 M3-Step4)
        
        逻辑：
        - TREND: imbalance > threshold AND oi_change > threshold AND price_change > threshold
        - RANGE: imbalance > threshold AND oi_change > threshold
        - RANGE短期机会: TODO（需要扩展models/thresholds.py添加DirectionThresholds）
        
        None-safe: 关键字段缺失时返回False（不误判LONG）
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
        
        Returns:
            (是否允许做多, 原因标签列表)
        """
        direction_tags = []
        
        # PATCH-P0-02: None-safe读取
        imbalance = features.features.taker_imbalance.taker_imbalance_1h
        oi_change = features.features.open_interest.oi_change_1h
        price_change = features.features.price.price_change_1h
        
        # 关键字段缺失，无法判断方向
        if imbalance is None or oi_change is None or price_change is None:
            logger.debug("Long direction eval skipped (key fields missing)")
            return False, direction_tags
        
        # TODO: 需要扩展models/thresholds.py添加DirectionThresholds
        # 临时使用硬编码阈值（应该从thresholds.direction读取）
        
        if regime == MarketRegime.TREND:
            # 趋势市：多方强势
            long_imbalance_trend = 0.6  # TODO: thresholds.direction.long_imbalance_trend
            long_oi_change_trend = 0.3  # TODO: thresholds.direction.long_oi_change_trend
            long_price_change_trend = 0.02  # TODO: thresholds.direction.long_price_change_trend
            
            if (imbalance > long_imbalance_trend and 
                oi_change > long_oi_change_trend and 
                price_change > long_price_change_trend):
                return True, direction_tags
        
        elif regime == MarketRegime.RANGE:
            # 震荡市：原有强信号逻辑
            long_imbalance_range = 0.7  # TODO: thresholds.direction.long_imbalance_range
            long_oi_change_range = 0.4  # TODO: thresholds.direction.long_oi_change_range
            
            if (imbalance > long_imbalance_range and 
                oi_change > long_oi_change_range):
                return True, direction_tags
            
            # TODO: 方案4：短期机会识别（综合指标，3选2确认）
            # 需要扩展models/thresholds.py添加:
            # - thresholds.direction.range.short_term_opportunity.long.min_price_change_1h
            # - thresholds.direction.range.short_term_opportunity.long.min_oi_change_1h
            # - thresholds.direction.range.short_term_opportunity.long.min_taker_imbalance
            # - thresholds.direction.range.short_term_opportunity.long.required_signals
        
        return False, direction_tags
    
    @staticmethod
    def _eval_short_direction(
        features: FeatureSnapshot,
        regime: MarketRegime,
        thresholds: Thresholds
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        做空方向评估（纯函数）
        
        提取自: market_state_machine_l1.py._eval_short_direction() (PR-ARCH-02 M3-Step4)
        
        逻辑：
        - TREND: imbalance < -threshold AND oi_change > threshold AND price_change < -threshold
        - RANGE: imbalance < -threshold AND oi_change > threshold
        - RANGE短期机会: TODO（需要扩展models/thresholds.py添加DirectionThresholds）
        
        None-safe: 关键字段缺失时返回False（不误判SHORT）
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
        
        Returns:
            (是否允许做空, 原因标签列表)
        """
        direction_tags = []
        
        # PATCH-P0-02: None-safe读取
        imbalance = features.features.taker_imbalance.taker_imbalance_1h
        oi_change = features.features.open_interest.oi_change_1h
        price_change = features.features.price.price_change_1h
        
        # 关键字段缺失，无法判断方向
        if imbalance is None or oi_change is None or price_change is None:
            logger.debug("Short direction eval skipped (key fields missing)")
            return False, direction_tags
        
        # TODO: 需要扩展models/thresholds.py添加DirectionThresholds
        # 临时使用硬编码阈值（应该从thresholds.direction读取）
        
        if regime == MarketRegime.TREND:
            # 趋势市：空方强势
            short_imbalance_trend = 0.6  # TODO: thresholds.direction.short_imbalance_trend
            short_oi_change_trend = 0.3  # TODO: thresholds.direction.short_oi_change_trend
            short_price_change_trend = 0.02  # TODO: thresholds.direction.short_price_change_trend
            
            if (imbalance < -short_imbalance_trend and 
                oi_change > short_oi_change_trend and 
                price_change < -short_price_change_trend):
                return True, direction_tags
        
        elif regime == MarketRegime.RANGE:
            # 震荡市：原有强信号逻辑
            short_imbalance_range = 0.7  # TODO: thresholds.direction.short_imbalance_range
            short_oi_change_range = 0.4  # TODO: thresholds.direction.short_oi_change_range
            
            if (imbalance < -short_imbalance_range and 
                oi_change > short_oi_change_range):
                return True, direction_tags
            
            # TODO: 方案4：短期机会识别（综合指标，3选2确认）
            # 需要扩展models/thresholds.py添加:
            # - thresholds.direction.range.short_term_opportunity.short.max_price_change_1h
            # - thresholds.direction.range.short_term_opportunity.short.min_oi_change_1h
            # - thresholds.direction.range.short_term_opportunity.short.max_taker_imbalance
            # - thresholds.direction.range.short_term_opportunity.short.required_signals
        
        return False, direction_tags
    
    # ========================================
    # Step 6: 决策优先级
    # ========================================
    
    @staticmethod
    def _decide_priority(
        allow_short: bool,
        allow_long: bool
    ) -> Tuple[Decision, List[ReasonTag]]:
        """
        决策优先级判断（纯函数）
        
        提取自: market_state_machine_l1.py._decide_priority() (PR-ARCH-02 M3-Step5)
        
        规则：SHORT > LONG > NO_TRADE
        冲突时：NO_TRADE（保守处理）
        
        Args:
            allow_short: 是否允许做空
            allow_long: 是否允许做多
        
        Returns:
            (Decision, 原因标签列表)
        """
        tags = []
        
        # 两个方向都不允许
        if not allow_short and not allow_long:
            tags.append(ReasonTag.NO_CLEAR_DIRECTION)
            return Decision.NO_TRADE, tags
        
        # 冲突（保守处理）
        if allow_short and allow_long:
            tags.append(ReasonTag.CONFLICTING_SIGNALS)
            return Decision.NO_TRADE, tags
        
        # SHORT优先
        if allow_short:
            tags.append(ReasonTag.STRONG_SELL_PRESSURE)
            return Decision.SHORT, tags
        
        # LONG
        if allow_long:
            tags.append(ReasonTag.STRONG_BUY_PRESSURE)
            return Decision.LONG, tags
        
        return Decision.NO_TRADE, tags
    
    # ========================================
    # Step 7: 资金费率降级
    # ========================================
    
    @staticmethod
    def _apply_funding_rate_downgrade(
        decision: Decision,
        features: FeatureSnapshot,
        thresholds: Thresholds
    ) -> Tuple[Decision, List[ReasonTag]]:
        """
        资金费率降级（纯函数）
        
        TODO: 从market_state_machine_l1.py相关逻辑提取（PR-ARCH-02 M3-Step6）
        
        规则：
        - LONG时，funding_rate > high_threshold → NO_TRADE
        - SHORT时，funding_rate < -high_threshold → NO_TRADE
        
        注意：需要在models/thresholds.py中添加funding_rate降级阈值
        
        Args:
            decision: 当前决策
            features: 特征快照
            thresholds: 阈值配置
        
        Returns:
            (Decision, 原因标签列表)
        """
        tags = []
        
        # TODO: 实现完整逻辑
        # 需要在thresholds中添加funding_rate降级配置
        # 临时实现：不降级
        
        return decision, tags
    
    # ========================================
    # Step 8: 执行权限判断
    # ========================================
    
    @staticmethod
    def _determine_execution_permission(
        regime: MarketRegime,
        quality: TradeQuality,
        decision: Decision,
        thresholds: Thresholds
    ) -> ExecutionPermission:
        """
        执行权限判断（策略层，纯函数）
        
        提取自: market_state_machine_l1.py相关逻辑（PR-ARCH-02 M3-Step7）
        
        规则（方案D）：
        - NO_TRADE → DENY
        - UNCERTAIN quality → ALLOW_REDUCED
        - POOR quality → DENY (should not reach here due to earlier filtering)
        - RANGE + GOOD → ALLOW
        - TREND + GOOD → ALLOW
        
        TODO: 需要完善规则，添加更多条件判断
        
        Args:
            regime: 市场环境
            quality: 交易质量
            decision: 决策
            thresholds: 阈值配置
        
        Returns:
            ExecutionPermission
        """
        # Rule 1: NO_TRADE总是DENY
        if decision == Decision.NO_TRADE:
            return ExecutionPermission.DENY
        
        # Rule 2: UNCERTAIN quality降级
        if quality == TradeQuality.UNCERTAIN:
            return ExecutionPermission.ALLOW_REDUCED
        
        # Rule 3: POOR quality（理论上不应该到这里，因为前面已过滤）
        if quality == TradeQuality.POOR:
            return ExecutionPermission.DENY
        
        # Rule 4: GOOD quality允许
        return ExecutionPermission.ALLOW
    
    # ========================================
    # Step 9: 置信度计算
    # ========================================
    
    @staticmethod
    def _compute_confidence(
        decision: Decision,
        regime: MarketRegime,
        quality: TradeQuality,
        reason_tags: List[ReasonTag],
        thresholds: Thresholds
    ) -> Confidence:
        """
        置信度计算（PR-D混合模式，纯函数）
        
        TODO: 从market_state_machine_l1.py._compute_confidence()提取（PR-ARCH-02 M3-Step8）
        
        流程：
        1. 基础加分（保持PR-005的加分制）
        2. 硬降级上限（caps）
        3. 强信号突破（+1档，不突破cap）
        
        需要在models/thresholds.py中添加:
        - thresholds.confidence_scoring.caps (EXTREME/RANGE caps)
        - thresholds.confidence_scoring.boosts (强信号加分)
        
        Args:
            decision: 决策
            regime: 市场环境
            quality: 交易质量
            reason_tags: 原因标签列表
            thresholds: 阈值配置
        
        Returns:
            Confidence
        """
        # TODO: 实现完整的PR-D混合模式置信度计算
        # 临时实现：简单规则
        
        if decision == Decision.NO_TRADE:
            return Confidence.LOW
        
        # 根据质量和环境简单映射
        if quality == TradeQuality.GOOD and regime == MarketRegime.TREND:
            return Confidence.HIGH
        elif quality == TradeQuality.GOOD:
            return Confidence.MEDIUM
        elif quality == TradeQuality.UNCERTAIN:
            return Confidence.LOW
        else:
            return Confidence.LOW


# ============================================
# 便捷函数
# ============================================

def evaluate_single_decision(
    features: FeatureSnapshot,
    thresholds: Thresholds,
    symbol: str = "UNKNOWN"
) -> TimeframeDecisionDraft:
    """
    便捷函数：单周期决策评估
    
    Args:
        features: 特征快照
        thresholds: 阈值配置
        symbol: 交易对符号
    
    Returns:
        TimeframeDecisionDraft
    """
    return DecisionCore.evaluate_single(features, thresholds, symbol)


def evaluate_dual_decision(
    features: FeatureSnapshot,
    thresholds: Thresholds,
    symbol: str = "UNKNOWN"
) -> DualTimeframeDecisionDraft:
    """
    便捷函数：双周期决策评估
    
    Args:
        features: 特征快照
        thresholds: 阈值配置
        symbol: 交易对符号
    
    Returns:
        DualTimeframeDecisionDraft
    """
    return DecisionCore.evaluate_dual(features, thresholds, symbol)
