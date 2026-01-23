"""
L1 Advisory Engine - 置信度计算模块

职责：
1. 置信度混合模式计算（加分+硬降级+强信号突破）
2. 执行许可计算
"""

from typing import List, Dict
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, ExecutionPermission
from models.reason_tags import ReasonTag, REASON_TAG_EXECUTABILITY, ExecutabilityLevel
import logging

logger = logging.getLogger(__name__)


class ConfidenceCalculator:
    """置信度计算器"""
    
    def __init__(self, config: Dict):
        """
        初始化置信度计算器
        
        Args:
            config: 完整配置字典
        """
        self.config = config
    
    def compute_confidence(
        self, 
        decision: Decision, 
        regime: MarketRegime, 
        quality: TradeQuality, 
        reason_tags: List[ReasonTag]
    ) -> Confidence:
        """
        置信度计算（混合模式）
        
        流程：
        1. 基础加分
        2. 硬降级上限（caps）
        3. 强信号突破（+1档，不突破cap）
        
        Args:
            decision: 决策
            regime: 市场环境
            quality: 交易质量
            reason_tags: 原因标签列表
        
        Returns:
            Confidence: 置信度
        """
        # NO_TRADE强制LOW
        if decision == Decision.NO_TRADE:
            return Confidence.LOW
        
        # ===== 第1步：基础加分 =====
        score = 0
        scoring_config = self.config.get('confidence_scoring', {})
        
        # 决策类型分
        if decision in [Decision.LONG, Decision.SHORT]:
            score += scoring_config.get('decision_score', 30)
        
        # 市场环境分
        if regime == MarketRegime.TREND:
            score += scoring_config.get('regime_trend_score', 30)
        elif regime == MarketRegime.RANGE:
            score += scoring_config.get('regime_range_score', 10)
        elif regime == MarketRegime.EXTREME:
            score += scoring_config.get('regime_extreme_score', 0)
        
        # 质量分
        if quality == TradeQuality.GOOD:
            score += scoring_config.get('quality_good_score', 30)
        elif quality == TradeQuality.UNCERTAIN:
            score += scoring_config.get('quality_uncertain_score', 15)
        elif quality == TradeQuality.POOR:
            score += scoring_config.get('quality_poor_score', 0)
        
        # 强信号加分
        boost_config = scoring_config.get('strong_signal_boost', {})
        required_tag_values = boost_config.get('required_tags', ['strong_buy_pressure', 'strong_sell_pressure'])
        
        strong_signals = []
        for tag_value in required_tag_values:
            try:
                strong_signals.append(ReasonTag(tag_value))
            except ValueError:
                logger.warning(f"Invalid required_tag in config: {tag_value}, skipping")
        
        has_strong_signal = any(tag in reason_tags for tag in strong_signals)
        if has_strong_signal:
            score += scoring_config.get('strong_signal_bonus', 10)
        
        # 映射到初始档位
        initial_confidence = self._score_to_confidence(score, scoring_config)
        
        # ===== 第2步：硬降级上限（caps）=====
        capped_confidence, has_cap = self._apply_confidence_caps(
            confidence=initial_confidence,
            quality=quality,
            reason_tags=reason_tags
        )
        
        # ===== 第3步：强信号突破（+1档，不突破cap）=====
        cap_limit = capped_confidence if has_cap else Confidence.ULTRA
        final_confidence = self._apply_strong_signal_boost(
            confidence=capped_confidence,
            reason_tags=reason_tags,
            cap_limit=cap_limit,
            has_strong_signal=has_strong_signal
        )
        
        return final_confidence
    
    def compute_execution_permission(self, reason_tags: List[ReasonTag]) -> ExecutionPermission:
        """
        计算执行许可级别
        
        映射规则：
        1. 频控标签 → DENY
        2. BLOCK级别标签 → DENY
        3. DEGRADE级别标签 → ALLOW_REDUCED
        4. 仅ALLOW级别标签 → ALLOW
        
        Args:
            reason_tags: 原因标签列表
        
        Returns:
            ExecutionPermission: 执行许可级别
        """
        # 优先级0: 频控标签（最高优先级）
        if ReasonTag.MIN_INTERVAL_BLOCK in reason_tags:
            logger.debug(f"[ExecPerm] DENY: MIN_INTERVAL_BLOCK (频控)")
            return ExecutionPermission.DENY
        
        if ReasonTag.FLIP_COOLDOWN_BLOCK in reason_tags:
            logger.debug(f"[ExecPerm] DENY: FLIP_COOLDOWN_BLOCK (频控)")
            return ExecutionPermission.DENY
        
        # 优先级0.5: EXTREME_VOLUME联立否决检查
        if ReasonTag.EXTREME_VOLUME in reason_tags:
            has_liquidation = ReasonTag.LIQUIDATION_PHASE in reason_tags
            has_extreme_regime = ReasonTag.EXTREME_REGIME in reason_tags
            
            if has_liquidation or has_extreme_regime:
                logger.debug(
                    f"[ExecPerm] DENY: EXTREME_VOLUME + "
                    f"{'LIQUIDATION_PHASE' if has_liquidation else 'EXTREME_REGIME'} "
                    f"(联立否决)"
                )
                return ExecutionPermission.DENY
        
        # 优先级1: 检查BLOCK级别标签
        for tag in reason_tags:
            exec_level = REASON_TAG_EXECUTABILITY.get(tag, ExecutabilityLevel.ALLOW)
            
            if exec_level == ExecutabilityLevel.BLOCK:
                logger.debug(f"[ExecPerm] DENY: found blocking tag {tag.value}")
                return ExecutionPermission.DENY
        
        # 优先级2: 检查DEGRADE级别标签
        for tag in reason_tags:
            exec_level = REASON_TAG_EXECUTABILITY.get(tag, ExecutabilityLevel.ALLOW)
            
            if exec_level == ExecutabilityLevel.DEGRADE:
                logger.debug(f"[ExecPerm] ALLOW_REDUCED: found degrading tag {tag.value}")
                return ExecutionPermission.ALLOW_REDUCED
        
        # 优先级3: 全是ALLOW级别
        logger.debug(f"[ExecPerm] ALLOW: no blocking or degrading tags")
        return ExecutionPermission.ALLOW
    
    def _score_to_confidence(self, score: int, scoring_config: dict) -> Confidence:
        """将分数映射到置信度档位"""
        thresholds = scoring_config.get('thresholds', {})
        ultra_threshold = thresholds.get('ultra', 90)
        high_threshold = thresholds.get('high', 65)
        medium_threshold = thresholds.get('medium', 40)
        
        if score >= ultra_threshold:
            return Confidence.ULTRA
        elif score >= high_threshold:
            return Confidence.HIGH
        elif score >= medium_threshold:
            return Confidence.MEDIUM
        else:
            return Confidence.LOW
    
    def _apply_confidence_caps(
        self,
        confidence: Confidence,
        quality: TradeQuality,
        reason_tags: List[ReasonTag]
    ) -> tuple:
        """应用硬降级上限"""
        scoring_config = self.config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        tag_rules = self.config.get('reason_tag_rules', {})
        
        has_cap = False
        
        # 1. UNCERTAIN质量上限
        if quality == TradeQuality.UNCERTAIN:
            max_level_str = caps_config.get('uncertain_quality_max', 'MEDIUM')
            max_level = self._string_to_confidence(max_level_str)
            if self._confidence_level(confidence) > self._confidence_level(max_level):
                logger.debug(f"[Cap] UNCERTAIN quality: {confidence.value} → {max_level.value}")
                confidence = max_level
                has_cap = True
        
        # 2. reduce_tags上限
        reduce_tags = tag_rules.get('reduce_tags', [])
        tag_caps = caps_config.get('tag_caps', {})
        reduce_default_max_str = caps_config.get('reduce_default_max', 
                                                  caps_config.get('uncertain_quality_max', 'MEDIUM'))
        
        for tag in reason_tags:
            tag_value = tag.value
            if tag_value in reduce_tags or tag_value in tag_caps:
                max_level_str = tag_caps.get(tag_value, reduce_default_max_str)
                max_level = self._string_to_confidence(max_level_str)
                if self._confidence_level(confidence) > self._confidence_level(max_level):
                    logger.debug(f"[Cap] Tag {tag_value}: {confidence.value} → {max_level.value}")
                    confidence = max_level
                    has_cap = True
        
        return confidence, has_cap
    
    def _apply_strong_signal_boost(
        self,
        confidence: Confidence,
        reason_tags: List[ReasonTag],
        cap_limit: Confidence,
        has_strong_signal: bool
    ) -> Confidence:
        """强信号突破"""
        boost_config = self.config.get('confidence_scoring', {}).get('strong_signal_boost', {})
        
        if not boost_config.get('enabled', True):
            return confidence
        
        if not has_strong_signal:
            return confidence
        
        # 提升1档
        boost_levels = boost_config.get('boost_levels', 1)
        boosted = self._boost_confidence(confidence, boost_levels)
        
        # 不能突破cap
        if self._confidence_level(boosted) > self._confidence_level(cap_limit):
            logger.debug(f"[Boost] Capped at {cap_limit.value}, cannot boost to {boosted.value}")
            return cap_limit
        
        if boosted != confidence:
            logger.debug(f"[Boost] Strong signal: {confidence.value} → {boosted.value}")
        
        return boosted
    
    def _boost_confidence(self, confidence: Confidence, levels: int) -> Confidence:
        """提升置信度档位"""
        order = [Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH, Confidence.ULTRA]
        try:
            current_idx = order.index(confidence)
            new_idx = min(current_idx + levels, len(order) - 1)
            return order[new_idx]
        except ValueError:
            return confidence
    
    def _confidence_level(self, confidence: Confidence) -> int:
        """置信度档位的数值表示（用于比较）"""
        order = {
            Confidence.LOW: 0,
            Confidence.MEDIUM: 1,
            Confidence.HIGH: 2,
            Confidence.ULTRA: 3
        }
        return order.get(confidence, 0)
    
    def _string_to_confidence(self, s: str) -> Confidence:
        """字符串转Confidence枚举"""
        mapping = {
            'LOW': Confidence.LOW,
            'MEDIUM': Confidence.MEDIUM,
            'HIGH': Confidence.HIGH,
            'ULTRA': Confidence.ULTRA
        }
        
        result = mapping.get(s.upper())
        if result is None:
            logger.error(
                f"⚠️ 配置错误: 未知的置信度字符串 '{s}'，"
                f"有效值: LOW/MEDIUM/HIGH/ULTRA，"
                f"已回退到 LOW（最保守）以确保安全"
            )
            return Confidence.LOW
        
        return result
