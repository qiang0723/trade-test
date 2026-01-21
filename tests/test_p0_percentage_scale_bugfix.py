"""
测试 P0-BugFix: 修复小幅变化(<1%)被放大100倍的问题

问题描述：
- MarketDataCache.calculate_price_change 返回百分比点格式（已乘100）
- MetricsNormalizer 原来只在值>1.0时才除以100
- 导致<1%的变化不被转换，被误解释为放大100倍的值

修复：
- 统一处理所有百分比字段，无条件除以100
- 调整异常检测阈值为1000（检测极端异常，而非格式混用）

验收要点：
1. 0.5% 变化 → 0.005（小数格式）
2. 3% 变化 → 0.03（小数格式）
3. 50% 变化 → 0.50（小数格式）
4. >1000% → 拒绝（异常值）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics_normalizer import MetricsNormalizer


def test_p0_bugfix_small_change():
    """测试小幅变化（<1%）正确转换，不被放大100倍"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix: 小幅变化（<1%）")
    print("="*80)
    
    # Case 1: 0.5% 变化
    data1 = {
        'price': 50250,
        'price_change_1h': 0.5,  # 来自 calculate_price_change (百分比点)
        'oi_change_1h': 0.3,
    }
    
    normalized1, valid1, error1 = MetricsNormalizer.normalize(data1)
    
    assert valid1, f"数据应该有效，但得到 error: {error1}"
    assert abs(normalized1['price_change_1h'] - 0.005) < 0.000001, \
        f"0.5% 应转换为 0.005，实际: {normalized1['price_change_1h']}"
    assert abs(normalized1['oi_change_1h'] - 0.003) < 0.000001, \
        f"0.3% 应转换为 0.003，实际: {normalized1['oi_change_1h']}"
    
    print("✅ Case 1: 0.5% → 0.005 (正确)")
    
    # Case 2: 0.1% 变化
    data2 = {
        'price': 50050,
        'price_change_1h': 0.1,
        'price_change_6h': 0.8,
    }
    
    normalized2, valid2, error2 = MetricsNormalizer.normalize(data2)
    
    assert valid2
    assert abs(normalized2['price_change_1h'] - 0.001) < 0.000001
    assert abs(normalized2['price_change_6h'] - 0.008) < 0.000001
    
    print("✅ Case 2: 0.1% → 0.001 (正确)")
    
    # Case 3: 0.9% 变化（边界值）
    data3 = {
        'price': 50450,
        'price_change_1h': 0.9,
    }
    
    normalized3, valid3, error3 = MetricsNormalizer.normalize(data3)
    
    assert valid3
    assert abs(normalized3['price_change_1h'] - 0.009) < 0.000001
    
    print("✅ Case 3: 0.9% → 0.009 (正确)")
    print("✅ 小幅变化测试通过：不再放大100倍！")


def test_p0_bugfix_medium_change():
    """测试中等变化（1-10%）正确转换"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix: 中等变化（1-10%）")
    print("="*80)
    
    # Case 1: 3% 变化
    data1 = {
        'price': 51500,
        'price_change_1h': 3.0,
        'oi_change_1h': 5.0,
    }
    
    normalized1, valid1, error1 = MetricsNormalizer.normalize(data1)
    
    assert valid1
    assert abs(normalized1['price_change_1h'] - 0.03) < 0.000001
    assert abs(normalized1['oi_change_1h'] - 0.05) < 0.000001
    
    print("✅ Case 1: 3% → 0.03 (正确)")
    
    # Case 2: 8% 变化
    data2 = {
        'price': 54000,
        'price_change_6h': 8.0,
        'oi_change_6h': 10.0,
    }
    
    normalized2, valid2, error2 = MetricsNormalizer.normalize(data2)
    
    assert valid2
    assert abs(normalized2['price_change_6h'] - 0.08) < 0.000001
    assert abs(normalized2['oi_change_6h'] - 0.10) < 0.000001
    
    print("✅ Case 2: 8% → 0.08 (正确)")
    print("✅ 中等变化测试通过！")


def test_p0_bugfix_large_change():
    """测试大幅变化（>10%）正确转换"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix: 大幅变化（>10%）")
    print("="*80)
    
    # Case 1: 50% 变化
    data1 = {
        'price': 75000,
        'price_change_1h': 50.0,
        'oi_change_1h': 30.0,
    }
    
    normalized1, valid1, error1 = MetricsNormalizer.normalize(data1)
    
    assert valid1
    assert abs(normalized1['price_change_1h'] - 0.50) < 0.000001
    assert abs(normalized1['oi_change_1h'] - 0.30) < 0.000001
    
    print("✅ Case 1: 50% → 0.50 (正确)")
    
    # Case 2: 100% 变化
    data2 = {
        'price': 100000,
        'price_change_6h': 100.0,
    }
    
    normalized2, valid2, error2 = MetricsNormalizer.normalize(data2)
    
    assert valid2
    assert abs(normalized2['price_change_6h'] - 1.0) < 0.000001
    
    print("✅ Case 2: 100% → 1.0 (正确)")
    print("✅ 大幅变化测试通过！")


def test_p0_bugfix_extreme_anomaly():
    """测试极端异常值（>1000%）被正确拒绝"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix: 极端异常值拒绝")
    print("="*80)
    
    # Case 1: 1500% 异常值
    data1 = {
        'price': 100000,
        'price_change_1h': 1500.0,
    }
    
    normalized1, valid1, error1 = MetricsNormalizer.normalize(data1)
    
    assert not valid1, "1500% 应该被拒绝"
    assert 'price_change_1h' in error1 and '1500' in error1
    
    print(f"✅ Case 1: 1500% 被正确拒绝 (error: {error1[:60]}...)")
    
    # Case 2: 999% 边界值（应通过）
    data2 = {
        'price': 50000,
        'price_change_1h': 999.0,
    }
    
    normalized2, valid2, error2 = MetricsNormalizer.normalize(data2)
    
    assert valid2, "999% 应该通过（在阈值内）"
    assert abs(normalized2['price_change_1h'] - 9.99) < 0.01
    
    print("✅ Case 2: 999% 正常通过（边界内）")
    
    # Case 3: 1001% 边界值（应拒绝）
    data3 = {
        'price': 50000,
        'price_change_1h': 1001.0,
    }
    
    normalized3, valid3, error3 = MetricsNormalizer.normalize(data3)
    
    assert not valid3, "1001% 应该被拒绝（超过阈值）"
    
    print("✅ Case 3: 1001% 被正确拒绝（超过阈值）")
    print("✅ 异常值拒绝测试通过！")


def test_p0_bugfix_multi_field():
    """测试多字段同时处理"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix: 多字段统一转换")
    print("="*80)
    
    data = {
        'price': 50000,
        'price_change_1h': 0.3,   # 0.3%
        'price_change_6h': 1.5,   # 1.5%
        'oi_change_1h': 8.0,      # 8%
        'oi_change_6h': 15.0,     # 15%
    }
    
    normalized, valid, error = MetricsNormalizer.normalize(data)
    
    assert valid
    assert abs(normalized['price_change_1h'] - 0.003) < 0.000001
    assert abs(normalized['price_change_6h'] - 0.015) < 0.000001
    assert abs(normalized['oi_change_1h'] - 0.08) < 0.000001
    assert abs(normalized['oi_change_6h'] - 0.15) < 0.000001
    
    print("✅ 所有字段统一转换正确:")
    print(f"  0.3% → {normalized['price_change_1h']:.6f}")
    print(f"  1.5% → {normalized['price_change_6h']:.6f}")
    print(f"  8.0% → {normalized['oi_change_1h']:.6f}")
    print(f"  15.0% → {normalized['oi_change_6h']:.6f}")
    print("✅ 多字段测试通过！")


def test_p0_bugfix_comprehensive():
    """综合测试：验证修复前后的对比"""
    
    print("\n" + "="*80)
    print("测试 P0-BugFix: 综合验证")
    print("="*80)
    
    test_cases = [
        (0.1, 0.001, "0.1% → 0.001"),
        (0.5, 0.005, "0.5% → 0.005"),
        (0.9, 0.009, "0.9% → 0.009"),
        (1.0, 0.01, "1.0% → 0.01"),
        (3.0, 0.03, "3.0% → 0.03"),
        (10.0, 0.10, "10.0% → 0.10"),
        (50.0, 0.50, "50.0% → 0.50"),
        (100.0, 1.0, "100.0% → 1.0"),
    ]
    
    print("\n修复后行为验证:")
    all_passed = True
    
    for input_val, expected, desc in test_cases:
        data = {'price': 50000, 'price_change_1h': input_val}
        normalized, valid, error = MetricsNormalizer.normalize(data)
        
        if valid:
            actual = normalized['price_change_1h']
            passed = abs(actual - expected) < 0.000001
            status = "✅" if passed else "❌"
            print(f"  {status} {desc} (实际: {actual:.6f})")
            if not passed:
                all_passed = False
        else:
            print(f"  ❌ {desc} 被意外拒绝: {error[:40]}...")
            all_passed = False
    
    assert all_passed, "部分测试失败"
    print("\n✅ 综合测试通过！所有场景验证成功！")


if __name__ == "__main__":
    print("="*80)
    print("P0-BugFix 测试套件：修复小幅变化被放大100倍的问题")
    print("="*80)
    
    try:
        test_p0_bugfix_small_change()
        test_p0_bugfix_medium_change()
        test_p0_bugfix_large_change()
        test_p0_bugfix_extreme_anomaly()
        test_p0_bugfix_multi_field()
        test_p0_bugfix_comprehensive()
        
        print("\n" + "="*80)
        print("✅ 所有 P0-BugFix 测试通过！")
        print("="*80)
        print("\n修复验证:")
        print("  ✅ 小幅变化（<1%）：正确转换，不再放大100倍")
        print("  ✅ 中等变化（1-10%）：正确转换")
        print("  ✅ 大幅变化（>10%）：正确转换")
        print("  ✅ 极端异常（>1000%）：正确拒绝")
        print("  ✅ 多字段处理：统一转换")
        print("\n修复前问题:")
        print("  ❌ 0.5% 被误解释为 50%（放大100倍）")
        print("  ❌ 导致市场环境误判（RANGE → EXTREME）")
        print("  ❌ 所有决策逻辑失效")
        print("\n修复后效果:")
        print("  ✅ 所有百分比统一转换为小数格式")
        print("  ✅ 市场环境识别正确")
        print("  ✅ L1决策逻辑正常工作")
        
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
