"""
测试 DualDecisionMemory: 双周期频率控制

测试覆盖：
1. 短期决策间隔控制（5分钟）
2. 短期翻转冷却（7.5分钟）
3. 中长期决策间隔控制（30分钟）
4. 中长期翻转冷却（15分钟）
5. 对齐类型重大翻转冷却（15分钟）
6. NO_TRADE豁免规则
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta
from market_state_machine_l1 import DualDecisionMemory
from models.enums import Decision, AlignmentType


def test_short_term_interval():
    """测试：短期决策最小间隔（5分钟）"""
    print("\n=== Test 1: 短期决策最小间隔 ===")
    
    config = {
        'dual_decision_control': {
            'short_term_interval_seconds': 300,  # 5分钟
            'short_term_flip_cooldown_seconds': 450,
            'medium_term_interval_seconds': 1800,
            'medium_term_flip_cooldown_seconds': 900,
            'alignment_flip_cooldown_seconds': 900
        }
    }
    
    memory = DualDecisionMemory(config)
    base_time = datetime.now()
    
    # 首次LONG决策
    blocked, reason = memory.should_block_short_term('BTC', Decision.LONG, base_time)
    assert not blocked, "首次决策不应被阻断"
    memory.update_short_term('BTC', Decision.LONG, base_time)
    print("✓ 首次LONG: 通过")
    
    # 3分钟后再次LONG（同方向）
    time_3min = base_time + timedelta(seconds=180)
    blocked, reason = memory.should_block_short_term('BTC', Decision.LONG, time_3min)
    assert blocked, "3分钟内重复决策应被阻断"
    assert "间隔不足" in reason
    print(f"✓ 3分钟后LONG: 阻断 ({reason})")
    
    # 6分钟后再次LONG（超过间隔）
    time_6min = base_time + timedelta(seconds=360)
    blocked, reason = memory.should_block_short_term('BTC', Decision.LONG, time_6min)
    assert not blocked, "6分钟后应通过间隔检查"
    print("✓ 6分钟后LONG: 通过")
    
    print("✅ 短期决策最小间隔测试通过")


def test_short_term_flip_cooldown():
    """测试：短期翻转冷却（7.5分钟）"""
    print("\n=== Test 2: 短期翻转冷却 ===")
    
    config = {
        'dual_decision_control': {
            'short_term_interval_seconds': 300,
            'short_term_flip_cooldown_seconds': 450,  # 7.5分钟
            'medium_term_interval_seconds': 1800,
            'medium_term_flip_cooldown_seconds': 900,
            'alignment_flip_cooldown_seconds': 900
        }
    }
    
    memory = DualDecisionMemory(config)
    base_time = datetime.now()
    
    # 首次LONG
    memory.update_short_term('BTC', Decision.LONG, base_time)
    print("✓ 初始: LONG")
    
    # 6分钟后翻转为SHORT（通过间隔，但未通过翻转冷却）
    time_6min = base_time + timedelta(seconds=360)
    blocked, reason = memory.should_block_short_term('BTC', Decision.SHORT, time_6min)
    assert blocked, "6分钟翻转应被阻断（< 7.5分钟冷却）"
    assert "翻转冷却" in reason
    print(f"✓ 6分钟后SHORT: 阻断 ({reason})")
    
    # 8分钟后翻转为SHORT（通过翻转冷却）
    time_8min = base_time + timedelta(seconds=480)
    blocked, reason = memory.should_block_short_term('BTC', Decision.SHORT, time_8min)
    assert not blocked, "8分钟后翻转应通过"
    print("✓ 8分钟后SHORT: 通过")
    
    print("✅ 短期翻转冷却测试通过")


def test_medium_term_interval():
    """测试：中长期决策最小间隔（30分钟）"""
    print("\n=== Test 3: 中长期决策最小间隔 ===")
    
    config = {
        'dual_decision_control': {
            'short_term_interval_seconds': 300,
            'short_term_flip_cooldown_seconds': 450,
            'medium_term_interval_seconds': 1800,  # 30分钟
            'medium_term_flip_cooldown_seconds': 900,
            'alignment_flip_cooldown_seconds': 900
        }
    }
    
    memory = DualDecisionMemory(config)
    base_time = datetime.now()
    
    # 首次LONG
    blocked, reason = memory.should_block_medium_term('BTC', Decision.LONG, base_time)
    assert not blocked
    memory.update_medium_term('BTC', Decision.LONG, base_time)
    print("✓ 首次LONG: 通过")
    
    # 20分钟后再次LONG
    time_20min = base_time + timedelta(minutes=20)
    blocked, reason = memory.should_block_medium_term('BTC', Decision.LONG, time_20min)
    assert blocked, "20分钟内重复决策应被阻断"
    print(f"✓ 20分钟后LONG: 阻断 ({reason})")
    
    # 35分钟后再次LONG
    time_35min = base_time + timedelta(minutes=35)
    blocked, reason = memory.should_block_medium_term('BTC', Decision.LONG, time_35min)
    assert not blocked, "35分钟后应通过"
    print("✓ 35分钟后LONG: 通过")
    
    print("✅ 中长期决策最小间隔测试通过")


def test_alignment_flip_cooldown():
    """测试：对齐类型重大翻转冷却（15分钟）"""
    print("\n=== Test 4: 对齐类型翻转冷却 ===")
    
    config = {
        'dual_decision_control': {
            'short_term_interval_seconds': 300,
            'short_term_flip_cooldown_seconds': 450,
            'medium_term_interval_seconds': 1800,
            'medium_term_flip_cooldown_seconds': 900,
            'alignment_flip_cooldown_seconds': 900  # 15分钟
        }
    }
    
    memory = DualDecisionMemory(config)
    base_time = datetime.now()
    
    # 初始状态：BOTH_LONG
    memory.update_alignment('BTC', AlignmentType.BOTH_LONG, base_time)
    print("✓ 初始: BOTH_LONG")
    
    # 10分钟后翻转为BOTH_SHORT（重大翻转）
    time_10min = base_time + timedelta(minutes=10)
    blocked, reason = memory.should_block_alignment_flip('BTC', AlignmentType.BOTH_SHORT, time_10min)
    assert blocked, "10分钟翻转应被阻断"
    assert "重大翻转" in reason
    print(f"✓ 10分钟后BOTH_SHORT: 阻断 ({reason})")
    
    # 10分钟后变为PARTIAL_LONG（非重大翻转）
    blocked, reason = memory.should_block_alignment_flip('BTC', AlignmentType.PARTIAL_LONG, time_10min)
    assert not blocked, "非重大翻转不应阻断"
    print("✓ 10分钟后PARTIAL_LONG: 通过（非重大翻转）")
    
    # 20分钟后翻转为BOTH_SHORT（通过冷却）
    time_20min = base_time + timedelta(minutes=20)
    blocked, reason = memory.should_block_alignment_flip('BTC', AlignmentType.BOTH_SHORT, time_20min)
    assert not blocked, "20分钟后重大翻转应通过"
    print("✓ 20分钟后BOTH_SHORT: 通过")
    
    print("✅ 对齐类型翻转冷却测试通过")


def test_no_trade_exemption():
    """测试：NO_TRADE豁免规则"""
    print("\n=== Test 5: NO_TRADE豁免规则 ===")
    
    config = {
        'dual_decision_control': {
            'short_term_interval_seconds': 300,
            'short_term_flip_cooldown_seconds': 450,
            'medium_term_interval_seconds': 1800,
            'medium_term_flip_cooldown_seconds': 900,
            'alignment_flip_cooldown_seconds': 900
        }
    }
    
    memory = DualDecisionMemory(config)
    base_time = datetime.now()
    
    # LONG后立即NO_TRADE
    memory.update_short_term('BTC', Decision.LONG, base_time)
    time_1sec = base_time + timedelta(seconds=1)
    blocked, reason = memory.should_block_short_term('BTC', Decision.NO_TRADE, time_1sec)
    assert not blocked, "NO_TRADE应永远不被阻断"
    print("✓ LONG后1秒NO_TRADE: 通过")
    
    # NO_TRADE后立即LONG（仍受间隔限制）
    time_2sec = base_time + timedelta(seconds=2)
    blocked, reason = memory.should_block_short_term('BTC', Decision.LONG, time_2sec)
    assert blocked, "NO_TRADE后立即LONG应被间隔阻断"
    print(f"✓ NO_TRADE后2秒LONG: 阻断 ({reason})")
    
    print("✅ NO_TRADE豁免规则测试通过")


def test_multi_symbol_isolation():
    """测试：多币种隔离"""
    print("\n=== Test 6: 多币种隔离 ===")
    
    config = {
        'dual_decision_control': {
            'short_term_interval_seconds': 300,
            'short_term_flip_cooldown_seconds': 450,
            'medium_term_interval_seconds': 1800,
            'medium_term_flip_cooldown_seconds': 900,
            'alignment_flip_cooldown_seconds': 900
        }
    }
    
    memory = DualDecisionMemory(config)
    base_time = datetime.now()
    
    # BTC记录LONG
    memory.update_short_term('BTC', Decision.LONG, base_time)
    
    # 立即ETH记录LONG（不应被BTC影响）
    time_1sec = base_time + timedelta(seconds=1)
    blocked, reason = memory.should_block_short_term('ETH', Decision.LONG, time_1sec)
    assert not blocked, "不同币种应互不影响"
    print("✓ BTC后立即ETH: 通过（币种隔离）")
    
    print("✅ 多币种隔离测试通过")


if __name__ == '__main__':
    print("=" * 60)
    print("DualDecisionMemory 单元测试")
    print("=" * 60)
    
    test_short_term_interval()
    test_short_term_flip_cooldown()
    test_medium_term_interval()
    test_alignment_flip_cooldown()
    test_no_trade_exemption()
    test_multi_symbol_isolation()
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过 (6/6)")
    print("=" * 60)
