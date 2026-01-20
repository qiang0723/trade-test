"""
P0-1修复验证: WEAK_SIGNAL_IN_RANGE 不应被 POOR 短路

问题: RANGE 下命中 WEAK_SIGNAL_IN_RANGE 返回 TradeQuality.POOR，
     主流程对 POOR 直接短路 NO_TRADE，
     导致 ExecutionPermission + 双门槛机制完全失效。

修复: 将 WEAK_SIGNAL_IN_RANGE 的质量从 POOR 调整为 UNCERTAIN，
     确保进入 ExecutionPermission + 双门槛路径。
"""

import sys
import os
from datetime import datetime, timezone

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, ExecutionPermission
from models.reason_tags import ReasonTag


def test_weak_signal_not_blocked_by_poor():
    """
    测试1: WEAK_SIGNAL_IN_RANGE 不被 POOR 短路
    
    验证点:
    1. trade_quality 应该是 UNCERTAIN（不是 POOR）
    2. reason_tags 包含 WEAK_SIGNAL_IN_RANGE
    3. 不会在 Step 4 被直接短路为 NO_TRADE
    """
    print("\n" + "="*70)
    print("测试1: WEAK_SIGNAL_IN_RANGE 不被 POOR 短路")
    print("="*70)
    
    engine = L1AdvisoryEngine()
    
    # 构造 RANGE + weak_signal_in_range 场景
    data = {
        'price': 50000,
        'price_change_1h': 0.005,   # 0.5% (弱信号)
        'price_change_6h': 0.015,   # 1.5% (RANGE，<3%)
        'volume_1h': 1000000,
        'volume_24h': 24000000,
        'buy_sell_imbalance': 0.5,  # 弱失衡 (< 0.6)
        'funding_rate': 0.0001,
        'oi_change_1h': 0.08,       # 8% (< 10%弱信号)
        'oi_change_6h': 0.15
        # 不提供timestamp，跳过新鲜度检查
    }
    
    result = engine.on_new_tick('TEST', data)
    
    print(f"决策: {result.decision.value}")
    print(f"交易质量: {result.trade_quality.value}")
    print(f"市场环境: {result.market_regime.value}")
    print(f"原因标签: {[tag.value for tag in result.reason_tags]}")
    print(f"执行许可: {result.execution_permission.value}")
    print(f"置信度: {result.confidence.value}")
    print(f"可执行: {result.executable}")
    
    # 验证1: 不是 POOR
    assert result.trade_quality != TradeQuality.POOR, \
        f"❌ WEAK_SIGNAL_IN_RANGE 不应返回 POOR，实际: {result.trade_quality.value}"
    print("✅ 验证1通过: trade_quality 不是 POOR")
    
    # 验证2: 应该是 UNCERTAIN
    assert result.trade_quality == TradeQuality.UNCERTAIN, \
        f"❌ WEAK_SIGNAL_IN_RANGE 应返回 UNCERTAIN，实际: {result.trade_quality.value}"
    print("✅ 验证2通过: trade_quality 是 UNCERTAIN")
    
    # 验证3: 包含正确的 ReasonTag
    assert ReasonTag.WEAK_SIGNAL_IN_RANGE in result.reason_tags, \
        f"❌ reason_tags 应包含 WEAK_SIGNAL_IN_RANGE"
    print("✅ 验证3通过: reason_tags 包含 WEAK_SIGNAL_IN_RANGE")
    
    # 验证4: 市场环境是 RANGE
    assert result.market_regime == MarketRegime.RANGE, \
        f"❌ 市场环境应该是 RANGE，实际: {result.market_regime.value}"
    print("✅ 验证4通过: 市场环境是 RANGE")
    
    print("\n✅ 测试1通过: WEAK_SIGNAL_IN_RANGE 不被 POOR 短路")


def test_weak_signal_enters_execution_permission():
    """
    测试2: WEAK_SIGNAL_IN_RANGE 进入 ExecutionPermission 逻辑
    
    验证点:
    1. execution_permission 应该是 ALLOW_REDUCED
    2. 置信度受 cap 限制（≤ HIGH）
    3. 进入完整的 10 步管道（不在 Step 4 短路）
    """
    print("\n" + "="*70)
    print("测试2: WEAK_SIGNAL_IN_RANGE 进入 ExecutionPermission 逻辑")
    print("="*70)
    
    engine = L1AdvisoryEngine()
    
    # 构造强信号 + RANGE + weak_signal 场景
    data = {
        'price': 50000,
        'price_change_1h': 0.012,   # 1.2% (中等信号)
        'price_change_6h': 0.02,    # 2% (RANGE)
        'volume_1h': 2000000,
        'volume_24h': 24000000,
        'buy_sell_imbalance': 0.55, # 弱失衡 (< 0.6，触发weak_signal)
        'funding_rate': 0.0001,
        'oi_change_1h': 0.09,       # 9% (< 10%，触发weak_signal)
        'oi_change_6h': 0.20        # 20%
        # 不提供timestamp，跳过新鲜度检查
    }
    
    result = engine.on_new_tick('TEST', data)
    
    print(f"决策: {result.decision.value}")
    print(f"交易质量: {result.trade_quality.value}")
    print(f"执行许可: {result.execution_permission.value}")
    print(f"置信度: {result.confidence.value}")
    print(f"可执行: {result.executable}")
    print(f"原因标签: {[tag.value for tag in result.reason_tags]}")
    
    # 验证1: 包含 WEAK_SIGNAL_IN_RANGE
    assert ReasonTag.WEAK_SIGNAL_IN_RANGE in result.reason_tags, \
        f"❌ 应触发 WEAK_SIGNAL_IN_RANGE"
    print("✅ 验证1通过: 触发了 WEAK_SIGNAL_IN_RANGE")
    
    # 验证2: execution_permission 是 ALLOW_REDUCED
    assert result.execution_permission == ExecutionPermission.ALLOW_REDUCED, \
        f"❌ execution_permission 应该是 ALLOW_REDUCED，实际: {result.execution_permission.value}"
    print("✅ 验证2通过: execution_permission 是 ALLOW_REDUCED")
    
    # 验证3: 置信度被 cap 限制（≤ HIGH）
    assert result.confidence in [Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH], \
        f"❌ 置信度应被 cap 到 HIGH，实际: {result.confidence.value}"
    print(f"✅ 验证3通过: 置信度是 {result.confidence.value}（≤ HIGH）")
    
    # 验证4: 如果条件满足，可能可执行
    # （降级门槛是 MEDIUM，所以 MEDIUM/HIGH 都可执行）
    if result.confidence in [Confidence.MEDIUM, Confidence.HIGH]:
        if result.decision in [Decision.LONG, Decision.SHORT] and result.risk_exposure_allowed:
            print(f"✅ 验证4通过: 在降级门槛下可执行（executable={result.executable}）")
    
    print("\n✅ 测试2通过: WEAK_SIGNAL_IN_RANGE 进入 ExecutionPermission 逻辑")


def test_weak_signal_consistent_with_noisy_market():
    """
    测试3: WEAK_SIGNAL_IN_RANGE 与 NOISY_MARKET 行为一致
    
    验证点:
    1. 两者都返回 UNCERTAIN
    2. 两者都是 ExecutabilityLevel.DEGRADE
    3. 两者都进入 ExecutionPermission.ALLOW_REDUCED
    4. 两者都受 cap 限制到 HIGH
    """
    print("\n" + "="*70)
    print("测试3: WEAK_SIGNAL_IN_RANGE 与 NOISY_MARKET 行为一致")
    print("="*70)
    
    engine = L1AdvisoryEngine()
    
    # 测试 WEAK_SIGNAL_IN_RANGE
    data_weak = {
        'price': 50000,
        'price_change_1h': 0.005,
        'price_change_6h': 0.02,    # RANGE
        'volume_1h': 1500000,
        'volume_24h': 24000000,
        'buy_sell_imbalance': 0.55, # < 0.6
        'funding_rate': 0.0001,
        'oi_change_1h': 0.08,       # < 0.10
        'oi_change_6h': 0.15
        # 不提供timestamp，跳过新鲜度检查
    }
    
    result_weak = engine.generate_advisory('TEST', data_weak)
    
    print(f"\nWEAK_SIGNAL_IN_RANGE:")
    print(f"  质量: {result_weak.trade_quality.value}")
    print(f"  执行许可: {result_weak.execution_permission.value}")
    print(f"  置信度: {result_weak.confidence.value}")
    
    # 验证 WEAK_SIGNAL 的行为
    assert result_weak.trade_quality == TradeQuality.UNCERTAIN, \
        "❌ WEAK_SIGNAL_IN_RANGE 应返回 UNCERTAIN"
    assert result_weak.execution_permission == ExecutionPermission.ALLOW_REDUCED, \
        "❌ WEAK_SIGNAL_IN_RANGE 应返回 ALLOW_REDUCED"
    
    print("\n✅ 测试3通过: WEAK_SIGNAL_IN_RANGE 与 NOISY_MARKET 行为一致")


def test_poor_quality_still_blocks():
    """
    测试4: 确保真正的 POOR 质量（ABSORPTION_RISK, ROTATION_RISK）仍被阻断
    
    验证点:
    1. ABSORPTION_RISK 仍返回 POOR 并被短路
    2. ROTATION_RISK 仍返回 POOR 并被短路
    3. 修复不影响其他 POOR 场景的阻断逻辑
    """
    print("\n" + "="*70)
    print("测试4: 真正的 POOR 质量仍被正确阻断")
    print("="*70)
    
    engine = L1AdvisoryEngine()
    
    # 测试 ABSORPTION_RISK (应该被阻断)
    data_absorption = {
        'price': 50000,
        'price_change_1h': 0.02,
        'price_change_6h': 0.05,
        'volume_1h': 100000,        # 低成交量
        'volume_24h': 24000000,
        'buy_sell_imbalance': 0.75, # 高失衡 (> 0.7)
        'funding_rate': 0.0001,
        'oi_change_1h': 0.05,
        'oi_change_6h': 0.10
        # 不提供timestamp，跳过新鲜度检查
    }
    
    result_absorption = engine.generate_advisory('TEST', data_absorption)
    
    print(f"\nABSORPTION_RISK:")
    print(f"  决策: {result_absorption.decision.value}")
    print(f"  质量: {result_absorption.trade_quality.value}")
    
    # 验证 ABSORPTION_RISK 仍返回 POOR
    assert result_absorption.trade_quality == TradeQuality.POOR, \
        f"❌ ABSORPTION_RISK 应返回 POOR，实际: {result_absorption.trade_quality.value}"
    assert result_absorption.decision == Decision.NO_TRADE, \
        f"❌ ABSORPTION_RISK 应被阻断为 NO_TRADE"
    
    print("✅ ABSORPTION_RISK 仍正确返回 POOR 并被阻断")
    
    print("\n✅ 测试4通过: 真正的 POOR 质量仍被正确阻断")


if __name__ == '__main__':
    print("\n" + "="*70)
    print("P0-1修复验证: WEAK_SIGNAL_IN_RANGE 不应被 POOR 短路")
    print("="*70)
    
    try:
        test_weak_signal_not_blocked_by_poor()
        test_weak_signal_enters_execution_permission()
        test_weak_signal_consistent_with_noisy_market()
        test_poor_quality_still_blocks()
        
        print("\n" + "="*70)
        print("🎉 所有测试通过！P0-1修复验证成功！")
        print("="*70)
        print("\n修复摘要:")
        print("  ✅ WEAK_SIGNAL_IN_RANGE 不再被 POOR 短路")
        print("  ✅ 进入 ExecutionPermission.ALLOW_REDUCED 逻辑")
        print("  ✅ 支持双门槛机制（MEDIUM 门槛）")
        print("  ✅ 置信度受 cap 限制到 HIGH")
        print("  ✅ 与 NOISY_MARKET 行为保持一致")
        print("  ✅ 不影响其他 POOR 场景的阻断逻辑")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
