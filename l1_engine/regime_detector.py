"""
L1 Advisory Engine - 市场环境识别模块

职责：
识别市场环境：TREND（趋势）/ RANGE（震荡）/ EXTREME（极端）
"""

from typing import Dict, Tuple, List
from models.enums import MarketRegime
from models.reason_tags import ReasonTag
import logging

logger = logging.getLogger(__name__)


class RegimeDetector:
    """市场环境识别器"""
    
    def __init__(self, thresholds: Dict):
        """
        初始化市场环境识别器
        
        Args:
            thresholds: 扁平化的阈值字典
        """
        self.thresholds = thresholds
    
    def detect_market_regime(self, data: Dict) -> Tuple[MarketRegime, List[ReasonTag]]:
        """
        识别市场环境：TREND（趋势）/ RANGE（震荡）/ EXTREME（极端）
        
        Args:
            data: 市场数据
        
        Returns:
            (MarketRegime, 标识标签列表)
        """
        regime_tags = []
        
        # None-safe读取
        price_change_1h = self._num(data, 'price_change_1h')
        price_change_6h = self._num(data, 'price_change_6h')
        price_change_15m = self._num(data, 'price_change_15m')  # fallback
        
        # 1. EXTREME: 极端波动（优先级最高）
        if price_change_1h is not None:
            price_change_1h_abs = abs(price_change_1h)
            if price_change_1h_abs > self.thresholds['extreme_price_change_1h']:
                return MarketRegime.EXTREME, regime_tags
        
        # 2. TREND: 趋势市
        # 2.1 中期趋势（6小时）
        if price_change_6h is not None:
            price_change_6h_abs = abs(price_change_6h)
            if price_change_6h_abs > self.thresholds['trend_price_change_6h']:
                return MarketRegime.TREND, regime_tags
        elif price_change_15m is not None:
            # 缺6h时使用15m退化判定（更保守阈值）
            price_change_15m_abs = abs(price_change_15m)
            fallback_threshold = self.thresholds['trend_price_change_6h'] * 0.5
            if price_change_15m_abs > fallback_threshold:
                regime_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)  # 标记退化
                logger.debug("Regime detection using 15m fallback (6h missing)")
                return MarketRegime.TREND, regime_tags
        
        # 2.2 短期趋势（1小时）
        if price_change_1h is not None:
            price_change_1h_abs = abs(price_change_1h)
            if price_change_1h_abs > self.thresholds.get('short_term_trend_1h', 0.02):
                regime_tags.append(ReasonTag.SHORT_TERM_TREND)
                return MarketRegime.TREND, regime_tags
        
        # 3. RANGE: 震荡市（默认）
        if price_change_1h is None and price_change_6h is None:
            regime_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)
            logger.debug("Regime defaults to RANGE (price_change data missing)")
        
        return MarketRegime.RANGE, regime_tags
    
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
