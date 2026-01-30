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
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, ExecutionPermission, Timeframe
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
        timeframe: 'Timeframe',
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
            timeframe: 周期标识（SHORT_TERM或MEDIUM_TERM）
            symbol: 交易对符号（用于日志）
        
        Returns:
            TimeframeDecisionDraft: 决策草稿
        """
        # Step 1: 数据验证
        # P0-1修复：根据timeframe检查对应的coverage
        if timeframe == Timeframe.SHORT_TERM:
            if not features.coverage.short_evaluable:
                logger.warning(f"[{symbol}] Short-term data insufficient")
                return create_no_trade_draft([ReasonTag.DATA_INCOMPLETE], MarketRegime.RANGE)
        elif timeframe == Timeframe.MEDIUM_TERM:
            if not features.coverage.medium_evaluable:
                logger.warning(f"[{symbol}] Medium-term data insufficient")
                return create_no_trade_draft([ReasonTag.DATA_INCOMPLETE_MTF], MarketRegime.RANGE)
        
        # Step 2: 市场环境识别 ✅
        regime, regime_tags = DecisionCore._detect_market_regime(features, thresholds, timeframe)
        
        # Step 3: 风险准入评估（第一道闸门） ✅
        risk_ok, risk_tags = DecisionCore._eval_risk_exposure(features, regime, thresholds)
        if not risk_ok:
            return create_no_trade_draft(risk_tags, regime)
        
        # Step 4: 交易质量评估（第二道闸门） ✅
        quality, quality_tags = DecisionCore._eval_trade_quality(features, regime, thresholds, symbol)
        if quality == TradeQuality.POOR:
            return create_no_trade_draft(quality_tags, regime)
        
        # Step 5: 方向评估 ✅（PR-FIX: 传递timeframe参数）
        allow_long, long_tags = DecisionCore._eval_long_direction(features, regime, thresholds, timeframe)
        allow_short, short_tags = DecisionCore._eval_short_direction(features, regime, thresholds, timeframe)
        
        # Step 6: 决策优先级 ✅
        decision, direction_tags = DecisionCore._decide_priority(allow_short, allow_long)
        
        # Step 7: 资金费率降级（TODO：实现完整逻辑）
        decision, funding_tags = DecisionCore._apply_funding_rate_downgrade(
            decision, features, thresholds
        )
        
        # 收集所有标签（Step 8和9需要）
        all_tags = regime_tags + risk_tags + quality_tags + long_tags + short_tags + direction_tags + funding_tags
        
        # Step 8: 执行权限判断（P0-04: 完全由ReasonTagRules驱动）
        execution_permission = DecisionCore._determine_execution_permission(
            regime, quality, decision, thresholds, all_tags
        )
        
        # Step 9: 置信度计算（PR-D混合模式）
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
        # TODO: 识别全局风险标签
        
        # ✅ P0-1修复：分别评估短期和中期，使用不同的timeframe参数
        from models.enums import Timeframe
        
        # 短期评估（5m/15m）
        short_draft = DecisionCore.evaluate_single(
            features, 
            thresholds, 
            Timeframe.SHORT_TERM,
            symbol
        )
        logger.debug(f"[{symbol}] Short-term evaluated: {short_draft.decision.value}")
        
        # 中期评估（1h/6h）
        medium_draft = DecisionCore.evaluate_single(
            features,
            thresholds,
            Timeframe.MEDIUM_TERM,
            symbol
        )
        logger.debug(f"[{symbol}] Medium-term evaluated: {medium_draft.decision.value}")
        
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
        thresholds: Thresholds,
        timeframe: 'Timeframe'
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
        
        P0-1修复：根据timeframe选择不同的判定逻辑
        - SHORT_TERM: 主要看5m/15m/1h数据
        - MEDIUM_TERM: 主要看1h/6h数据
        
        Args:
            features: 特征快照
            thresholds: 阈值配置
            timeframe: 周期标识
        
        Returns:
            (MarketRegime, 原因标签列表)
        """
        regime_tags = []
        
        # 提取price features（None-safe）
        price_change_1h = features.features.price.price_change_1h
        price_change_6h = features.features.price.price_change_6h
        price_change_15m = features.features.price.price_change_15m  # fallback
        price_change_5m = features.features.price.price_change_5m  # short-term
        
        # 获取阈值配置
        regime_thresholds = thresholds.market_regime
        
        # P0-1修复：根据timeframe选择不同的判定策略
        from models.enums import Timeframe
        
        # 1. EXTREME: 极端波动（优先级最高，两个周期都检查）
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
        thresholds: Thresholds,
        timeframe: 'Timeframe' = None
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        做多方向评估（纯函数）
        
        P0-02/P0-03 重构：
        - SHORT_TERM: 使用MultiTF三层触发（context_1h → confirm_15m → trigger_5m）
        - MEDIUM_TERM: 使用传统1h/6h判定
        
        None-safe: 关键字段缺失时返回False（不误判LONG）
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
            timeframe: 时间框架
        
        Returns:
            (是否允许做多, 原因标签列表)
        """
        direction_tags = []
        
        # P0-02/P0-03: SHORT_TERM使用MultiTF三层触发
        if timeframe == Timeframe.SHORT_TERM:
            return DecisionCore._eval_long_multi_tf(features, regime, thresholds)
        
        # MEDIUM_TERM或默认：使用传统1h/6h判定
        price_change = features.features.price.price_change_1h
        oi_change = features.features.open_interest.oi_change_1h
        imbalance = features.features.taker_imbalance.taker_imbalance_1h
        
        if imbalance is None or price_change is None:
            logger.debug(f"Long direction eval skipped (key fields missing)")
            return False, direction_tags
        
        if regime == MarketRegime.TREND:
            trend_cfg = thresholds.direction.trend.long
            imbalance_ok = imbalance > trend_cfg.imbalance
            price_ok = price_change > (trend_cfg.price_change or 0.004)
            
            if imbalance_ok and price_ok:
                direction_tags.append(ReasonTag.STRONG_BUY_PRESSURE)
                return True, direction_tags
        
        elif regime == MarketRegime.RANGE:
            range_cfg = thresholds.direction.range.long
            if (imbalance > range_cfg.imbalance and 
                oi_change is not None and oi_change > range_cfg.oi_change):
                direction_tags.append(ReasonTag.STRONG_BUY_PRESSURE)
                return True, direction_tags
        
        return False, direction_tags
    
    @staticmethod
    def _eval_long_multi_tf(
        features: FeatureSnapshot,
        regime: MarketRegime,
        thresholds: Thresholds
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        P0-03: MultiTF三层触发LONG评估（context_1h → confirm_15m → trigger_5m）
        
        三层逻辑：
        1. Context(1h): 大方向偏多（3选2）
        2. Confirm(15m): 确认信号（4选2）
        3. Trigger(5m): 入场触发（3选2）
        
        Returns:
            (是否触发LONG, 原因标签列表)
        """
        tags = []
        
        # 获取MultiTF配置
        multi_tf_cfg = thresholds.multi_tf
        if not multi_tf_cfg or not multi_tf_cfg.enabled:
            # MultiTF未启用，fallback到传统逻辑
            return False, tags
        
        # ===== Layer 1: Context (1h) =====
        context_cfg = multi_tf_cfg.context_1h.long if hasattr(multi_tf_cfg.context_1h, 'long') else None
        if not context_cfg:
            return False, tags
        
        price_1h = features.features.price.price_change_1h
        imbalance_1h = features.features.taker_imbalance.taker_imbalance_1h
        oi_1h = features.features.open_interest.oi_change_1h
        
        context_signals = 0
        if price_1h is not None and price_1h > context_cfg.min_price_change:
            context_signals += 1
        if imbalance_1h is not None and imbalance_1h > context_cfg.min_taker_imbalance:
            context_signals += 1
        if oi_1h is not None and oi_1h > context_cfg.min_oi_change:
            context_signals += 1
        
        required_context = context_cfg.required_signals if hasattr(context_cfg, 'required_signals') else 2
        if context_signals < required_context:
            tags.append(ReasonTag.LTF_CONTEXT_DENIED)
            logger.debug(f"LONG Context denied: {context_signals}/{required_context}")
            return False, tags
        
        # ===== Layer 2: Confirm (15m) =====
        confirm_cfg = multi_tf_cfg.confirm_15m.long if hasattr(multi_tf_cfg.confirm_15m, 'long') else None
        if not confirm_cfg:
            return False, tags
        
        price_15m = features.features.price.price_change_15m
        imbalance_15m = features.features.taker_imbalance.taker_imbalance_15m
        volume_ratio_15m = features.features.volume.volume_ratio_15m
        oi_15m = features.features.open_interest.oi_change_15m
        
        confirm_signals = 0
        if price_15m is not None and price_15m > confirm_cfg.min_price_change:
            confirm_signals += 1
        if imbalance_15m is not None and imbalance_15m > confirm_cfg.min_taker_imbalance:
            confirm_signals += 1
        if volume_ratio_15m is not None and volume_ratio_15m > confirm_cfg.min_volume_ratio:
            confirm_signals += 1
        if oi_15m is not None and oi_15m > confirm_cfg.min_oi_change:
            confirm_signals += 1
        
        required_confirm = confirm_cfg.required_confirmed if hasattr(confirm_cfg, 'required_confirmed') else 2
        required_partial = confirm_cfg.required_partial if hasattr(confirm_cfg, 'required_partial') else 1
        
        if confirm_signals >= required_confirm:
            tags.append(ReasonTag.LTF_CONFIRMED)
        elif confirm_signals >= required_partial:
            tags.append(ReasonTag.LTF_PARTIAL_CONFIRM)
        else:
            tags.append(ReasonTag.LTF_FAILED_CONFIRM)
            logger.debug(f"LONG Confirm failed: {confirm_signals}/{required_confirm}")
            return False, tags
        
        # ===== Layer 3: Trigger (5m) =====
        trigger_cfg = multi_tf_cfg.trigger_5m.long if hasattr(multi_tf_cfg.trigger_5m, 'long') else None
        if not trigger_cfg:
            # 如果没有trigger配置，Confirm通过即可
            tags.append(ReasonTag.STRONG_BUY_PRESSURE)
            return True, tags
        
        price_5m = features.features.price.price_change_5m
        imbalance_5m = features.features.taker_imbalance.taker_imbalance_5m
        volume_ratio_5m = features.features.volume.volume_ratio_5m
        
        trigger_signals = 0
        if price_5m is not None and price_5m > trigger_cfg.min_price_change:
            trigger_signals += 1
        if imbalance_5m is not None and imbalance_5m > trigger_cfg.min_taker_imbalance:
            trigger_signals += 1
        if volume_ratio_5m is not None and volume_ratio_5m > trigger_cfg.min_volume_ratio:
            trigger_signals += 1
        
        required_trigger = trigger_cfg.required_signals if hasattr(trigger_cfg, 'required_signals') else 2
        if trigger_signals >= required_trigger:
            tags.append(ReasonTag.STRONG_BUY_PRESSURE)
            logger.debug(f"LONG MultiTF triggered: context={context_signals}, confirm={confirm_signals}, trigger={trigger_signals}")
            return True, tags
        
        # Trigger不足，但有部分确认，降级输出
        if ReasonTag.LTF_PARTIAL_CONFIRM in tags:
            logger.debug(f"LONG Trigger weak but partial confirm: trigger={trigger_signals}/{required_trigger}")
            return True, tags
        
        logger.debug(f"LONG Trigger failed: {trigger_signals}/{required_trigger}")
        return False, tags
    
    @staticmethod
    def _eval_short_direction(
        features: FeatureSnapshot,
        regime: MarketRegime,
        thresholds: Thresholds,
        timeframe: 'Timeframe' = None
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        做空方向评估（纯函数）
        
        P0-02/P0-03 重构：
        - SHORT_TERM: 使用MultiTF三层触发（context_1h → confirm_15m → trigger_5m）
        - MEDIUM_TERM: 使用传统1h/6h判定
        
        None-safe: 关键字段缺失时返回False（不误判SHORT）
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
            timeframe: 时间框架
        
        Returns:
            (是否允许做空, 原因标签列表)
        """
        direction_tags = []
        
        # P0-02/P0-03: SHORT_TERM使用MultiTF三层触发
        if timeframe == Timeframe.SHORT_TERM:
            return DecisionCore._eval_short_multi_tf(features, regime, thresholds)
        
        # MEDIUM_TERM或默认：使用传统1h/6h判定
        price_change = features.features.price.price_change_1h
        oi_change = features.features.open_interest.oi_change_1h
        imbalance = features.features.taker_imbalance.taker_imbalance_1h
        
        if imbalance is None and price_change is None:
            logger.debug(f"Short direction eval skipped (key fields missing)")
            return False, direction_tags
        
        if regime == MarketRegime.TREND:
            trend_cfg = thresholds.direction.trend.short
            conditions_met = 0
            if imbalance is not None and imbalance < -trend_cfg.imbalance:
                conditions_met += 1
            if oi_change is not None and oi_change > trend_cfg.oi_change:
                conditions_met += 1
            if price_change is not None and price_change < -(trend_cfg.price_change or 0.004):
                conditions_met += 1
            
            if conditions_met >= 2:
                direction_tags.append(ReasonTag.STRONG_SELL_PRESSURE)
                return True, direction_tags
        
        elif regime == MarketRegime.RANGE:
            range_cfg = thresholds.direction.range.short
            if (imbalance is not None and imbalance < -range_cfg.imbalance and 
                oi_change is not None and oi_change > range_cfg.oi_change):
                direction_tags.append(ReasonTag.STRONG_SELL_PRESSURE)
                return True, direction_tags
        
        return False, direction_tags
    
    @staticmethod
    def _eval_short_multi_tf(
        features: FeatureSnapshot,
        regime: MarketRegime,
        thresholds: Thresholds
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        P0-03: MultiTF三层触发SHORT评估（context_1h → confirm_15m → trigger_5m）
        
        三层逻辑：
        1. Context(1h): 大方向偏空（3选2）
        2. Confirm(15m): 确认信号（4选2）
        3. Trigger(5m): 入场触发（3选2）
        
        Returns:
            (是否触发SHORT, 原因标签列表)
        """
        tags = []
        
        # 获取MultiTF配置
        multi_tf_cfg = thresholds.multi_tf
        if not multi_tf_cfg or not multi_tf_cfg.enabled:
            return False, tags
        
        # ===== Layer 1: Context (1h) =====
        context_cfg = multi_tf_cfg.context_1h.short if hasattr(multi_tf_cfg.context_1h, 'short') else None
        if not context_cfg:
            return False, tags
        
        price_1h = features.features.price.price_change_1h
        imbalance_1h = features.features.taker_imbalance.taker_imbalance_1h
        oi_1h = features.features.open_interest.oi_change_1h
        
        context_signals = 0
        if price_1h is not None and price_1h < context_cfg.max_price_change:
            context_signals += 1
        if imbalance_1h is not None and imbalance_1h < context_cfg.max_taker_imbalance:
            context_signals += 1
        if oi_1h is not None and oi_1h > context_cfg.min_oi_change:
            context_signals += 1
        
        required_context = context_cfg.required_signals if hasattr(context_cfg, 'required_signals') else 2
        if context_signals < required_context:
            tags.append(ReasonTag.LTF_CONTEXT_DENIED)
            logger.debug(f"SHORT Context denied: {context_signals}/{required_context}")
            return False, tags
        
        # ===== Layer 2: Confirm (15m) =====
        confirm_cfg = multi_tf_cfg.confirm_15m.short if hasattr(multi_tf_cfg.confirm_15m, 'short') else None
        if not confirm_cfg:
            return False, tags
        
        price_15m = features.features.price.price_change_15m
        imbalance_15m = features.features.taker_imbalance.taker_imbalance_15m
        volume_ratio_15m = features.features.volume.volume_ratio_15m
        oi_15m = features.features.open_interest.oi_change_15m
        
        confirm_signals = 0
        if price_15m is not None and price_15m < confirm_cfg.max_price_change:
            confirm_signals += 1
        if imbalance_15m is not None and imbalance_15m < confirm_cfg.max_taker_imbalance:
            confirm_signals += 1
        if volume_ratio_15m is not None and volume_ratio_15m > confirm_cfg.min_volume_ratio:
            confirm_signals += 1
        if oi_15m is not None and oi_15m > confirm_cfg.min_oi_change:
            confirm_signals += 1
        
        required_confirm = confirm_cfg.required_confirmed if hasattr(confirm_cfg, 'required_confirmed') else 2
        required_partial = confirm_cfg.required_partial if hasattr(confirm_cfg, 'required_partial') else 1
        
        if confirm_signals >= required_confirm:
            tags.append(ReasonTag.LTF_CONFIRMED)
        elif confirm_signals >= required_partial:
            tags.append(ReasonTag.LTF_PARTIAL_CONFIRM)
        else:
            tags.append(ReasonTag.LTF_FAILED_CONFIRM)
            logger.debug(f"SHORT Confirm failed: {confirm_signals}/{required_confirm}")
            return False, tags
        
        # ===== Layer 3: Trigger (5m) =====
        trigger_cfg = multi_tf_cfg.trigger_5m.short if hasattr(multi_tf_cfg.trigger_5m, 'short') else None
        if not trigger_cfg:
            tags.append(ReasonTag.STRONG_SELL_PRESSURE)
            return True, tags
        
        price_5m = features.features.price.price_change_5m
        imbalance_5m = features.features.taker_imbalance.taker_imbalance_5m
        volume_ratio_5m = features.features.volume.volume_ratio_5m
        
        trigger_signals = 0
        if price_5m is not None and price_5m < trigger_cfg.max_price_change:
            trigger_signals += 1
        if imbalance_5m is not None and imbalance_5m < trigger_cfg.max_taker_imbalance:
            trigger_signals += 1
        if volume_ratio_5m is not None and volume_ratio_5m > trigger_cfg.min_volume_ratio:
            trigger_signals += 1
        
        required_trigger = trigger_cfg.required_signals if hasattr(trigger_cfg, 'required_signals') else 2
        if trigger_signals >= required_trigger:
            tags.append(ReasonTag.STRONG_SELL_PRESSURE)
            logger.debug(f"SHORT MultiTF triggered: context={context_signals}, confirm={confirm_signals}, trigger={trigger_signals}")
            return True, tags
        
        if ReasonTag.LTF_PARTIAL_CONFIRM in tags:
            logger.debug(f"SHORT Trigger weak but partial confirm: trigger={trigger_signals}/{required_trigger}")
            return True, tags
        
        logger.debug(f"SHORT Trigger failed: {trigger_signals}/{required_trigger}")
        return False, tags
    
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
        thresholds: Thresholds,
        reason_tags: List[ReasonTag] = None
    ) -> ExecutionPermission:
        """
        执行权限判断（P0-04: 完全由ReasonTagRules驱动）
        
        规则：
        1. NO_TRADE → DENY（最高优先）
        2. 检查所有ReasonTag的ExecutabilityLevel
           - 任何BLOCK级别标签 → DENY
           - 任何DEGRADE级别标签 → ALLOW_REDUCED
           - 全是ALLOW级别 → ALLOW
        
        Args:
            regime: 市场环境（仅用于日志，不影响Permission）
            quality: 交易质量（仅用于日志，不影响Permission）
            decision: 决策
            thresholds: 阈值配置
            reason_tags: 原因标签列表
        
        Returns:
            ExecutionPermission
        """
        from models.reason_tags import REASON_TAG_EXECUTABILITY, ExecutabilityLevel
        
        # Rule 1: NO_TRADE总是DENY
        if decision == Decision.NO_TRADE:
            return ExecutionPermission.DENY
        
        # P0-04: 完全由ReasonTags驱动
        if reason_tags is None:
            reason_tags = []
        
        has_block = False
        has_degrade = False
        
        for tag in reason_tags:
            level = REASON_TAG_EXECUTABILITY.get(tag, ExecutabilityLevel.ALLOW)
            if level == ExecutabilityLevel.BLOCK:
                has_block = True
                logger.debug(f"Permission: BLOCK tag found - {tag.value}")
                break  # BLOCK立即终止
            elif level == ExecutabilityLevel.DEGRADE:
                has_degrade = True
                logger.debug(f"Permission: DEGRADE tag found - {tag.value}")
        
        # Rule 2: BLOCK标签 → DENY
        if has_block:
            return ExecutionPermission.DENY
        
        # Rule 3: DEGRADE标签 → ALLOW_REDUCED
        if has_degrade:
            return ExecutionPermission.ALLOW_REDUCED
        
        # Rule 4: 全是ALLOW级别 → ALLOW
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
        置信度计算（P0-05增强：tag_caps生效）
        
        流程：
        1. 基础加分（保持PR-005的加分制）
        2. 档位映射
        3. tag_caps应用（只cap，不硬降）
        4. 强信号突破（+1档，不突破cap）
        
        P0-05改进：
        - UNCERTAIN不再总是LOW，而是参与正常评分
        - tag_caps按标签类型独立cap
        - caps只限制上限，不强制降级
        
        Args:
            decision: 决策
            regime: 市场环境
            quality: 交易质量
            reason_tags: 原因标签列表
            thresholds: 阈值配置
        
        Returns:
            Confidence
        """
        # NO_TRADE总是LOW
        if decision == Decision.NO_TRADE:
            return Confidence.LOW
        
        # 从配置读取评分参数
        scoring = thresholds.confidence_scoring
        
        # 置信度优先级映射
        CONF_PRIORITY = {Confidence.ULTRA: 4, Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1}
        
        # Step 1: 基础加分
        score = 0
        
        # 决策分（有方向=加分）
        score += scoring.decision_score  # 30分
        
        # 市场环境分
        if regime == MarketRegime.TREND:
            score += scoring.regime_trend_score  # 35分
        elif regime == MarketRegime.RANGE:
            score += scoring.regime_range_score  # 0分（回测优化后）
        elif regime == MarketRegime.EXTREME:
            score += scoring.regime_extreme_score  # 0分
        
        # 质量分（P0-05: UNCERTAIN不再总是LOW，参与正常评分）
        if quality == TradeQuality.GOOD:
            score += scoring.quality_good_score  # 30分
        elif quality == TradeQuality.UNCERTAIN:
            score += scoring.quality_uncertain_score  # 15分（不再强制LOW）
        elif quality == TradeQuality.POOR:
            score += scoring.quality_poor_score  # 0分
        
        # 强信号加分（在cap之前）
        strong_tags = {ReasonTag.STRONG_BUY_PRESSURE, ReasonTag.STRONG_SELL_PRESSURE}
        has_strong_signal = scoring.strong_signal_boost.enabled and any(t in strong_tags for t in reason_tags)
        if has_strong_signal:
            score += scoring.strong_signal_bonus  # 15分
        
        # Step 2: 档位映射
        thresholds_map = scoring.thresholds
        if score >= thresholds_map.ultra:
            confidence = Confidence.ULTRA
        elif score >= thresholds_map.high:
            confidence = Confidence.HIGH
        elif score >= thresholds_map.medium:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW
        
        logger.debug(f"Confidence before caps: score={score}, confidence={confidence.value}")
        
        # Step 3: tag_caps应用（P0-05核心：只cap，不硬降）
        caps = scoring.caps
        
        # 3.1 检查tag_caps（每个标签独立cap）
        tag_caps_config = caps.tag_caps if hasattr(caps, 'tag_caps') and caps.tag_caps else {}
        applied_caps = []
        
        for tag in reason_tags:
            tag_key = tag.value
            if tag_key in tag_caps_config:
                cap_str = tag_caps_config[tag_key]
                try:
                    cap_conf = Confidence[cap_str.upper()]
                    applied_caps.append((tag_key, cap_conf))
                except KeyError:
                    logger.warning(f"Invalid cap confidence: {cap_str}")
        
        # 3.2 应用最严格的cap
        if applied_caps:
            min_cap = min(applied_caps, key=lambda x: CONF_PRIORITY.get(x[1], 0))
            cap_confidence = min_cap[1]
            if CONF_PRIORITY.get(confidence, 0) > CONF_PRIORITY.get(cap_confidence, 0):
                logger.debug(f"Confidence capped by {min_cap[0]}: {confidence.value} → {cap_confidence.value}")
                confidence = cap_confidence
        
        # 3.3 检查reduce_tags的默认cap
        reduce_tags = set(thresholds.reason_tag_rules.reduce_tags) if thresholds.reason_tag_rules else set()
        reduce_tag_values = {rt.value if hasattr(rt, 'value') else rt for rt in reduce_tags}
        has_reduce_tag = any(t.value in reduce_tag_values for t in reason_tags)
        
        if has_reduce_tag and caps.reduce_default_max:
            try:
                default_cap = Confidence[caps.reduce_default_max.upper()]
                if CONF_PRIORITY.get(confidence, 0) > CONF_PRIORITY.get(default_cap, 0):
                    logger.debug(f"Confidence capped by reduce_default_max: {confidence.value} → {default_cap.value}")
                    confidence = default_cap
            except KeyError:
                pass
        
        # 3.4 UNCERTAIN质量上限（可选，如果配置了）
        if quality == TradeQuality.UNCERTAIN and caps.uncertain_quality_max:
            try:
                uncertain_cap = Confidence[caps.uncertain_quality_max.upper()]
                if CONF_PRIORITY.get(confidence, 0) > CONF_PRIORITY.get(uncertain_cap, 0):
                    logger.debug(f"Confidence capped by uncertain_quality: {confidence.value} → {uncertain_cap.value}")
                    confidence = uncertain_cap
            except KeyError:
                pass
        
        logger.debug(f"Confidence final: score={score}, confidence={confidence.value}")
        return confidence


# ============================================
# 便捷函数
# ============================================

def evaluate_single_decision(
    features: FeatureSnapshot,
    thresholds: Thresholds,
    timeframe: 'Timeframe',
    symbol: str = "UNKNOWN"
) -> TimeframeDecisionDraft:
    """
    便捷函数：单周期决策评估
    
    Args:
        features: 特征快照
        thresholds: 阈值配置
        timeframe: 周期标识
        symbol: 交易对符号
    
    Returns:
        TimeframeDecisionDraft
    """
    return DecisionCore.evaluate_single(features, thresholds, timeframe, symbol)


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
