"""
L1 Advisory Layer - 指标口径规范化（PATCH-1增强版）

负责：
1. 统一所有百分比指标的口径（小数格式 vs 百分比点）
2. 字段族规则：自动覆盖所有 price_change_*/oi_change_* 字段
3. 提供数据验证和转换，含 trace 输出
4. 元数据缺失处理策略（WARN/FAIL_FAST/ASSUME_PERCENT_POINT）

口径标准：
- 所有百分比类指标统一为 **小数格式**
- 例如：5% → 0.05，-2.5% → -0.025
- 资金费率已经是小数格式（0.0001 = 0.01%），无需转换

PATCH-1 改进：
- ✅ 字段族规则（price_change_*、oi_change_*）自动覆盖所有周期
- ✅ Trace 输出（converted_fields、skipped_fields、range_fail_fields）
- ✅ 元数据处理策略配置
- ✅ 范围校验扩展到所有字段族
"""

import logging
import re
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MetadataPolicy(Enum):
    """元数据缺失时的处理策略"""
    WARN = "warn"                    # 警告并假设 percent_point（向后兼容）
    FAIL_FAST = "fail_fast"          # 失败并拒绝处理
    ASSUME_PERCENT_POINT = "assume_percent_point"  # 静默假设（不推荐）


@dataclass
class NormalizationTrace:
    """规范化过程追溯信息"""
    input_percentage_format: str                    # 输入格式（percent_point/decimal/unknown）
    converted_fields: List[str] = field(default_factory=list)  # 转换的字段
    skipped_fields: List[str] = field(default_factory=list)    # 跳过的字段（已是decimal）
    range_fail_fields: List[str] = field(default_factory=list) # 范围校验失败的字段
    metadata_policy_applied: Optional[str] = None    # 应用的元数据策略
    field_family_matched: Dict[str, List[str]] = field(default_factory=dict)  # 字段族匹配结果
    
    def to_dict(self) -> dict:
        """转换为字典供 Step1 trace 使用"""
        return {
            'input_percentage_format': self.input_percentage_format,
            'converted_fields': self.converted_fields,
            'skipped_fields': self.skipped_fields,
            'range_fail_fields': self.range_fail_fields,
            'metadata_policy_applied': self.metadata_policy_applied,
            'field_family_matched': self.field_family_matched
        }


class MetricsNormalizer:
    """指标口径规范化器（PATCH-1增强版）"""
    
    # ==========================================
    # PATCH-1: 字段族规则（替代静态列表）
    # ==========================================
    
    # 百分比字段族（自动匹配所有周期）
    PERCENTAGE_FIELD_PATTERNS = [
        r'^price_change_\w+$',   # price_change_5m, price_change_15m, price_change_1h, price_change_6h, etc.
        r'^oi_change_\w+$',      # oi_change_15m, oi_change_1h, oi_change_6h, etc.
    ]
    
    # 无量纲字段（范围约束）
    DIMENSIONLESS_FIELDS = {
        'buy_sell_imbalance': (-1.0, 1.0),      # [-1, 1]
        'taker_imbalance_5m': (-1.0, 1.0),      # [-1, 1]
        'taker_imbalance_15m': (-1.0, 1.0),     # [-1, 1]
        'taker_imbalance_1h': (-1.0, 1.0),      # [-1, 1]
    }
    
    # 正数字段（无量纲但必须为正）
    POSITIVE_FIELDS = [
        r'^volume_ratio_\w+$',   # volume_ratio_5m, volume_ratio_15m, etc.
        'volume_ratio',
    ]
    
    # 小数字段（已经是小数格式，无需转换）
    DECIMAL_FIELDS = [
        'funding_rate',           # 0.0001 = 0.01%
    ]
    
    # 异常检测阈值
    SUSPICIOUS_HIGH_THRESHOLD = 1000.0  # 百分比点格式：>1000% 视为异常
    SUSPICIOUS_LOW_THRESHOLD = 0.0001  # 小于0.0001视为可疑
    
    # 范围校验配置（小数格式）
    RANGE_LIMITS = {
        'price_change_5m': 0.05,    # 5分钟 ±5%
        'price_change_15m': 0.10,   # 15分钟 ±10%
        'price_change_1h': 0.20,    # 1小时 ±20%
        'price_change_6h': 0.50,    # 6小时 ±50%
        'oi_change_15m': 0.50,      # 15分钟 ±50%
        'oi_change_1h': 1.0,        # 1小时 ±100%
        'oi_change_6h': 2.0,        # 6小时 ±200%
        'funding_rate': 0.01,       # 单次费率 ±1%
        'volume_ratio': (0, 50),    # 0到50倍
        'price': (0, float('inf')), # 必须为正
    }
    
    def __init__(self, metadata_policy: MetadataPolicy = MetadataPolicy.WARN):
        """
        初始化规范化器
        
        Args:
            metadata_policy: 元数据缺失时的处理策略
        """
        self.metadata_policy = metadata_policy
    
    @classmethod
    def _is_percentage_field(cls, field_name: str) -> bool:
        """
        判断字段是否属于百分比字段族
        
        Args:
            field_name: 字段名
        
        Returns:
            是否匹配百分比字段族
        """
        for pattern in cls.PERCENTAGE_FIELD_PATTERNS:
            if re.match(pattern, field_name):
                return True
        return False
    
    @classmethod
    def _is_positive_field(cls, field_name: str) -> bool:
        """判断字段是否属于正数字段族"""
        for pattern in cls.POSITIVE_FIELDS:
            if isinstance(pattern, str):
                if pattern.startswith('^'):
                    if re.match(pattern, field_name):
                        return True
                elif pattern == field_name:
                    return True
            elif re.match(pattern, field_name):
                return True
        return False
    
    def normalize(self, data: Dict) -> Tuple[Dict, bool, str, NormalizationTrace]:
        """
        规范化市场数据指标（PATCH-1增强版）
        
        Args:
            data: 原始市场数据字典
        
        Returns:
            (规范化后的数据, 是否有效, 错误信息, Trace信息)
        """
        normalized = data.copy()
        trace = NormalizationTrace(input_percentage_format='unknown')
        
        # ===== Step 1: 读取元数据 =====
        metadata = data.get('_metadata', {})
        input_format = metadata.get('percentage_format')
        
        # ===== Step 2: 元数据缺失处理 =====
        if input_format is None:
            if self.metadata_policy == MetadataPolicy.FAIL_FAST:
                error_msg = "数据缺失 _metadata.percentage_format，且策略为 FAIL_FAST"
                logger.error(error_msg)
                trace.metadata_policy_applied = 'FAIL_FAST'
                return normalized, False, error_msg, trace
            
            elif self.metadata_policy == MetadataPolicy.WARN:
                logger.warning(
                    "数据缺失 _metadata.percentage_format，假设为 'percent_point'（向后兼容）。"
                    "建议：确保数据源层（MarketDataCache/BinanceDataFetcher）正确注入元数据。"
                )
                input_format = 'percent_point'
                trace.metadata_policy_applied = 'WARN_ASSUME_PERCENT_POINT'
            
            else:  # ASSUME_PERCENT_POINT
                input_format = 'percent_point'
                trace.metadata_policy_applied = 'ASSUME_PERCENT_POINT'
        
        trace.input_percentage_format = input_format
        
        # ===== Step 3: 验证格式声明 =====
        if input_format not in ['percent_point', 'decimal']:
            error_msg = f"未知的百分比格式声明: {input_format}（应为 'percent_point' 或 'decimal'）"
            logger.error(error_msg)
            return normalized, False, error_msg, trace
        
        # ===== Step 4: 字段族匹配与转换 =====
        percentage_fields_found = []
        positive_fields_found = []
        
        for field_name in list(normalized.keys()):
            if field_name == '_metadata':
                continue
            
            # 匹配百分比字段族
            if self._is_percentage_field(field_name):
                percentage_fields_found.append(field_name)
            
            # 匹配正数字段族
            if self._is_positive_field(field_name):
                positive_fields_found.append(field_name)
        
        trace.field_family_matched = {
            'percentage_fields': percentage_fields_found,
            'positive_fields': positive_fields_found
        }
        
        # ===== Step 5: 异常检测 =====
        is_valid, error_msg = self._detect_scale_anomaly(data, input_format, percentage_fields_found)
        if not is_valid:
            return normalized, False, error_msg, trace
        
        # ===== Step 6: 转换百分比字段 =====
        if input_format == 'percent_point':
            for field in percentage_fields_found:
                if field in normalized and normalized[field] is not None:
                    value = normalized[field]
                    normalized[field] = value / 100.0
                    trace.converted_fields.append(field)
                    logger.debug(f"Converted {field}: {value}% → {normalized[field]:.6f}")
        
        elif input_format == 'decimal':
            # 已是小数格式，记录跳过
            trace.skipped_fields = percentage_fields_found.copy()
            logger.debug(f"Input already in decimal format, skipped {len(percentage_fields_found)} fields")
        
        # ===== Step 7: 范围校验 =====
        is_valid, error_msg, failed_fields = self._validate_ranges(normalized, percentage_fields_found)
        if not is_valid:
            trace.range_fail_fields = failed_fields
            return normalized, False, error_msg, trace
        
        # 移除元数据字段
        normalized.pop('_metadata', None)
        
        logger.debug(f"Normalization complete: {len(trace.converted_fields)} converted, {len(trace.skipped_fields)} skipped")
        
        return normalized, True, "", trace
    
    def _detect_scale_anomaly(self, data: Dict, input_format: str, fields_to_check: List[str]) -> Tuple[bool, str]:
        """
        检测尺度异常（极端异常值）
        
        Args:
            data: 市场数据字典
            input_format: 输入格式
            fields_to_check: 需要检查的字段列表
        
        Returns:
            (是否有效, 错误信息)
        """
        if input_format == 'percent_point':
            threshold = self.SUSPICIOUS_HIGH_THRESHOLD  # 1000.0
            threshold_display = f"{threshold}%"
        else:
            threshold = self.SUSPICIOUS_HIGH_THRESHOLD / 100.0  # 10.0
            threshold_display = f"{threshold*100}%"
        
        for field in fields_to_check:
            if field in data and data[field] is not None:
                value = abs(data[field])
                
                if value > threshold:
                    if input_format == 'percent_point':
                        display_value = f"{value:.2f}%"
                    else:
                        display_value = f"{value*100:.2f}%"
                    
                    error_msg = (
                        f"指标值异常：{field}={display_value} 超出合理范围 (>{threshold_display})。"
                        f"这可能是数据错误或API异常。"
                    )
                    logger.error(error_msg)
                    return False, error_msg
        
        return True, ""
    
    def _validate_ranges(self, data: Dict, percentage_fields: List[str]) -> Tuple[bool, str, List[str]]:
        """
        验证指标合理性范围（PATCH-1增强：支持字段族）
        
        Args:
            data: 规范化后的数据
            percentage_fields: 百分比字段列表
        
        Returns:
            (是否有效, 错误信息, 失败字段列表)
        """
        failed_fields = []
        
        # 检查百分比字段族
        for field in percentage_fields:
            if field in self.RANGE_LIMITS and field in data and data[field] is not None:
                value = abs(data[field])
                limit = self.RANGE_LIMITS[field]
                if value > limit:
                    failed_fields.append(field)
                    return False, f"{field}超出合理范围：{value*100:.2f}% (>{limit*100}%)", failed_fields
        
        # 检查无量纲字段
        for field, (min_val, max_val) in self.DIMENSIONLESS_FIELDS.items():
            if field in data and data[field] is not None:
                value = data[field]
                if value < min_val or value > max_val:
                    failed_fields.append(field)
                    return False, f"{field}超出范围：{value:.4f} (应在{min_val}到{max_val}之间)", failed_fields
        
        # 检查正数字段
        if 'volume_ratio' in self.RANGE_LIMITS and 'volume_ratio' in data and data['volume_ratio'] is not None:
            min_val, max_val = self.RANGE_LIMITS['volume_ratio']
            value = data['volume_ratio']
            if value < min_val or value > max_val:
                failed_fields.append('volume_ratio')
                return False, f"volume_ratio超出范围：{value:.2f} (应在{min_val}到{max_val}之间)", failed_fields
        
        # 检查价格
        if 'price' in data and data['price'] is not None:
            value = data['price']
            if value <= 0:
                failed_fields.append('price')
                return False, f"price必须为正：{value}", failed_fields
        
        # 检查资金费率
        if 'funding_rate' in data and data['funding_rate'] is not None:
            value = abs(data['funding_rate'])
            limit = self.RANGE_LIMITS.get('funding_rate', 0.01)
            if value > limit:
                failed_fields.append('funding_rate')
                return False, f"funding_rate超出合理范围：{value*100:.4f}% (>{limit*100}%)", failed_fields
        
        return True, "", failed_fields


# ==========================================
# 便捷函数（向后兼容）
# ==========================================

_default_normalizer = MetricsNormalizer(metadata_policy=MetadataPolicy.WARN)


def normalize_metrics(data: Dict) -> Tuple[Dict, bool, str]:
    """
    规范化市场数据指标（便捷函数，向后兼容）
    
    Args:
        data: 原始市场数据字典
    
    Returns:
        (规范化后的数据, 是否有效, 错误信息)
    """
    normalized, is_valid, error_msg, trace = _default_normalizer.normalize(data)
    # 兼容旧接口：不返回 trace
    return normalized, is_valid, error_msg


def normalize_metrics_with_trace(data: Dict) -> Tuple[Dict, bool, str, NormalizationTrace]:
    """
    规范化市场数据指标（新接口，返回 trace）
    
    Args:
        data: 原始市场数据字典
    
    Returns:
        (规范化后的数据, 是否有效, 错误信息, Trace信息)
    """
    return _default_normalizer.normalize(data)
