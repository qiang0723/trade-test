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
    
    # ========================================
    # P2-1: 数据质量评分系统
    # ========================================
    
    def calculate_quality_score(self, data: Dict) -> Dict:
        """
        计算数据质量评分（P2-1优化）
        
        评分维度：
        1. 字段完整性（40%）：核心+可选字段覆盖率
        2. 数据新鲜度（30%）：数据延迟程度
        3. Lookback覆盖（30%）：历史数据窗口完整性
        
        Args:
            data: 规范化后的市场数据
        
        Returns:
            质量评分详情字典：
            {
                'total_score': 0-100,
                'field_score': 0-100,
                'freshness_score': 0-100,
                'coverage_score': 0-100,
                'confidence_cap': Confidence枚举值字符串,
                'details': {...}
            }
        """
        from models.enums import Confidence
        
        details = {}
        
        # 1. 字段完整性评分（40分）
        field_gaps = data.get('_field_gaps', {'short_term': [], 'medium_term': []})
        
        # 核心字段满分（已通过验证）
        core_score = 100
        
        # 短期字段评分
        short_term_missing = len(field_gaps.get('short_term', []))
        short_term_total = len(self.SHORT_TERM_OPTIONAL_FIELDS)
        short_term_score = max(0, 100 - (short_term_missing / short_term_total * 100)) if short_term_total > 0 else 100
        
        # 中期字段评分
        medium_term_missing = len(field_gaps.get('medium_term', []))
        medium_term_total = len(self.MEDIUM_TERM_OPTIONAL_FIELDS)
        medium_term_score = max(0, 100 - (medium_term_missing / medium_term_total * 100)) if medium_term_total > 0 else 100
        
        # 综合字段评分（核心50%，短期25%，中期25%）
        field_score = core_score * 0.5 + short_term_score * 0.25 + medium_term_score * 0.25
        
        details['field'] = {
            'core_score': core_score,
            'short_term_score': round(short_term_score, 1),
            'medium_term_score': round(medium_term_score, 1),
            'short_term_missing': short_term_missing,
            'medium_term_missing': medium_term_missing
        }
        
        # 2. 数据新鲜度评分（30分）
        freshness_score = 100
        staleness_seconds = 0
        
        if 'timestamp' in data or 'source_timestamp' in data:
            data_time = data.get('source_timestamp') or data.get('timestamp')
            if data_time is not None:
                try:
                    if isinstance(data_time, str):
                        data_time = datetime.fromisoformat(data_time)
                    elif isinstance(data_time, int):
                        data_time = datetime.fromtimestamp(data_time / 1000)
                    elif isinstance(data_time, datetime):
                        pass
                    else:
                        data_time = datetime.fromtimestamp(int(data_time) / 1000)
                    
                    staleness_seconds = (datetime.now() - data_time).total_seconds()
                    max_staleness = self.thresholds.get('data_max_staleness_seconds', 120)
                    
                    # 线性衰减：0秒=100分，max_staleness秒=0分
                    freshness_score = max(0, 100 - (staleness_seconds / max_staleness * 100))
                except:
                    pass  # 无法解析时间，使用默认满分
        
        details['freshness'] = {
            'staleness_seconds': round(staleness_seconds, 1),
            'score': round(freshness_score, 1)
        }
        
        # 3. Lookback覆盖评分（30分）
        coverage_score = 100
        metadata = data.get('_metadata', {})
        coverage = metadata.get('lookback_coverage', {})
        
        if coverage and coverage.get('has_data'):
            windows = coverage.get('windows', {})
            window_scores = []
            
            # 各窗口权重：1h最重要
            window_weights = {'1h': 0.4, '15m': 0.3, '5m': 0.2, '6h': 0.1}
            
            for window_key, weight in window_weights.items():
                window_info = windows.get(window_key, {})
                is_valid = window_info.get('is_valid', True)
                if is_valid:
                    window_scores.append(100 * weight)
                else:
                    window_scores.append(0)
            
            coverage_score = sum(window_scores)
        
        details['coverage'] = {
            'score': round(coverage_score, 1),
            'has_metadata': bool(coverage)
        }
        
        # 4. 计算总分（加权平均）
        total_score = field_score * 0.4 + freshness_score * 0.3 + coverage_score * 0.3
        
        # 5. 确定置信度上限
        # 规则：
        # - 90+ 分：不限制（ULTRA）
        # - 70-89 分：最高 HIGH
        # - 50-69 分：最高 MEDIUM
        # - <50 分：最高 LOW
        if total_score >= 90:
            confidence_cap = Confidence.ULTRA
        elif total_score >= 70:
            confidence_cap = Confidence.HIGH
        elif total_score >= 50:
            confidence_cap = Confidence.MEDIUM
        else:
            confidence_cap = Confidence.LOW
        
        logger.info(f"Data quality score: {total_score:.1f}/100 (cap={confidence_cap.value})")
        
        return {
            'total_score': round(total_score, 1),
            'field_score': round(field_score, 1),
            'freshness_score': round(freshness_score, 1),
            'coverage_score': round(coverage_score, 1),
            'confidence_cap': confidence_cap.value,
            'details': details
        }
