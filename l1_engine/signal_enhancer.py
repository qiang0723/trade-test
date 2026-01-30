"""
L1 Advisory Engine - 信号增强模块（Phase 1/2）

负责评估增强信号：
1. Phase 1.1: 资金费率极端反转信号
2. Phase 1.2: OI与价格背离信号
3. Phase 1.3: 多周期一致性评分
4. Phase 2: 大户多空比信号（预留）

设计原则：
- 纯函数：无状态，相同输入相同输出
- 可选增强：不影响核心决策逻辑，仅提供加分/减分
- 独立模块：易于测试和维护
"""

import logging
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass
from models.reason_tags import ReasonTag
from models.enums import Decision

logger = logging.getLogger(__name__)


@dataclass
class EnhancementResult:
    """增强评估结果"""
    tags: List[ReasonTag]           # 触发的标签
    confidence_boost: int           # 置信度加分（可正可负）
    signal_quality: str             # 信号质量评估: 'strong', 'moderate', 'weak', 'neutral'
    details: Dict                   # 详细信息


class SignalEnhancer:
    """
    信号增强器
    
    评估各种增强信号，为决策提供额外的信息维度
    """
    
    # 默认阈值配置
    DEFAULT_THRESHOLDS = {
        # Phase 1.1: 资金费率极端反转
        'funding_extreme_positive': 0.001,     # 正极端费率 > 0.1%
        'funding_extreme_negative': -0.001,    # 负极端费率 < -0.1%
        'funding_very_extreme': 0.002,         # 非常极端费率 > 0.2%
        
        # Phase 1.2: OI与价格背离
        'divergence_price_threshold': 0.01,    # 价格变化阈值 1%
        'divergence_oi_threshold': 0.02,       # OI变化阈值 2%
        'healthy_trend_oi_threshold': 0.01,    # 健康趋势OI阈值 1%
        
        # Phase 1.3: 多周期一致性
        'alignment_imbalance_threshold': 0.05, # 方向判定阈值 5%
        
        # Phase 2: 大户多空比（P0-3优化：增强权重）
        'top_trader_bias_threshold': 0.55,     # 偏向阈值 55%
        'top_trader_extreme_threshold': 0.70,  # 极端阈值 70%
        'smart_money_divergence_boost': 16,    # 聪明钱背离加分（12→16）
        'bias_confirm_boost': 10,              # 偏向确认加分（8→10）
        'extreme_reverse_boost': 8,            # 极端逆向加分（5→8）
        'extreme_follow_penalty': -8,          # 极端顺向惩罚（-5→-8）
        'retail_divergence_threshold': 0.15,   # 大户-散户偏差阈值
        'retail_divergence_bonus': 3,          # 偏差加分
        
        # P0-1: 24h长期趋势
        'long_term_strong_threshold': 0.05,    # 强趋势 5%
        'long_term_range_threshold': 0.02,     # 震荡 2%
        'long_term_trend_boost': 8,            # 趋势确认加分
        'long_term_counter_penalty': -5,       # 逆势惩罚
        
        # P0-4: 1h放量确认
        'volume_surge_threshold': 2.0,         # 大幅放量 2x
        'volume_moderate_threshold': 1.5,      # 中度放量 1.5x
        'volume_low_threshold': 0.5,           # 缩量 0.5x
        'volume_surge_boost': 8,               # 大幅放量加分
        'volume_moderate_boost': 5,            # 中度放量加分
        'volume_low_penalty': -3,              # 缩量惩罚
    }
    
    def __init__(self, thresholds: Dict = None):
        """
        初始化信号增强器
        
        Args:
            thresholds: 阈值配置（可选，使用默认值）
        """
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        logger.info("SignalEnhancer initialized (Phase 1/2)")
    
    # ========================================
    # Phase 1.1: 资金费率极端反转信号
    # ========================================
    
    def eval_funding_extreme(
        self,
        funding_rate: Optional[float],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估资金费率极端反转信号
        
        逻辑：
        1. 极端正费率（>0.1%）+ 做空决策 → 顺势，但拥挤风险
        2. 极端正费率（>0.1%）+ 做多决策 → 逆势，但收取费率（TAILWIND）
        3. 极端负费率（<-0.1%）+ 做多决策 → 顺势，但拥挤风险
        4. 极端负费率（<-0.1%）+ 做空决策 → 逆势，但收取费率（TAILWIND）
        
        关键洞察：
        - 极端费率 + 逆势开仓 = 高概率反转信号
        - 极端费率 + 顺势开仓 = 拥挤风险
        
        Args:
            funding_rate: 当前资金费率（小数格式，0.001=0.1%）
            decision: 当前决策方向
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {'funding_rate': funding_rate}
        
        if funding_rate is None or decision == Decision.NO_TRADE:
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        extreme_pos = self.thresholds['funding_extreme_positive']
        extreme_neg = self.thresholds['funding_extreme_negative']
        very_extreme = self.thresholds['funding_very_extreme']
        
        # 极端正费率（多头拥挤）
        if funding_rate > extreme_pos:
            details['funding_status'] = 'extreme_positive'
            
            if decision == Decision.SHORT:
                # 做空 + 极端正费率 = 反转信号（收取高费率）
                tags.append(ReasonTag.FUNDING_EXTREME_SHORT)
                if funding_rate > very_extreme:
                    tags.append(ReasonTag.FUNDING_EXTREME_REVERSAL)
                    confidence_boost = 15  # 非常强的反转信号
                    signal_quality = 'strong'
                else:
                    confidence_boost = 10
                    signal_quality = 'moderate'
                logger.info(f"Funding extreme reversal (SHORT): rate={funding_rate:.4f}, boost={confidence_boost}")
            else:
                # 做多 + 极端正费率 = 顺势拥挤（警告但不加分）
                confidence_boost = -5
                signal_quality = 'weak'
                details['warning'] = 'crowding_with_trend'
        
        # 极端负费率（空头拥挤）
        elif funding_rate < extreme_neg:
            details['funding_status'] = 'extreme_negative'
            
            if decision == Decision.LONG:
                # 做多 + 极端负费率 = 反转信号（收取高费率）
                tags.append(ReasonTag.FUNDING_EXTREME_LONG)
                if funding_rate < -very_extreme:
                    tags.append(ReasonTag.FUNDING_EXTREME_REVERSAL)
                    confidence_boost = 15
                    signal_quality = 'strong'
                else:
                    confidence_boost = 10
                    signal_quality = 'moderate'
                logger.info(f"Funding extreme reversal (LONG): rate={funding_rate:.4f}, boost={confidence_boost}")
            else:
                # 做空 + 极端负费率 = 顺势拥挤
                confidence_boost = -5
                signal_quality = 'weak'
                details['warning'] = 'crowding_with_trend'
        
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    # ========================================
    # Phase 1.2: OI与价格背离信号
    # ========================================
    
    def eval_oi_price_divergence(
        self,
        price_change_1h: Optional[float],
        oi_change_1h: Optional[float],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估OI与价格背离信号
        
        背离类型：
        1. 看涨背离：价格↓ + OI↑ → 新空头入场，可能反弹
        2. 看跌背离：价格↑ + OI↓ → 多头出场，可能回调
        3. 健康上涨：价格↑ + OI↑ → 新资金入场
        4. 健康下跌：价格↓ + OI↑ → 新空头入场
        
        Args:
            price_change_1h: 1小时价格变化（小数格式）
            oi_change_1h: 1小时OI变化（小数格式）
            decision: 当前决策方向
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {
            'price_change_1h': price_change_1h,
            'oi_change_1h': oi_change_1h
        }
        
        if price_change_1h is None or oi_change_1h is None:
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        price_threshold = self.thresholds['divergence_price_threshold']
        oi_threshold = self.thresholds['divergence_oi_threshold']
        healthy_oi_threshold = self.thresholds['healthy_trend_oi_threshold']
        
        # 看涨背离：价格下跌但OI增长
        if price_change_1h < -price_threshold and oi_change_1h > oi_threshold:
            tags.append(ReasonTag.OI_PRICE_DIVERGENCE_BULL)
            details['divergence_type'] = 'bullish'
            
            if decision == Decision.LONG:
                # 做多 + 看涨背离 = 强信号
                confidence_boost = 10
                signal_quality = 'strong'
                logger.info(f"Bullish divergence confirmed: price={price_change_1h:.2%}, oi={oi_change_1h:.2%}")
            elif decision == Decision.SHORT:
                # 做空 + 看涨背离 = 警告
                confidence_boost = -10
                signal_quality = 'weak'
                details['warning'] = 'divergence_against_decision'
        
        # 看跌背离：价格上涨但OI下降
        elif price_change_1h > price_threshold and oi_change_1h < -oi_threshold:
            tags.append(ReasonTag.OI_PRICE_DIVERGENCE_BEAR)
            details['divergence_type'] = 'bearish'
            
            if decision == Decision.SHORT:
                # 做空 + 看跌背离 = 强信号
                confidence_boost = 10
                signal_quality = 'strong'
                logger.info(f"Bearish divergence confirmed: price={price_change_1h:.2%}, oi={oi_change_1h:.2%}")
            elif decision == Decision.LONG:
                # 做多 + 看跌背离 = 警告
                confidence_boost = -10
                signal_quality = 'weak'
                details['warning'] = 'divergence_against_decision'
        
        # 健康上涨：价格上涨 + OI增长
        elif price_change_1h > price_threshold and oi_change_1h > healthy_oi_threshold:
            tags.append(ReasonTag.HEALTHY_UPTREND)
            details['trend_health'] = 'healthy_up'
            
            if decision == Decision.LONG:
                confidence_boost = 8
                signal_quality = 'strong'
            else:
                confidence_boost = -5
                signal_quality = 'weak'
        
        # 健康下跌：价格下跌 + OI增长（新空头入场）
        elif price_change_1h < -price_threshold and oi_change_1h > healthy_oi_threshold:
            tags.append(ReasonTag.HEALTHY_DOWNTREND)
            details['trend_health'] = 'healthy_down'
            
            if decision == Decision.SHORT:
                confidence_boost = 8
                signal_quality = 'strong'
            else:
                confidence_boost = -5
                signal_quality = 'weak'
        
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    # ========================================
    # Phase 1.3: 多周期一致性评分
    # ========================================
    
    def eval_timeframe_alignment(
        self,
        imbalance_5m: Optional[float],
        imbalance_15m: Optional[float],
        imbalance_1h: Optional[float],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估多周期方向一致性
        
        逻辑：
        - 所有周期同向 → 高质量信号
        - 大部分周期同向 → 中等质量
        - 周期方向不一致 → 信号不稳定
        
        Args:
            imbalance_5m: 5分钟失衡度
            imbalance_15m: 15分钟失衡度
            imbalance_1h: 1小时失衡度
            decision: 当前决策方向
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {
            'imbalance_5m': imbalance_5m,
            'imbalance_15m': imbalance_15m,
            'imbalance_1h': imbalance_1h
        }
        
        if decision == Decision.NO_TRADE:
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        threshold = self.thresholds['alignment_imbalance_threshold']
        
        # 计算各周期方向
        def get_direction(imb: Optional[float]) -> int:
            if imb is None:
                return 0
            if imb > threshold:
                return 1   # 做多方向
            elif imb < -threshold:
                return -1  # 做空方向
            return 0       # 中性
        
        dir_5m = get_direction(imbalance_5m)
        dir_15m = get_direction(imbalance_15m)
        dir_1h = get_direction(imbalance_1h)
        
        directions = [dir_5m, dir_15m, dir_1h]
        non_zero = [d for d in directions if d != 0]
        
        details['directions'] = {'5m': dir_5m, '15m': dir_15m, '1h': dir_1h}
        
        if len(non_zero) == 0:
            # 全部中性
            signal_quality = 'neutral'
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        # 计算一致性
        alignment_sum = sum(non_zero)
        alignment_count = len(non_zero)
        alignment_score = abs(alignment_sum) / alignment_count
        
        details['alignment_score'] = alignment_score
        
        # 判断是否与决策方向一致
        expected_dir = 1 if decision == Decision.LONG else -1
        direction_match = (alignment_sum * expected_dir) > 0
        
        # 全部一致
        if alignment_count == 3 and abs(alignment_sum) == 3:
            tags.append(ReasonTag.TIMEFRAME_FULL_ALIGNMENT)
            if direction_match:
                confidence_boost = 12
                signal_quality = 'strong'
                logger.info(f"Full timeframe alignment: {directions} → {decision.value}")
            else:
                confidence_boost = -12
                signal_quality = 'weak'
                details['warning'] = 'alignment_against_decision'
        
        # 大部分一致（2/3）
        elif alignment_count >= 2 and abs(alignment_sum) >= 2:
            tags.append(ReasonTag.TIMEFRAME_PARTIAL_ALIGNMENT)
            if direction_match:
                confidence_boost = 6
                signal_quality = 'moderate'
            else:
                confidence_boost = -6
                signal_quality = 'weak'
        
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    # ========================================
    # Phase 2: 大户多空比（P0-3优化：增强权重）
    # ========================================
    
    def eval_top_trader_ratio(
        self,
        top_long_ratio: Optional[float],
        retail_long_ratio: Optional[float],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估大户多空比信号（P0-3优化：增强权重）
        
        Args:
            top_long_ratio: 大户做多比例（0-1）
            retail_long_ratio: 散户做多比例（0-1）
            decision: 当前决策方向
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {
            'top_long_ratio': top_long_ratio,
            'retail_long_ratio': retail_long_ratio
        }
        
        if top_long_ratio is None:
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        bias_threshold = self.thresholds['top_trader_bias_threshold']
        extreme_threshold = self.thresholds['top_trader_extreme_threshold']
        
        # P0-3: 使用配置的权重（增强版）
        bias_confirm_boost = self.thresholds.get('bias_confirm_boost', 10)
        extreme_reverse_boost = self.thresholds.get('extreme_reverse_boost', 8)
        extreme_follow_penalty = self.thresholds.get('extreme_follow_penalty', -8)
        smart_money_boost = self.thresholds.get('smart_money_divergence_boost', 16)
        retail_divergence_threshold = self.thresholds.get('retail_divergence_threshold', 0.15)
        retail_divergence_bonus = self.thresholds.get('retail_divergence_bonus', 3)
        
        # 大户偏多
        if top_long_ratio > bias_threshold:
            if top_long_ratio > extreme_threshold:
                tags.append(ReasonTag.TOP_TRADER_EXTREME_LONG)
                details['top_trader_status'] = 'extreme_long'
                # 极端偏多可能预示反转
                if decision == Decision.SHORT:
                    confidence_boost = extreme_reverse_boost  # 逆向信号加分（5→8）
                else:
                    confidence_boost = extreme_follow_penalty  # 警告（-5→-8）
            else:
                tags.append(ReasonTag.TOP_TRADER_LONG_BIAS)
                details['top_trader_status'] = 'long_bias'
                if decision == Decision.LONG:
                    confidence_boost = bias_confirm_boost  # 偏向确认（8→10）
                    signal_quality = 'moderate'
        
        # 大户偏空
        elif top_long_ratio < (1 - bias_threshold):
            if top_long_ratio < (1 - extreme_threshold):
                tags.append(ReasonTag.TOP_TRADER_EXTREME_SHORT)
                details['top_trader_status'] = 'extreme_short'
                if decision == Decision.LONG:
                    confidence_boost = extreme_reverse_boost  # 逆向信号加分
                else:
                    confidence_boost = extreme_follow_penalty  # 警告
            else:
                tags.append(ReasonTag.TOP_TRADER_SHORT_BIAS)
                details['top_trader_status'] = 'short_bias'
                if decision == Decision.SHORT:
                    confidence_boost = bias_confirm_boost  # 偏向确认
                    signal_quality = 'moderate'
        
        # 聪明钱背离：大户与散户方向相反
        if retail_long_ratio is not None:
            retail_short_ratio = 1 - retail_long_ratio
            
            # 大户做多 + 散户做空
            if top_long_ratio > bias_threshold and retail_short_ratio > bias_threshold:
                tags.append(ReasonTag.SMART_MONEY_DIVERGENCE)
                details['smart_money_divergence'] = 'top_long_retail_short'
                if decision == Decision.LONG:
                    confidence_boost += smart_money_boost  # 聪明钱背离（12→16）
                    signal_quality = 'strong'
                    logger.info(f"Smart money divergence (LONG): top={top_long_ratio:.2%}, retail_short={retail_short_ratio:.2%}")
            
            # 大户做空 + 散户做多
            elif top_long_ratio < (1 - bias_threshold) and retail_long_ratio > bias_threshold:
                tags.append(ReasonTag.SMART_MONEY_DIVERGENCE)
                details['smart_money_divergence'] = 'top_short_retail_long'
                if decision == Decision.SHORT:
                    confidence_boost += smart_money_boost  # 聪明钱背离（12→16）
                    signal_quality = 'strong'
                    logger.info(f"Smart money divergence (SHORT): top_short={1-top_long_ratio:.2%}, retail_long={retail_long_ratio:.2%}")
            
            # P0-3新增：大户-散户偏差分析
            divergence = abs(top_long_ratio - retail_long_ratio)
            if divergence > retail_divergence_threshold:
                details['retail_divergence'] = divergence
                # 高偏差时，如果方向与大户一致，额外加分
                is_aligned_with_top = (
                    (decision == Decision.LONG and top_long_ratio > bias_threshold) or
                    (decision == Decision.SHORT and top_long_ratio < (1 - bias_threshold))
                )
                if is_aligned_with_top:
                    confidence_boost += retail_divergence_bonus
                    logger.debug(f"Retail divergence bonus: divergence={divergence:.2%}, bonus=+{retail_divergence_bonus}")
        
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    # ========================================
    # P0-1: 24h长期趋势评估
    # ========================================
    
    def eval_long_term_trend(
        self,
        price_change_24h: Optional[float],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估24h长期趋势信号（P0-1优化）
        
        逻辑：
        - 24h强势上涨（>5%）+ LONG → 顺势加分
        - 24h强势下跌（<-5%）+ SHORT → 顺势加分
        - 逆势开仓 → 扣分
        - 震荡（<2%）→ 标记但不加减分
        
        Args:
            price_change_24h: 24小时价格变化（小数格式）
            decision: 当前决策方向
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {'price_change_24h': price_change_24h}
        
        if price_change_24h is None or decision == Decision.NO_TRADE:
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        strong_threshold = self.thresholds.get('long_term_strong_threshold', 0.05)
        range_threshold = self.thresholds.get('long_term_range_threshold', 0.02)
        trend_boost = self.thresholds.get('long_term_trend_boost', 8)
        counter_penalty = self.thresholds.get('long_term_counter_penalty', -5)
        
        abs_change = abs(price_change_24h)
        
        # 强势上涨
        if price_change_24h > strong_threshold:
            tags.append(ReasonTag.LONG_TERM_UPTREND)
            details['long_term_status'] = 'uptrend'
            
            if decision == Decision.LONG:
                # 顺势做多
                confidence_boost = trend_boost
                signal_quality = 'strong'
                logger.info(f"Long-term uptrend confirmed (LONG): 24h={price_change_24h:.2%}, boost=+{trend_boost}")
            else:
                # 逆势做空
                confidence_boost = counter_penalty
                signal_quality = 'weak'
                details['warning'] = 'counter_trend_short'
        
        # 强势下跌
        elif price_change_24h < -strong_threshold:
            tags.append(ReasonTag.LONG_TERM_DOWNTREND)
            details['long_term_status'] = 'downtrend'
            
            if decision == Decision.SHORT:
                # 顺势做空
                confidence_boost = trend_boost
                signal_quality = 'strong'
                logger.info(f"Long-term downtrend confirmed (SHORT): 24h={price_change_24h:.2%}, boost=+{trend_boost}")
            else:
                # 逆势做多
                confidence_boost = counter_penalty
                signal_quality = 'weak'
                details['warning'] = 'counter_trend_long'
        
        # 震荡
        elif abs_change < range_threshold:
            tags.append(ReasonTag.LONG_TERM_RANGE)
            details['long_term_status'] = 'range'
            # 震荡不加减分
        
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    # ========================================
    # P0-4: 1h放量确认
    # ========================================
    
    def eval_volume_confirmation(
        self,
        volume_ratio_1h: Optional[float],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估1h放量确认信号（P0-4优化）
        
        逻辑：
        - 大幅放量（>2x）+ 有方向 → 资金强势进场，加分
        - 中度放量（>1.5x）+ 有方向 → 资金增加，适度加分
        - 缩量（<0.5x）→ 交投清淡，扣分
        
        Args:
            volume_ratio_1h: 1小时成交量比率（相对于历史均值）
            decision: 当前决策方向
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {'volume_ratio_1h': volume_ratio_1h}
        
        if volume_ratio_1h is None or decision == Decision.NO_TRADE:
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        surge_threshold = self.thresholds.get('volume_surge_threshold', 2.0)
        moderate_threshold = self.thresholds.get('volume_moderate_threshold', 1.5)
        low_threshold = self.thresholds.get('volume_low_threshold', 0.5)
        surge_boost = self.thresholds.get('volume_surge_boost', 8)
        moderate_boost = self.thresholds.get('volume_moderate_boost', 5)
        low_penalty = self.thresholds.get('volume_low_penalty', -3)
        
        # 大幅放量
        if volume_ratio_1h > surge_threshold:
            tags.append(ReasonTag.VOLUME_SURGE_1H)
            details['volume_status'] = 'surge'
            confidence_boost = surge_boost
            signal_quality = 'strong'
            logger.info(f"Volume surge confirmed: ratio={volume_ratio_1h:.2f}x, boost=+{surge_boost}")
        
        # 中度放量
        elif volume_ratio_1h > moderate_threshold:
            tags.append(ReasonTag.VOLUME_MODERATE_1H)
            details['volume_status'] = 'moderate'
            confidence_boost = moderate_boost
            signal_quality = 'moderate'
        
        # 缩量
        elif volume_ratio_1h < low_threshold:
            tags.append(ReasonTag.VOLUME_LOW_1H)
            details['volume_status'] = 'low'
            confidence_boost = low_penalty
            signal_quality = 'weak'
            details['warning'] = 'low_volume'
        
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    # ========================================
    # 综合评估入口
    # ========================================
    
    def evaluate_all(
        self,
        funding_rate: Optional[float],
        price_change_1h: Optional[float],
        oi_change_1h: Optional[float],
        imbalance_5m: Optional[float],
        imbalance_15m: Optional[float],
        imbalance_1h: Optional[float],
        decision: Decision,
        top_long_ratio: Optional[float] = None,
        retail_long_ratio: Optional[float] = None,
        price_change_24h: Optional[float] = None,
        volume_ratio_1h: Optional[float] = None
    ) -> EnhancementResult:
        """
        综合评估所有增强信号（第一批优化：增加24h趋势和1h放量）
        
        Args:
            funding_rate: 资金费率
            price_change_1h: 1小时价格变化
            oi_change_1h: 1小时OI变化
            imbalance_5m/15m/1h: 各周期失衡度
            decision: 当前决策方向
            top_long_ratio: 大户做多比例（可选）
            retail_long_ratio: 散户做多比例（可选）
            price_change_24h: 24小时价格变化（P0-1新增）
            volume_ratio_1h: 1小时成交量比率（P0-4新增）
        
        Returns:
            EnhancementResult: 综合结果
        """
        all_tags = []
        total_boost = 0
        all_details = {}
        
        # Phase 1.1: 资金费率极端反转
        funding_result = self.eval_funding_extreme(funding_rate, decision)
        all_tags.extend(funding_result.tags)
        total_boost += funding_result.confidence_boost
        all_details['funding'] = funding_result.details
        
        # Phase 1.2: OI与价格背离
        divergence_result = self.eval_oi_price_divergence(price_change_1h, oi_change_1h, decision)
        all_tags.extend(divergence_result.tags)
        total_boost += divergence_result.confidence_boost
        all_details['divergence'] = divergence_result.details
        
        # Phase 1.3: 多周期一致性
        alignment_result = self.eval_timeframe_alignment(
            imbalance_5m, imbalance_15m, imbalance_1h, decision
        )
        all_tags.extend(alignment_result.tags)
        total_boost += alignment_result.confidence_boost
        all_details['alignment'] = alignment_result.details
        
        # Phase 2: 大户多空比（P0-3优化：增强权重）
        if top_long_ratio is not None:
            top_trader_result = self.eval_top_trader_ratio(
                top_long_ratio, retail_long_ratio, decision
            )
            all_tags.extend(top_trader_result.tags)
            total_boost += top_trader_result.confidence_boost
            all_details['top_trader'] = top_trader_result.details
        
        # P0-1: 24h长期趋势
        if price_change_24h is not None:
            long_term_result = self.eval_long_term_trend(price_change_24h, decision)
            all_tags.extend(long_term_result.tags)
            total_boost += long_term_result.confidence_boost
            all_details['long_term_trend'] = long_term_result.details
        
        # P0-4: 1h放量确认
        if volume_ratio_1h is not None:
            volume_result = self.eval_volume_confirmation(volume_ratio_1h, decision)
            all_tags.extend(volume_result.tags)
            total_boost += volume_result.confidence_boost
            all_details['volume_1h'] = volume_result.details
        
        # 综合信号质量
        if total_boost >= 20:
            signal_quality = 'strong'
        elif total_boost >= 10:
            signal_quality = 'moderate'
        elif total_boost <= -10:
            signal_quality = 'weak'
        else:
            signal_quality = 'neutral'
        
        all_details['total_boost'] = total_boost
        all_details['signal_quality'] = signal_quality
        
        return EnhancementResult(all_tags, total_boost, signal_quality, all_details)


# 全局实例（可选）
_enhancer_instance = None

def get_signal_enhancer(thresholds: Dict = None) -> SignalEnhancer:
    """获取全局SignalEnhancer实例"""
    global _enhancer_instance
    if _enhancer_instance is None:
        _enhancer_instance = SignalEnhancer(thresholds)
    return _enhancer_instance
