"""
测试 PR-J: MetricsNormalizer.validate_ranges 纳入 L1 校验链路

验收要点：
1. 构造超范围输入（funding_rate=0.5 或 oi_change_1h=2.0）时，输出 NO_TRADE
2. 带 INVALID_DATA 错误标签
3. 记录具体字段名
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics_normalizer import MetricsNormalizer


def test_pr_j_range_validation():
    """测试 PR-J: validate_ranges 超范围拦截"""
    
    print("\n" + "="*80)
    print("测试 PR-J: MetricsNormalizer.validate_ranges 纳入 L1 校验链路")
    print("="*80)
    
    # 基础合法数据
    base_data = {
        'price': 50000.0,
        'price_change_1h': 0.01,      # 1%
        'price_change_6h': 0.03,      # 3%
        'oi_change_1h': 0.05,         # 5%
        'oi_change_6h': 0.10,         # 10%
        'funding_rate': 0.0001,       # 0.01%
        'buy_sell_imbalance': 0.3,    # 30%
        'volume_ratio': 1.5,
        'volatility': 0.01,
    }
    
    # ========== 测试1: 合法数据应该通过 ==========
    print("\n[测试1] 合法数据应该通过校验...")
    valid, error = MetricsNormalizer.validate_ranges(base_data)
    if valid:
        print("✅ 合法数据通过校验")
        test1_passed = True
    else:
        print(f"❌ 合法数据意外失败: {error}")
        test1_passed = False
    
    # ========== 测试2: funding_rate=0.5 (50%) 超范围 ==========
    print("\n[测试2] funding_rate=0.5 (50%) 应该被拒绝...")
    data2 = base_data.copy()
    data2['funding_rate'] = 0.5  # 50%，远超合理范围（>1%）
    
    valid2, error2 = MetricsNormalizer.validate_ranges(data2)
    if not valid2 and 'funding_rate' in error2:
        print(f"✅ funding_rate超范围被正确拒绝: {error2}")
        test2_passed = True
    else:
        print(f"❌ funding_rate超范围未被拒绝，valid={valid2}, error={error2}")
        test2_passed = False
    
    # ========== 测试3: oi_change_1h=2.0 (200%) 超范围 ==========
    print("\n[测试3] oi_change_1h=2.0 (200%) 应该被拒绝...")
    data3 = base_data.copy()
    data3['oi_change_1h'] = 2.0  # 200%，超过合理范围（>100%）
    
    valid3, error3 = MetricsNormalizer.validate_ranges(data3)
    if not valid3 and 'oi_change_1h' in error3:
        print(f"✅ oi_change_1h超范围被正确拒绝: {error3}")
        test3_passed = True
    else:
        print(f"❌ oi_change_1h超范围未被拒绝，valid={valid3}, error={error3}")
        test3_passed = False
    
    # ========== 测试4: price_change_1h=0.5 (50%) 超范围 ==========
    print("\n[测试4] price_change_1h=0.5 (50%) 应该被拒绝...")
    data4 = base_data.copy()
    data4['price_change_1h'] = 0.5  # 50%，超过合理范围（>20%）
    
    valid4, error4 = MetricsNormalizer.validate_ranges(data4)
    if not valid4 and 'price_change_1h' in error4:
        print(f"✅ price_change_1h超范围被正确拒绝: {error4}")
        test4_passed = True
    else:
        print(f"❌ price_change_1h超范围未被拒绝，valid={valid4}, error={error4}")
        test4_passed = False
    
    # ========== 测试5: buy_sell_imbalance=5.0 超范围 ==========
    print("\n[测试5] buy_sell_imbalance=5.0 超范围应该被拒绝...")
    data5 = base_data.copy()
    data5['buy_sell_imbalance'] = 5.0  # 远超范围（应在-1到1之间）
    
    valid5, error5 = MetricsNormalizer.validate_ranges(data5)
    if not valid5 and 'buy_sell_imbalance' in error5:
        print(f"✅ buy_sell_imbalance超范围被正确拒绝: {error5}")
        test5_passed = True
    else:
        print(f"❌ buy_sell_imbalance超范围未被拒绝，valid={valid5}, error={error5}")
        test5_passed = False
    
    # ========== 测试6: 边界值测试（刚好在范围内）==========
    print("\n[测试6] 边界值（刚好在范围内）应该通过...")
    data6 = base_data.copy()
    data6['price_change_1h'] = 0.20    # 20%（边界值）
    data6['oi_change_1h'] = 1.0        # 100%（边界值）
    data6['funding_rate'] = 0.01       # 1%（边界值）
    data6['buy_sell_imbalance'] = 1.0  # 1（边界值）
    
    valid6, error6 = MetricsNormalizer.validate_ranges(data6)
    if valid6:
        print("✅ 边界值正确通过校验")
        test6_passed = True
    else:
        print(f"❌ 边界值意外失败: {error6}")
        test6_passed = False
    
    # ========== 测试7: 边界值测试（刚好超过）==========
    print("\n[测试7] 边界值（刚好超过）应该被拒绝...")
    data7 = base_data.copy()
    data7['price_change_1h'] = 0.21  # 21%（刚超过）
    
    valid7, error7 = MetricsNormalizer.validate_ranges(data7)
    if not valid7 and 'price_change_1h' in error7:
        print(f"✅ 刚超过边界值被正确拒绝: {error7}")
        test7_passed = True
    else:
        print(f"❌ 刚超过边界值未被拒绝，valid={valid7}, error={error7}")
        test7_passed = False
    
    # ========== 测试8: oi_change_6h=3.0 (300%) 超范围 ==========
    print("\n[测试8] oi_change_6h=3.0 (300%) 应该被拒绝...")
    data8 = base_data.copy()
    data8['oi_change_6h'] = 3.0  # 300%，超过合理范围（>200%）
    
    valid8, error8 = MetricsNormalizer.validate_ranges(data8)
    if not valid8 and 'oi_change_6h' in error8:
        print(f"✅ oi_change_6h超范围被正确拒绝: {error8}")
        test8_passed = True
    else:
        print(f"❌ oi_change_6h超范围未被拒绝，valid={valid8}, error={error8}")
        test8_passed = False
    
    # ========== 测试9: volume_ratio=100 超范围 ==========
    print("\n[测试9] volume_ratio=100 (100倍) 应该被拒绝...")
    data9 = base_data.copy()
    data9['volume_ratio'] = 100  # 100倍，超过合理范围（>50x）
    
    valid9, error9 = MetricsNormalizer.validate_ranges(data9)
    if not valid9 and 'volume_ratio' in error9:
        print(f"✅ volume_ratio超范围被正确拒绝: {error9}")
        test9_passed = True
    else:
        print(f"❌ volume_ratio超范围未被拒绝，valid={valid9}, error={error9}")
        test9_passed = False
    
    # ========== 测试10: price<=0 无效值 ==========
    print("\n[测试10] price<=0 无效值应该被拒绝...")
    data10 = base_data.copy()
    data10['price'] = -100  # 负价格
    
    valid10, error10 = MetricsNormalizer.validate_ranges(data10)
    if not valid10 and 'price' in error10:
        print(f"✅ price<=0 被正确拒绝: {error10}")
        test10_passed = True
    else:
        print(f"❌ price<=0 未被拒绝，valid={valid10}, error={error10}")
        test10_passed = False
    
    # ========== 汇总结果 ==========
    print("\n" + "="*80)
    print("测试结果汇总")
    print("="*80)
    
    all_tests = [
        ("合法数据通过", test1_passed),
        ("funding_rate=0.5超范围被拒绝", test2_passed),
        ("oi_change_1h=2.0超范围被拒绝", test3_passed),
        ("price_change_1h=0.5超范围被拒绝", test4_passed),
        ("buy_sell_imbalance=5.0超范围被拒绝", test5_passed),
        ("边界值通过", test6_passed),
        ("刚超过边界值被拒绝", test7_passed),
        ("oi_change_6h=3.0超范围被拒绝", test8_passed),
        ("volume_ratio=100超范围被拒绝", test9_passed),
        ("price<=0被拒绝", test10_passed),
    ]
    
    for test_name, passed in all_tests:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {test_name}")
    
    all_passed = all(passed for _, passed in all_tests)
    
    if all_passed:
        print("\n" + "="*80)
        print("✅ PR-J 所有测试通过！")
        print("="*80)
        print("\n验收要点:")
        print("  1. ✅ 超范围输入被正确拒绝")
        print("  2. ✅ 错误信息包含具体字段名")
        print("  3. ✅ 边界值处理正确")
        print("  4. ✅ 覆盖所有关键字段（funding_rate, oi_change, price_change等）")
        print("\n设计原理:")
        print("  - 统一超范围拦截：集中式校验，避免异常数据进入策略")
        print("  - 明确错误信息：记录具体字段名，便于问题定位")
        print("  - 合理范围设定：基于市场实际情况设定极限值")
        print("  - 数据安全保护：在策略判断前拦截异常数据")
        print("\n注意: 这是逻辑验证测试，L1集成测试需要在Docker环境运行")
        return True
    else:
        print("\n" + "="*80)
        print("❌ PR-J 部分测试失败")
        print("="*80)
        return False


if __name__ == "__main__":
    success = test_pr_j_range_validation()
    sys.exit(0 if success else 1)
