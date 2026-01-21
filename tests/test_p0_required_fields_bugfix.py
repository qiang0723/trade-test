"""
测试 P0-BugFix-4: 修复关键字段缺失静默失败问题

问题描述：
- price_change_6h 用于市场环境识别（TREND判断）
- oi_change_6h 用于拥挤风险检测
- 但这两个字段未在 required_fields 中强制要求
- 导致缺失时默认为0，相关逻辑静默失败

修复：
- 将 price_change_6h 和 oi_change_6h 加入 required_fields
- 确保字段缺失时 fail-fast，输出 INVALID_DATA

影响：
- 市场环境识别（TREND永远不触发）
- 拥挤风险检测（CROWDING_RISK永远不触发）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, SystemState
from models.reason_tags import ReasonTag


def test_p0_bugfix4_missing_price_change_6h():
    """测试缺失 price_change_6h 时 fail-fast"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-4: 缺失 price_change_6h")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    # 构造缺失 price_change_6h 的数据（使用百分比点格式）
    incomplete_data = {
        'price': 50000,
        'price_change_1h': 0.1,    # 0.1% (百分比点)
        # ❌ price_change_6h 缺失
        'volume_1h': 100,
        'volume_24h': 2400,
        'buy_sell_imbalance': 0.3,
        'funding_rate': 0.01,      # 0.01% (百分比点)
        'oi_change_1h': 1.0,       # 1% (百分比点)
        'oi_change_6h': 5.0        # 5% (百分比点)
    }
    
    print(f"\n输入数据（缺失 price_change_6h）:")
    for k, v in incomplete_data.items():
        print(f"  {k}: {v}")
    
    # 调用决策
    result = engine.on_new_tick("BTCUSDT", incomplete_data)
    
    print(f"\n决策结果:")
    print(f"  decision: {result.decision}")
    print(f"  system_state: {result.system_state}")
    print(f"  reason_tags: {[tag.value for tag in result.reason_tags]}")
    
    # 验证
    assert result.decision == Decision.NO_TRADE, "应该输出 NO_TRADE"
    assert ReasonTag.INVALID_DATA in result.reason_tags, "reason_tags 应包含 INVALID_DATA"
    
    print(f"\n✅ 修复验证通过：缺失 price_change_6h 时正确 fail-fast！")


def test_p0_bugfix4_missing_oi_change_6h():
    """测试缺失 oi_change_6h 时 fail-fast"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-4: 缺失 oi_change_6h")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    # 构造缺失 oi_change_6h 的数据（使用百分比点格式）
    incomplete_data = {
        'price': 50000,
        'price_change_1h': 0.1,    # 0.1% (百分比点)
        'price_change_6h': 3.5,    # 3.5% (百分比点)，应识别为 TREND
        'volume_1h': 100,
        'volume_24h': 2400,
        'buy_sell_imbalance': 0.3,
        'funding_rate': 0.01,      # 0.01% (百分比点)
        'oi_change_1h': 1.0,       # 1% (百分比点)
        # ❌ oi_change_6h 缺失
    }
    
    print(f"\n输入数据（缺失 oi_change_6h）:")
    for k, v in incomplete_data.items():
        print(f"  {k}: {v}")
    
    # 调用决策
    result = engine.on_new_tick("BTCUSDT", incomplete_data)
    
    print(f"\n决策结果:")
    print(f"  decision: {result.decision}")
    print(f"  system_state: {result.system_state}")
    print(f"  reason_tags: {[tag.value for tag in result.reason_tags]}")
    
    # 验证
    assert result.decision == Decision.NO_TRADE, "应该输出 NO_TRADE"
    assert ReasonTag.INVALID_DATA in result.reason_tags, "reason_tags 应包含 INVALID_DATA"
    
    print(f"\n✅ 修复验证通过：缺失 oi_change_6h 时正确 fail-fast！")


def test_p0_bugfix4_missing_both_fields():
    """测试同时缺失两个字段"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-4: 同时缺失 price_change_6h 和 oi_change_6h")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    # 构造同时缺失两个字段的数据（使用百分比点格式）
    incomplete_data = {
        'price': 50000,
        'price_change_1h': 0.1,    # 0.1% (百分比点)
        # ❌ price_change_6h 缺失
        'volume_1h': 100,
        'volume_24h': 2400,
        'buy_sell_imbalance': 0.3,
        'funding_rate': 0.01,      # 0.01% (百分比点)
        'oi_change_1h': 1.0,       # 1% (百分比点)
        # ❌ oi_change_6h 缺失
    }
    
    print(f"\n输入数据（同时缺失两个字段）:")
    for k, v in incomplete_data.items():
        print(f"  {k}: {v}")
    
    # 调用决策
    result = engine.on_new_tick("BTCUSDT", incomplete_data)
    
    print(f"\n决策结果:")
    print(f"  decision: {result.decision}")
    print(f"  system_state: {result.system_state}")
    print(f"  reason_tags: {[tag.value for tag in result.reason_tags]}")
    
    # 验证
    assert result.decision == Decision.NO_TRADE, "应该输出 NO_TRADE"
    assert ReasonTag.INVALID_DATA in result.reason_tags, "reason_tags 应包含 INVALID_DATA"
    
    print(f"\n✅ 修复验证通过：同时缺失时正确 fail-fast！")


def test_p0_bugfix4_all_fields_present():
    """测试所有字段都存在时正常运行"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-4: 所有字段完整（正常场景）")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    # 构造完整数据（使用百分比点格式）
    complete_data = {
        'price': 50000,
        'price_change_1h': 0.1,    # 0.1% (百分比点)
        'price_change_6h': 2.0,    # 2% (百分比点)
        'volume_1h': 100,
        'volume_24h': 2400,
        'buy_sell_imbalance': 0.3,
        'funding_rate': 0.01,      # 0.01% (百分比点)
        'oi_change_1h': 1.0,       # 1% (百分比点)
        'oi_change_6h': 5.0        # 5% (百分比点)
    }
    
    print(f"\n输入数据（完整）:")
    for k, v in complete_data.items():
        print(f"  {k}: {v}")
    
    # 调用决策
    result = engine.on_new_tick("BTCUSDT", complete_data)
    
    print(f"\n决策结果:")
    print(f"  decision: {result.decision}")
    print(f"  system_state: {result.system_state}")
    print(f"  market_regime: {result.market_regime}")
    print(f"  confidence: {result.confidence}")
    
    # 验证：不应该因为字段缺失而失败
    assert ReasonTag.INVALID_DATA not in result.reason_tags, "不应该包含 INVALID_DATA"
    
    print(f"\n✅ 完整数据验证通过：系统正常运行！")


def test_p0_bugfix4_impact_on_trend_detection():
    """测试修复对 TREND 识别的影响"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-4: 修复对 TREND 识别的影响")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    print(f"\n场景: 强趋势市场")
    print(f"  price_change_6h = 4% (> 3% TREND阈值)")
    
    # 构造强趋势数据
    trend_data = {
        'price': 50000,
        'price_change_1h': 0.015,   # 1.5%
        'price_change_6h': 0.04,    # 4% - 应识别为 TREND
        'volume_1h': 100,
        'volume_24h': 2400,
        'buy_sell_imbalance': 0.6,  # 明显做多信号
        'funding_rate': 0.0001,
        'oi_change_1h': 0.01,
        'oi_change_6h': 0.05
    }
    
    result = engine.on_new_tick("BTCUSDT", trend_data)
    
    print(f"\n决策结果:")
    print(f"  market_regime: {result.market_regime}")
    print(f"  decision: {result.decision}")
    print(f"  reason_tags: {[tag.value for tag in result.reason_tags]}")
    
    # 修复前：如果 price_change_6h 缺失（默认0），永远不会识别为 TREND
    # 修复后：price_change_6h 必填，字段完整时正确识别为 TREND
    from models.enums import MarketRegime
    assert result.market_regime == MarketRegime.TREND, "应该识别为 TREND"
    
    print(f"\n✅ TREND 识别正常工作！")
    print(f"  修复前: price_change_6h 缺失 → 默认0 → 永远是 RANGE")
    print(f"  修复后: price_change_6h 必填 → 4% → 正确识别 TREND")


def test_p0_bugfix4_impact_on_crowding_risk():
    """测试修复对拥挤风险检测的影响"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-4: 修复对拥挤风险检测的影响")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    print(f"\n场景: 拥挤风险（极端费率 + 高OI增长）")
    print(f"  funding_rate = 0.1% (> 0.05%阈值)")
    print(f"  oi_change_6h = 20% (> 15%阈值)")
    
    # 构造拥挤风险数据（注意：使用百分比点格式）
    crowding_data = {
        'price': 50000,
        'price_change_1h': 1.0,     # 1% (百分比点)
        'price_change_6h': 2.0,     # 2% (百分比点)
        'volume_1h': 100,
        'volume_24h': 2400,
        'buy_sell_imbalance': 0.3,
        'funding_rate': 0.1,        # 0.1% (百分比点)
        'oi_change_1h': 5.0,        # 5% (百分比点)
        'oi_change_6h': 20.0        # 20% (百分比点) - 高OI增长
    }
    
    result = engine.on_new_tick("BTCUSDT", crowding_data)
    
    print(f"\n决策结果:")
    print(f"  decision: {result.decision}")
    print(f"  primary_tags: {result.primary_tags}")
    
    # 修复前：如果 oi_change_6h 缺失（默认0），永远不会触发拥挤风险
    # 修复后：正确检测拥挤风险
    assert result.decision == Decision.NO_TRADE, "应该拒绝交易"
    assert ReasonTag.CROWDING_RISK in result.primary_tags, "应该触发拥挤风险"
    
    print(f"\n✅ 拥挤风险检测正常工作！")
    print(f"  修复前: oi_change_6h 缺失 → 默认0 → 永远不触发")
    print(f"  修复后: oi_change_6h 必填 → 20% → 正确触发风险警报")


def test_p0_bugfix4_comprehensive():
    """综合测试：验证修复的完整性"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-4: 综合验证")
    print("="*80)
    
    test_cases = [
        # (description, missing_field, should_fail)
        ("缺失 price_change_6h", "price_change_6h", True),
        ("缺失 oi_change_6h", "oi_change_6h", True),
        ("完整数据", None, False),
    ]
    
    engine = L1AdvisoryEngine()
    
    print(f"\n综合场景测试:")
    print(f"{'场景':<30} {'应失败':<10} {'实际结果':<15} {'状态'}")
    print("-" * 70)
    
    all_passed = True
    
    for desc, missing_field, should_fail in test_cases:
        # 基础完整数据（使用百分比点格式）
        data = {
            'price': 50000,
            'price_change_1h': 0.1,    # 0.1% (百分比点)
            'price_change_6h': 2.0,    # 2% (百分比点)
            'volume_1h': 100,
            'volume_24h': 2400,
            'buy_sell_imbalance': 0.3,
            'funding_rate': 0.01,      # 0.01% (百分比点)
            'oi_change_1h': 1.0,       # 1% (百分比点)
            'oi_change_6h': 5.0        # 5% (百分比点)
        }
        
        # 移除指定字段
        if missing_field:
            del data[missing_field]
        
        result = engine.on_new_tick("BTCUSDT", data)
        is_failed = (ReasonTag.INVALID_DATA in result.reason_tags)
        
        passed = (is_failed == should_fail)
        status = "✅" if passed else "❌"
        
        print(f"{desc:<30} {str(should_fail):<10} {str(is_failed):<15} {status}")
        
        if not passed:
            all_passed = False
    
    assert all_passed, "部分测试场景失败"
    
    print(f"\n✅ 综合验证通过！所有场景正确！")


if __name__ == "__main__":
    print("="*80)
    print("P0-BugFix-4 测试套件：修复关键字段缺失静默失败")
    print("="*80)
    
    try:
        test_p0_bugfix4_missing_price_change_6h()
        test_p0_bugfix4_missing_oi_change_6h()
        test_p0_bugfix4_missing_both_fields()
        test_p0_bugfix4_all_fields_present()
        test_p0_bugfix4_impact_on_trend_detection()
        test_p0_bugfix4_impact_on_crowding_risk()
        test_p0_bugfix4_comprehensive()
        
        print("\n" + "="*80)
        print("✅ 所有 P0-BugFix-4 测试通过！")
        print("="*80)
        
        print("\n修复验证:")
        print("  ✅ price_change_6h 和 oi_change_6h 已加入必填字段")
        print("  ✅ 字段缺失时正确 fail-fast")
        print("  ✅ TREND 市场环境识别恢复正常")
        print("  ✅ 拥挤风险检测恢复正常")
        
        print("\n修复前问题:")
        print("  ❌ price_change_6h 缺失 → 默认0 → TREND 永远不触发")
        print("  ❌ oi_change_6h 缺失 → 默认0 → 拥挤风险永远不触发")
        print("  ❌ 静默失败，不报错，难以察觉")
        
        print("\n修复后效果:")
        print("  ✅ 字段缺失立即报错")
        print("  ✅ 输出 INVALID_DATA + NO_TRADE")
        print("  ✅ 日志明确指出缺失字段")
        print("  ✅ 核心功能逻辑恢复正常")
        
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
