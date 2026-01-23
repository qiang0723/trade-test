#!/usr/bin/env python3
"""
P0改进快速验证脚本（独立运行，不依赖pytest）

验证内容：
1. P0-01: Medium-term None-safe
2. P0-02: taker_imbalance兼容注入
3. P0-05: Short-term None-safe
4. P0-03: Dual独立评估
"""

import sys
from datetime import datetime
from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision
from models.reason_tags import ReasonTag


def print_result(test_name, passed, message=""):
    """打印测试结果"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if message:
        print(f"    {message}")


def test_p0_01_medium_term_none_safe():
    """P0-01验证: Medium-term缺数据显性标记"""
    print("\n[P0-01] Medium-term None-safe验证")
    print("-" * 60)
    
    try:
        engine = L1AdvisoryEngine(config_path='config/l1_thresholds.yaml')
        
        # 测试1: 缺失price_change_1h
        data = {
            'price': 50000,
            'volume_24h': 1000,
            # 缺少price_change_1h（关键字段）
            'price_change_6h': 0.02,
            'oi_change_1h': 0.05,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.6,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # 验证: medium_term应为NO_TRADE + DATA_INCOMPLETE_MTF
        test1_pass = (
            result.medium_term.decision == Decision.NO_TRADE and
            ReasonTag.DATA_INCOMPLETE_MTF in result.medium_term.reason_tags
        )
        
        print_result(
            "缺失price_change_1h应显性标记",
            test1_pass,
            f"medium_term.decision={result.medium_term.decision.value}, "
            f"has_DATA_INCOMPLETE_MTF={ReasonTag.DATA_INCOMPLETE_MTF in result.medium_term.reason_tags}"
        )
        
        return test1_pass
        
    except Exception as e:
        print_result("P0-01验证", False, f"Exception: {e}")
        return False


def test_p0_02_compatibility_injection():
    """P0-02验证: taker_imbalance兼容注入"""
    print("\n[P0-02] taker_imbalance兼容注入验证")
    print("-" * 60)
    
    try:
        engine = L1AdvisoryEngine(config_path='config/l1_thresholds.yaml')
        
        # 测试: 只提供buy_sell_imbalance
        data = {
            'price': 50000,
            'volume_24h': 1000,
            'price_change_1h': 0.03,
            'price_change_6h': 0.04,
            'oi_change_1h': 0.06,
            'oi_change_6h': 0.08,
            'buy_sell_imbalance': 0.7,  # 旧字段
            # 缺少taker_imbalance_1h
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick('BTC', data)
        
        # 验证: 应该注入taker_imbalance_1h
        test1_pass = 'taker_imbalance_1h' in data
        test2_pass = data.get('taker_imbalance_1h') == 0.7 if test1_pass else False
        
        print_result(
            "buy_sell_imbalance应注入到taker_imbalance_1h",
            test1_pass and test2_pass,
            f"taker_imbalance_1h={'存在' if test1_pass else '不存在'}, "
            f"值={data.get('taker_imbalance_1h')}"
        )
        
        # 测试: 新字段优先
        data2 = {
            'price': 50000,
            'volume_24h': 1000,
            'price_change_1h': 0.03,
            'price_change_6h': 0.04,
            'oi_change_1h': 0.06,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.8,  # 新字段
            'buy_sell_imbalance': 0.3,  # 旧字段
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result2 = engine.on_new_tick('BTC', data2)
        
        # 验证: 新字段不被旧字段覆盖
        test3_pass = data2.get('taker_imbalance_1h') == 0.8
        
        print_result(
            "新字段优先，不被旧字段覆盖",
            test3_pass,
            f"taker_imbalance_1h保持为{data2.get('taker_imbalance_1h')}（预期0.8）"
        )
        
        return test1_pass and test2_pass and test3_pass
        
    except Exception as e:
        print_result("P0-02验证", False, f"Exception: {e}")
        return False


def test_p0_05_short_term_none_safe():
    """P0-05验证: Short-term None-safe"""
    print("\n[P0-05] Short-term None-safe验证")
    print("-" * 60)
    
    try:
        engine = L1AdvisoryEngine(config_path='config/l1_thresholds.yaml')
        
        # 测试: 短期字段缺失
        data = {
            'price': 50000,
            'volume_24h': 1000,
            # 短期字段不完整
            'price_change_15m': 0.008,
            # 缺少其他短期关键字段
            # 中期字段完整
            'price_change_1h': 0.02,
            'price_change_6h': 0.03,
            'oi_change_1h': 0.06,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.7,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # 验证: short_term应为NO_TRADE + DATA_INCOMPLETE_LTF
        test1_pass = (
            result.short_term.decision == Decision.NO_TRADE and
            ReasonTag.DATA_INCOMPLETE_LTF in result.short_term.reason_tags
        )
        
        print_result(
            "短期缺数据应显性标记",
            test1_pass,
            f"short_term.decision={result.short_term.decision.value}, "
            f"has_DATA_INCOMPLETE_LTF={ReasonTag.DATA_INCOMPLETE_LTF in result.short_term.reason_tags}"
        )
        
        return test1_pass
        
    except Exception as e:
        print_result("P0-05验证", False, f"Exception: {e}")
        return False


def test_p0_03_dual_independence():
    """P0-03验证: Dual独立评估"""
    print("\n[P0-03] Dual独立评估验证")
    print("-" * 60)
    
    try:
        engine = L1AdvisoryEngine(config_path='config/l1_thresholds.yaml')
        
        # 测试: short缺数据，medium完整
        data = {
            'price': 50000,
            'volume_24h': 1000,
            # 短期字段全缺
            # 中期字段完整且强势
            'price_change_1h': 0.03,
            'price_change_6h': 0.04,
            'oi_change_1h': 0.06,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.75,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # 验证1: short应为NO_TRADE（缺数据）
        test1_pass = (
            result.short_term.decision == Decision.NO_TRADE and
            ReasonTag.DATA_INCOMPLETE_LTF in result.short_term.reason_tags
        )
        
        print_result(
            "short缺数据应标记NO_TRADE",
            test1_pass,
            f"short_term.decision={result.short_term.decision.value}"
        )
        
        # 验证2: medium应正常评估（不被short短路）
        test2_pass = (
            result.medium_term.decision != None and  # 有输出
            ReasonTag.DATA_INCOMPLETE_MTF not in result.medium_term.reason_tags  # 没有MTF缺失标签
        )
        
        print_result(
            "medium仍正常评估（不被short短路）",
            test2_pass,
            f"medium_term.decision={result.medium_term.decision.value}, "
            f"executable={result.medium_term.executable}"
        )
        
        return test1_pass and test2_pass
        
    except Exception as e:
        print_result("P0-03验证", False, f"Exception: {e}")
        return False


def test_basic_functionality():
    """基础功能验证：确保改动不破坏现有功能"""
    print("\n[基础功能] 验证现有功能未破坏")
    print("-" * 60)
    
    try:
        engine = L1AdvisoryEngine(config_path='config/l1_thresholds.yaml')
        
        # 测试: 完整数据的正常评估
        data = {
            'price': 50000,
            'volume_24h': 1000,
            'volume_1h': 50,
            # 短期字段完整
            'price_change_5m': 0.003,
            'price_change_15m': 0.010,
            'taker_imbalance_5m': 0.70,
            'taker_imbalance_15m': 0.65,
            'volume_ratio_5m': 2.5,
            'volume_ratio_15m': 2.0,
            'oi_change_15m': 0.04,
            # 中期字段完整
            'price_change_1h': 0.03,
            'price_change_6h': 0.04,
            'oi_change_1h': 0.06,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.75,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # 验证: 能正常返回结果
        test1_pass = result is not None
        test2_pass = hasattr(result, 'short_term') and hasattr(result, 'medium_term')
        test3_pass = result.short_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE]
        test4_pass = result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE]
        
        print_result(
            "Dual评估能正常返回",
            test1_pass and test2_pass,
            f"short={result.short_term.decision.value}, medium={result.medium_term.decision.value}"
        )
        
        print_result(
            "决策值有效",
            test3_pass and test4_pass,
            f"决策均在有效范围内"
        )
        
        return test1_pass and test2_pass and test3_pass and test4_pass
        
    except Exception as e:
        print_result("基础功能验证", False, f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主验证函数"""
    print("\n" + "=" * 60)
    print("🚀 P0改进快速验证脚本")
    print("=" * 60)
    
    results = {}
    
    # 运行所有验证
    results['基础功能'] = test_basic_functionality()
    results['P0-01'] = test_p0_01_medium_term_none_safe()
    results['P0-02'] = test_p0_02_compatibility_injection()
    results['P0-05'] = test_p0_05_short_term_none_safe()
    results['P0-03'] = test_p0_03_dual_independence()
    
    # 统计结果
    print("\n" + "=" * 60)
    print("📊 验证结果汇总")
    print("=" * 60)
    
    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("-" * 60)
    print(f"总计: {passed_count}/{total_count} 通过")
    
    if passed_count == total_count:
        print("\n🎉 所有验证通过！P0改进实施成功！")
        return 0
    else:
        print(f"\n⚠️  有 {total_count - passed_count} 个验证失败，请检查问题")
        return 1


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  验证被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 验证脚本异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
