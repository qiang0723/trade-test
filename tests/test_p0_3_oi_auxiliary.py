"""
P0-3 修复验证: OI 辅助标签阈值口径修正

验证点:
1. oi_change_1h=0.06 (6%) 时能触发 OI_GROWING
2. oi_change_1h=-0.06 (-6%) 时能触发 OI_DECLINING
3. 边界值不触发（0.04 不应触发）
4. 极端值正确触发（0.50 应触发）
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.reason_tags import ReasonTag

print("="*70)
print("P0-3 修复验证: OI 辅助标签阈值口径修正")
print("="*70)

engine = L1AdvisoryEngine()

# 基础数据模板（使用decimal格式避免转换）
base_data = {
    'price': 50000,
    'volume_1h': 1000000,
    'volume_24h': 24000000,
    'price_change_1h': 0.002,
    'price_change_6h': 0.01,
    'oi_change_6h': 0.10,
    'funding_rate': 0.0001,
    'buy_sell_imbalance': 0.5,
    '_metadata': {'percentage_format': 'decimal'}  # P0修复：避免格式转换
}

# ==================== 验收1: OI_GROWING 正确触发 ====================
print("\n【验收1】: oi_change_1h=0.06 (6%) 触发 OI_GROWING")
print("-"*70)

data1 = base_data.copy()
data1['oi_change_1h'] = 0.06  # 6% (> 5%)

result1 = engine.on_new_tick('BTC', data1)

print(f"输入: oi_change_1h = 0.06 (6%)")
print(f"配置阈值: aux_oi_growing_threshold = {engine.thresholds.get('aux_oi_growing_threshold', '未配置')}")
print(f"reason_tags: {[tag.value for tag in result1.reason_tags]}")

# 验证
if ReasonTag.OI_GROWING in result1.reason_tags:
    print("✅ 验收1通过: OI_GROWING 正确触发")
else:
    print("❌ 验收1失败: OI_GROWING 未触发")
    print(f"   实际标签: {[tag.value for tag in result1.reason_tags]}")

assert ReasonTag.OI_GROWING in result1.reason_tags, \
    f"❌ 应包含 OI_GROWING，实际: {[tag.value for tag in result1.reason_tags]}"

# ==================== 验收2: OI_DECLINING 正确触发 ====================
print("\n【验收2】: oi_change_1h=-0.06 (-6%) 触发 OI_DECLINING")
print("-"*70)

data2 = base_data.copy()
data2['oi_change_1h'] = -0.06  # -6% (< -5%)

result2 = engine.on_new_tick('ETH', data2)

print(f"输入: oi_change_1h = -0.06 (-6%)")
print(f"配置阈值: aux_oi_declining_threshold = {engine.thresholds.get('aux_oi_declining_threshold', '未配置')}")
print(f"reason_tags: {[tag.value for tag in result2.reason_tags]}")

# 验证
if ReasonTag.OI_DECLINING in result2.reason_tags:
    print("✅ 验收2通过: OI_DECLINING 正确触发")
else:
    print("❌ 验收2失败: OI_DECLINING 未触发")
    print(f"   实际标签: {[tag.value for tag in result2.reason_tags]}")

assert ReasonTag.OI_DECLINING in result2.reason_tags, \
    f"❌ 应包含 OI_DECLINING，实际: {[tag.value for tag in result2.reason_tags]}"

# ==================== 验收3: 边界值不触发 ====================
print("\n【验收3】: oi_change_1h=0.04 (4%) 不触发（边界值测试）")
print("-"*70)

data3 = base_data.copy()
data3['oi_change_1h'] = 0.04  # 4% (< 5%，未达阈值)

result3 = engine.on_new_tick('AIA', data3)

print(f"输入: oi_change_1h = 0.04 (4%)")
print(f"reason_tags: {[tag.value for tag in result3.reason_tags]}")

# 验证
if ReasonTag.OI_GROWING not in result3.reason_tags:
    print("✅ 验收3通过: OI_GROWING 正确不触发（未达阈值）")
else:
    print("❌ 验收3失败: OI_GROWING 错误触发")

assert ReasonTag.OI_GROWING not in result3.reason_tags, \
    f"❌ 不应包含 OI_GROWING，实际: {[tag.value for tag in result3.reason_tags]}"

# 边界值负向测试
data3b = base_data.copy()
data3b['oi_change_1h'] = -0.04  # -4% (> -5%，未达阈值)

result3b = engine.on_new_tick('GPS', data3b)

print(f"输入: oi_change_1h = -0.04 (-4%)")
print(f"reason_tags: {[tag.value for tag in result3b.reason_tags]}")

if ReasonTag.OI_DECLINING not in result3b.reason_tags:
    print("✅ 验收3b通过: OI_DECLINING 正确不触发（未达阈值）")
else:
    print("❌ 验收3b失败: OI_DECLINING 错误触发")

assert ReasonTag.OI_DECLINING not in result3b.reason_tags, \
    f"❌ 不应包含 OI_DECLINING，实际: {[tag.value for tag in result3b.reason_tags]}"

# ==================== 验收4: 极端值正确触发 ====================
print("\n【验收4】: oi_change_1h=0.50 (50%) 触发 OI_GROWING（极端值）")
print("-"*70)

data4 = base_data.copy()
data4['oi_change_1h'] = 0.50  # 50% (远超阈值)

result4 = engine.on_new_tick('BTC', data4)

print(f"输入: oi_change_1h = 0.50 (50%)")
print(f"reason_tags: {[tag.value for tag in result4.reason_tags]}")

# 验证
if ReasonTag.OI_GROWING in result4.reason_tags:
    print("✅ 验收4通过: OI_GROWING 正确触发（极端值）")
else:
    print("❌ 验收4失败: OI_GROWING 未触发")

assert ReasonTag.OI_GROWING in result4.reason_tags, \
    f"❌ 应包含 OI_GROWING，实际: {[tag.value for tag in result4.reason_tags]}"

# 极端值负向测试
data4b = base_data.copy()
data4b['oi_change_1h'] = -0.30  # -30% (远超阈值)

result4b = engine.on_new_tick('ETH', data4b)

print(f"输入: oi_change_1h = -0.30 (-30%)")
print(f"reason_tags: {[tag.value for tag in result4b.reason_tags]}")

if ReasonTag.OI_DECLINING in result4b.reason_tags:
    print("✅ 验收4b通过: OI_DECLINING 正确触发（极端值）")
else:
    print("❌ 验收4b失败: OI_DECLINING 未触发")

assert ReasonTag.OI_DECLINING in result4b.reason_tags, \
    f"❌ 应包含 OI_DECLINING，实际: {[tag.value for tag in result4b.reason_tags]}"

# ==================== 验收5: 精确边界测试 ====================
print("\n【验收5】: 精确边界值测试（0.05/-0.05）")
print("-"*70)

# 正向精确边界（应该不触发，因为是 > 而非 >=）
data5a = base_data.copy()
data5a['oi_change_1h'] = 0.05  # 恰好 5%

result5a = engine.on_new_tick('AIA', data5a)
print(f"输入: oi_change_1h = 0.05 (恰好5%)")
print(f"reason_tags: {[tag.value for tag in result5a.reason_tags]}")
print(f"  ℹ️  0.05 不应触发（阈值是 > 0.05）")

# 稍大于边界（应该触发）
data5b = base_data.copy()
data5b['oi_change_1h'] = 0.051  # 5.1%

result5b = engine.on_new_tick('GPS', data5b)
print(f"输入: oi_change_1h = 0.051 (5.1%)")
print(f"reason_tags: {[tag.value for tag in result5b.reason_tags]}")

if ReasonTag.OI_GROWING in result5b.reason_tags:
    print("✅ 验收5通过: 0.051 正确触发 OI_GROWING")
else:
    print("❌ 验收5失败: 0.051 未触发")

assert ReasonTag.OI_GROWING in result5b.reason_tags, \
    f"❌ 0.051 应触发，实际: {[tag.value for tag in result5b.reason_tags]}"

# ==================== 总结 ====================
print("\n" + "="*70)
print("P0-3 修复验证总结")
print("="*70)
print("✅ 验收1: oi_change_1h=0.06 正确触发 OI_GROWING")
print("✅ 验收2: oi_change_1h=-0.06 正确触发 OI_DECLINING")
print("✅ 验收3: 边界值 0.04/-0.04 正确不触发")
print("✅ 验收4: 极端值 0.50/-0.30 正确触发")
print("✅ 验收5: 精确边界值 0.051 正确触发")
print("\n🎉 P0-3 修复完全成功！")
print("\n关键修复点:")
print("  1. 配置文件新增 aux_oi_growing_threshold: 0.05")
print("  2. 配置文件新增 aux_oi_declining_threshold: -0.05")
print("  3. 代码改用配置化阈值（从 5.0 → 0.05）")
print("  4. 与系统 DECIMAL 口径完全一致")
print("\n修复前: 阈值 5.0 (500%) → 几乎永不触发 ❌")
print("修复后: 阈值 0.05 (5%) → 正常触发 ✅")
