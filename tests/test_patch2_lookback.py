"""
PATCH-2: Cache Lookback Floor + Gap Guardrail 测试

测试内容：
1. Floor查找（禁止未来点）
2. Gap tolerance检查
3. Coverage输出完整性
4. L1Engine集成（ReasonTag）
5. 稀疏数据场景
6. 回测与线上同构
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta
from data_cache import MarketDataCache, LookbackResult, TickData
from market_state_machine_l1 import L1AdvisoryEngine
from models.reason_tags import ReasonTag
from models.enums import Decision


class TestFloorLookup:
    """测试 floor 查找（只允许历史点）"""
    
    def test_floor_lookup_no_future_points(self):
        """测试不会选中未来点"""
        cache = MarketDataCache()
        
        # 存储一些数据
        base_time = datetime.now()
        for i in range(-5, 6):  # -5到+5分钟
            timestamp = base_time + timedelta(minutes=i)
            data = {'price': 90000 + i * 100, 'volume': 1000, 'open_interest': 100000}
            cache.store_tick('BTC', data, timestamp)
        
        # 目标时间：当前时间（base_time）
        # 应该只选中 <= base_time 的点，即 base_time（0分钟）
        result = cache._find_floor_tick('BTC', base_time, tolerance_seconds=300)
        
        assert result.is_valid
        assert result.tick is not None
        # 应该选中 base_time（gap=0）
        assert result.gap_seconds == 0
        assert result.actual_time == base_time
    
    def test_floor_lookup_closest_historical(self):
        """测试选择最接近的历史点"""
        cache = MarketDataCache()
        
        base_time = datetime.now()
        # 存储数据：-10, -5, -2分钟
        for offset in [-10, -5, -2]:
            timestamp = base_time + timedelta(minutes=offset)
            data = {'price': 90000, 'volume': 1000, 'open_interest': 100000}
            cache.store_tick('BTC', data, timestamp)
        
        # 目标时间：base_time（0分钟）
        # 应该选中 -2分钟（最接近且 <= 目标）
        result = cache._find_floor_tick('BTC', base_time, tolerance_seconds=600)
        
        assert result.is_valid
        assert result.gap_seconds == pytest.approx(120, abs=1)  # 2分钟 = 120秒
        assert result.actual_time == base_time + timedelta(minutes=-2)


class TestGapTolerance:
    """测试 gap tolerance 检查"""
    
    @pytest.mark.parametrize("gap_minutes,tolerance_seconds,should_pass", [
        (1, 90, True),      # gap=60s < tolerance=90s，通过
        (2, 90, False),     # gap=120s > tolerance=90s，失败
        (5, 300, True),     # gap=300s = tolerance=300s，边界通过
        (6, 300, False),    # gap=360s > tolerance=300s，失败
    ])
    def test_gap_tolerance_boundary(self, gap_minutes, tolerance_seconds, should_pass):
        """测试 gap tolerance 边界条件（参数化）"""
        cache = MarketDataCache()
        
        base_time = datetime.now()
        # 存储一个历史点（gap_minutes 之前）
        past_time = base_time - timedelta(minutes=gap_minutes)
        data = {'price': 90000, 'volume': 1000, 'open_interest': 100000}
        cache.store_tick('BTC', data, past_time)
        
        # 查找 base_time
        result = cache._find_floor_tick('BTC', base_time, tolerance_seconds)
        
        if should_pass:
            assert result.is_valid, f"应该通过：gap={gap_minutes*60}s, tolerance={tolerance_seconds}s"
            assert result.tick is not None
        else:
            assert not result.is_valid, f"应该失败：gap={gap_minutes*60}s, tolerance={tolerance_seconds}s"
            assert result.tick is None  # gap 超出范围，不返回 tick
            assert 'GAP_TOO_LARGE' in result.error_reason
    
    def test_no_historical_data(self):
        """测试无历史数据的情况"""
        cache = MarketDataCache()
        
        base_time = datetime.now()
        # 只存储未来点
        future_time = base_time + timedelta(minutes=5)
        data = {'price': 90000, 'volume': 1000, 'open_interest': 100000}
        cache.store_tick('BTC', data, future_time)
        
        # 查找 base_time（没有 <= base_time 的点）
        result = cache._find_floor_tick('BTC', base_time, tolerance_seconds=300)
        
        assert not result.is_valid
        assert result.tick is None
        assert result.error_reason == 'NO_HISTORICAL_DATA'


class TestCoverageOutput:
    """测试 coverage 输出完整性"""
    
    def test_coverage_contains_all_windows(self):
        """测试 coverage 包含所有窗口"""
        cache = MarketDataCache()
        
        base_time = datetime.now()
        # 存储6小时的数据（每5分钟一个点）
        for i in range(0, 360, 5):  # 0到360分钟，每5分钟
            timestamp = base_time - timedelta(minutes=i)
            data = {'price': 90000 + i, 'volume': 1000, 'open_interest': 100000}
            cache.store_tick('BTC', data, timestamp)
        
        # 获取 coverage
        coverage = cache.get_lookback_coverage('BTC')
        
        assert coverage['has_data']
        assert 'windows' in coverage
        
        # 应该包含所有窗口
        expected_windows = ['5m', '15m', '1h', '6h']
        for window in expected_windows:
            assert window in coverage['windows']
            window_info = coverage['windows'][window]
            assert 'target_time' in window_info
            assert 'actual_time' in window_info
            assert 'gap_seconds' in window_info
            assert 'is_valid' in window_info
    
    def test_coverage_with_gaps(self):
        """测试有缺口的 coverage"""
        cache = MarketDataCache()
        
        base_time = datetime.now()
        # 只存储最近30分钟的数据（缺少1h/6h）
        # 注意：必须从旧到新存储，确保最新的在deque末尾
        for i in reversed(range(0, 30, 5)):  # 从25分钟前到0（即现在）
            timestamp = base_time - timedelta(minutes=i)
            data = {'price': 90000, 'volume': 1000, 'open_interest': 100000}
            cache.store_tick('BTC', data, timestamp)
        
        coverage = cache.get_lookback_coverage('BTC')
        
        # 5m/15m 应该有效
        assert coverage['windows']['5m']['is_valid']
        assert coverage['windows']['15m']['is_valid']
        
        # 1h 应该无效（最早点是30分钟前，gap=30分钟，超过tolerance=10分钟）
        # 但由于tolerance=600s（10分钟），30分钟（1800s）超过，所以应该无效
        # 修正预期：实际上最早点是25分钟前（0,5,10,15,20,25），目标是60分钟前
        # gap = 60-25 = 35分钟 = 2100s > 600s，确实无效
        assert not coverage['windows']['1h']['is_valid'], \
            f"1h window should be invalid, got: {coverage['windows']['1h']}"
        
        # 6h 应该无效
        assert not coverage['windows']['6h']['is_valid'], \
            f"6h window should be invalid, got: {coverage['windows']['6h']}"


class TestPriceChangeWithFloor:
    """测试价格变化计算（使用 floor 查找）"""
    
    def test_price_change_with_valid_gap(self):
        """测试 gap 在容忍范围内的价格变化计算"""
        cache = MarketDataCache()
        
        base_time = datetime.now()
        # 存储当前和1小时前的数据
        past_data = {'price': 90000, 'volume': 1000, 'open_interest': 100000}
        current_data = {'price': 92700, 'volume': 1100, 'open_interest': 101000}
        
        cache.store_tick('BTC', past_data, base_time - timedelta(hours=1))
        cache.store_tick('BTC', current_data, base_time)
        
        # 计算1小时价格变化率
        change = cache.calculate_price_change('BTC', hours=1.0)
        
        assert change is not None
        # (92700 - 90000) / 90000 * 100 = 3.0%
        assert abs(change - 3.0) < 0.01
    
    def test_price_change_with_large_gap(self):
        """测试 gap 过大时返回 None"""
        cache = MarketDataCache()
        
        base_time = datetime.now()
        # 只存储当前数据，没有1小时前的数据
        current_data = {'price': 92700, 'volume': 1100, 'open_interest': 101000}
        cache.store_tick('BTC', current_data, base_time)
        
        # 计算1小时价格变化率（应该失败）
        change = cache.calculate_price_change('BTC', hours=1.0)
        
        assert change is None


class TestL1EngineIntegration:
    """测试与 L1Engine 的集成"""
    
    def test_engine_coverage_check_pass(self):
        """测试引擎 coverage 检查通过"""
        engine = L1AdvisoryEngine()
        cache = MarketDataCache()
        
        # 构造带 coverage 的数据（all valid）
        data = {
            'price': 90000,
            'price_change_1h': 3.0,
            'price_change_6h': 8.0,
            'oi_change_1h': 5.0,
            'oi_change_6h': 12.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {
                'percentage_format': 'percent_point',
                'lookback_coverage': {
                    'has_data': True,
                    'windows': {
                        '5m': {'is_valid': True, 'gap_seconds': 30},
                        '15m': {'is_valid': True, 'gap_seconds': 120},
                        '1h': {'is_valid': True, 'gap_seconds': 300},
                        '6h': {'is_valid': True, 'gap_seconds': 600},
                    }
                }
            }
        }
        
        result = engine.on_new_tick('BTC', data)
        
        # 不应该有 DATA_GAP_* 标签
        gap_tags = [ReasonTag.DATA_GAP_5M, ReasonTag.DATA_GAP_15M, ReasonTag.DATA_GAP_1H, ReasonTag.DATA_GAP_6H]
        for tag in gap_tags:
            assert tag not in result.reason_tags
    
    def test_engine_coverage_check_fail_5m(self):
        """测试引擎检测到 5分钟数据缺口"""
        engine = L1AdvisoryEngine()
        
        data = {
            'price': 90000,
            'price_change_1h': 3.0,
            'price_change_6h': 8.0,
            'oi_change_1h': 5.0,
            'oi_change_6h': 12.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {
                'percentage_format': 'percent_point',
                'lookback_coverage': {
                    'has_data': True,
                    'windows': {
                        '5m': {'is_valid': False, 'gap_seconds': 500, 'error_reason': 'GAP_TOO_LARGE'},
                        '15m': {'is_valid': True, 'gap_seconds': 120},
                        '1h': {'is_valid': True, 'gap_seconds': 300},
                        '6h': {'is_valid': True, 'gap_seconds': 600},
                    }
                }
            }
        }
        
        result = engine.on_new_tick('BTC', data)
        
        # 应该返回 NO_TRADE
        assert result.decision == Decision.NO_TRADE
        # 应该有 DATA_GAP_5M 标签
        assert ReasonTag.DATA_GAP_5M in result.reason_tags
    
    def test_engine_coverage_check_fail_multiple(self):
        """测试引擎检测到多个窗口缺口"""
        engine = L1AdvisoryEngine()
        
        data = {
            'price': 90000,
            'price_change_1h': 3.0,
            'price_change_6h': 8.0,
            'oi_change_1h': 5.0,
            'oi_change_6h': 12.0,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            '_metadata': {
                'percentage_format': 'percent_point',
                'lookback_coverage': {
                    'has_data': True,
                    'windows': {
                        '5m': {'is_valid': False, 'gap_seconds': 500, 'error_reason': 'GAP_TOO_LARGE'},
                        '15m': {'is_valid': False, 'gap_seconds': 1000, 'error_reason': 'GAP_TOO_LARGE'},
                        '1h': {'is_valid': True, 'gap_seconds': 300},
                        '6h': {'is_valid': True, 'gap_seconds': 600},
                    }
                }
            }
        }
        
        result = engine.on_new_tick('BTC', data)
        
        # 应该返回 NO_TRADE
        assert result.decision == Decision.NO_TRADE
        # 应该有两个 DATA_GAP 标签
        assert ReasonTag.DATA_GAP_5M in result.reason_tags
        assert ReasonTag.DATA_GAP_15M in result.reason_tags


class TestSparseDataScenario:
    """测试稀疏数据场景"""
    
    def test_sparse_tick_with_large_gaps(self):
        """测试稀疏tick数据（有大缺口）"""
        cache = MarketDataCache()
        
        base_time = datetime.now()
        # 存储稀疏数据：-60min, -10min, 0min
        timestamps = [-60, -10, 0]
        for offset in timestamps:
            timestamp = base_time + timedelta(minutes=offset)
            data = {'price': 90000 + abs(offset) * 10, 'volume': 1000, 'open_interest': 100000}
            cache.store_tick('BTC', data, timestamp)
        
        # 查找 -15min（应该找到 -60min，gap=45min=2700s）
        target_time = base_time - timedelta(minutes=15)
        result = cache._find_floor_tick('BTC', target_time, tolerance_seconds=300)  # 5分钟容忍
        
        # gap太大，应该失败
        assert not result.is_valid
        assert result.gap_seconds >= 2700 - 60  # 约2700秒（允许小误差）
        assert 'GAP_TOO_LARGE' in result.error_reason


class TestCacheWithEnhancedData:
    """测试 enhanced_market_data 中的 coverage"""
    
    def test_enhanced_data_contains_coverage(self):
        """测试 enhanced_data 包含 coverage"""
        cache = MarketDataCache()
        
        base_time = datetime.now()
        # 存储充足的历史数据
        for i in range(0, 360, 5):
            timestamp = base_time - timedelta(minutes=i)
            data = {'price': 90000, 'volume': 1000 + i, 'volume_24h': 24000, 
                    'open_interest': 100000, 'funding_rate': 0.0001,
                    'buy_volume': 600, 'sell_volume': 400}
            cache.store_tick('BTC', data, timestamp)
        
        # 获取 enhanced data
        current_data = {
            'price': 91000,
            'volume': 2000,
            'volume_24h': 50000,
            'open_interest': 112000,
            'funding_rate': 0.0002,
            'buy_volume': 1200,
            'sell_volume': 800
        }
        
        enhanced = cache.get_enhanced_market_data('BTC', current_data)
        
        # 应该包含 coverage
        assert '_metadata' in enhanced
        assert 'lookback_coverage' in enhanced['_metadata']
        
        coverage = enhanced['_metadata']['lookback_coverage']
        assert coverage['has_data']
        assert 'windows' in coverage
        
        # 所有窗口应该有效
        for window in ['5m', '15m', '1h', '6h']:
            assert coverage['windows'][window]['is_valid']


class TestBacktestConsistency:
    """测试回测与线上同构"""
    
    def test_same_input_same_output(self):
        """测试相同输入序列得到相同 lookback 结果"""
        cache1 = MarketDataCache()
        cache2 = MarketDataCache()
        
        base_time = datetime.now()
        tick_sequence = []
        
        # 生成相同的tick序列
        for i in range(100):
            timestamp = base_time - timedelta(minutes=100-i)
            data = {'price': 90000 + i * 10, 'volume': 1000, 'open_interest': 100000}
            tick_sequence.append((timestamp, data))
        
        # 存入两个cache
        for timestamp, data in tick_sequence:
            cache1.store_tick('BTC', data, timestamp)
            cache2.store_tick('BTC', data, timestamp)
        
        # 查找相同的目标时间
        target_time = base_time - timedelta(minutes=15)
        result1 = cache1._find_floor_tick('BTC', target_time, tolerance_seconds=300)
        result2 = cache2._find_floor_tick('BTC', target_time, tolerance_seconds=300)
        
        # 结果应该完全一致
        assert result1.is_valid == result2.is_valid
        assert result1.gap_seconds == result2.gap_seconds
        if result1.tick and result2.tick:
            assert result1.tick.timestamp == result2.tick.timestamp
            assert result1.tick.price == result2.tick.price


class TestWindowKeyMapping:
    """测试窗口key映射"""
    
    @pytest.mark.parametrize("hours,expected_key", [
        (5/60, '5m'),
        (0.25, '15m'),
        (1.0, '1h'),
        (6.0, '6h'),
    ])
    def test_hours_to_window_key(self, hours, expected_key):
        """测试小时数到窗口key的映射（参数化）"""
        cache = MarketDataCache()
        key = cache._hours_to_window_key(hours)
        assert key == expected_key


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
