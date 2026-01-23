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
        # TODO: Step 1: 数据验证
        # 检查features.coverage.short_evaluable或medium_evaluable
        # 缺失关键数据时返回create_no_trade_draft([ReasonTag.DATA_INCOMPLETE])
        
        # TODO: Step 2: 市场环境识别
        regime, regime_tags = DecisionCore._detect_market_regime(features, thresholds)
        
        # TODO: Step 3: 风险准入评估（第一道闸门）
        risk_ok, risk_tags = DecisionCore._eval_risk_exposure(features, regime, thresholds)
        if not risk_ok:
            return create_no_trade_draft(risk_tags, regime)
        
        # TODO: Step 4: 交易质量评估（第二道闸门）
        quality, quality_tags = DecisionCore._eval_trade_quality(features, regime, thresholds, symbol)
        if quality == TradeQuality.POOR:
            return create_no_trade_draft(quality_tags, regime)
        
        # TODO: Step 5: 方向评估
        allow_long, long_tags = DecisionCore._eval_long_direction(features, regime, thresholds)
        allow_short, short_tags = DecisionCore._eval_short_direction(features, regime, thresholds)
        
        # TODO: Step 6: 决策优先级
        decision, direction_tags = DecisionCore._decide_priority(allow_short, allow_long)
        
        # TODO: Step 7: 资金费率降级
        decision, funding_tags = DecisionCore._apply_funding_rate_downgrade(
            decision, features, thresholds
        )
        
        # TODO: Step 8: 执行权限判断（策略层）
        execution_permission = DecisionCore._determine_execution_permission(
            regime, quality, decision, thresholds
        )
        
        # TODO: Step 9: 置信度计算
        all_tags = regime_tags + risk_tags + quality_tags + long_tags + short_tags + direction_tags + funding_tags
        confidence = DecisionCore._compute_confidence(
            decision, regime, quality, all_tags, thresholds
        )
        
        # TODO: Step 10: 组装DecisionDraft
        return TimeframeDecisionDraft(
            decision=decision,
            confidence=confidence,
            market_regime=regime,
            trade_quality=quality,
            execution_permission=execution_permission,
            reason_tags=all_tags,
            key_metrics={}  # TODO: 添加关键指标
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
        
        TODO: 从market_state_machine_l1.py._detect_market_regime()提取
        
        逻辑：
        1. EXTREME: price_change_1h > extreme_threshold
        2. TREND: price_change_6h > trend_threshold 或 price_change_1h > short_term_trend_threshold
        3. RANGE: 默认
        
        Args:
            features: 特征快照
            thresholds: 阈值配置
        
        Returns:
            (MarketRegime, 原因标签列表)
        """
        # TODO: 实现逻辑
        return MarketRegime.RANGE, []
    
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
        
        TODO: 从market_state_machine_l1.py._eval_risk_exposure_allowed()提取
        
        检查项：
        1. 极端行情（EXTREME regime）
        2. 清算阶段（price急变 + OI急降）
        3. 拥挤风险（极端费率 + 高OI增长）
        4. 极端成交量
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
        
        Returns:
            (是否允许风险敞口, 原因标签列表)
        """
        # TODO: 实现逻辑
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
        
        TODO: 从market_state_machine_l1.py._eval_trade_quality()提取
        
        检查项：
        1. 吸纳风险（高失衡 + 低成交量）
        2. 噪音市（费率波动大但无方向）
        3. 轮动风险（OI和价格背离）
        4. 震荡市弱信号
        
        注意：噪音市检测需要funding_rate_prev，需要特殊处理
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
            symbol: 交易对符号
        
        Returns:
            (TradeQuality, 原因标签列表)
        """
        # TODO: 实现逻辑
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
        
        TODO: 从market_state_machine_l1.py._eval_long_direction()提取
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
        
        Returns:
            (是否允许做多, 原因标签列表)
        """
        # TODO: 实现逻辑
        return False, []
    
    @staticmethod
    def _eval_short_direction(
        features: FeatureSnapshot,
        regime: MarketRegime,
        thresholds: Thresholds
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        做空方向评估（纯函数）
        
        TODO: 从market_state_machine_l1.py._eval_short_direction()提取
        
        Args:
            features: 特征快照
            regime: 市场环境
            thresholds: 阈值配置
        
        Returns:
            (是否允许做空, 原因标签列表)
        """
        # TODO: 实现逻辑
        return False, []
    
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
        
        TODO: 从market_state_machine_l1.py._decide_priority()提取
        
        规则：SHORT > LONG > NO_TRADE
        冲突时：NO_TRADE
        
        Args:
            allow_short: 是否允许做空
            allow_long: 是否允许做多
        
        Returns:
            (Decision, 原因标签列表)
        """
        # TODO: 实现逻辑
        return Decision.NO_TRADE, [ReasonTag.NO_CLEAR_DIRECTION]
    
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
        
        TODO: 从market_state_machine_l1.py相关逻辑提取
        
        规则：
        - LONG时，funding_rate > high_threshold → NO_TRADE
        - SHORT时，funding_rate < -high_threshold → NO_TRADE
        
        Args:
            decision: 当前决策
            features: 特征快照
            thresholds: 阈值配置
        
        Returns:
            (Decision, 原因标签列表)
        """
        # TODO: 实现逻辑
        return decision, []
    
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
        
        TODO: 从market_state_machine_l1.py相关逻辑提取
        
        规则（方案D）：
        - NO_TRADE → DENY
        - UNCERTAIN quality → ALLOW_REDUCED
        - RANGE + weak signals → ALLOW_REDUCED
        - 其他 → ALLOW
        
        Args:
            regime: 市场环境
            quality: 交易质量
            decision: 决策
            thresholds: 阈值配置
        
        Returns:
            ExecutionPermission
        """
        # TODO: 实现逻辑
        if decision == Decision.NO_TRADE:
            return ExecutionPermission.DENY
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
        
        TODO: 从market_state_machine_l1.py._compute_confidence()提取
        
        流程：
        1. 基础加分（保持PR-005的加分制）
        2. 硬降级上限（caps）
        3. 强信号突破（+1档，不突破cap）
        
        Args:
            decision: 决策
            regime: 市场环境
            quality: 交易质量
            reason_tags: 原因标签列表
            thresholds: 阈值配置
        
        Returns:
            Confidence
        """
        # TODO: 实现逻辑
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
