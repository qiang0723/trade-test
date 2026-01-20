"""
P0-1修复验证脚本（简化版）
直接测试 _eval_trade_quality 方法
"""

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import TradeQuality, MarketRegime
from models.reason_tags import ReasonTag

print("="*70)
print("P0-1修复验证: WEAK_SIGNAL_IN_RANGE 质量评级")
print("="*70)

engine = L1AdvisoryEngine()

# 测试数据：RANGE环境 + 弱信号
data = {
    'price': 50000,
    'price_change_1h': 0.005,
    'price_change_6h': 0.015,  # RANGE (<3%)
    'volume_1h': 1000000,
    'volume_24h': 24000000,
    'buy_sell_imbalance': 0.5,  # < 0.6 (弱失衡)
    'funding_rate': 0.0001,
    'oi_change_1h': 0.08,  # < 0.10 (弱OI变化)
    'oi_change_6h': 0.15
}

# 调用质量评估方法
quality, tags = engine._eval_trade_quality(data, MarketRegime.RANGE)

print(f"\n测试场景: RANGE环境 + 弱信号")
print(f"  buy_sell_imbalance: {data['buy_sell_imbalance']} (< 0.6)")
print(f"  oi_change_1h: {data['oi_change_1h']} (< 0.10)")
print(f"\n结果:")
print(f"  质量评级: {quality.value}")
print(f"  原因标签: {[tag.value for tag in tags]}")

print(f"\n验证:")
if ReasonTag.WEAK_SIGNAL_IN_RANGE in tags:
    print(f"  ✅ 触发了 WEAK_SIGNAL_IN_RANGE 标签")
else:
    print(f"  ❌ 未触发 WEAK_SIGNAL_IN_RANGE 标签")

if quality == TradeQuality.UNCERTAIN:
    print(f"  ✅ 质量评级是 UNCERTAIN（修复成功！）")
    print(f"\n🎉 P0-1修复验证通过！")
    print(f"     WEAK_SIGNAL_IN_RANGE 不再被 POOR 短路")
    print(f"     可以进入 ExecutionPermission + 双门槛逻辑")
elif quality == TradeQuality.POOR:
    print(f"  ❌ 质量评级是 POOR（修复失败）")
    print(f"\n❌ P0-1修复未生效，仍会被主流程短路")
else:
    print(f"  ⚠️  质量评级是 {quality.value}（未预期）")

print("="*70)
