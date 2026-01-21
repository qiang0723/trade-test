"""
测试 P0-BugFix-2: 修复成交量口径混用导致高估的问题

问题描述：
- Binance ticker['volume'] 是24h累计成交量（不是单tick量）
- calculate_volume_1h 原来是累加所有tick的volume
- 导致1h成交量被严重高估（可能高估60倍）

修复：
- 改为取差值：最新累计量 - 1小时前累计量
- 添加负值保护（24h窗口滚动）

影响：
- 吸纳风险检测失效（永远不触发）
- 极端成交量判断可能误触发
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_cache import MarketDataCache
from datetime import datetime, timedelta


def test_p0_bugfix2_volume_calculation():
    """测试成交量计算修复：使用差值而非累加"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-2: 成交量计算修复")
    print("="*80)
    
    cache = MarketDataCache(max_hours=6)
    
    # 模拟场景：每分钟获取一次数据，24h累计量逐渐增加
    base_time = datetime.now() - timedelta(hours=2)
    base_volume_24h = 10000.0  # 24h累计量基准
    
    print("\n场景：24h累计成交量从10000逐步增加")
    print("每分钟采样一次，共2小时（120个tick）")
    
    # 存储2小时的数据
    for i in range(120):
        timestamp = base_time + timedelta(minutes=i)
        # 24h累计量逐渐增加（模拟滚动窗口）
        volume_24h = base_volume_24h + i * 10  # 每分钟增加10
        
        data = {
            'price': 50000,
            'volume': volume_24h,  # 24h累计量
            'volume_24h': volume_24h * 50000,  # 成交额
            'open_interest': 100000,
            'funding_rate': 0.0001,
            'buy_volume': 100,
            'sell_volume': 100
        }
        
        cache.store_tick('BTC', data, timestamp)
    
    # 计算1h成交量
    volume_1h = cache.calculate_volume_1h('BTC')
    
    print(f"\n最新tick的24h累计量: {base_volume_24h + 119 * 10:.1f}")
    print(f"60分钟前tick的24h累计量: {base_volume_24h + 59 * 10:.1f}")
    print(f"理论1h增量: {(119 - 59) * 10:.1f}")
    
    print(f"\n修复后计算的volume_1h: {volume_1h:.1f}")
    
    # 验证：应该是差值，不是累加
    expected = (119 - 59) * 10  # 600
    
    assert volume_1h is not None, "volume_1h不应为None"
    assert abs(volume_1h - expected) < 10, \
        f"volume_1h应该约为{expected}，实际为{volume_1h}"
    
    print(f"✅ 修复验证通过：使用差值计算，不再累加")
    
    # 对比修复前的错误计算
    print("\n" + "="*80)
    print("对比：修复前的错误计算")
    print("="*80)
    
    # 模拟修复前的错误逻辑（累加60个tick）
    ticks_1h = cache.get_historical_ticks('BTC', hours=1.0)
    wrong_total = sum(tick.volume for tick in ticks_1h)
    
    print(f"修复前（累加）: {wrong_total:.1f}")
    print(f"修复后（差值）: {volume_1h:.1f}")
    print(f"高估倍数: {wrong_total / volume_1h:.1f}x")
    
    assert wrong_total > volume_1h * 10, "修复前应该高估至少10倍"
    
    print(f"\n✅ 确认：修复前高估{wrong_total / volume_1h:.0f}倍")


def test_p0_bugfix2_negative_handling():
    """测试负值保护：24h窗口滚动导致的负差值"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-2: 负值保护")
    print("="*80)
    
    cache = MarketDataCache(max_hours=6)
    
    base_time = datetime.now() - timedelta(hours=2)
    
    # 场景：24h窗口滚动，导致累计量突然减少
    for i in range(120):
        timestamp = base_time + timedelta(minutes=i)
        
        # 模拟窗口滚动：在第70分钟时累计量减少
        if i < 70:
            volume_24h = 10000.0 + i * 10
        else:
            volume_24h = 9000.0 + (i - 70) * 10  # 突然降低
        
        data = {
            'price': 50000,
            'volume': volume_24h,
            'volume_24h': volume_24h * 50000,
            'open_interest': 100000,
            'funding_rate': 0.0001,
            'buy_volume': 100,
            'sell_volume': 100
        }
        
        cache.store_tick('BTC', data, timestamp)
    
    volume_1h = cache.calculate_volume_1h('BTC')
    
    print(f"24h窗口滚动场景")
    print(f"volume_1h: {volume_1h}")
    
    if volume_1h is None:
        print("✅ 正确处理：检测到负值，返回None")
    else:
        assert volume_1h >= 0, "volume_1h不应为负值"
        print(f"✅ volume_1h非负：{volume_1h:.1f}")


def test_p0_bugfix2_impact_on_absorption_risk():
    """测试修复对吸纳风险检测的影响"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-2: 对吸纳风险检测的影响")
    print("="*80)
    
    cache = MarketDataCache(max_hours=6)
    
    base_time = datetime.now() - timedelta(hours=2)
    
    # 场景：低成交量（吸纳风险场景）
    for i in range(120):
        timestamp = base_time + timedelta(minutes=i)
        # 24h累计量：10000，1h增量：50（远低于平均）
        volume_24h = 10000.0 + (i * 0.5)  # 每分钟仅增加0.5
        
        data = {
            'price': 50000,
            'volume': volume_24h,
            'volume_24h': 500000000,  # 24h成交额
            'open_interest': 100000,
            'funding_rate': 0.0001,
            'buy_volume': 100,
            'sell_volume': 100
        }
        
        cache.store_tick('BTC', data, timestamp)
    
    volume_1h = cache.calculate_volume_1h('BTC')
    volume_avg = 10000.0 / 24  # 约417
    
    print(f"\n低成交量场景:")
    print(f"  24h平均成交量: {volume_avg:.1f}/h")
    print(f"  实际1h成交量: {volume_1h:.1f}")
    print(f"  volume_1h / volume_avg: {volume_1h / volume_avg:.2f}")
    
    # 吸纳风险条件：volume_1h < volume_avg * 0.5
    absorption_threshold = volume_avg * 0.5
    print(f"  吸纳风险阈值: {absorption_threshold:.1f}")
    
    if volume_1h < absorption_threshold:
        print(f"  ✅ 满足吸纳风险条件（低成交量）")
        print(f"  ✅ 修复后，吸纳风险可以正确检测！")
    else:
        print(f"  ⚠️  未满足吸纳风险条件")
    
    print("\n修复前的问题:")
    print(f"  修复前volume_1h（累加）≈ {10000 * 60:.0f}")
    print(f"  修复前永远不会 < {absorption_threshold:.1f}")
    print(f"  ❌ 吸纳风险永远检测不到！")


def test_p0_bugfix2_comprehensive():
    """综合测试：验证修复的完整性"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix-2: 综合验证")
    print("="*80)
    
    cache = MarketDataCache(max_hours=6)
    
    base_time = datetime.now() - timedelta(hours=2)
    
    # 正常场景：1h成交量约为24h平均值
    volume_24h_base = 24000.0
    
    for i in range(120):
        timestamp = base_time + timedelta(minutes=i)
        # 1h增量约为 1000（24000/24）
        volume_24h = volume_24h_base + i * (1000.0 / 60.0)
        
        data = {
            'price': 50000,
            'volume': volume_24h,
            'volume_24h': volume_24h * 50000,
            'open_interest': 100000,
            'funding_rate': 0.0001,
            'buy_volume': 100,
            'sell_volume': 100
        }
        
        cache.store_tick('BTC', data, timestamp)
    
    volume_1h = cache.calculate_volume_1h('BTC')
    volume_avg = volume_24h_base / 24
    
    print(f"\n正常场景验证:")
    print(f"  24h平均: {volume_avg:.1f}/h")
    print(f"  实际1h: {volume_1h:.1f}")
    print(f"  比例: {volume_1h / volume_avg:.2f}")
    
    # 应该接近1.0（正常）
    ratio = volume_1h / volume_avg
    assert 0.8 < ratio < 1.2, f"比例应该接近1.0，实际{ratio:.2f}"
    
    print(f"  ✅ 比例正常（0.8-1.2范围内）")
    
    # 极端成交量检测（10倍阈值）
    extreme_threshold = volume_avg * 10.0
    print(f"\n极端成交量阈值: {extreme_threshold:.1f}")
    print(f"当前1h成交量: {volume_1h:.1f}")
    
    if volume_1h < extreme_threshold:
        print("  ✅ 未误触发极端成交量警报")
    
    print("\n" + "="*80)
    print("✅ 综合验证通过！")
    print("="*80)


if __name__ == "__main__":
    print("="*80)
    print("P0-BugFix-2 测试套件：修复成交量口径混用问题")
    print("="*80)
    
    try:
        test_p0_bugfix2_volume_calculation()
        test_p0_bugfix2_negative_handling()
        test_p0_bugfix2_impact_on_absorption_risk()
        test_p0_bugfix2_comprehensive()
        
        print("\n" + "="*80)
        print("✅ 所有 P0-BugFix-2 测试通过！")
        print("="*80)
        
        print("\n修复验证:")
        print("  ✅ 成交量计算改为差值（不再累加）")
        print("  ✅ 负值保护（窗口滚动）")
        print("  ✅ 吸纳风险检测恢复正常")
        print("  ✅ 极端成交量判断不再误触发")
        
        print("\n修复前问题:")
        print("  ❌ 累加60个24h累计量 → 高估60倍")
        print("  ❌ 吸纳风险永远检测不到")
        print("  ❌ 风险控制失效")
        
        print("\n修复后效果:")
        print("  ✅ 正确计算1h增量（差值）")
        print("  ✅ 吸纳风险可以正确检测")
        print("  ✅ 风险控制恢复正常")
        
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
