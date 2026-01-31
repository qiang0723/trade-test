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
        
        # P1-3: 资金费率趋势分析
        'funding_trend_normal': 0.0003,        # 正常费率区间 0.03%
        'funding_trend_elevated': 0.0008,      # 升高费率区间 0.08%
        'funding_acceleration_boost': 6,       # 费率加速加分
        'funding_reversal_boost': 10,          # 费率反转信号加分
        
        # Coinglass数据融合
        'cg_long_liquidation_threshold': 0.7,  # 多头清算占比阈值 70%
        'cg_short_liquidation_threshold': 0.3, # 空头清算占比阈值 30%
        'cg_liquidation_boost': 8,             # 清算信号加分
        'cg_fear_greed_extreme_fear': 25,      # 极度恐惧阈值
        'cg_fear_greed_extreme_greed': 75,     # 极度贪婪阈值
        'cg_fear_greed_boost': 6,              # 恐惧贪婪加分
        'cg_long_ratio_crowded': 0.70,         # 多头拥挤阈值
        'cg_short_ratio_crowded': 0.30,        # 空头拥挤阈值
        'cg_crowded_penalty': -5,              # 拥挤惩罚
        'cg_contrarian_boost': 8,              # 逆向加分
        'cg_oi_surge_threshold': 0.03,         # OI激增阈值 3%
        'cg_oi_drop_threshold': -0.02,         # OI下降阈值 -2%
        'cg_oi_boost': 5,                      # OI信号加分
        
        # P0-1: 趋势数据利用
        'ls_trend_accelerating_threshold': 2.0,  # 多空比变化加速阈值 2%
        'ls_trend_accelerating_boost': 5,        # 趋势加速加分
        'ls_trend_reversal_penalty': -6,         # 趋势反转惩罚
        'oi_trend_confirm_boost': 4,             # OI趋势确认加分
        'oi_4h_surge_threshold': 0.05,           # 4h OI激增阈值
        'oi_4h_drop_threshold': -0.03,           # 4h OI下降阈值
        'oi_4h_boost': 4,                        # 4h OI加分
        'funding_trend_reversal_boost': 8,       # 费率趋势反转加分
        'funding_extreme_vs_max_threshold': 0.9, # 接近历史极值阈值
        'funding_near_extreme_penalty': -6,      # 接近极值惩罚
        
        # P0-2: SHORT信号质量加强
        'short_multi_confirm_bonus': 8,          # SHORT多条件确认加分
        'short_weak_confirm_penalty': -5,        # SHORT弱确认惩罚
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
    # P1-3: 资金费率趋势分析
    # ========================================
    
    def eval_funding_trend(
        self,
        funding_rate: Optional[float],
        oi_change_1h: Optional[float],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估资金费率趋势信号（P1-3优化）
        
        逻辑：
        - 费率远离中性（加速）→ 标记趋势强化
        - 费率极端 + OI增长 → 拥挤加剧
        - 费率极端 + OI下降 → 可能反转
        
        Args:
            funding_rate: 当前资金费率（小数格式）
            oi_change_1h: 1小时OI变化
            decision: 当前决策方向
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {'funding_rate': funding_rate, 'oi_change_1h': oi_change_1h}
        
        if funding_rate is None or decision == Decision.NO_TRADE:
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        normal_threshold = self.thresholds.get('funding_trend_normal', 0.0003)
        elevated_threshold = self.thresholds.get('funding_trend_elevated', 0.0008)
        acceleration_boost = self.thresholds.get('funding_acceleration_boost', 6)
        reversal_boost = self.thresholds.get('funding_reversal_boost', 10)
        
        abs_funding = abs(funding_rate)
        
        # 费率加速：远离中性区间
        if abs_funding > elevated_threshold:
            details['funding_status'] = 'elevated'
            
            # 结合OI变化判断趋势
            if oi_change_1h is not None:
                if oi_change_1h < -0.02:  # OI下降>2%，可能反转
                    tags.append(ReasonTag.FUNDING_TREND_REVERSAL)
                    details['trend_type'] = 'potential_reversal'
                    
                    # 逆势开仓时加分
                    is_counter_trend = (
                        (funding_rate > 0 and decision == Decision.SHORT) or
                        (funding_rate < 0 and decision == Decision.LONG)
                    )
                    if is_counter_trend:
                        confidence_boost = reversal_boost
                        signal_quality = 'strong'
                        logger.info(f"Funding reversal signal: rate={funding_rate:.4f}, oi_change={oi_change_1h:.2%}")
                else:
                    # OI增长或稳定，趋势加速
                    tags.append(ReasonTag.FUNDING_TREND_ACCELERATING)
                    details['trend_type'] = 'accelerating'
                    
                    # 顺势开仓时适度加分（但需警惕拥挤）
                    is_with_trend = (
                        (funding_rate > 0 and decision == Decision.LONG) or
                        (funding_rate < 0 and decision == Decision.SHORT)
                    )
                    if is_with_trend:
                        # 顺势但费率极端，小扣分（拥挤风险）
                        confidence_boost = -3
                        signal_quality = 'weak'
                    else:
                        # 逆势+费率加速，潜力信号
                        confidence_boost = acceleration_boost
                        signal_quality = 'moderate'
        
        # 费率从正常升高到警戒区
        elif abs_funding > normal_threshold:
            details['funding_status'] = 'rising'
            # 仅标记，不加减分
        
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    # ========================================
    # Coinglass数据融合评估
    # ========================================
    
    def eval_coinglass_liquidation(
        self,
        liquidation_summary: Optional[Dict],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估Coinglass清算数据
        
        逻辑：
        - 多头清算占比>70% + 做多 → 加分（可能触底反弹）
        - 空头清算占比>70% + 做空 → 加分（可能见顶回落）
        - 顺势拥挤 → 惩罚
        
        Args:
            liquidation_summary: 清算汇总数据
            decision: 当前决策
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {'source': 'coinglass_liquidation'}
        
        if not liquidation_summary:
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        long_ratio = liquidation_summary.get('long_ratio', 0.5)
        liq_intensity = liquidation_summary.get('liquidation_intensity', 'low')
        
        long_threshold = self.thresholds.get('cg_long_liquidation_threshold', 0.7)
        short_threshold = self.thresholds.get('cg_short_liquidation_threshold', 0.3)
        boost = self.thresholds.get('cg_liquidation_boost', 8)
        
        details['long_ratio'] = long_ratio
        details['intensity'] = liq_intensity
        
        # 高强度清算时信号更强
        intensity_multiplier = 1.5 if liq_intensity == 'high' else 1.0
        
        if long_ratio > long_threshold:
            # 多头被大量清算
            tags.append(ReasonTag.LIQUIDATION_IMBALANCE_LONG)
            details['signal'] = 'long_liquidation_dominant'
            
            if decision == Decision.LONG:
                # 做多 + 多头清算 → 可能反弹
                confidence_boost = int(boost * intensity_multiplier)
                signal_quality = 'strong'
                details['interpretation'] = 'potential_bounce'
            elif decision == Decision.SHORT:
                # 做空 + 多头清算 → 顺势但要警惕反弹
                confidence_boost = -3
                signal_quality = 'weak'
                details['interpretation'] = 'trend_but_bounce_risk'
        
        elif long_ratio < short_threshold:
            # 空头被大量清算
            tags.append(ReasonTag.LIQUIDATION_IMBALANCE_SHORT)
            details['signal'] = 'short_liquidation_dominant'
            
            if decision == Decision.SHORT:
                # 做空 + 空头清算 → 可能回调
                confidence_boost = int(boost * intensity_multiplier)
                signal_quality = 'strong'
                details['interpretation'] = 'potential_pullback'
            elif decision == Decision.LONG:
                # 做多 + 空头清算 → 顺势但要警惕回调
                confidence_boost = -3
                signal_quality = 'weak'
                details['interpretation'] = 'trend_but_pullback_risk'
        
        details['confidence_boost'] = confidence_boost
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    def eval_coinglass_sentiment(
        self,
        fear_greed: Optional[Dict],
        long_short_ratio: Optional[Dict],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估Coinglass市场情绪（恐惧贪婪指数 + 多空比）
        
        逻辑：
        - 极度恐惧 + 做多 → 逆向加分
        - 极度贪婪 + 做空 → 逆向加分
        - 多头拥挤 + 做多 → 惩罚
        - 空头拥挤 + 做空 → 惩罚
        
        Args:
            fear_greed: 恐惧贪婪指数数据
            long_short_ratio: 多空比数据
            decision: 当前决策
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {'source': 'coinglass_sentiment'}
        
        extreme_fear = self.thresholds.get('cg_fear_greed_extreme_fear', 25)
        extreme_greed = self.thresholds.get('cg_fear_greed_extreme_greed', 75)
        fg_boost = self.thresholds.get('cg_fear_greed_boost', 6)
        
        long_crowded = self.thresholds.get('cg_long_ratio_crowded', 0.70)
        short_crowded = self.thresholds.get('cg_short_ratio_crowded', 0.30)
        crowded_penalty = self.thresholds.get('cg_crowded_penalty', -5)
        contrarian_boost = self.thresholds.get('cg_contrarian_boost', 8)
        
        # 1. 恐惧贪婪指数分析
        if fear_greed:
            fg_value = fear_greed.get('current', 50)
            fg_sentiment = fear_greed.get('sentiment', 'neutral')
            details['fear_greed'] = {'value': fg_value, 'sentiment': fg_sentiment}
            
            if fg_value <= extreme_fear:
                # 极度恐惧
                if decision == Decision.LONG:
                    confidence_boost += fg_boost
                    details['fg_signal'] = 'extreme_fear_long_opportunity'
                    signal_quality = 'moderate'
            elif fg_value >= extreme_greed:
                # 极度贪婪
                if decision == Decision.SHORT:
                    confidence_boost += fg_boost
                    details['fg_signal'] = 'extreme_greed_short_opportunity'
                    signal_quality = 'moderate'
        
        # 2. 多空比分析
        if long_short_ratio:
            long_pct = long_short_ratio.get('long_percent', 50) / 100
            ls_sentiment = long_short_ratio.get('sentiment', 'neutral')
            ls_trend = long_short_ratio.get('trend')  # P0-1: 获取趋势数据
            details['long_short'] = {'long_pct': long_pct, 'sentiment': ls_sentiment, 'trend': ls_trend}
            
            if long_pct > long_crowded:
                # 多头拥挤
                if decision == Decision.LONG:
                    # 顺势拥挤 → 惩罚
                    confidence_boost += crowded_penalty
                    details['ls_signal'] = 'long_crowded_penalty'
                    signal_quality = 'weak'
                elif decision == Decision.SHORT:
                    # 逆势 → 加分
                    confidence_boost += contrarian_boost
                    tags.append(ReasonTag.LIQUIDATION_CASCADE_RISK)
                    details['ls_signal'] = 'contrarian_short_opportunity'
                    signal_quality = 'strong'
            
            elif long_pct < short_crowded:
                # 空头拥挤（或多头稀少）
                if decision == Decision.SHORT:
                    # 顺势拥挤 → 惩罚
                    confidence_boost += crowded_penalty
                    details['ls_signal'] = 'short_crowded_penalty'
                    signal_quality = 'weak'
                elif decision == Decision.LONG:
                    # 逆势 → 加分
                    confidence_boost += contrarian_boost
                    tags.append(ReasonTag.LIQUIDATION_CASCADE_RISK)
                    details['ls_signal'] = 'contrarian_long_opportunity'
                    signal_quality = 'strong'
            
            # P0-1: 多空比趋势分析（新增）
            if ls_trend is not None:
                ls_trend_threshold = self.thresholds.get('ls_trend_accelerating_threshold', 2.0)
                ls_trend_boost = self.thresholds.get('ls_trend_accelerating_boost', 5)
                ls_trend_penalty = self.thresholds.get('ls_trend_reversal_penalty', -6)
                
                # 多头快速增加（趋势加速）
                if ls_trend > ls_trend_threshold:
                    details['ls_trend_status'] = 'long_accelerating'
                    if decision == Decision.LONG:
                        # 趋势加速时做多 → 惩罚（拥挤加剧）
                        confidence_boost += ls_trend_penalty
                        details['ls_trend_signal'] = 'crowding_accelerating_penalty'
                        logger.debug(f"LS trend accelerating (LONG): trend={ls_trend:.2f}%, penalty={ls_trend_penalty}")
                    elif decision == Decision.SHORT:
                        # 趋势加速时做空 → 逆向机会加分
                        confidence_boost += ls_trend_boost
                        details['ls_trend_signal'] = 'contrarian_opportunity_boost'
                
                # 多头快速减少（空头趋势）
                elif ls_trend < -ls_trend_threshold:
                    details['ls_trend_status'] = 'short_accelerating'
                    if decision == Decision.SHORT:
                        # 空头趋势加速时做空 → 惩罚（拥挤加剧）
                        confidence_boost += ls_trend_penalty
                        details['ls_trend_signal'] = 'crowding_accelerating_penalty'
                    elif decision == Decision.LONG:
                        # 空头趋势加速时做多 → 逆向机会加分
                        confidence_boost += ls_trend_boost
                        details['ls_trend_signal'] = 'contrarian_opportunity_boost'
        
        details['confidence_boost'] = confidence_boost
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    def eval_coinglass_oi(
        self,
        oi_history: Optional[Dict],
        funding_history: Optional[Dict],
        decision: Decision
    ) -> EnhancementResult:
        """
        评估Coinglass OI和费率历史数据（P0-1增强：趋势确认）
        
        逻辑：
        - OI激增 + 趋势方向 → 加分
        - OI下降 → 趋势可能终结
        - OI趋势确认 → 额外加分（P0-1新增）
        - 4h OI变化分析（P0-1新增）
        - 费率趋势分析（P0-1新增）
        - 费率极高 + 顺势 → 惩罚（拥挤风险）
        - 费率接近历史极值 → 反转警告（P0-1新增）
        
        Args:
            oi_history: OI历史数据
            funding_history: 费率历史数据
            decision: 当前决策
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {'source': 'coinglass_oi'}
        
        oi_surge = self.thresholds.get('cg_oi_surge_threshold', 0.03)
        oi_drop = self.thresholds.get('cg_oi_drop_threshold', -0.02)
        oi_boost = self.thresholds.get('cg_oi_boost', 5)
        
        # P0-1: 新增阈值
        oi_trend_boost = self.thresholds.get('oi_trend_confirm_boost', 4)
        oi_4h_surge = self.thresholds.get('oi_4h_surge_threshold', 0.05)
        oi_4h_drop = self.thresholds.get('oi_4h_drop_threshold', -0.03)
        oi_4h_boost = self.thresholds.get('oi_4h_boost', 4)
        
        # 1. OI变化分析（增强版）
        if oi_history:
            oi_change = oi_history.get('oi_change_1h')
            oi_change_4h = oi_history.get('oi_change_4h')  # P0-1: 获取4h变化
            oi_trend = oi_history.get('trend', 'stable')
            details['oi'] = {'change_1h': oi_change, 'change_4h': oi_change_4h, 'trend': oi_trend}
            
            if oi_change is not None:
                if oi_change > oi_surge:
                    # OI激增
                    tags.append(ReasonTag.AGGREGATED_OI_SURGE)
                    if decision in [Decision.LONG, Decision.SHORT]:
                        confidence_boost += oi_boost
                        details['oi_signal'] = 'oi_surge_trend_confirm'
                        signal_quality = 'moderate'
                
                elif oi_change < oi_drop:
                    # OI下降
                    tags.append(ReasonTag.AGGREGATED_OI_DROP)
                    confidence_boost -= 3
                    details['oi_signal'] = 'oi_drop_trend_exhaustion'
                    signal_quality = 'weak'
            
            # P0-1: OI趋势确认
            if oi_trend == 'increasing' and oi_change and oi_change > 0.02:
                # 趋势加速 + OI激增 → 强信号
                confidence_boost += oi_trend_boost
                details['oi_trend_signal'] = 'trend_accelerating_confirm'
                logger.debug(f"OI trend confirming: trend={oi_trend}, change_1h={oi_change:.2%}")
            elif oi_trend == 'decreasing' and oi_change and oi_change < -0.015:
                # 趋势减速 + OI下降 → 趋势终结警告
                confidence_boost -= 4
                details['oi_trend_signal'] = 'trend_exhaustion_warning'
            
            # P0-1: 4h OI变化分析（中期趋势确认）
            if oi_change_4h is not None:
                if oi_change_4h > oi_4h_surge:
                    # 4h OI激增 → 中期趋势强
                    confidence_boost += oi_4h_boost
                    details['oi_4h_signal'] = 'medium_term_surge'
                    logger.debug(f"4h OI surge: {oi_change_4h:.2%}")
                elif oi_change_4h < oi_4h_drop:
                    # 4h OI下降 → 中期趋势弱
                    confidence_boost -= 3
                    details['oi_4h_signal'] = 'medium_term_drop'
        
        # 2. 费率历史分析（增强版：趋势和极值）
        if funding_history:
            current_rate = funding_history.get('current_rate', 0)
            fr_sentiment = funding_history.get('sentiment', 'neutral')
            fr_trend = funding_history.get('trend')  # P0-1: 获取费率趋势
            max_rate = funding_history.get('max_rate')
            min_rate = funding_history.get('min_rate')
            details['funding'] = {
                'rate': current_rate, 
                'sentiment': fr_sentiment, 
                'trend': fr_trend,
                'max_rate': max_rate,
                'min_rate': min_rate
            }
            
            # 费率极端时的拥挤警告
            if fr_sentiment == 'extremely_bullish' and decision == Decision.LONG:
                confidence_boost -= 5
                details['funding_signal'] = 'extreme_bullish_crowded'
            elif fr_sentiment == 'extremely_bearish' and decision == Decision.SHORT:
                confidence_boost -= 5
                details['funding_signal'] = 'extreme_bearish_crowded'
            
            # P0-1: 费率趋势分析
            fr_trend_boost = self.thresholds.get('funding_trend_reversal_boost', 8)
            if fr_trend:
                details['funding_trend_status'] = fr_trend
                
                # 费率加速 + 极端情绪 → 反转风险
                if fr_trend == 'increasing' and fr_sentiment in ['extremely_bullish', 'bullish']:
                    if decision == Decision.LONG:
                        # 做多时费率加速上升 → 拥挤加剧
                        confidence_boost -= 4
                        details['funding_trend_signal'] = 'crowding_accelerating'
                    elif decision == Decision.SHORT:
                        # 做空时费率加速上升 → 反转机会
                        confidence_boost += fr_trend_boost
                        details['funding_trend_signal'] = 'reversal_opportunity'
                        logger.info(f"Funding trend reversal signal (SHORT): rate={current_rate:.4f}, trend={fr_trend}")
                
                elif fr_trend == 'decreasing' and fr_sentiment in ['extremely_bearish', 'bearish']:
                    if decision == Decision.SHORT:
                        # 做空时费率加速下降 → 拥挤加剧
                        confidence_boost -= 4
                        details['funding_trend_signal'] = 'crowding_accelerating'
                    elif decision == Decision.LONG:
                        # 做多时费率加速下降 → 反转机会
                        confidence_boost += fr_trend_boost
                        details['funding_trend_signal'] = 'reversal_opportunity'
                        logger.info(f"Funding trend reversal signal (LONG): rate={current_rate:.4f}, trend={fr_trend}")
            
            # P0-1: 费率接近历史极值分析
            extreme_threshold = self.thresholds.get('funding_extreme_vs_max_threshold', 0.9)
            extreme_penalty = self.thresholds.get('funding_near_extreme_penalty', -6)
            
            if max_rate and current_rate > 0 and current_rate >= max_rate * extreme_threshold:
                # 接近历史最高费率 → 反转风险
                details['funding_extreme_signal'] = 'near_historical_max'
                if decision == Decision.LONG:
                    confidence_boost += extreme_penalty
                    logger.debug(f"Funding near max: current={current_rate:.4f}, max={max_rate:.4f}")
            
            elif min_rate and current_rate < 0 and current_rate <= min_rate * extreme_threshold:
                # 接近历史最低费率 → 反转风险
                details['funding_extreme_signal'] = 'near_historical_min'
                if decision == Decision.SHORT:
                    confidence_boost += extreme_penalty
                    logger.debug(f"Funding near min: current={current_rate:.4f}, min={min_rate:.4f}")
        
        details['confidence_boost'] = confidence_boost
        return EnhancementResult(tags, confidence_boost, signal_quality, details)
    
    # ========================================
    # 市场整体情绪评估（主流币种汇总）
    # ========================================
    
    def eval_market_sentiment(
        self,
        market_sentiment: Dict,
        decision: Decision
    ) -> EnhancementResult:
        """
        评估市场整体情绪（基于主流币种数据汇总）
        
        逻辑：
        - 主流币种多空比一致性 → 强化/惩罚信号
        - 资金费率整体方向 → 趋势确认
        - BTC/ETH清算主导 → 市场情绪指引
        
        Args:
            market_sentiment: 市场情绪汇总数据
            decision: 当前决策
        
        Returns:
            EnhancementResult
        """
        tags = []
        confidence_boost = 0
        signal_quality = 'neutral'
        details = {'source': 'market_sentiment'}
        
        if not market_sentiment:
            return EnhancementResult(tags, confidence_boost, signal_quality, details)
        
        # 1. 主流币种多空比一致性
        major_ls_bias = market_sentiment.get('major_ls_bias')
        major_ls_avg = market_sentiment.get('major_ls_avg')
        
        if major_ls_bias:
            details['major_ls_bias'] = major_ls_bias
            details['major_ls_avg'] = major_ls_avg
            
            if major_ls_bias == 'LONG_CROWDED':
                if decision == Decision.SHORT:
                    # 做空时市场拥挤多头 → 逆向加分
                    confidence_boost += 5
                    tags.append(ReasonTag.CROWDED_LONG_CONTRARIAN)
                    details['ls_signal'] = 'market_long_crowded_short_favorable'
                    signal_quality = 'moderate'
                elif decision == Decision.LONG:
                    # 做多时市场已拥挤多头 → 惩罚
                    confidence_boost -= 3
                    details['ls_signal'] = 'market_long_crowded_long_risky'
                    signal_quality = 'weak'
            
            elif major_ls_bias == 'SHORT_CROWDED':
                if decision == Decision.LONG:
                    # 做多时市场拥挤空头 → 逆向加分
                    confidence_boost += 5
                    tags.append(ReasonTag.CROWDED_SHORT_CONTRARIAN)
                    details['ls_signal'] = 'market_short_crowded_long_favorable'
                    signal_quality = 'moderate'
                elif decision == Decision.SHORT:
                    # 做空时市场已拥挤空头 → 惩罚
                    confidence_boost -= 3
                    details['ls_signal'] = 'market_short_crowded_short_risky'
                    signal_quality = 'weak'
        
        # 2. 资金费率整体趋势
        funding_sentiment = market_sentiment.get('funding_sentiment')
        if funding_sentiment:
            details['funding_sentiment'] = funding_sentiment
            
            if funding_sentiment in ['VERY_BULLISH', 'BULLISH'] and decision == Decision.LONG:
                # 顺势但可能拥挤
                if funding_sentiment == 'VERY_BULLISH':
                    confidence_boost -= 2  # 极端时轻微惩罚
                    details['fr_signal'] = 'market_very_bullish_crowded_risk'
            
            elif funding_sentiment in ['VERY_BEARISH', 'BEARISH'] and decision == Decision.SHORT:
                if funding_sentiment == 'VERY_BEARISH':
                    confidence_boost -= 2
                    details['fr_signal'] = 'market_very_bearish_crowded_risk'
        
        # 3. BTC清算主导方向参考
        btc_liq = market_sentiment.get('btc_liquidation_dominance')
        if btc_liq:
            details['btc_liquidation'] = btc_liq
            
            if btc_liq == 'LONG' and decision == Decision.LONG:
                # BTC多头被清算，市场可能反弹 → 加分
                confidence_boost += 3
                details['btc_signal'] = 'btc_long_liquidated_bounce_likely'
            elif btc_liq == 'SHORT' and decision == Decision.SHORT:
                # BTC空头被清算，市场可能回调 → 加分
                confidence_boost += 3
                details['btc_signal'] = 'btc_short_liquidated_pullback_likely'
        
        # 统计分析的币种数量
        symbols_analyzed = market_sentiment.get('symbols_analyzed', [])
        details['symbols_analyzed'] = symbols_analyzed
        details['confidence_boost'] = confidence_boost
        
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
        volume_ratio_1h: Optional[float] = None,
        # Coinglass数据（新增）
        cg_liquidation_summary: Optional[Dict] = None,
        cg_fear_greed: Optional[Dict] = None,
        cg_long_short_ratio: Optional[Dict] = None,
        cg_oi_history: Optional[Dict] = None,
        cg_funding_history: Optional[Dict] = None,
        # 市场整体情绪（新增：充分利用API配额）
        market_sentiment: Optional[Dict] = None
    ) -> EnhancementResult:
        """
        综合评估所有增强信号（含Coinglass数据融合 + 市场整体情绪）
        
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
            cg_liquidation_summary: Coinglass清算汇总（新增）
            cg_fear_greed: Coinglass恐惧贪婪指数（新增）
            cg_long_short_ratio: Coinglass多空比（新增）
            cg_oi_history: Coinglass OI历史（新增）
            cg_funding_history: Coinglass费率历史（新增）
            market_sentiment: 市场整体情绪（主流币种汇总，新增）
        
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
        
        # P1-3: 资金费率趋势分析
        funding_trend_result = self.eval_funding_trend(funding_rate, oi_change_1h, decision)
        all_tags.extend(funding_trend_result.tags)
        total_boost += funding_trend_result.confidence_boost
        all_details['funding_trend'] = funding_trend_result.details
        
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
        
        # ========================================
        # Coinglass数据融合（STARTUP套餐）
        # ========================================
        
        # CG-1: 清算数据分析
        if cg_liquidation_summary is not None:
            cg_liq_result = self.eval_coinglass_liquidation(cg_liquidation_summary, decision)
            all_tags.extend(cg_liq_result.tags)
            total_boost += cg_liq_result.confidence_boost
            all_details['cg_liquidation'] = cg_liq_result.details
        
        # CG-2: 市场情绪分析（恐惧贪婪 + 多空比）
        if cg_fear_greed is not None or cg_long_short_ratio is not None:
            cg_sentiment_result = self.eval_coinglass_sentiment(
                cg_fear_greed, cg_long_short_ratio, decision
            )
            all_tags.extend(cg_sentiment_result.tags)
            total_boost += cg_sentiment_result.confidence_boost
            all_details['cg_sentiment'] = cg_sentiment_result.details
        
        # CG-3: OI和费率历史分析
        if cg_oi_history is not None or cg_funding_history is not None:
            cg_oi_result = self.eval_coinglass_oi(cg_oi_history, cg_funding_history, decision)
            all_tags.extend(cg_oi_result.tags)
            total_boost += cg_oi_result.confidence_boost
            all_details['cg_oi'] = cg_oi_result.details
        
        # 综合信号质量
        if total_boost >= 20:
            signal_quality = 'strong'
        elif total_boost >= 10:
            signal_quality = 'moderate'
        elif total_boost <= -10:
            signal_quality = 'weak'
        else:
            signal_quality = 'neutral'
        
        # ========================================
        # 市场整体情绪分析（主流币种汇总）
        # ========================================
        if market_sentiment:
            market_result = self.eval_market_sentiment(market_sentiment, decision)
            all_tags.extend(market_result.tags)
            total_boost += market_result.confidence_boost
            all_details['market_sentiment'] = market_result.details
        
        # 重新计算信号质量
        if total_boost >= 15:
            signal_quality = 'strong'
        elif total_boost >= 5:
            signal_quality = 'moderate'
        elif total_boost <= -10:
            signal_quality = 'weak'
        else:
            signal_quality = 'neutral'
        
        all_details['total_boost'] = total_boost
        all_details['signal_quality'] = signal_quality
        
        # 记录Coinglass贡献（含市场情绪）
        cg_boost = sum([
            all_details.get('cg_liquidation', {}).get('confidence_boost', 0) if isinstance(all_details.get('cg_liquidation'), dict) else 0,
            all_details.get('cg_sentiment', {}).get('confidence_boost', 0) if isinstance(all_details.get('cg_sentiment'), dict) else 0,
            all_details.get('cg_oi', {}).get('confidence_boost', 0) if isinstance(all_details.get('cg_oi'), dict) else 0,
            all_details.get('market_sentiment', {}).get('confidence_boost', 0) if isinstance(all_details.get('market_sentiment'), dict) else 0,
        ])
        all_details['coinglass_contribution'] = cg_boost
        
        # ========================================
        # P0-2: SHORT信号质量加强（多条件确认）
        # ========================================
        if decision == Decision.SHORT:
            short_confirms = []
            short_warnings = []
            
            # 检查各维度确认条件
            # 1. 费率确认：正费率（多头付费）支持做空
            if funding_rate is not None and funding_rate > 0.0003:
                short_confirms.append('funding_positive')
            elif funding_rate is not None and funding_rate < -0.0005:
                short_warnings.append('funding_negative')  # 负费率做空有风险
            
            # 2. OI确认：OI下降或稳定支持做空
            if oi_change_1h is not None:
                if oi_change_1h < -0.01:
                    short_confirms.append('oi_declining')
                elif oi_change_1h > 0.03:
                    short_warnings.append('oi_surging')  # OI激增时做空风险大
            
            # 3. 价格趋势确认：价格下跌支持做空
            if price_change_1h is not None and price_change_1h < -0.005:
                short_confirms.append('price_declining')
            elif price_change_1h is not None and price_change_1h > 0.02:
                short_warnings.append('price_surging')
            
            # 4. 多空比确认：多头拥挤支持做空
            if cg_long_short_ratio:
                long_pct = cg_long_short_ratio.get('long_percent', 50)
                if long_pct > 60:
                    short_confirms.append('long_crowded')
                elif long_pct < 40:
                    short_warnings.append('short_crowded')
            
            # 5. 大户确认：大户偏空支持做空
            if top_long_ratio is not None:
                if top_long_ratio < 0.45:
                    short_confirms.append('top_trader_short')
                elif top_long_ratio > 0.60:
                    short_warnings.append('top_trader_long')
            
            # 6. 费率趋势确认
            if cg_funding_history:
                fr_trend = cg_funding_history.get('trend')
                if fr_trend == 'increasing':
                    short_confirms.append('funding_trend_up')
            
            # 计算确认强度
            confirm_count = len(short_confirms)
            warning_count = len(short_warnings)
            
            all_details['short_confirmation'] = {
                'confirms': short_confirms,
                'warnings': short_warnings,
                'confirm_count': confirm_count,
                'warning_count': warning_count
            }
            
            # 根据确认数量调整加分
            multi_confirm_bonus = self.thresholds.get('short_multi_confirm_bonus', 8)
            weak_confirm_penalty = self.thresholds.get('short_weak_confirm_penalty', -5)
            
            if confirm_count >= 4 and warning_count == 0:
                # 强确认：4+维度确认且无警告
                total_boost += multi_confirm_bonus
                all_details['short_quality'] = 'strong_multi_confirm'
                signal_quality = 'strong'
                logger.info(f"SHORT strong confirmation: {confirm_count} confirms, boost=+{multi_confirm_bonus}")
            elif confirm_count >= 3 and warning_count <= 1:
                # 中等确认
                total_boost += multi_confirm_bonus // 2
                all_details['short_quality'] = 'moderate_confirm'
            elif confirm_count <= 1 and warning_count >= 2:
                # 弱确认：确认少且警告多
                total_boost += weak_confirm_penalty
                all_details['short_quality'] = 'weak_confirm'
                signal_quality = 'weak'
                logger.info(f"SHORT weak confirmation: {confirm_count} confirms, {warning_count} warnings, penalty={weak_confirm_penalty}")
            elif warning_count > confirm_count:
                # 警告多于确认
                total_boost += weak_confirm_penalty // 2
                all_details['short_quality'] = 'risky'
        
        # 更新最终信号质量
        if total_boost >= 20:
            signal_quality = 'strong'
        elif total_boost >= 10:
            signal_quality = 'moderate'
        elif total_boost <= -10:
            signal_quality = 'weak'
        
        all_details['final_total_boost'] = total_boost
        
        return EnhancementResult(all_tags, total_boost, signal_quality, all_details)


# 全局实例（可选）
_enhancer_instance = None

def get_signal_enhancer(thresholds: Dict = None) -> SignalEnhancer:
    """获取全局SignalEnhancer实例"""
    global _enhancer_instance
    if _enhancer_instance is None:
        _enhancer_instance = SignalEnhancer(thresholds)
    return _enhancer_instance
