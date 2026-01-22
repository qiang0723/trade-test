"""
PATCH-P0-07: 短线信号频率可量化回归测试

目标：
- 确保短期信号密度在合理区间（不过严不过松）
- 验证数据缺口场景下短期仍可产生方向信号
- 使用deterministic fixture，可复现

不涉及：
- 收益回测
- 真实市场数据
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import random
from datetime import datetime
from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, ExecutionPermission


class TestSignalFrequency:
    """P0-07: 短线信号频率测试"""
    
    @pytest.fixture
    def engine(self):
        """创建L1引擎（禁用频控避免时间依赖）"""
        engine = L1AdvisoryEngine()
        # 禁用频控（通过修改配置）
        engine.config['decision_control'] = {
            'enable_min_interval': False,
            'enable_flip_cooldown': False
        }
        return engine
    
    @pytest.fixture
    def deterministic_data_generator(self):
        """确定性数据生成器（固定种子）"""
        random.seed(42)  # 固定种子，确保可复现
        
        def generate_snapshot(scenario='normal'):
            """生成市场快照
            
            Args:
                scenario: 'normal' / 'bullish' / 'bearish' / 'gap_medium' / 'gap_short'
            """
            base_price = 50000.0
            
            if scenario == 'normal':
                # 正常数据：随机小幅波动
                return {
                    'symbol': 'BTC',
                    'price': base_price + random.uniform(-1000, 1000),
                    'volume_24h': 1000000000 + random.uniform(-1e8, 1e8),
                    'funding_rate': random.uniform(-0.0005, 0.0005),
                    'price_change_5m': random.uniform(-0.003, 0.003),
                    'price_change_15m': random.uniform(-0.008, 0.008),
                    'price_change_1h': random.uniform(-0.015, 0.015),
                    'price_change_6h': random.uniform(-0.03, 0.03),
                    'oi_change_5m': random.uniform(-0.02, 0.02),
                    'oi_change_15m': random.uniform(-0.05, 0.05),
                    'oi_change_1h': random.uniform(-0.1, 0.1),
                    'oi_change_6h': random.uniform(-0.2, 0.2),
                    'taker_imbalance_5m': random.uniform(-0.3, 0.3),
                    'taker_imbalance_15m': random.uniform(-0.3, 0.3),
                    'taker_imbalance_1h': random.uniform(-0.3, 0.3),
                    'volume_ratio_5m': random.uniform(0.8, 1.5),
                    'volume_ratio_15m': random.uniform(0.8, 1.5),
                    'volume_1h': 1e9 + random.uniform(-1e8, 1e8)
                }
            
            elif scenario == 'bullish':
                # 看多信号：短期上涨 + 买压
                return {
                    'symbol': 'BTC',
                    'price': base_price + random.uniform(500, 1500),
                    'volume_24h': 1200000000,
                    'funding_rate': 0.0003,
                    'price_change_5m': random.uniform(0.002, 0.005),
                    'price_change_15m': random.uniform(0.006, 0.012),
                    'price_change_1h': random.uniform(0.015, 0.025),
                    'price_change_6h': random.uniform(0.02, 0.04),
                    'oi_change_5m': random.uniform(0.01, 0.03),
                    'oi_change_15m': random.uniform(0.02, 0.05),
                    'oi_change_1h': random.uniform(0.05, 0.15),
                    'oi_change_6h': random.uniform(0.1, 0.3),
                    'taker_imbalance_5m': random.uniform(0.4, 0.7),
                    'taker_imbalance_15m': random.uniform(0.3, 0.6),
                    'taker_imbalance_1h': random.uniform(0.2, 0.4),
                    'volume_ratio_5m': random.uniform(1.5, 2.5),
                    'volume_ratio_15m': random.uniform(1.3, 2.0),
                    'volume_1h': 1.2e9
                }
            
            elif scenario == 'bearish':
                # 看空信号：短期下跌 + 卖压
                return {
                    'symbol': 'BTC',
                    'price': base_price - random.uniform(500, 1500),
                    'volume_24h': 1200000000,
                    'funding_rate': -0.0003,
                    'price_change_5m': random.uniform(-0.005, -0.002),
                    'price_change_15m': random.uniform(-0.012, -0.006),
                    'price_change_1h': random.uniform(-0.025, -0.015),
                    'price_change_6h': random.uniform(-0.04, -0.02),
                    'oi_change_5m': random.uniform(0.01, 0.03),
                    'oi_change_15m': random.uniform(0.02, 0.05),
                    'oi_change_1h': random.uniform(0.05, 0.15),
                    'oi_change_6h': random.uniform(0.1, 0.3),
                    'taker_imbalance_5m': random.uniform(-0.7, -0.4),
                    'taker_imbalance_15m': random.uniform(-0.6, -0.3),
                    'taker_imbalance_1h': random.uniform(-0.4, -0.2),
                    'volume_ratio_5m': random.uniform(1.5, 2.5),
                    'volume_ratio_15m': random.uniform(1.3, 2.0),
                    'volume_1h': 1.2e9
                }
            
            elif scenario == 'gap_medium':
                # 中期数据缺口（6h缺失）- 短期应仍可工作
                return {
                    'symbol': 'BTC',
                    'price': base_price + random.uniform(-500, 500),
                    'volume_24h': 1000000000,
                    'funding_rate': random.uniform(-0.0003, 0.0003),
                    'price_change_5m': random.uniform(-0.003, 0.003),
                    'price_change_15m': random.uniform(-0.008, 0.008),
                    'price_change_1h': random.uniform(-0.015, 0.015),
                    'price_change_6h': None,  # 缺失
                    'oi_change_5m': random.uniform(-0.02, 0.02),
                    'oi_change_15m': random.uniform(-0.05, 0.05),
                    'oi_change_1h': random.uniform(-0.1, 0.1),
                    'oi_change_6h': None,  # 缺失
                    'taker_imbalance_5m': random.uniform(-0.3, 0.3),
                    'taker_imbalance_15m': random.uniform(-0.3, 0.3),
                    'taker_imbalance_1h': random.uniform(-0.3, 0.3),
                    'volume_ratio_5m': random.uniform(0.8, 1.5),
                    'volume_ratio_15m': random.uniform(0.8, 1.5),
                    'volume_1h': 1e9
                }
            
            elif scenario == 'gap_short':
                # 短期数据缺口（5m/15m缺失）- 应返回NO_TRADE
                return {
                    'symbol': 'BTC',
                    'price': base_price,
                    'volume_24h': 1000000000,
                    'funding_rate': 0.0001,
                    'price_change_5m': None,  # 缺失
                    'price_change_15m': None,  # 缺失
                    'price_change_1h': 0.01,
                    'price_change_6h': 0.02,
                    'oi_change_5m': None,  # 缺失
                    'oi_change_15m': None,  # 缺失
                    'oi_change_1h': 0.05,
                    'oi_change_6h': 0.1,
                    'taker_imbalance_5m': None,  # 缺失
                    'taker_imbalance_15m': None,  # 缺失
                    'taker_imbalance_1h': 0.2,
                    'volume_ratio_5m': None,  # 缺失
                    'volume_ratio_15m': None,  # 缺失
                    'volume_1h': 1e9
                }
        
        return generate_snapshot
    
    def test_short_term_signal_frequency_normal(self, engine, deterministic_data_generator):
        """测试：正常数据下，短期信号密度在合理区间"""
        N = 100
        snapshots = [deterministic_data_generator('normal') for _ in range(N)]
        
        direction_count = 0  # LONG/SHORT数量
        no_trade_count = 0
        
        for data in snapshots:
            result = engine.on_new_tick_dual('BTC', data)
            short_term = result.short_term
            
            if short_term.decision in [Decision.LONG, Decision.SHORT]:
                direction_count += 1
            else:
                no_trade_count += 1
        
        direction_rate = direction_count / N
        
        print(f"\n正常数据测试结果 (N={N}):")
        print(f"  方向信号率: {direction_rate:.1%} ({direction_count}/{N})")
        print(f"  NO_TRADE率: {(no_trade_count/N):.1%}")
        
        # 断言：方向信号率应在5%-50%之间（防止过严或过松）
        assert 0.05 <= direction_rate <= 0.50, \
            f"短期方向信号率异常：{direction_rate:.1%}（期望5%-50%）"
    
    def test_short_term_with_medium_gap(self, engine, deterministic_data_generator):
        """测试：中期数据缺口时，短期仍可产生方向信号"""
        N = 50
        snapshots = [deterministic_data_generator('gap_medium') for _ in range(N)]
        
        direction_count = 0
        degraded_count = 0
        
        for data in snapshots:
            result = engine.on_new_tick_dual('BTC', data)
            short_term = result.short_term
            
            if short_term.decision in [Decision.LONG, Decision.SHORT]:
                direction_count += 1
                # 检查是否降级
                if short_term.execution_permission == ExecutionPermission.ALLOW_REDUCED:
                    degraded_count += 1
        
        print(f"\n中期缺口数据测试 (N={N}):")
        print(f"  短期方向信号: {direction_count}/{N}")
        print(f"  降级执行: {degraded_count}/{direction_count if direction_count > 0 else 1}")
        
        # 断言：中期缺口不应完全阻止短期信号
        assert direction_count > 0, "中期数据缺口导致短期完全无信号（不符合预期）"
    
    def test_short_term_with_short_gap(self, engine, deterministic_data_generator):
        """测试：短期数据缺口时，应返回NO_TRADE"""
        N = 20
        snapshots = [deterministic_data_generator('gap_short') for _ in range(N)]
        
        no_trade_count = 0
        
        for data in snapshots:
            result = engine.on_new_tick_dual('BTC', data)
            short_term = result.short_term
            
            if short_term.decision == Decision.NO_TRADE:
                no_trade_count += 1
        
        print(f"\n短期缺口数据测试 (N={N}):")
        print(f"  NO_TRADE: {no_trade_count}/{N}")
        
        # 断言：短期数据缺口应全部返回NO_TRADE
        assert no_trade_count == N, \
            f"短期数据缺口未全部NO_TRADE：{no_trade_count}/{N}"
    
    def test_bullish_signal_frequency(self, engine, deterministic_data_generator):
        """测试：明确看多数据应产生LONG信号"""
        N = 20
        snapshots = [deterministic_data_generator('bullish') for _ in range(N)]
        
        long_count = 0
        executable_count = 0
        
        for data in snapshots:
            result = engine.on_new_tick_dual('BTC', data)
            short_term = result.short_term
            
            if short_term.decision == Decision.LONG:
                long_count += 1
                if short_term.executable:
                    executable_count += 1
        
        long_rate = long_count / N
        executable_rate = executable_count / N if long_count > 0 else 0
        
        print(f"\n看多数据测试 (N={N}):")
        print(f"  LONG信号率: {long_rate:.1%} ({long_count}/{N})")
        print(f"  可执行率: {executable_rate:.1%} ({executable_count}/{N})")
        
        # 断言：明确看多数据应有合理LONG信号率
        assert long_rate >= 0.3, \
            f"明确看多数据但LONG信号率过低：{long_rate:.1%}（期望>=30%）"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
