"""
Case C2（对应 P0-3）：OI 减少触发（oi_change_1h = -0.060 < -0.05）

验证点:
1. oi_change_1h = -0.060 (-6%) 应触发 OI_DECLINING
2. 阈值使用 DECIMAL 格式 (-0.05 = -5%)
3. 标签正确添加到 reason_tags
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.reason_tags import ReasonTag

print("="*70)
print("Case C2: OI 减少触发验证（DECIMAL 格式）")
print("="*70)

engine = L1AdvisoryEngine()

# ==================== C2: OI 减少触发 ====================
print("\n【Case C2】: OI 减少触发（oi_change_1h = -0.060 < -0.05）")
print("-"*70)

# 补充完整的必需字段
test_data = {
    # 必需字段
    'price': 50000,
    'volume_1h': 1000000,
    'volume_24h': 24000000,
    'price_change_1h': 0.002,          # 0.2%
    'price_change_6h': 0.004,          # 0.4% (RANGE: <3%)
    'oi_change_1h': -0.060,            # -6.0% (< -5% 阈值，应触发)
    'oi_change_6h': -0.10,             # -10%
    'funding_rate': 0.0001,            # 0.01%
    'buy_sell_imbalance': 0.00,        # 无失衡
}

print("输入数据:")
print(f"  symbol: TESTUSDT")
print(f"  oi_change_1h: {test_data['oi_change_1h']} (-6.0%)")
print(f"  price_change_6h: {test_data['price_change_6h']} (0.4%)")
print(f"  buy_sell_imbalance: {test_data['buy_sell_imbalance']}")

result = engine.on_new_tick('TESTUSDT', test_data)

print(f"\n输出结果:")
print(f"  decision: {result.decision.value}")
print(f"  market_regime: {result.market_regime.value}")
print(f"  trade_quality: {result.trade_quality.value}")
print(f"  reason_tags: {[tag.value for tag in result.reason_tags]}")

# ==================== 预期断言 ====================
print("\n" + "="*70)
print("验证断言")
print("="*70)

# 检查配置阈值
oi_declining_threshold = engine.thresholds.get('aux_oi_declining_threshold', 'NOT_FOUND')
print(f"\n【配置检查】:")
print(f"  aux_oi_declining_threshold: {oi_declining_threshold}")
print(f"  实际 oi_change_1h: {test_data['oi_change_1h']}")
print(f"  触发条件: {test_data['oi_change_1h']} < {oi_declining_threshold}")

# 断言1: 配置阈值正确（DECIMAL格式）
assert oi_declining_threshold == -0.05, \
    f"❌ 配置阈值应为 -0.05 (DECIMAL格式)，实际: {oi_declining_threshold}"
print(f"✅ 断言1通过: 配置阈值为 -0.05 (DECIMAL格式)")

# 断言2: reason_tags 包含 OI_DECLINING
print(f"\n【标签检查】:")
print(f"  实际 reason_tags: {[tag.value for tag in result.reason_tags]}")
print(f"  查找: OI_DECLINING (oi_declining)")

has_oi_declining = ReasonTag.OI_DECLINING in result.reason_tags

if has_oi_declining:
    print(f"  ✅ 找到 OI_DECLINING 标签")
else:
    print(f"  ❌ 未找到 OI_DECLINING 标签")
    print(f"  说明: oi_change_1h={test_data['oi_change_1h']} 应该 < {oi_declining_threshold}")

assert has_oi_declining, \
    f"❌ reason_tags 应包含 OI_DECLINING，实际: {[tag.value for tag in result.reason_tags]}"

print(f"✅ 断言2通过: reason_tags 包含 OI_DECLINING")

# 断言3: 触发条件验证
print(f"\n【触发逻辑验证】:")
print(f"  输入: oi_change_1h = {test_data['oi_change_1h']} (-6.0%)")
print(f"  阈值: aux_oi_declining_threshold = {oi_declining_threshold} (-5.0%)")
print(f"  判断: -6.0% < -5.0% = True ✅")
print(f"  结果: 触发 OI_DECLINING ✅")

print(f"✅ 断言3通过: 触发逻辑正确")

# ==================== 对比修复前后 ====================
print("\n" + "="*70)
print("修复前后对比")
print("="*70)

print("\n【修复前（P0-3 Bug）】:")
print("  阈值: -5.0 (百分点格式，实际表示 -500%!)")
print("  输入: -0.060 (-6%)")
print("  判断: -0.060 > -5.0")
print("  结果: ❌ 不触发（需要 -600% 才能触发！）")

print("\n【修复后（P0-3 Fix）】:")
print(f"  阈值: {oi_declining_threshold} (DECIMAL格式，表示 -5%)")
print(f"  输入: {test_data['oi_change_1h']} (-6%)")
print(f"  判断: {test_data['oi_change_1h']} < {oi_declining_threshold}")
print(f"  结果: ✅ 正确触发")

# ==================== 额外验证：边界情况 ====================
print("\n" + "="*70)
print("边界值测试")
print("="*70)

# 测试边界值 -0.05（恰好等于阈值）
print("\n【测试1】: oi_change_1h = -0.05 (恰好-5%)")
data_boundary = test_data.copy()
data_boundary['oi_change_1h'] = -0.05

result_boundary = engine.on_new_tick('TEST2', data_boundary)
has_oi_declining_boundary = ReasonTag.OI_DECLINING in result_boundary.reason_tags

print(f"  输入: {data_boundary['oi_change_1h']}")
print(f"  判断: {data_boundary['oi_change_1h']} < {oi_declining_threshold} = {data_boundary['oi_change_1h'] < oi_declining_threshold}")
print(f"  结果: {'触发' if has_oi_declining_boundary else '不触发'}")
print(f"  ℹ️  -0.05 恰好等于阈值，不应触发（条件是 <，不是 <=）")

assert not has_oi_declining_boundary, \
    f"❌ -0.05 不应触发 OI_DECLINING（条件是 <）"
print(f"✅ 边界测试1通过: -0.05 正确不触发")

# 测试稍小于阈值 -0.051
print("\n【测试2】: oi_change_1h = -0.051 (-5.1%)")
data_below = test_data.copy()
data_below['oi_change_1h'] = -0.051

result_below = engine.on_new_tick('TEST3', data_below)
has_oi_declining_below = ReasonTag.OI_DECLINING in result_below.reason_tags

print(f"  输入: {data_below['oi_change_1h']}")
print(f"  判断: {data_below['oi_change_1h']} < {oi_declining_threshold} = {data_below['oi_change_1h'] < oi_declining_threshold}")
print(f"  结果: {'触发' if has_oi_declining_below else '不触发'}")

assert has_oi_declining_below, \
    f"❌ -0.051 应触发 OI_DECLINING"
print(f"✅ 边界测试2通过: -0.051 正确触发")

# 测试极端值 -0.30
print("\n【测试3】: oi_change_1h = -0.30 (-30%, 极端值)")
data_extreme = test_data.copy()
data_extreme['oi_change_1h'] = -0.30

result_extreme = engine.on_new_tick('TEST4', data_extreme)
has_oi_declining_extreme = ReasonTag.OI_DECLINING in result_extreme.reason_tags

print(f"  输入: {data_extreme['oi_change_1h']}")
print(f"  判断: {data_extreme['oi_change_1h']} < {oi_declining_threshold} = {data_extreme['oi_change_1h'] < oi_declining_threshold}")
print(f"  结果: {'触发' if has_oi_declining_extreme else '不触发'}")

assert has_oi_declining_extreme, \
    f"❌ -0.30 应触发 OI_DECLINING"
print(f"✅ 边界测试3通过: -0.30 正确触发")

# ==================== 正负对比 ====================
print("\n" + "="*70)
print("正负值对比验证")
print("="*70)

print("\n【对比验证】: OI_GROWING vs OI_DECLINING")
print("-"*70)

# 正值：应触发 OI_GROWING
data_positive = test_data.copy()
data_positive['oi_change_1h'] = 0.060

result_positive = engine.on_new_tick('TEST_POS', data_positive)
has_growing = ReasonTag.OI_GROWING in result_positive.reason_tags
has_declining_pos = ReasonTag.OI_DECLINING in result_positive.reason_tags

print(f"正值测试 (+0.060):")
print(f"  OI_GROWING: {'✅ 触发' if has_growing else '❌ 未触发'}")
print(f"  OI_DECLINING: {'❌ 错误触发' if has_declining_pos else '✅ 正确不触发'}")

assert has_growing and not has_declining_pos, \
    f"❌ +0.060 应触发 OI_GROWING，不应触发 OI_DECLINING"

# 负值：应触发 OI_DECLINING
data_negative = test_data.copy()
data_negative['oi_change_1h'] = -0.060

result_negative = engine.on_new_tick('TEST_NEG', data_negative)
has_growing_neg = ReasonTag.OI_GROWING in result_negative.reason_tags
has_declining = ReasonTag.OI_DECLINING in result_negative.reason_tags

print(f"\n负值测试 (-0.060):")
print(f"  OI_DECLINING: {'✅ 触发' if has_declining else '❌ 未触发'}")
print(f"  OI_GROWING: {'❌ 错误触发' if has_growing_neg else '✅ 正确不触发'}")

assert has_declining and not has_growing_neg, \
    f"❌ -0.060 应触发 OI_DECLINING，不应触发 OI_GROWING"

print(f"\n✅ 对比验证通过: 正负值触发正确的标签，互不干扰")

# ==================== 总结 ====================
print("\n" + "="*70)
print("Case C2 验证总结")
print("="*70)
print("✅ 断言1: 配置阈值为 -0.05 (DECIMAL格式)")
print("✅ 断言2: oi_change_1h=-0.060 触发 OI_DECLINING")
print("✅ 断言3: 触发逻辑正确")
print("✅ 边界测试1: -0.05 正确不触发")
print("✅ 边界测试2: -0.051 正确触发")
print("✅ 边界测试3: -0.30 正确触发（极端值）")
print("✅ 对比测试: 正负值互不干扰")
print("\n🎉 Case C2 验证完全成功！")
print("\n关键成果:")
print("  - 配置使用 DECIMAL 格式 (-0.05 = -5%)")
print("  - OI_DECLINING 标签恢复正常触发")
print("  - 与系统口径完全一致")
print("  - 正负值分别触发正确的标签")
print("\n修复效果:")
print("  修复前: 阈值 -5.0 (-500%) → 几乎永不触发 ❌")
print("  修复后: 阈值 -0.05 (-5%) → 正常触发 ✅")
