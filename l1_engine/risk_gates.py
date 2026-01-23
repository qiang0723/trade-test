"""
L1 Advisory Engine - 风险闸门模块

职责：
1. 风险准入评估（第一道闸门）
2. 交易质量评估（第二道闸门）
"""

from typing import Dict, Tuple, List
from models.enums import MarketRegime, TradeQuality
from models.reason_tags import ReasonTag
import logging

logger = logging.getLogger(__name__)


class RiskGates:
    """风险闸门（准入+质量）"""
    
    def __init__(self, thresholds: Dict):
        """
        初始化风险闸门
        
        Args:
            thresholds: 扁平化的阈值字典
        """
        self.thresholds = thresholds
        self.history_data = {}  # 用于噪音市检测
    
    def eval_risk_exposure_allowed(
        self, 
        data: Dict, 
        regime: MarketRegime
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        风险准入评估 - 系统性风险检查
        
        检查项：
        1. 极端行情（最高优先级）
        2. 清算阶段（价格急变 + OI急降）
        3. 拥挤风险（极端费率 + 高OI增长）
        4. 极端成交量
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (是否允许风险敞口, 原因标签列表)
        """
        tags = []
        
        # 1. 极端行情
        if regime == MarketRegime.EXTREME:
            tags.append(ReasonTag.EXTREME_REGIME)
            return False, tags
        
        # 2. 清算阶段
        price_change_1h = self._num(data, 'price_change_1h')
        oi_change_1h = self._num(data, 'oi_change_1h')
        
        if price_change_1h is not None and oi_change_1h is not None:
            if (abs(price_change_1h) > self.thresholds['liquidation_price_change'] and 
                oi_change_1h < self.thresholds['liquidation_oi_drop']):
                tags.append(ReasonTag.LIQUIDATION_PHASE)
                return False, tags
        else:
            if price_change_1h is None or oi_change_1h is None:
                logger.debug("Liquidation check skipped (price_change_1h or oi_change_1h missing)")
        
        # 3. 拥挤风险
        funding_rate_value = self._num(data, 'funding_rate')
        oi_change_6h = self._num(data, 'oi_change_6h')
        
        if funding_rate_value is not None and oi_change_6h is not None:
            funding_rate_abs = abs(funding_rate_value)
            if (funding_rate_abs > self.thresholds['crowding_funding_abs'] and 
                oi_change_6h > self.thresholds['crowding_oi_growth']):
                tags.append(ReasonTag.CROWDING_RISK)
                return False, tags
        else:
            if funding_rate_value is None or oi_change_6h is None:
                logger.debug("Crowding check skipped (funding_rate or oi_change_6h missing)")
        
        # 4. 极端成交量
        volume_1h = self._num(data, 'volume_1h')
        volume_24h = self._num(data, 'volume_24h')
        
        if volume_1h is not None and volume_24h is not None and volume_24h > 0:
            volume_avg = volume_24h / 24
            if volume_1h > volume_avg * self.thresholds['extreme_volume_multiplier']:
                tags.append(ReasonTag.EXTREME_VOLUME)
                return False, tags
        else:
            logger.debug("Extreme volume check skipped (volume data missing)")
        
        # 通过所有风险检查
        return True, []
    
    def eval_trade_quality(
        self, 
        symbol: str,
        data: Dict, 
        regime: MarketRegime
    ) -> Tuple[TradeQuality, List[ReasonTag]]:
        """
        交易质量评估 - 机会质量检查
        
        检查项：
        1. 吸纳风险（高失衡 + 低成交量）
        2. 噪音市（费率波动大但无方向）
        3. 轮动风险（OI和价格背离）
        4. 震荡市弱信号
        
        Args:
            symbol: 币种符号
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (交易质量, 原因标签列表)
        """
        tags = []
        
        # 1. 吸纳风险
        imbalance_value = self._num(data, 'taker_imbalance_1h')
        volume_1h = self._num(data, 'volume_1h')
        volume_24h = self._num(data, 'volume_24h')
        
        if imbalance_value is not None and volume_1h is not None and volume_24h is not None and volume_24h > 0:
            imbalance_abs = abs(imbalance_value)
            volume_avg = volume_24h / 24
            if (imbalance_abs > self.thresholds['absorption_imbalance'] and 
                volume_1h < volume_avg * self.thresholds['absorption_volume_ratio']):
                tags.append(ReasonTag.ABSORPTION_RISK)
                return TradeQuality.POOR, tags
        elif imbalance_value is None or volume_1h is None or volume_24h is None:
            logger.debug(f"[{symbol}] Absorption check skipped (imbalance/volume missing)")
            tags.append(ReasonTag.DATA_INCOMPLETE_MTF)
            return TradeQuality.UNCERTAIN, tags
        
        # 2. 噪音市
        funding_rate = self._num(data, 'funding_rate')
        
        if funding_rate is not None:
            history_key = f'{symbol}_funding_rate_prev'
            is_first_call = history_key not in self.history_data
            
            funding_rate_prev = self.history_data.get(history_key, funding_rate)
            funding_volatility = abs(funding_rate - funding_rate_prev)
            
            self.history_data[history_key] = funding_rate
            
            if is_first_call:
                logger.debug(f"[{symbol}] First call for noise detection, funding_rate history initialized")
            
            if (funding_volatility > self.thresholds['noisy_funding_volatility'] and 
                abs(funding_rate) < self.thresholds['noisy_funding_abs']):
                tags.append(ReasonTag.NOISY_MARKET)
                return TradeQuality.UNCERTAIN, tags
        else:
            logger.debug(f"[{symbol}] Noise check skipped (funding_rate missing)")
        
        # 3. 轮动风险
        price_change_1h = self._num(data, 'price_change_1h')
        oi_change_1h = self._num(data, 'oi_change_1h')
        
        if price_change_1h is not None and oi_change_1h is not None:
            if ((price_change_1h > self.thresholds['rotation_price_threshold'] and 
                 oi_change_1h < -self.thresholds['rotation_oi_threshold']) or
                (price_change_1h < -self.thresholds['rotation_price_threshold'] and 
                 oi_change_1h > self.thresholds['rotation_oi_threshold'])):
                tags.append(ReasonTag.ROTATION_RISK)
                return TradeQuality.POOR, tags
        else:
            logger.debug(f"[{symbol}] Rotation check skipped (price_change_1h or oi_change_1h missing)")
        
        # 4. 震荡市弱信号
        if regime == MarketRegime.RANGE:
            imbalance_abs = self._abs(imbalance_value) if imbalance_value is not None else None
            oi_change_1h_abs = self._abs(oi_change_1h) if oi_change_1h is not None else None
            
            if imbalance_abs is not None and oi_change_1h_abs is not None:
                if (imbalance_abs < self.thresholds['range_weak_imbalance'] and 
                    oi_change_1h_abs < self.thresholds['range_weak_oi']):
                    tags.append(ReasonTag.WEAK_SIGNAL_IN_RANGE)
                    return TradeQuality.UNCERTAIN, tags
            else:
                logger.debug(f"[{symbol}] Range weak signal check skipped (imbalance or oi_change missing)")
        
        # 通过所有质量检查
        return TradeQuality.GOOD, []
    
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
    
    def _abs(self, value: float) -> float:
        """None-safe abs"""
        return abs(value) if value is not None else None
