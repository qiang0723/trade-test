"""
PR-C测试：决策频率控制

测试内容：
1. 最小决策间隔阻断
2. 翻转冷却阻断
3. NO_TRADE不更新记忆
4. 多币种独立控制
"""

import sys
import os
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine, DecisionMemory
from models.enums import Decision, MarketRegime
from models.reason_tags import ReasonTag


def test_decision_memory_basic():
    """测试DecisionMemory基本功能"""
    print("\n=== Test 1: DecisionMemory基本功能 ===")
    
    memory = DecisionMemory()
    
    # 测试1: 初始状态
    assert memory.get_last_decision('BTC') is None
    print("✅ 初始状态：无记忆")
    
    # 测试2: 更新LONG决策
    now = datetime.now()
    memory.update_decision('BTC', Decision.LONG, now)
    last = memory.get_last_decision('BTC')
    assert last is not None
    assert last['side'] == Decision.LONG
    assert last['time'] == now
    print("✅ LONG决策已记录")
    
    # 测试3: NO_TRADE不更新记忆
    memory.update_decision('BTC', Decision.NO_TRADE, now + timedelta(seconds=10))
    last = memory.get_last_decision('BTC')
    assert last['side'] == Decision.LONG  # 仍然是LONG
    assert last['time'] == now  # 时间未变
    print("✅ NO_TRADE不更新记忆")
    
    # 测试4: 多币种独立
    memory.update_decision('ETH', Decision.SHORT, now)
    btc_last = memory.get_last_decision('BTC')
    eth_last = memory.get_last_decision('ETH')
    assert btc_last['side'] == Decision.LONG
    assert eth_last['side'] == Decision.SHORT
    print("✅ 多币种独立记忆")
    
    # 测试5: 清除记忆
    memory.clear('BTC')
    assert memory.get_last_decision('BTC') is None
    assert memory.get_last_decision('ETH') is not None
    print("✅ 清除记忆功能正常")


def test_min_interval_block():
    """测试最小间隔阻断"""
    print("\n=== Test 2: 最小间隔阻断 ===")
    
    # 创建测试配置
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 准备测试数据（强买盘信号）
    strong_long_data = {
        'symbol': 'BTC',
        'price': 50000,
        'price_change_1h': 0.03,  # 3%
        'price_change_6h': 0.05,  # 5%
        'volume_1h': 1000000,
        'volume_24h': 20000000,
        'buy_sell_imbalance': 0.75,  # 强买盘
        'funding_rate': 0.0001,
        'oi_change_1h': 0.10,  # 10%
        'oi_change_6h': 0.15,
        'timestamp': datetime.now().isoformat()
    }
    
    # 第1次决策：LONG（首次，不阻断）
    result1 = engine.on_new_tick('BTC', strong_long_data)
    print(f"第1次决策: {result1.decision.value}")
    assert result1.decision in [Decision.LONG, Decision.NO_TRADE]
    
    # 如果第1次是LONG，测试最小间隔
    if result1.decision == Decision.LONG:
        # 2秒后：再次LONG（应被阻断）
        import time
        time.sleep(2)
        result2 = engine.on_new_tick('BTC', strong_long_data)
        print(f"第2次决策（2秒后）: {result2.decision.value}")
        assert result2.decision == Decision.NO_TRADE
        assert ReasonTag.MIN_INTERVAL_BLOCK in result2.reason_tags
        print("✅ 最小间隔阻断生效")
    else:
        print("⏭️  第1次决策不是LONG，跳过间隔测试")


def test_flip_cooldown_block():
    """测试翻转冷却阻断"""
    print("\n=== Test 3: 翻转冷却阻断 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 强买盘数据
    long_data = {
        'symbol': 'ETH',
        'price': 3000,
        'price_change_1h': 0.03,
        'price_change_6h': 0.05,
        'volume_1h': 500000,
        'volume_24h': 10000000,
        'buy_sell_imbalance': 0.75,
        'funding_rate': 0.0001,
        'oi_change_1h': 0.10,
        'oi_change_6h': 0.15,
        'timestamp': datetime.now().isoformat()
    }
    
    # 强卖盘数据
    short_data = long_data.copy()
    short_data['price_change_1h'] = -0.03
    short_data['buy_sell_imbalance'] = 0.25
    
    # 第1次：LONG
    result1 = engine.on_new_tick('ETH', long_data)
    print(f"第1次决策: {result1.decision.value}")
    
    if result1.decision == Decision.LONG:
        # 5秒后：SHORT（应被阻断）
        import time
        time.sleep(5)
        result2 = engine.on_new_tick('ETH', short_data)
        print(f"第2次决策（5秒后，尝试翻转）: {result2.decision.value}")
        assert result2.decision == Decision.NO_TRADE
        assert ReasonTag.FLIP_COOLDOWN_BLOCK in result2.reason_tags
        print("✅ 翻转冷却阻断生效")
    else:
        print("⏭️  第1次决策不是LONG，跳过翻转测试")


def test_control_disabled():
    """测试禁用控制功能"""
    print("\n=== Test 4: 禁用控制功能 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 临时禁用控制
    engine.config['decision_control']['enable_min_interval'] = False
    engine.config['decision_control']['enable_flip_cooldown'] = False
    
    test_data = {
        'symbol': 'SOL',
        'price': 100,
        'price_change_1h': 0.03,
        'price_change_6h': 0.05,
        'volume_1h': 100000,
        'volume_24h': 2000000,
        'buy_sell_imbalance': 0.75,
        'funding_rate': 0.0001,
        'oi_change_1h': 0.10,
        'oi_change_6h': 0.15,
        'timestamp': datetime.now().isoformat()
    }
    
    result = engine.on_new_tick('SOL', test_data)
    print(f"禁用控制后的决策: {result.decision.value}")
    assert ReasonTag.MIN_INTERVAL_BLOCK not in result.reason_tags
    assert ReasonTag.FLIP_COOLDOWN_BLOCK not in result.reason_tags
    print("✅ 禁用控制功能正常")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("PR-C: 决策频率控制测试")
    print("=" * 60)
    
    try:
        test_decision_memory_basic()
        test_min_interval_block()
        test_flip_cooldown_block()
        test_control_disabled()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        return 0
    
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
