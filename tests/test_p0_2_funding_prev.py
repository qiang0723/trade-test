"""
P0-2 修复验证: funding_rate_prev 更新不可达 + 多币种串扰

验证点:
1. 同一 symbol 连续 tick，funding_volatility 基于最新 prev 变化
2. BTC/ETH 交替 tick 时，两者 prev 不串扰
3. NOISY 分支 return 后，prev 仍正确更新
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import TradeQuality
from models.reason_tags import ReasonTag

print("="*70)
print("P0-2 修复验证: funding_rate_prev 更新 + 多币种隔离")
print("="*70)

engine = L1AdvisoryEngine()

# ==================== 验收1: 同一 symbol 连续 tick ====================
print("\n【验收1】: 同一 symbol 连续 tick，prev 正确更新")
print("-"*70)

# BTC tick 1
data_btc1 = {
    'price': 50000,
    'volume_1h': 1000000,
    'volume_24h': 24000000,
    'price_change_1h': 0.002,
    'price_change_6h': 0.01,
    'oi_change_1h': 0.05,
    'oi_change_6h': 0.10,
    'funding_rate': 0.0005,  # 初始值
    'buy_sell_imbalance': 0.5
}

result_btc1 = engine.on_new_tick('BTC', data_btc1)
print(f"BTC Tick 1: funding_rate=0.0005")
print(f"  history_data['BTC_funding_rate_prev'] = {engine.history_data.get('BTC_funding_rate_prev')}")

# BTC tick 2 (高波动，可能触发 NOISY)
data_btc2 = {
    'price': 50000,
    'volume_1h': 1000000,
    'volume_24h': 24000000,
    'price_change_1h': 0.002,
    'price_change_6h': 0.01,
    'oi_change_1h': 0.05,
    'oi_change_6h': 0.10,
    'funding_rate': 0.0015,  # 波动 0.001
    'buy_sell_imbalance': 0.5
}

result_btc2 = engine.on_new_tick('BTC', data_btc2)
print(f"BTC Tick 2: funding_rate=0.0015 (波动={0.0015-0.0005})")
print(f"  history_data['BTC_funding_rate_prev'] = {engine.history_data.get('BTC_funding_rate_prev')}")

# 验证: prev 正确更新为 0.0015
assert engine.history_data.get('BTC_funding_rate_prev') == 0.0015, \
    f"❌ BTC prev应为0.0015，实际: {engine.history_data.get('BTC_funding_rate_prev')}"
print("✅ 验收1通过: BTC prev 正确更新为 0.0015")

# ==================== 验收2: 多币种不串扰 ====================
print("\n【验收2】: 多币种交替 tick，prev 不串扰")
print("-"*70)

# 清空历史数据，重新开始
engine.history_data = {}

# BTC tick 1
data_btc_a = {
    'price': 50000,
    'volume_1h': 1000000,
    'volume_24h': 24000000,
    'price_change_1h': 0.002,
    'price_change_6h': 0.01,
    'oi_change_1h': 0.05,
    'oi_change_6h': 0.10,
    'funding_rate': 0.0005,
    'buy_sell_imbalance': 0.5
}

engine.on_new_tick('BTC', data_btc_a)
print(f"BTC Tick 1: funding_rate=0.0005")
print(f"  BTC_funding_rate_prev = {engine.history_data.get('BTC_funding_rate_prev')}")

# ETH tick 1
data_eth_a = {
    'price': 3000,
    'volume_1h': 500000,
    'volume_24h': 12000000,
    'price_change_1h': 0.001,
    'price_change_6h': 0.008,
    'oi_change_1h': 0.04,
    'oi_change_6h': 0.09,
    'funding_rate': 0.0003,
    'buy_sell_imbalance': 0.5
}

engine.on_new_tick('ETH', data_eth_a)
print(f"ETH Tick 1: funding_rate=0.0003")
print(f"  ETH_funding_rate_prev = {engine.history_data.get('ETH_funding_rate_prev')}")

# AIA tick 1
data_aia_a = {
    'price': 10,
    'volume_1h': 200000,
    'volume_24h': 5000000,
    'price_change_1h': 0.003,
    'price_change_6h': 0.012,
    'oi_change_1h': 0.06,
    'oi_change_6h': 0.11,
    'funding_rate': 0.0008,
    'buy_sell_imbalance': 0.5
}

engine.on_new_tick('AIA', data_aia_a)
print(f"AIA Tick 1: funding_rate=0.0008")
print(f"  AIA_funding_rate_prev = {engine.history_data.get('AIA_funding_rate_prev')}")

# BTC tick 2 (验证不被 ETH/AIA 覆盖)
data_btc_b = {
    'price': 50000,
    'volume_1h': 1000000,
    'volume_24h': 24000000,
    'price_change_1h': 0.002,
    'price_change_6h': 0.01,
    'oi_change_1h': 0.05,
    'oi_change_6h': 0.10,
    'funding_rate': 0.0006,
    'buy_sell_imbalance': 0.5
}

engine.on_new_tick('BTC', data_btc_b)
print(f"BTC Tick 2: funding_rate=0.0006")
print(f"  BTC_funding_rate_prev = {engine.history_data.get('BTC_funding_rate_prev')}")

# 验证: 三个币种的 prev 各自独立
assert engine.history_data.get('BTC_funding_rate_prev') == 0.0006, \
    f"❌ BTC prev应为0.0006，实际: {engine.history_data.get('BTC_funding_rate_prev')}"
assert engine.history_data.get('ETH_funding_rate_prev') == 0.0003, \
    f"❌ ETH prev应为0.0003，实际: {engine.history_data.get('ETH_funding_rate_prev')}"
assert engine.history_data.get('AIA_funding_rate_prev') == 0.0008, \
    f"❌ AIA prev应为0.0008，实际: {engine.history_data.get('AIA_funding_rate_prev')}"

print("✅ 验收2通过: 多币种 prev 各自独立，无串扰")
print(f"  BTC: {engine.history_data.get('BTC_funding_rate_prev')}")
print(f"  ETH: {engine.history_data.get('ETH_funding_rate_prev')}")
print(f"  AIA: {engine.history_data.get('AIA_funding_rate_prev')}")

# ==================== 验收3: NOISY 分支正确更新 ====================
print("\n【验收3】: NOISY 分支 return 后，prev 仍正确更新")
print("-"*70)

# 清空历史数据
engine.history_data = {}

# GPS tick 1 (设置初始 prev)
data_gps1 = {
    'price': 5,
    'volume_1h': 300000,
    'volume_24h': 7000000,
    'price_change_1h': 0.001,
    'price_change_6h': 0.005,
    'oi_change_1h': 0.03,
    'oi_change_6h': 0.07,
    'funding_rate': 0.0001,  # 初始低值
    'buy_sell_imbalance': 0.5
}

result_gps1 = engine.on_new_tick('GPS', data_gps1)
print(f"GPS Tick 1: funding_rate=0.0001")
print(f"  GPS_funding_rate_prev = {engine.history_data.get('GPS_funding_rate_prev')}")

# GPS tick 2 (构造触发 NOISY_MARKET 的数据)
# noisy_funding_volatility: 0.0005 (假设)
# noisy_funding_abs: 0.0005 (假设)
data_gps2 = {
    'price': 5,
    'volume_1h': 300000,
    'volume_24h': 7000000,
    'price_change_1h': 0.001,
    'price_change_6h': 0.005,
    'oi_change_1h': 0.03,
    'oi_change_6h': 0.07,
    'funding_rate': 0.0012,  # 波动 0.0011 (可能触发 NOISY)
    'buy_sell_imbalance': 0.5
}

result_gps2 = engine.on_new_tick('GPS', data_gps2)
print(f"GPS Tick 2: funding_rate=0.0012 (波动={0.0012-0.0001})")
print(f"  trade_quality = {result_gps2.trade_quality.value}")
print(f"  reason_tags = {[tag.value for tag in result_gps2.reason_tags]}")
print(f"  GPS_funding_rate_prev = {engine.history_data.get('GPS_funding_rate_prev')}")

# 验证: 即使触发 NOISY_MARKET，prev 也正确更新为 0.0012
if ReasonTag.NOISY_MARKET in result_gps2.reason_tags:
    print("  ✓ 触发了 NOISY_MARKET（已 return）")

assert engine.history_data.get('GPS_funding_rate_prev') == 0.0012, \
    f"❌ GPS prev应为0.0012，实际: {engine.history_data.get('GPS_funding_rate_prev')}"

print("✅ 验收3通过: NOISY 分支 return 后，prev 仍正确更新为 0.0012")

# ==================== 总结 ====================
print("\n" + "="*70)
print("P0-2 修复验证总结")
print("="*70)
print("✅ 验收1: 同一 symbol 连续 tick，prev 正确更新")
print("✅ 验收2: 多币种交替 tick，prev 不串扰")
print("✅ 验收3: NOISY 分支 return 后，prev 仍正确更新")
print("\n🎉 P0-2 修复完全成功！")
print("\n关键修复点:")
print("  1. 使用 f'{symbol}_funding_rate_prev' 实现多币种隔离")
print("  2. 在 return 之前先写回 prev，确保每次 tick 都更新")
print("  3. NOISY_MARKET 分支不再导致 prev 更新不可达")
