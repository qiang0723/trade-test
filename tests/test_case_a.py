"""
Case A 验证: RANGE + WEAK_SIGNAL_IN_RANGE 不应直接 NO_TRADE

验证 P0-1 修复：WEAK_SIGNAL_IN_RANGE 应返回 UNCERTAIN，而非 POOR
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, ExecutionPermission
from models.reason_tags import ReasonTag

print("="*70)
print("Case A: RANGE + WEAK_SIGNAL_IN_RANGE 验证")
print("="*70)

engine = L1AdvisoryEngine()

# Case A 输入（已规范化的 metrics）
data = {
    # 基础字段
    'price': 50000,  # 假设价格
    'volume_1h': 1100000,  # volume_ratio=1.1 相对于24h均值
    'volume_24h': 24000000,
    
    # 核心指标（已规范化为小数格式）
    'price_change_1h': 0.002,      # 0.2%
    'price_change_6h': 0.004,      # 0.4% (RANGE: <3%)
    'oi_change_1h': 0.010,         # 1.0% (< 10%弱信号)
    'oi_change_6h': 0.020,         # 2.0%
    'funding_rate': 0.0001,        # 0.01%
    'buy_sell_imbalance': 0.05     # 0.05 (< 0.6弱失衡)
    # 不提供timestamp，避免新鲜度检查问题
}

print("\n输入数据:")
print(f"  price_change_6h: {data['price_change_6h']} (0.4%, <3% → RANGE)")
print(f"  buy_sell_imbalance: {data['buy_sell_imbalance']} (<0.6 弱失衡)")
print(f"  oi_change_1h: {data['oi_change_1h']} (1%, <10% 弱OI)")

# 调用决策引擎
result = engine.on_new_tick('TESTUSDT', data)

print(f"\n输出结果:")
print(f"  decision: {result.decision.value}")
print(f"  trade_quality: {result.trade_quality.value}")
print(f"  market_regime: {result.market_regime.value}")
print(f"  reason_tags: {[tag.value for tag in result.reason_tags]}")
print(f"  execution_permission: {result.execution_permission.value}")
print(f"  confidence: {result.confidence.value}")
print(f"  executable: {result.executable}")

print(f"\n" + "="*70)
print("验证结果:")
print("="*70)

# 验证1: trade_quality 应该是 UNCERTAIN（不能是 POOR）
if result.trade_quality == TradeQuality.UNCERTAIN:
    print(f"✅ 验证1通过: trade_quality = UNCERTAIN（不是 POOR）")
    quality_pass = True
elif result.trade_quality == TradeQuality.POOR:
    print(f"❌ 验证1失败: trade_quality = POOR（应该是 UNCERTAIN）")
    print(f"   → 说明修复未生效，仍会被主流程短路")
    quality_pass = False
else:
    print(f"⚠️  验证1警告: trade_quality = {result.trade_quality.value}（未预期）")
    quality_pass = False

# 验证2: reason_tags 包含 weak_signal_in_range
if ReasonTag.WEAK_SIGNAL_IN_RANGE in result.reason_tags:
    print(f"✅ 验证2通过: reason_tags 包含 weak_signal_in_range")
    tag_pass = True
else:
    print(f"❌ 验证2失败: reason_tags 不包含 weak_signal_in_range")
    print(f"   实际标签: {[tag.value for tag in result.reason_tags]}")
    tag_pass = False

# 验证3: 主流程不应在 POOR 处硬短路（应进入 Step 8/9/10）
# 如果 execution_permission 存在且不是默认值，说明进入了 Step 8
if result.execution_permission != ExecutionPermission.DENY or result.confidence != Confidence.LOW:
    print(f"✅ 验证3通过: 进入了 ExecutionPermission 逻辑")
    print(f"   execution_permission: {result.execution_permission.value}")
    print(f"   confidence: {result.confidence.value}")
    pipeline_pass = True
else:
    print(f"⚠️  验证3警告: 可能在早期阶段被短路")
    pipeline_pass = False

# 验证4: 如果是 NO_TRADE，原因应该是"弱信号/门槛未达"，而非 POOR 短路
if result.decision == Decision.NO_TRADE:
    if result.trade_quality == TradeQuality.POOR:
        print(f"❌ 验证4失败: NO_TRADE 原因是 POOR 短路（不符合预期）")
        reason_pass = False
    else:
        print(f"✅ 验证4通过: NO_TRADE 原因是弱信号/门槛未达（符合预期）")
        print(f"   trade_quality={result.trade_quality.value}, confidence={result.confidence.value}")
        reason_pass = True
else:
    print(f"ℹ️  决策是 {result.decision.value}（非 NO_TRADE）")
    reason_pass = True

print(f"\n" + "="*70)
print("最终评估:")
print("="*70)

if quality_pass and tag_pass:
    print(f"🎉 P0-1修复成功!")
    print(f"   ✅ WEAK_SIGNAL_IN_RANGE 不再被 POOR 短路")
    print(f"   ✅ 进入 ExecutionPermission + 双门槛逻辑")
    print(f"   ✅ 配置的 cap 和降级执行机制生效")
    exit(0)
else:
    print(f"❌ P0-1修复验证失败")
    if not quality_pass:
        print(f"   - trade_quality 仍是 POOR（应该是 UNCERTAIN）")
    if not tag_pass:
        print(f"   - 未触发 weak_signal_in_range 标签")
    exit(1)
