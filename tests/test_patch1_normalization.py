"""
PATCH-1: Normalization 字段族全覆盖测试

测试内容：
1. 字段族自动匹配（price_change_*/oi_change_*）
2. percent_point → decimal 转换
3. decimal 输入保持不变
4. 元数据缺失策略（WARN/FAIL_FAST）
5. 范围校验
6. trace 输出完整性
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime
from metrics_normalizer import (
    MetricsNormalizer, 
    normalize_metrics_with_trace, 
    MetadataPolicy,
    NormalizationTrace
)
from market_state_machine_l1 import L1AdvisoryEngine
from models.reason_tags import ReasonTag


class TestFieldFamilyMatching:
    """测试字段族自动匹配"""
    
    @pytest.mark.parametrize("field_name,expected_match", [
        # 价格变化字段族
        ('price_change_5m', True),
        ('price_change_15m', True),
        ('price_change_1h', True),
        ('price_change_4h', True),
        ('price_change_6h', True),
        ('price_change_24h', True),
        # OI变化字段族
        ('oi_change_5m', True),
        ('oi_change_15m', True),
        ('oi_change_1h', True),
        ('oi_change_6h', True),
        # 非百分比字段
        ('price', False),
        ('volume_1h', False),
        ('funding_rate', False),
        ('buy_sell_imbalance', False),
    ])
    def test_percentage_field_pattern(self, field_name, expected_match):
        """测试百分比字段族正则匹配"""
        normalizer = MetricsNormalizer()
        result = normalizer._is_percentage_field(field_name)
        assert result == expected_match, f"{field_name} 匹配结果应为 {expected_match}"


class TestPercentPointToDecimalConversion:
    """测试 percent_point → decimal 转换"""
    
    @pytest.mark.parametrize("input_field,input_value,expected_output", [
        # 常见周期
        ('price_change_5m', 3.0, 0.03),      # 3% → 0.03
        ('price_change_15m', 2.5, 0.025),    # 2.5% → 0.025
        ('price_change_1h', 5.0, 0.05),      # 5% → 0.05
        ('price_change_6h', 10.0, 0.10),     # 10% → 0.10
        # OI 变化
        ('oi_change_15m', 8.0, 0.08),        # 8% → 0.08
        ('oi_change_1h', 15.0, 0.15),        # 15% → 0.15
        ('oi_change_6h', 25.0, 0.25),        # 25% → 0.25
        # 负值
        ('price_change_1h', -3.5, -0.035),   # -3.5% → -0.035
        ('oi_change_1h', -5.0, -0.05),       # -5% → -0.05
        # 零值
        ('price_change_1h', 0.0, 0.0),       # 0% → 0.0
    ])
    def test_convert_percent_point_to_decimal(self, input_field, input_value, expected_output):
        """测试百分比点转小数（参数化）"""
        data = {
            'price': 90000,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            input_field: input_value,
            '_metadata': {'percentage_format': 'percent_point'}
        }
        
        # 填充其他必需字段（避免校验失败）
        for field in ['price_change_1h', 'price_change_6h', 'oi_change_1h', 'oi_change_6h']:
            if field not in data:
                data[field] = 0.0
        
        normalized, is_valid, error, trace = normalize_metrics_with_trace(data)
        
        assert is_valid, f"转换失败: {error}"
        assert abs(normalized[input_field] - expected_output) < 0.000001, \
            f"{input_field}: {input_value} 应转换为 {expected_output}, 实际 {normalized[input_field]}"
        assert input_field in trace.converted_fields, f"{input_field} 应在 converted_fields 中"


class TestDecimalInputPreservation:
    """测试 decimal 输入保持不变"""
    
    def test_decimal_format_unchanged(self):
        """测试小数格式输入保持不变"""
        data = {
            'price': 90000,
            'price_change_5m': 0.015,    # 已是小数
            'price_change_15m': 0.025,
            'price_change_1h': 0.05,
            'price_change_6h': 0.10,
            'oi_change_15m': 0.08,
            'oi_change_1h': 0.10,
            'oi_change_6h': 0.15,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        normalized, is_valid, error, trace = normalize_metrics_with_trace(data)
        
        assert is_valid, f"验证失败: {error}"
        # 所有值应保持不变
        assert normalized['price_change_5m'] == 0.015
        assert normalized['price_change_15m'] == 0.025
        assert normalized['price_change_1h'] == 0.05
        # skipped_fields 应包含所有字段
        assert len(trace.skipped_fields) > 0
        assert 'price_change_5m' in trace.skipped_fields


class TestMetadataMissingPolicy:
    """测试元数据缺失策略"""
    
    def test_warn_policy_default(self):
        """测试 WARN 策略（默认）：警告并假设 percent_point"""
        data = {
            'price': 90000,
            'price_change_1h': 5.0,
            'price_change_6h': 10.0,
            'oi_change_1h': 8.0,
            'oi_change_6h': 15.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            # ❌ 缺少 _metadata
        }
        
        normalized, is_valid, error, trace = normalize_metrics_with_trace(data)
        
        assert is_valid, "WARN 策略应成功"
        assert trace.input_percentage_format == 'percent_point'
        assert trace.metadata_policy_applied == 'WARN_ASSUME_PERCENT_POINT'
        # 应该进行了转换
        assert abs(normalized['price_change_1h'] - 0.05) < 0.0001
    
    def test_fail_fast_policy(self):
        """测试 FAIL_FAST 策略：元数据缺失时拒绝"""
        normalizer = MetricsNormalizer(metadata_policy=MetadataPolicy.FAIL_FAST)
        
        data = {
            'price': 90000,
            'price_change_1h': 5.0,
            'price_change_6h': 10.0,
            'oi_change_1h': 8.0,
            'oi_change_6h': 15.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            # ❌ 缺少 _metadata
        }
        
        normalized, is_valid, error, trace = normalizer.normalize(data)
        
        assert not is_valid, "FAIL_FAST 应拒绝无元数据的输入"
        assert "FAIL_FAST" in error
        assert trace.metadata_policy_applied == 'FAIL_FAST'


class TestRangeValidation:
    """测试范围校验"""
    
    @pytest.mark.parametrize("field,bad_value,error_substring", [
        ('price_change_1h', 0.25, "20"),       # 超过20%（匹配 20.0% 或 20%）
        ('price_change_6h', 0.60, "50"),       # 超过50%
        ('oi_change_1h', 1.5, "100"),          # 超过100%
        ('buy_sell_imbalance', 1.5, "-1"),     # 超出 [-1, 1]（匹配 -1.0 或 -1）
        ('buy_sell_imbalance', -1.5, "-1"),
        ('funding_rate', 0.015, "1."),         # 超过1%（匹配 1.0% 或 1%）
    ])
    def test_out_of_range_values(self, field, bad_value, error_substring):
        """测试超出范围的值被拒绝（参数化）"""
        data = {
            'price': 90000,
            'price_change_1h': 0.05,
            'price_change_6h': 0.10,
            'oi_change_1h': 0.08,
            'oi_change_6h': 0.15,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'},
            field: bad_value  # 覆盖为异常值
        }
        
        normalized, is_valid, error, trace = normalize_metrics_with_trace(data)
        
        assert not is_valid, f"{field}={bad_value} 应被拒绝"
        assert error_substring in error, f"错误信息应包含 '{error_substring}'"
        assert field in trace.range_fail_fields


class TestTraceCompleteness:
    """测试 trace 输出完整性"""
    
    def test_trace_contains_all_fields(self):
        """测试 trace 包含所有必需字段"""
        data = {
            'price': 90000,
            'price_change_5m': 1.5,     # percent_point
            'price_change_15m': 2.0,
            'price_change_1h': 3.0,
            'price_change_6h': 8.0,
            'oi_change_15m': 5.0,
            'oi_change_1h': 10.0,
            'oi_change_6h': 20.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'percent_point'}
        }
        
        normalized, is_valid, error, trace = normalize_metrics_with_trace(data)
        
        assert is_valid
        
        # 验证 trace 结构
        assert trace.input_percentage_format == 'percent_point'
        assert len(trace.converted_fields) == 7  # 7个字段被转换
        assert 'price_change_5m' in trace.converted_fields
        assert 'price_change_15m' in trace.converted_fields
        assert 'price_change_1h' in trace.converted_fields
        assert 'oi_change_15m' in trace.converted_fields
        
        # 验证字段族匹配结果
        assert 'percentage_fields' in trace.field_family_matched
        assert len(trace.field_family_matched['percentage_fields']) == 7


class TestL1EngineIntegration:
    """测试与 L1Engine 的集成"""
    
    def test_engine_pipeline_contains_trace(self):
        """测试引擎管道步骤包含 normalization_trace"""
        engine = L1AdvisoryEngine()
        
        data = {
            'price': 90000,
            'price_change_1h': 3.0,   # percent_point
            'price_change_6h': 8.0,
            'oi_change_1h': 5.0,
            'oi_change_6h': 12.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'percent_point'}
        }
        
        result = engine.on_new_tick('BTC', data)
        
        # 验证管道步骤包含 normalization_trace
        assert len(engine.last_pipeline_steps) > 0
        step1 = engine.last_pipeline_steps[0]
        assert step1['name'] == 'validate_data'
        assert 'normalization_trace' in step1
        assert step1['normalization_trace']['input_percentage_format'] == 'percent_point'
        assert len(step1['normalization_trace']['converted_fields']) > 0
    
    def test_engine_with_decimal_input(self):
        """测试引擎使用 decimal 输入"""
        engine = L1AdvisoryEngine()
        
        data = {
            'price': 90000,
            'price_change_1h': 0.03,
            'price_change_6h': 0.08,
            'oi_change_1h': 0.05,
            'oi_change_6h': 0.12,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick('BTC', data)
        
        # 验证 trace
        step1 = engine.last_pipeline_steps[0]
        assert step1['normalization_trace']['input_percentage_format'] == 'decimal'
        assert len(step1['normalization_trace']['skipped_fields']) > 0


class TestNewFieldAutomatic:
    """测试新增字段自动纳入规范化"""
    
    def test_new_price_change_field_auto_converted(self):
        """测试任意新增 price_change_X 字段自动转换"""
        data = {
            'price': 90000,
            'price_change_1h': 3.0,
            'price_change_6h': 8.0,
            'price_change_30m': 2.0,     # 新增字段
            'price_change_2h': 4.0,      # 新增字段
            'oi_change_1h': 5.0,
            'oi_change_6h': 12.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'percent_point'}
        }
        
        normalized, is_valid, error, trace = normalize_metrics_with_trace(data)
        
        assert is_valid
        # 新增字段应自动被转换
        assert abs(normalized['price_change_30m'] - 0.02) < 0.0001
        assert abs(normalized['price_change_2h'] - 0.04) < 0.0001
        assert 'price_change_30m' in trace.converted_fields
        assert 'price_change_2h' in trace.converted_fields
    
    def test_new_oi_change_field_auto_converted(self):
        """测试任意新增 oi_change_X 字段自动转换"""
        data = {
            'price': 90000,
            'price_change_1h': 3.0,
            'price_change_6h': 8.0,
            'oi_change_1h': 5.0,
            'oi_change_6h': 12.0,
            'oi_change_30m': 3.0,        # 新增字段
            'oi_change_4h': 10.0,        # 新增字段
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'percent_point'}
        }
        
        normalized, is_valid, error, trace = normalize_metrics_with_trace(data)
        
        assert is_valid
        assert abs(normalized['oi_change_30m'] - 0.03) < 0.0001
        assert abs(normalized['oi_change_4h'] - 0.10) < 0.0001
        assert 'oi_change_30m' in trace.converted_fields


class TestScaleAnomalyDetection:
    """测试尺度异常检测"""
    
    def test_extreme_value_rejected(self):
        """测试极端异常值被拒绝（>1000%）"""
        data = {
            'price': 90000,
            'price_change_1h': 1500.0,  # 1500% 异常
            'price_change_6h': 8.0,
            'oi_change_1h': 5.0,
            'oi_change_6h': 12.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'percent_point'}
        }
        
        normalized, is_valid, error, trace = normalize_metrics_with_trace(data)
        
        assert not is_valid
        assert "异常" in error or "超出" in error


class TestBackwardCompatibility:
    """测试向后兼容性"""
    
    def test_old_api_still_works(self):
        """测试旧的 normalize_metrics 函数仍然可用"""
        from metrics_normalizer import normalize_metrics
        
        data = {
            'price': 90000,
            'price_change_1h': 3.0,
            'price_change_6h': 8.0,
            'oi_change_1h': 5.0,
            'oi_change_6h': 12.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'taker_imbalance_1h': 0.5,
            'funding_rate': 0.0001,
        }
        
        # 旧接口不返回 trace
        normalized, is_valid, error = normalize_metrics(data)
        
        assert is_valid
        assert abs(normalized['price_change_1h'] - 0.03) < 0.0001


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
