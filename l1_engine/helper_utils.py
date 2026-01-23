"""
L1 Advisory Engine - 辅助工具模块

职责：
提供None-safe的helper函数
"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class HelperUtils:
    """辅助工具集"""
    
    @staticmethod
    def num(data: Dict, key: str, default=None) -> Optional[float]:
        """
        None-safe数值读取
        
        Args:
            data: 数据字典
            key: 键名
            default: 默认值（None）
        
        Returns:
            float值或None
        """
        value = data.get(key, default)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning(f"Invalid numeric value for {key}: {value}")
            return None
    
    @staticmethod
    def safe_abs(value: Optional[float]) -> Optional[float]:
        """
        None-safe abs
        
        Args:
            value: 数值或None
        
        Returns:
            abs(value)或None
        """
        return abs(value) if value is not None else None
    
    @staticmethod
    def compare(value: Optional[float], op: str, threshold: float) -> bool:
        """
        None-safe比较（None视为False）
        
        Args:
            value: 数值或None
            op: 操作符（'>', '<', '>=', '<=', '==', '!='）
            threshold: 阈值
        
        Returns:
            比较结果（None返回False）
        """
        if value is None:
            return False
        
        if op == '>':
            return value > threshold
        elif op == '<':
            return value < threshold
        elif op == '>=':
            return value >= threshold
        elif op == '<=':
            return value <= threshold
        elif op == '==':
            return value == threshold
        elif op == '!=':
            return value != threshold
        else:
            logger.warning(f"Unknown operator: {op}")
            return False
    
    @staticmethod
    def fmt(value: Optional[float], precision: int = 2) -> str:
        """
        None-safe格式化（用于日志）
        
        Args:
            value: 数值或None
            precision: 小数位数
        
        Returns:
            格式化字符串（None返回"NA"）
        """
        if value is None:
            return "NA"
        try:
            return f"{value:.{precision}f}"
        except (TypeError, ValueError):
            return str(value)
    
    @staticmethod
    def flatten_thresholds(config: dict) -> dict:
        """
        将嵌套配置扁平化为易于访问的字典
        
        Args:
            config: 嵌套配置字典
        
        Returns:
            dict: 扁平化后的阈值字典
        """
        flat = {}
        
        # 数据质量
        dq = config.get('data_quality', {})
        flat['data_max_staleness_seconds'] = dq.get('max_staleness_seconds', 120)
        
        # 市场环境
        mr = config.get('market_regime', {})
        flat['extreme_price_change_1h'] = mr.get('extreme_price_change_1h', 0.05)
        flat['trend_price_change_6h'] = mr.get('trend_price_change_6h', 0.03)
        flat['short_term_trend_1h'] = mr.get('short_term_trend_1h', 0.02)
        
        # 风险准入
        re = config.get('risk_exposure', {})
        flat['liquidation_price_change'] = re.get('liquidation', {}).get('price_change', 0.05)
        flat['liquidation_oi_drop'] = re.get('liquidation', {}).get('oi_drop', -0.15)
        flat['crowding_funding_abs'] = re.get('crowding', {}).get('funding_abs', 0.001)
        flat['crowding_oi_growth'] = re.get('crowding', {}).get('oi_growth', 0.30)
        flat['extreme_volume_multiplier'] = re.get('extreme_volume', {}).get('multiplier', 10.0)
        
        # 交易质量
        tq = config.get('trade_quality', {})
        flat['absorption_imbalance'] = tq.get('absorption', {}).get('imbalance', 0.7)
        flat['absorption_volume_ratio'] = tq.get('absorption', {}).get('volume_ratio', 0.5)
        flat['noisy_funding_volatility'] = tq.get('noise', {}).get('funding_volatility', 0.0005)
        flat['noisy_funding_abs'] = tq.get('noise', {}).get('funding_abs', 0.0001)
        flat['rotation_price_threshold'] = tq.get('rotation', {}).get('price_threshold', 0.02)
        flat['rotation_oi_threshold'] = tq.get('rotation', {}).get('oi_threshold', 0.05)
        flat['range_weak_imbalance'] = tq.get('range_weak', {}).get('imbalance', 0.6)
        flat['range_weak_oi'] = tq.get('range_weak', {}).get('oi', 0.10)
        
        # 方向评估
        d = config.get('direction', {})
        flat['long_imbalance_trend'] = d.get('trend', {}).get('long', {}).get('imbalance', 0.6)
        flat['long_oi_change_trend'] = d.get('trend', {}).get('long', {}).get('oi_change', 0.05)
        flat['long_price_change_trend'] = d.get('trend', {}).get('long', {}).get('price_change', 0.01)
        flat['short_imbalance_trend'] = d.get('trend', {}).get('short', {}).get('imbalance', 0.6)
        flat['short_oi_change_trend'] = d.get('trend', {}).get('short', {}).get('oi_change', 0.05)
        flat['short_price_change_trend'] = d.get('trend', {}).get('short', {}).get('price_change', 0.01)
        flat['long_imbalance_range'] = d.get('range', {}).get('long', {}).get('imbalance', 0.7)
        flat['long_oi_change_range'] = d.get('range', {}).get('long', {}).get('oi_change', 0.10)
        flat['short_imbalance_range'] = d.get('range', {}).get('short', {}).get('imbalance', 0.7)
        flat['short_oi_change_range'] = d.get('range', {}).get('short', {}).get('oi_change', 0.10)
        
        # 辅助标签阈值
        aux = config.get('auxiliary_tags', {})
        flat['aux_oi_growing_threshold'] = aux.get('oi_growing_threshold', 0.05)
        flat['aux_oi_declining_threshold'] = aux.get('oi_declining_threshold', -0.05)
        flat['aux_funding_rate_threshold'] = aux.get('funding_rate_threshold', 0.0005)
        
        return flat
