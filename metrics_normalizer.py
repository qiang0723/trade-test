"""
L1 Advisory Layer - 指标口径规范化

负责：
1. 统一所有百分比指标的口径（小数格式 vs 百分比点）
2. 检测异常尺度（混用风险）
3. 提供数据验证和转换

口径标准：
- 所有百分比类指标统一为 **小数格式**
- 例如：5% → 0.05，-2.5% → -0.025
- 资金费率已经是小数格式（0.0001 = 0.01%），无需转换
"""

import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class MetricsNormalizer:
    """指标口径规范化器"""
    
    # 百分比字段列表（需要统一为小数格式）
    PERCENTAGE_FIELDS = [
        'price_change_1h',
        'price_change_6h',
        'oi_change_1h',
        'oi_change_6h',
    ]
    
    # 小数字段（已经是小数格式，无需转换）
    DECIMAL_FIELDS = [
        'funding_rate',           # 0.0001 = 0.01%
        'buy_sell_imbalance',     # -1 到 1
    ]
    
    # 异常检测阈值
    SUSPICIOUS_HIGH_THRESHOLD = 10.0  # 超过10视为可疑（可能是百分比点）
    SUSPICIOUS_LOW_THRESHOLD = 0.0001  # 小于0.0001视为可疑（可能是误差）
    
    @classmethod
    def normalize(cls, data: Dict) -> Tuple[Dict, bool, str]:
        """
        规范化市场数据指标
        
        Args:
            data: 原始市场数据字典
        
        Returns:
            (规范化后的数据, 是否有效, 错误信息)
        """
        normalized = data.copy()
        
        # 检测口径异常
        is_valid, error_msg = cls._detect_scale_anomaly(data)
        if not is_valid:
            return normalized, False, error_msg
        
        # 转换百分比字段
        for field in cls.PERCENTAGE_FIELDS:
            if field in normalized and normalized[field] is not None:
                value = normalized[field]
                
                # 如果值 > 1，可能是百分比点格式（如 5.0 表示 5%）
                # 自动转换为小数格式
                if abs(value) > 1.0:
                    normalized[field] = value / 100.0
                    logger.debug(f"Converted {field} from {value} to {normalized[field]} (percent to decimal)")
        
        return normalized, True, ""
    
    @classmethod
    def _detect_scale_anomaly(cls, data: Dict) -> Tuple[bool, str]:
        """
        检测尺度异常（混用风险）
        
        检查同一批数据中是否存在明显的尺度不一致
        
        Args:
            data: 市场数据字典
        
        Returns:
            (是否有效, 错误信息)
        """
        percentage_values = []
        
        # 收集所有百分比字段的值
        for field in cls.PERCENTAGE_FIELDS:
            if field in data and data[field] is not None:
                value = abs(data[field])
                if value > cls.SUSPICIOUS_LOW_THRESHOLD:  # 忽略接近0的值
                    percentage_values.append((field, value))
        
        if len(percentage_values) < 2:
            # 只有一个值，无法检测混用
            return True, ""
        
        # 检测是否同时存在 "很大" 和 "很小" 的值
        # 例如：price_change_1h=0.05（5%），oi_change_1h=50（误用百分比点）
        has_large = any(v > cls.SUSPICIOUS_HIGH_THRESHOLD for _, v in percentage_values)
        has_small = any(v < 1.0 for _, v in percentage_values)
        
        if has_large and has_small:
            # 可能存在混用
            large_fields = [f for f, v in percentage_values if v > cls.SUSPICIOUS_HIGH_THRESHOLD]
            small_fields = [f for f, v in percentage_values if v < 1.0]
            
            error_msg = (
                f"指标尺度异常：检测到可能的百分比格式混用。"
                f"大值字段: {large_fields}，小值字段: {small_fields}。"
                f"请确保所有百分比指标使用统一格式（推荐小数格式，如 0.05 表示 5%）"
            )
            logger.error(error_msg)
            return False, error_msg
        
        return True, ""
    
    @classmethod
    def validate_ranges(cls, data: Dict) -> Tuple[bool, str]:
        """
        验证指标合理性范围
        
        Args:
            data: 规范化后的数据
        
        Returns:
            (是否有效, 错误信息)
        """
        # 价格变化率合理性检查（1小时内 ±20% 视为极限）
        if 'price_change_1h' in data:
            value = abs(data['price_change_1h'])
            if value > 0.20:  # 20%
                return False, f"price_change_1h超出合理范围：{value*100:.2f}% (>20%)"
        
        # 买卖失衡必须在 -1 到 1 之间
        if 'buy_sell_imbalance' in data:
            value = data['buy_sell_imbalance']
            if value < -1 or value > 1:
                return False, f"buy_sell_imbalance超出范围：{value} (应在-1到1之间)"
        
        # 资金费率合理性检查（单次费率 ±1% 视为极限）
        if 'funding_rate' in data:
            value = abs(data['funding_rate'])
            if value > 0.01:  # 1%
                return False, f"funding_rate超出合理范围：{value*100:.4f}% (>1%)"
        
        return True, ""


# 便捷函数
def normalize_metrics(data: Dict) -> Tuple[Dict, bool, str]:
    """
    规范化市场数据指标（便捷函数）
    
    Args:
        data: 原始市场数据字典
    
    Returns:
        (规范化后的数据, 是否有效, 错误信息)
    """
    return MetricsNormalizer.normalize(data)
