"""
测试 PR-001, PR-002, PR-003 的功能

- PR-001: 指标口径统一
- PR-002: 数据新鲜度闸门
- PR-003: ReasonTag统一
"""

import pytest
from datetime import datetime, timedelta
from market_state_machine_l1 import L1AdvisoryEngine
from metrics_normalizer import normalize_metrics
from models.reason_tags import ReasonTag
from models.enums import Decision


class TestPR001MetricsNormalization:
    """测试 PR-001: 指标口径统一"""
    
    def test_normalize_percentage_from_points(self):
        """测试百分比点转小数（5.0 → 0.05）"""
        data = {
            'price_change_1h': 5.0,  # 百分比点格式
            'oi_change_1h': 10.0,
            'price': 100,
            'funding_rate': 0.0001,
            'buy_sell_imbalance': 0.5,
            'volume_1h': 1000,
            'volume_24h': 24000
        }
        
        normalized, is_valid, error = normalize_metrics(data)
        
        assert is_valid, f"Normalization failed: {error}"
        assert abs(normalized['price_change_1h'] - 0.05) < 0.0001  # 5.0 → 0.05
        assert abs(normalized['oi_change_1h'] - 0.10) < 0.0001  # 10.0 → 0.10
    
    def test_detect_mixed_scale_anomaly(self):
        """测试检测混合尺度异常"""
        data = {
            'price_change_1h': 0.05,  # 小数格式（正常）
            'oi_change_1h': 50.0,     # 百分比点格式（异常混用）
            'price': 100,
            'funding_rate': 0.0001,
            'buy_sell_imbalance': 0.5,
            'volume_1h': 1000,
            'volume_24h': 24000
        }
        
        normalized, is_valid, error = normalize_metrics(data)
        
        # 应该检测到尺度异常
        assert not is_valid, "Should detect scale anomaly"
        assert "尺度异常" in error or "混用" in error
    
    def test_keep_decimal_format_unchanged(self):
        """测试小数格式保持不变"""
        data = {
            'price_change_1h': 0.05,  # 已经是小数格式
            'oi_change_1h': 0.10,
            'price': 100,
            'funding_rate': 0.0001,
            'buy_sell_imbalance': 0.5,
            'volume_1h': 1000,
            'volume_24h': 24000
        }
        
        normalized, is_valid, error = normalize_metrics(data)
        
        assert is_valid
        assert abs(normalized['price_change_1h'] - 0.05) < 0.0001  # 保持不变
        assert abs(normalized['oi_change_1h'] - 0.10) < 0.0001


class TestPR002DataStaleness:
    """测试 PR-002: 数据新鲜度闸门"""
    
    def test_fresh_data_passes(self):
        """测试新鲜数据通过验证"""
        engine = L1AdvisoryEngine()
        
        data = {
            'price': 100,
            'price_change_1h': 0.05,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            'oi_change_1h': 0.10,
            'source_timestamp': datetime.now(),  # 当前时间
        }
        
        is_valid, normalized, fail_tag = engine._validate_data(data)
        
        assert is_valid, f"Fresh data should pass: {fail_tag}"
        assert fail_tag is None
    
    def test_stale_data_rejected(self):
        """测试过期数据被拒绝"""
        engine = L1AdvisoryEngine()
        
        # 3分钟前的数据（超过120秒阈值）
        stale_time = datetime.now() - timedelta(seconds=180)
        
        data = {
            'price': 100,
            'price_change_1h': 0.05,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            'oi_change_1h': 0.10,
            'source_timestamp': stale_time,
        }
        
        is_valid, normalized, fail_tag = engine._validate_data(data)
        
        assert not is_valid, "Stale data should be rejected"
        assert fail_tag == ReasonTag.DATA_STALE
    
    def test_borderline_staleness(self):
        """测试边界情况（119秒 vs 121秒）"""
        engine = L1AdvisoryEngine()
        
        # 119秒前（应该通过）
        fresh_data = {
            'price': 100,
            'price_change_1h': 0.05,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            'oi_change_1h': 0.10,
            'source_timestamp': datetime.now() - timedelta(seconds=119),
        }
        
        is_valid, _, fail_tag = engine._validate_data(fresh_data)
        assert is_valid, "119s should pass"
        
        # 121秒前（应该拒绝）
        stale_data = fresh_data.copy()
        stale_data['source_timestamp'] = datetime.now() - timedelta(seconds=121)
        
        is_valid, _, fail_tag = engine._validate_data(stale_data)
        assert not is_valid, "121s should be rejected"
        assert fail_tag == ReasonTag.DATA_STALE


class TestPR003ReasonTagUnification:
    """测试 PR-003: ReasonTag统一"""
    
    def test_all_tags_are_enum(self):
        """测试所有标签都是枚举"""
        engine = L1AdvisoryEngine()
        
        # 构造一个会触发各种tag的场景
        data = {
            'price': 100,
            'price_change_1h': 0.06,  # 6% 极端波动
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            'oi_change_1h': 0.10,
        }
        
        result = engine.on_new_tick('BTC', data)
        
        # 所有reason_tags都应该是ReasonTag枚举
        for tag in result.reason_tags:
            assert isinstance(tag, ReasonTag), f"Tag {tag} is not a ReasonTag enum"
    
    def test_reason_tag_values_are_consistent(self):
        """测试ReasonTag值的一致性"""
        # 枚举名和值应该对应
        assert ReasonTag.INVALID_DATA.value == "invalid_data"
        assert ReasonTag.DATA_STALE.value == "data_stale"
        assert ReasonTag.EXTREME_REGIME.value == "extreme_regime"
        assert ReasonTag.LIQUIDATION_PHASE.value == "liquidation_phase"
    
    def test_no_hardcoded_strings(self):
        """测试没有硬编码字符串（通过检查引擎代码）"""
        # 这个测试主要是文档性的，证明我们使用了枚举
        engine = L1AdvisoryEngine()
        
        # 触发INVALID_DATA
        invalid_data = {}
        is_valid, _, fail_tag = engine._validate_data(invalid_data)
        
        assert not is_valid
        assert fail_tag == ReasonTag.INVALID_DATA  # 使用枚举，不是字符串


class TestIntegration:
    """集成测试：三个PR协同工作"""
    
    def test_full_pipeline_with_all_features(self):
        """测试完整管道（规范化+新鲜度+枚举）"""
        engine = L1AdvisoryEngine()
        
        # 使用百分比点格式的数据（会被自动规范化）
        data = {
            'price': 91000,
            'price_change_1h': 2.0,  # 百分比点格式，会被转换为0.02
            'price_change_6h': 5.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.6,
            'funding_rate': 0.0001,
            'oi_change_1h': 8.0,  # 会被转换为0.08
            'oi_change_6h': 15.0,
            'source_timestamp': datetime.now(),  # 新鲜数据
        }
        
        result = engine.on_new_tick('BTC', data)
        
        # 验证结果
        assert result is not None
        assert isinstance(result.decision, Decision)
        
        # 验证所有tags都是枚举
        for tag in result.reason_tags:
            assert isinstance(tag, ReasonTag)
        
        # 验证管道步骤记录
        assert len(engine.last_pipeline_steps) == 8
        assert engine.last_pipeline_steps[0]['name'] == 'validate_data'
        assert engine.last_pipeline_steps[0]['status'] == 'success'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
