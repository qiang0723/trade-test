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
    # P0-BugFix: 调整阈值，因为所有输入都是百分比点格式（已乘100）
    SUSPICIOUS_HIGH_THRESHOLD = 1000.0  # 超过1000视为异常（表示100000%）
    SUSPICIOUS_LOW_THRESHOLD = 0.0001  # 小于0.0001视为可疑（可能是误差）
    
    @classmethod
    def normalize(cls, data: Dict) -> Tuple[Dict, bool, str]:
        """
        规范化市场数据指标
        
        Args:
            data: 原始市场数据字典
        
        Returns:
            (规范化后的数据, 是否有效, 错误信息)
        
        重要：
        - PR-M (方案B): 支持元数据标注的格式声明
        - 读取 _metadata.percentage_format 来决定是否需要转换
        - 向后兼容：无元数据时默认为 percent_point 格式
        """
        normalized = data.copy()
        
        # PR-M: 读取元数据中的格式声明
        metadata = data.get('_metadata', {})
        input_format = metadata.get('percentage_format', 'percent_point')  # 默认 percent_point（向后兼容）
        
        # PR-M 建议A：上游注入点唯一性检查
        if not metadata:
            logger.warning(
                "数据缺失 _metadata 标注，使用默认格式 'percent_point'。"
                "建议：确保数据源层（MarketDataCache）正确注入元数据。"
            )
        
        # 验证格式声明
        if input_format not in ['percent_point', 'decimal']:
            error_msg = f"未知的百分比格式声明: {input_format}（应为 'percent_point' 或 'decimal'）"
            logger.error(error_msg)
            return normalized, False, error_msg
        
        # 检测口径异常（极端异常值，如 >1000 表示100000%）
        # 注意：异常检测需要考虑当前格式
        is_valid, error_msg = cls._detect_scale_anomaly(data, input_format)
        if not is_valid:
            return normalized, False, error_msg
        
        # 根据输入格式决定是否转换
        if input_format == 'percent_point':
            # 百分比点格式：需要转换为小数格式（除以100）
            for field in cls.PERCENTAGE_FIELDS:
                if field in normalized and normalized[field] is not None:
                    value = normalized[field]
                    # 统一转换：百分比点 → 小数
                    # 0.5 (0.5%) → 0.005
                    # 3.0 (3%) → 0.03
                    # 50.0 (50%) → 0.50
                    normalized[field] = value / 100.0
                    logger.debug(f"Converted {field} from {value}% to {normalized[field]:.6f} (decimal)")
            
            logger.debug(f"Normalized metrics from percent_point to decimal format")
        
        elif input_format == 'decimal':
            # 小数格式：无需转换，直接使用
            logger.debug(f"Input already in decimal format, no conversion needed")
        
        # 移除元数据字段（不传递给下游）
        normalized.pop('_metadata', None)
        
        return normalized, True, ""
    
    @classmethod
    def _detect_scale_anomaly(cls, data: Dict, input_format: str = 'percent_point') -> Tuple[bool, str]:
        """
        检测尺度异常（极端异常值）
        
        PR-M: 根据输入格式调整异常检测阈值
        
        Args:
            data: 市场数据字典
            input_format: 输入格式 ('percent_point' 或 'decimal')
        
        Returns:
            (是否有效, 错误信息)
        """
        # 根据输入格式设置不同的阈值
        if input_format == 'percent_point':
            # 百分比点格式：3.0 表示 3%，1000.0 表示 1000%
            threshold = cls.SUSPICIOUS_HIGH_THRESHOLD  # 1000.0 (1000%)
            threshold_display = f"{threshold}%"
        else:  # decimal
            # 小数格式：0.03 表示 3%，10.0 表示 1000%
            threshold = cls.SUSPICIOUS_HIGH_THRESHOLD / 100.0  # 10.0 (1000%)
            threshold_display = f"{threshold*100}%"
        
        # 检测极端异常值
        for field in cls.PERCENTAGE_FIELDS:
            if field in data and data[field] is not None:
                value = abs(data[field])
                
                # 检测异常大的值
                if value > threshold:
                    if input_format == 'percent_point':
                        display_value = f"{value:.2f}%"
                    else:
                        display_value = f"{value*100:.2f}%"
                    
                    error_msg = (
                        f"指标值异常：{field}={display_value} 超出合理范围 "
                        f"(>{threshold_display})。"
                        f"这可能是数据错误或API异常。"
                    )
                    logger.error(error_msg)
                    return False, error_msg
        
        return True, ""
    
    @classmethod
    def validate_ranges(cls, data: Dict) -> Tuple[bool, str]:
        """
        验证指标合理性范围（PR-J: 纳入L1校验链路）
        
        Args:
            data: 规范化后的数据
        
        Returns:
            (是否有效, 错误信息)
        """
        # 价格变化率合理性检查（1小时内 ±20% 视为极限）
        if 'price_change_1h' in data and data['price_change_1h'] is not None:
            value = abs(data['price_change_1h'])
            if value > 0.20:  # 20%
                return False, f"price_change_1h超出合理范围：{value*100:.2f}% (>20%)"
        
        # 价格变化率合理性检查（6小时内 ±50% 视为极限）
        if 'price_change_6h' in data and data['price_change_6h'] is not None:
            value = abs(data['price_change_6h'])
            if value > 0.50:  # 50%
                return False, f"price_change_6h超出合理范围：{value*100:.2f}% (>50%)"
        
        # OI变化率合理性检查（1小时内 ±100% 视为极限）
        if 'oi_change_1h' in data and data['oi_change_1h'] is not None:
            value = abs(data['oi_change_1h'])
            if value > 1.0:  # 100%
                return False, f"oi_change_1h超出合理范围：{value*100:.2f}% (>100%)"
        
        # OI变化率合理性检查（6小时内 ±200% 视为极限）
        if 'oi_change_6h' in data and data['oi_change_6h'] is not None:
            value = abs(data['oi_change_6h'])
            if value > 2.0:  # 200%
                return False, f"oi_change_6h超出合理范围：{value*100:.2f}% (>200%)"
        
        # 买卖失衡必须在 -1 到 1 之间
        if 'buy_sell_imbalance' in data and data['buy_sell_imbalance'] is not None:
            value = data['buy_sell_imbalance']
            if value < -1 or value > 1:
                return False, f"buy_sell_imbalance超出范围：{value:.4f} (应在-1到1之间)"
        
        # 资金费率合理性检查（单次费率 ±1% 视为极限）
        if 'funding_rate' in data and data['funding_rate'] is not None:
            value = abs(data['funding_rate'])
            if value > 0.01:  # 1%
                return False, f"funding_rate超出合理范围：{value*100:.4f}% (>1%)"
        
        # 成交量比例合理性检查（相对于24h均值，10倍视为极限）
        if 'volume_ratio' in data and data['volume_ratio'] is not None:
            value = data['volume_ratio']
            if value < 0:
                return False, f"volume_ratio不能为负：{value:.2f}"
            if value > 50:  # 50倍
                return False, f"volume_ratio超出合理范围：{value:.2f}x (>50x)"
        
        # 价格必须为正
        if 'price' in data and data['price'] is not None:
            value = data['price']
            if value <= 0:
                return False, f"price必须为正：{value}"
        
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
