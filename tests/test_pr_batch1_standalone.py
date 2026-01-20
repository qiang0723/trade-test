#!/usr/bin/env python3
"""
独立测试脚本 - PR-001/002/003
不依赖pytest，直接运行
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from market_state_machine_l1 import L1AdvisoryEngine
from metrics_normalizer import normalize_metrics
from models.reason_tags import ReasonTag
from models.enums import Decision


class TestRunner:
    """简单的测试运行器"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def test(self, name, func):
        """运行单个测试"""
        try:
            func()
            self.passed += 1
            print(f"✅ {name}")
        except AssertionError as e:
            self.failed += 1
            error_msg = f"❌ {name}: {str(e)}"
            self.errors.append(error_msg)
            print(error_msg)
        except Exception as e:
            self.failed += 1
            error_msg = f"💥 {name}: {type(e).__name__}: {str(e)}"
            self.errors.append(error_msg)
            print(error_msg)
    
    def summary(self):
        """打印测试摘要"""
        total = self.passed + self.failed
        print("\n" + "="*60)
        print(f"测试结果: {self.passed}/{total} 通过")
        if self.failed > 0:
            print(f"\n失败的测试:")
            for error in self.errors:
                print(f"  {error}")
        print("="*60)
        return self.failed == 0


def main():
    runner = TestRunner()
    
    print("="*60)
    print("测试 PR-001: 指标口径统一")
    print("="*60)
    
    def test_normalize_percentage_from_points():
        """测试百分比点转小数（5.0 → 0.05）"""
        data = {
            'price_change_1h': 5.0,
            'oi_change_1h': 10.0,
            'price': 100,
            'funding_rate': 0.0001,
            'buy_sell_imbalance': 0.5,
            'volume_1h': 1000,
            'volume_24h': 24000
        }
        
        normalized, is_valid, error = normalize_metrics(data)
        
        assert is_valid, f"规范化失败: {error}"
        assert abs(normalized['price_change_1h'] - 0.05) < 0.0001, \
            f"期望 0.05, 得到 {normalized['price_change_1h']}"
        assert abs(normalized['oi_change_1h'] - 0.10) < 0.0001, \
            f"期望 0.10, 得到 {normalized['oi_change_1h']}"
    
    def test_detect_mixed_scale():
        """测试检测混合尺度异常"""
        data = {
            'price_change_1h': 0.05,  # 小数
            'oi_change_1h': 50.0,     # 百分比点（异常）
            'price': 100,
            'funding_rate': 0.0001,
            'buy_sell_imbalance': 0.5,
            'volume_1h': 1000,
            'volume_24h': 24000
        }
        
        normalized, is_valid, error = normalize_metrics(data)
        
        assert not is_valid, "应该检测到尺度异常"
        assert "尺度" in error or "混用" in error, f"错误信息应包含'尺度'或'混用': {error}"
    
    def test_keep_decimal_unchanged():
        """测试小数格式保持不变"""
        data = {
            'price_change_1h': 0.05,
            'oi_change_1h': 0.10,
            'price': 100,
            'funding_rate': 0.0001,
            'buy_sell_imbalance': 0.5,
            'volume_1h': 1000,
            'volume_24h': 24000
        }
        
        normalized, is_valid, error = normalize_metrics(data)
        
        assert is_valid, f"验证失败: {error}"
        assert abs(normalized['price_change_1h'] - 0.05) < 0.0001
        assert abs(normalized['oi_change_1h'] - 0.10) < 0.0001
    
    runner.test("PR-001: 百分比点转小数", test_normalize_percentage_from_points)
    runner.test("PR-001: 检测混合尺度", test_detect_mixed_scale)
    runner.test("PR-001: 小数格式保持不变", test_keep_decimal_unchanged)
    
    print("\n" + "="*60)
    print("测试 PR-002: 数据新鲜度闸门")
    print("="*60)
    
    def test_fresh_data_passes():
        """测试新鲜数据通过"""
        engine = L1AdvisoryEngine()
        
        data = {
            'price': 100,
            'price_change_1h': 0.05,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            'oi_change_1h': 0.10,
            'source_timestamp': datetime.now(),
        }
        
        is_valid, normalized, fail_tag = engine._validate_data(data)
        
        assert is_valid, f"新鲜数据应通过: {fail_tag}"
        assert fail_tag is None
    
    def test_stale_data_rejected():
        """测试过期数据被拒绝"""
        engine = L1AdvisoryEngine()
        
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
        
        assert not is_valid, "过期数据应被拒绝"
        assert fail_tag == ReasonTag.DATA_STALE, f"期望 DATA_STALE, 得到 {fail_tag}"
    
    def test_borderline_staleness():
        """测试边界情况（119秒 vs 121秒）"""
        engine = L1AdvisoryEngine()
        
        # 119秒前（应通过）
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
        assert is_valid, f"119秒应通过, 得到: {fail_tag}"
        
        # 121秒前（应拒绝）
        stale_data = fresh_data.copy()
        stale_data['source_timestamp'] = datetime.now() - timedelta(seconds=121)
        
        is_valid, _, fail_tag = engine._validate_data(stale_data)
        assert not is_valid, "121秒应被拒绝"
        assert fail_tag == ReasonTag.DATA_STALE
    
    runner.test("PR-002: 新鲜数据通过", test_fresh_data_passes)
    runner.test("PR-002: 过期数据拒绝", test_stale_data_rejected)
    runner.test("PR-002: 边界测试", test_borderline_staleness)
    
    print("\n" + "="*60)
    print("测试 PR-003: ReasonTag统一")
    print("="*60)
    
    def test_reason_tag_consistency():
        """测试ReasonTag枚举一致性"""
        assert ReasonTag.INVALID_DATA.value == "invalid_data"
        assert ReasonTag.DATA_STALE.value == "data_stale"
        assert ReasonTag.EXTREME_REGIME.value == "extreme_regime"
        assert ReasonTag.LIQUIDATION_PHASE.value == "liquidation_phase"
    
    def test_all_tags_are_enum():
        """测试所有标签都是枚举"""
        engine = L1AdvisoryEngine()
        
        data = {
            'price': 100,
            'price_change_1h': 0.06,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            'oi_change_1h': 0.10,
        }
        
        result = engine.on_new_tick('BTC', data)
        
        for tag in result.reason_tags:
            assert isinstance(tag, ReasonTag), \
                f"标签 {tag} 不是 ReasonTag 枚举"
    
    runner.test("PR-003: 枚举值一致性", test_reason_tag_consistency)
    runner.test("PR-003: 所有标签都是枚举", test_all_tags_are_enum)
    
    print("\n" + "="*60)
    print("集成测试")
    print("="*60)
    
    def test_full_pipeline():
        """测试完整管道"""
        engine = L1AdvisoryEngine()
        
        data = {
            'price': 91000,
            'price_change_1h': 2.0,  # 百分比点，会被转换
            'price_change_6h': 5.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.6,
            'funding_rate': 0.0001,
            'oi_change_1h': 8.0,
            'oi_change_6h': 15.0,
            'source_timestamp': datetime.now(),
        }
        
        result = engine.on_new_tick('BTC', data)
        
        assert result is not None
        assert isinstance(result.decision, Decision)
        
        for tag in result.reason_tags:
            assert isinstance(tag, ReasonTag)
        
        assert len(engine.last_pipeline_steps) == 8
        assert engine.last_pipeline_steps[0]['name'] == 'validate_data'
        assert engine.last_pipeline_steps[0]['status'] == 'success'
    
    runner.test("集成测试: 完整管道", test_full_pipeline)
    
    # 打印摘要
    success = runner.summary()
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
