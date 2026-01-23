"""
L1 Advisory Engine - 信号生成器模块

职责：
1. 做多/做空方向评估
2. 决策优先级判断
"""

from typing import Dict, Tuple, List
from models.enums import Decision, MarketRegime
from models.reason_tags import ReasonTag
import logging

logger = logging.getLogger(__name__)


class SignalGenerator:
    """信号生成器（方向评估）"""
    
    def __init__(self, thresholds: Dict, config: Dict):
        """
        初始化信号生成器
        
        Args:
            thresholds: 扁平化的阈值字典
            config: 完整配置字典
        """
        self.thresholds = thresholds
        self.config = config
    
    def eval_long_direction(self, data: Dict, regime: MarketRegime) -> Tuple[bool, List[ReasonTag]]:
        """
        做多方向评估
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (是否允许做多, 标签列表)
        """
        direction_tags = []
        
        # None-safe读取
        imbalance = self._num(data, 'taker_imbalance_1h')
        oi_change = self._num(data, 'oi_change_1h')
        price_change = self._num(data, 'price_change_1h')
        
        # 关键字段缺失，无法判断方向
        if imbalance is None or oi_change is None or price_change is None:
            logger.debug("Long direction eval skipped (key fields missing)")
            return False, direction_tags
        
        if regime == MarketRegime.TREND:
            # 趋势市：多方强势
            if (imbalance > self.thresholds['long_imbalance_trend'] and 
                oi_change > self.thresholds['long_oi_change_trend'] and 
                price_change > self.thresholds['long_price_change_trend']):
                return True, direction_tags
        
        elif regime == MarketRegime.RANGE:
            # 震荡市：原有强信号逻辑
            if (imbalance > self.thresholds['long_imbalance_range'] and 
                oi_change > self.thresholds['long_oi_change_range']):
                return True, direction_tags
            
            # 短期机会识别
            short_term_config = self.config.get('direction', {}).get('range', {}).get('short_term_opportunity', {}).get('long', {})
            if short_term_config:
                signals = []
                signal_tags = []
                
                # 信号1: 价格短期上涨
                if price_change > short_term_config.get('min_price_change_1h', 0.015):
                    signals.append('price_surge')
                    signal_tags.append(ReasonTag.SHORT_TERM_PRICE_SURGE)
                
                # 信号2: OI增长
                if oi_change > short_term_config.get('min_oi_change_1h', 0.15):
                    signals.append('oi_growing')
                
                # 信号3: 强买压
                min_imbalance_threshold = short_term_config.get('min_taker_imbalance') or short_term_config.get('min_buy_sell_imbalance', 0.65)
                if imbalance > min_imbalance_threshold:
                    signals.append('strong_buy_pressure')
                    signal_tags.append(ReasonTag.SHORT_TERM_STRONG_BUY)
                
                # 至少满足required_signals个信号
                required = short_term_config.get('required_signals', 2)
                if len(signals) >= required:
                    direction_tags.append(ReasonTag.RANGE_SHORT_TERM_LONG)
                    direction_tags.extend(signal_tags)
                    return True, direction_tags
        
        return False, direction_tags
    
    def eval_short_direction(self, data: Dict, regime: MarketRegime) -> Tuple[bool, List[ReasonTag]]:
        """
        做空方向评估
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (是否允许做空, 标签列表)
        """
        direction_tags = []
        
        # None-safe读取
        imbalance = self._num(data, 'taker_imbalance_1h')
        oi_change = self._num(data, 'oi_change_1h')
        price_change = self._num(data, 'price_change_1h')
        
        # 关键字段缺失，无法判断方向
        if imbalance is None or oi_change is None or price_change is None:
            logger.debug("Short direction eval skipped (key fields missing)")
            return False, direction_tags
        
        if regime == MarketRegime.TREND:
            # 趋势市：空方强势
            if (imbalance < -self.thresholds['short_imbalance_trend'] and 
                oi_change > self.thresholds['short_oi_change_trend'] and 
                price_change < -self.thresholds['short_price_change_trend']):
                return True, direction_tags
        
        elif regime == MarketRegime.RANGE:
            # 震荡市：原有强信号逻辑
            if (imbalance < -self.thresholds['short_imbalance_range'] and 
                oi_change > self.thresholds['short_oi_change_range']):
                return True, direction_tags
            
            # 短期机会识别
            short_term_config = self.config.get('direction', {}).get('range', {}).get('short_term_opportunity', {}).get('short', {})
            if short_term_config:
                signals = []
                signal_tags = []
                
                # 信号1: 价格短期下跌
                if price_change < short_term_config.get('max_price_change_1h', -0.015):
                    signals.append('price_drop')
                    signal_tags.append(ReasonTag.SHORT_TERM_PRICE_DROP)
                
                # 信号2: OI增长
                if oi_change > short_term_config.get('min_oi_change_1h', 0.15):
                    signals.append('oi_growing')
                
                # 信号3: 强卖压
                max_imbalance_threshold = short_term_config.get('max_taker_imbalance') or short_term_config.get('max_buy_sell_imbalance', -0.65)
                if imbalance < max_imbalance_threshold:
                    signals.append('strong_sell_pressure')
                    signal_tags.append(ReasonTag.SHORT_TERM_STRONG_SELL)
                
                # 至少满足required_signals个信号
                required = short_term_config.get('required_signals', 2)
                if len(signals) >= required:
                    direction_tags.append(ReasonTag.RANGE_SHORT_TERM_SHORT)
                    direction_tags.extend(signal_tags)
                    return True, direction_tags
        
        return False, direction_tags
    
    def decide_priority(
        self, 
        allow_short: bool, 
        allow_long: bool
    ) -> Tuple[Decision, List[ReasonTag]]:
        """
        决策优先级判断：SHORT > LONG > NO_TRADE
        
        Args:
            allow_short: 是否允许做空
            allow_long: 是否允许做多
        
        Returns:
            (决策, 原因标签列表)
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
    
    def _num(self, data: Dict, key: str, default=None):
        """None-safe数值读取"""
        value = data.get(key, default)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning(f"Invalid numeric value for {key}: {value}")
            return None
