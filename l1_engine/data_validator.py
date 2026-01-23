"""
L1 Advisory Engine - 数据验证模块

职责：
1. 数据完整性验证
2. 指标规范化
3. Lookback Coverage 检查
4. 字段分级检查（核心/可选）
"""

from typing import Dict, Tuple, Optional, List
from datetime import datetime
from models.reason_tags import ReasonTag
from metrics_normalizer import normalize_metrics_with_trace
import logging

logger = logging.getLogger(__name__)


class DataValidator:
    """数据验证器"""
    
    # 核心必需字段（最小不可缺集合）
    CORE_REQUIRED_FIELDS = [
        'price',
        'volume_24h',
        'funding_rate'
    ]
    
    # 短期可选字段（5m/15m）- 缺失影响short_term结论
    SHORT_TERM_OPTIONAL_FIELDS = [
        'price_change_5m',
        'price_change_15m',
        'oi_change_5m',
        'oi_change_15m',
        'taker_imbalance_5m',
        'taker_imbalance_15m',
        'volume_ratio_5m',
        'volume_ratio_15m'
    ]
    
    # 中期可选字段（1h/6h）- 缺失影响medium_term结论
    MEDIUM_TERM_OPTIONAL_FIELDS = [
        'price_change_1h',
        'price_change_6h',
        'oi_change_1h',
        'oi_change_6h',
        'taker_imbalance_1h',
        'volume_1h'
    ]
    
    def __init__(self, config: Dict):
        """
        初始化数据验证器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.thresholds = self._flatten_thresholds(config)
    
    def validate_data(self, data: Dict) -> Tuple[bool, Dict, Optional[ReasonTag], Optional[dict]]:
        """
        验证输入数据的完整性和有效性
        
        包含：
        1. 必需字段检查
        2. 指标口径规范化（百分比统一为小数格式）
        3. 异常尺度检测（防止混用）
        4. 数据新鲜度检查
        
        Args:
            data: 市场数据字典
        
        Returns:
            (是否有效, 规范化后的数据, 失败原因tag, normalization_trace字典)
        """
        # 1. 检查核心必需字段（最小不可缺集合）
        missing_core = [f for f in self.CORE_REQUIRED_FIELDS if f not in data or data[f] is None]
        if missing_core:
            logger.error(f"Missing core required fields: {missing_core}")
            return False, data, ReasonTag.INVALID_DATA, None
        
        # 2. 检查短期可选字段（缺失标记但不硬失败）
        missing_short_term = [f for f in self.SHORT_TERM_OPTIONAL_FIELDS if f not in data or data[f] is None]
        
        # 3. 检查中期可选字段（缺失标记但不硬失败）
        missing_medium_term = [f for f in self.MEDIUM_TERM_OPTIONAL_FIELDS if f not in data or data[f] is None]
        
        # 4. 记录缺失情况（用于后续决策）
        data['_field_gaps'] = {
            'short_term': missing_short_term,
            'medium_term': missing_medium_term
        }
        
        # 5. 日志输出
        if missing_short_term:
            logger.info(f"Short-term optional fields missing: {missing_short_term}")
        if missing_medium_term:
            logger.info(f"Medium-term optional fields missing: {missing_medium_term}")
        
        # 数据新鲜度检查
        if 'timestamp' in data or 'source_timestamp' in data:
            data_time = data.get('source_timestamp') or data.get('timestamp')
            if data_time is not None:
                # 计算数据年龄，统一转换为datetime对象
                if isinstance(data_time, str):
                    data_time = datetime.fromisoformat(data_time)
                elif isinstance(data_time, int):
                    # 毫秒时间戳转换为datetime
                    data_time = datetime.fromtimestamp(data_time / 1000)
                elif not isinstance(data_time, datetime):
                    # 其他类型尝试转换
                    try:
                        data_time = datetime.fromtimestamp(int(data_time) / 1000)
                    except:
                        pass  # 无法转换，跳过时效性检查
                
                if isinstance(data_time, datetime):
                    staleness_seconds = (datetime.now() - data_time).total_seconds()
                else:
                    staleness_seconds = 0  # 无效时间，不检查时效性
                max_staleness = self.thresholds.get('data_max_staleness_seconds', 120)
                
                if staleness_seconds > max_staleness:
                    logger.warning(
                        f"Data is stale: {staleness_seconds:.1f}s old "
                        f"(max: {max_staleness}s)"
                    )
                    return False, data, ReasonTag.DATA_STALE, None
        
        # 保存 coverage（normalize 会移除 _metadata）
        lookback_coverage = data.get('_metadata', {}).get('lookback_coverage')
        
        # 指标口径规范化
        normalized_data, is_valid, error_msg, norm_trace = normalize_metrics_with_trace(data)
        if not is_valid:
            logger.error(f"Metrics normalization failed: {error_msg}")
            return False, data, ReasonTag.INVALID_DATA, norm_trace.to_dict()
        
        # 恢复 coverage（用于后续检查）
        if lookback_coverage:
            normalized_data['_metadata'] = {'lookback_coverage': lookback_coverage}
        
        # 规范化成功，记录 trace
        logger.debug(
            f"Normalization trace: format={norm_trace.input_percentage_format}, "
            f"converted={len(norm_trace.converted_fields)}, "
            f"skipped={len(norm_trace.skipped_fields)}"
        )
        
        # 基础异常值检查（保留，作为双重保护）
        taker_imb_1h = normalized_data.get('taker_imbalance_1h', 0)
        if taker_imb_1h < -1 or taker_imb_1h > 1:
            logger.error(f"Invalid taker_imbalance_1h: {taker_imb_1h}")
            return False, normalized_data, ReasonTag.INVALID_DATA, norm_trace.to_dict()
        
        if normalized_data['price'] <= 0:
            logger.error(f"Invalid price: {normalized_data['price']}")
            return False, normalized_data, ReasonTag.INVALID_DATA, norm_trace.to_dict()
        
        return True, normalized_data, None, norm_trace.to_dict()
    
    def check_lookback_coverage(self, data: Dict) -> Tuple[bool, List[ReasonTag]]:
        """
        检查 lookback coverage
        
        从 _metadata.lookback_coverage 读取各窗口的 lookback 结果，
        检查关键窗口是否存在数据缺口。
        
        Args:
            data: 市场数据字典（包含 _metadata）
        
        Returns:
            (是否通过检查, 失败原因tags列表)
        """
        metadata = data.get('_metadata', {})
        coverage = metadata.get('lookback_coverage', {})
        
        if not coverage or not coverage.get('has_data'):
            # 没有 coverage 信息（可能是旧版数据源），不检查
            logger.debug("No lookback_coverage in metadata, skipping coverage check")
            return True, []
        
        windows = coverage.get('windows', {})
        failed_tags = []
        
        # 检查各窗口
        window_tag_map = {
            '5m': ReasonTag.DATA_GAP_5M,
            '15m': ReasonTag.DATA_GAP_15M,
            '1h': ReasonTag.DATA_GAP_1H,
            '6h': ReasonTag.DATA_GAP_6H,
        }
        
        for window_key, tag in window_tag_map.items():
            window_info = windows.get(window_key, {})
            if not window_info.get('is_valid', True):  # 默认 True 避免误报
                error_reason = window_info.get('error_reason', 'UNKNOWN')
                gap_seconds = window_info.get('gap_seconds')
                logger.warning(
                    f"Lookback failed for {window_key}: {error_reason} "
                    f"(gap={gap_seconds}s)" if gap_seconds else f"Lookback failed for {window_key}: {error_reason}"
                )
                failed_tags.append(tag)
        
        # 如果有任何窗口失败，返回失败
        if failed_tags:
            return False, failed_tags
        
        return True, []
    
    def _flatten_thresholds(self, config: dict) -> dict:
        """提取数据质量相关阈值"""
        flat = {}
        dq = config.get('data_quality', {})
        flat['data_max_staleness_seconds'] = dq.get('max_staleness_seconds', 120)
        return flat
