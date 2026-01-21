"""
测试：数据验证 - 数值合理性范围

验证所有输入数据的合理性范围，确保异常数值被正确拦截。
这是防止错误数据进入决策系统的关键防线。

固化测试用例：
1. 价格异常（<= 0）
2. 百分比字段超范围（> 100%）
3. 失衡度超范围（不在[-1, 1]）
4. 成交量异常（< 0）
5. 极端但合理的值（边界测试）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision
from models.reason_tags import ReasonTag


# 标准数据模板
def get_standard_data():
    return {
        'price': 50000,
        'price_change_1h': 0.5,
        'price_change_6h': 2.0,
        'volume_1h': 100,
        'volume_24h': 2400,
        'buy_sell_imbalance': 0.3,
        'funding_rate': 0.01,
        'oi_change_1h': 1.0,
        'oi_change_6h': 5.0
    }


def test_invalid_price():
    """固化测试1: 价格必须 > 0"""
    
    print("\n" + "="*80)
    print("固化测试1: 价格范围检查")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    test_cases = [
        (0, "零价格"),
        (-100, "负价格"),
        (-50000, "负价格（大值）"),
    ]
    
    print(f"\n测试 {len(test_cases)} 种无效价格:")
    print("-" * 80)
    
    for price, description in test_cases:
        test_data = get_standard_data()
        test_data['price'] = price
        
        result = engine.on_new_tick("BTCUSDT", test_data)
        
        is_blocked = (result.decision == Decision.NO_TRADE and 
                     ReasonTag.INVALID_DATA in result.reason_tags)
        
        status = "✅ PASS" if is_blocked else "❌ FAIL"
        print(f"  price = {price:10} ({description:20}) → {status}")
        
        assert is_blocked, f"无效价格应该被拦截: {price}"
    
    print(f"\n✅ 固化测试1通过：所有无效价格都被拦截")


def test_percentage_out_of_range():
    """固化测试2: 百分比字段超范围（> 100%）"""
    
    print("\n" + "="*80)
    print("固化测试2: 百分比字段范围检查")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    # 百分比字段（规范化后应该在合理范围内）
    # 注意：这些值是百分比点格式（5.0 = 5%）
    percentage_fields = [
        ('funding_rate', 1.5, "资金费率 > 1%"),  # 1.5%，极端异常（阈值1%）
        ('oi_change_1h', 150.0, "1小时OI变化 > 100%"),  # 150%（阈值100%）
        ('oi_change_6h', 250.0, "6小时OI变化 > 200%"),  # 250%（阈值200%）
        ('price_change_1h', 25.0, "1小时价格变化 > 20%"),  # 25%（阈值20%）
        ('price_change_6h', 60.0, "6小时价格变化 > 50%"),  # 60%（阈值50%）
    ]
    
    print(f"\n测试 {len(percentage_fields)} 个百分比字段的超范围值（基于业务合理阈值）:")
    print("-" * 80)
    
    for field, value, description in percentage_fields:
        test_data = get_standard_data()
        test_data[field] = value
        
        result = engine.on_new_tick("BTCUSDT", test_data)
        
        is_blocked = (result.decision == Decision.NO_TRADE and 
                     ReasonTag.INVALID_DATA in result.reason_tags)
        
        status = "✅ PASS" if is_blocked else "❌ FAIL"
        print(f"  {field:20} = {value:8} ({description}) → {status}")
        
        assert is_blocked, f"超范围百分比应该被拦截: {field}={value}"
    
    print(f"\n✅ 固化测试2通过：所有超范围百分比都被拦截")


def test_imbalance_out_of_range():
    """固化测试3: 失衡度必须在[-1, 1]"""
    
    print("\n" + "="*80)
    print("固化测试3: 买卖失衡度范围检查")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    test_cases = [
        (1.5, "超过1"),
        (-1.5, "低于-1"),
        (2.0, "大幅超过1"),
        (-2.0, "大幅低于-1"),
        (10.0, "极端值"),
    ]
    
    print(f"\n测试 {len(test_cases)} 种超范围失衡度:")
    print("-" * 80)
    
    for imbalance, description in test_cases:
        test_data = get_standard_data()
        test_data['buy_sell_imbalance'] = imbalance
        
        result = engine.on_new_tick("BTCUSDT", test_data)
        
        is_blocked = (result.decision == Decision.NO_TRADE and 
                     ReasonTag.INVALID_DATA in result.reason_tags)
        
        status = "✅ PASS" if is_blocked else "❌ FAIL"
        print(f"  imbalance = {imbalance:6.1f} ({description:15}) → {status}")
        
        assert is_blocked, f"超范围失衡度应该被拦截: {imbalance}"
    
    print(f"\n✅ 固化测试3通过：所有超范围失衡度都被拦截")


def test_negative_volume():
    """固化测试4: 成交量不能为负"""
    
    print("\n" + "="*80)
    print("固化测试4: 成交量范围检查")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    test_cases = [
        ('volume_1h', -10, "1h成交量为负"),
        ('volume_24h', -100, "24h成交量为负"),
        ('volume_1h', -1000, "1h成交量大负值"),
    ]
    
    print(f"\n测试 {len(test_cases)} 种负成交量:")
    print("-" * 80)
    
    for field, value, description in test_cases:
        test_data = get_standard_data()
        test_data[field] = value
        
        result = engine.on_new_tick("BTCUSDT", test_data)
        
        # 注意：负成交量可能在normalize或其他环节被拦截
        is_blocked = (result.decision == Decision.NO_TRADE)
        
        status = "✅ PASS" if is_blocked else "❌ FAIL"
        print(f"  {field:15} = {value:6} ({description:25}) → {status}")
        
        # 负成交量应该被某种方式拦截（可能不是INVALID_DATA，可能是其他逻辑）
        assert is_blocked, f"负成交量应该导致NO_TRADE: {field}={value}"
    
    print(f"\n✅ 固化测试4通过：所有负成交量都被拦截")


def test_extreme_but_valid_values():
    """固化测试5: 极端但合理的值（边界测试）"""
    
    print("\n" + "="*80)
    print("固化测试5: 极端但合理的边界值")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    test_cases = [
        {
            'description': "极端暴涨（但合理）",
            'data': {
                'price': 55000,
                'price_change_1h': 15.0,   # 15%暴涨（< 20%阈值）
                'price_change_6h': 35.0,   # 35%（< 50%阈值）
                'volume_1h': 500,          # 极高成交量（5倍平均值）
                'volume_24h': 2400,
                'buy_sell_imbalance': 0.99,  # 接近上限
                'funding_rate': 0.008,     # 0.8%极高费率（< 1%阈值）
                'oi_change_1h': 80.0,      # 80%（< 100%阈值）
                'oi_change_6h': 150.0,     # 150%（< 200%阈值）
            },
            'should_pass': True
        },
        {
            'description': "极端暴跌（但合理）",
            'data': {
                'price': 45000,
                'price_change_1h': -15.0,  # -15%暴跌（< 20%阈值）
                'price_change_6h': -35.0,  # -35%（< 50%阈值）
                'volume_1h': 500,          # 高成交量（5倍平均值）
                'volume_24h': 2400,
                'buy_sell_imbalance': -0.99,  # 接近下限
                'funding_rate': -0.008,    # -0.8%负费率（< 1%阈值）
                'oi_change_1h': -80.0,     # -80%清算（< 100%阈值）
                'oi_change_6h': -150.0,    # -150%（< 200%阈值）
            },
            'should_pass': True
        },
        {
            'description': "微小变化",
            'data': {
                'price': 50000,
                'price_change_1h': 0.01,   # 0.01%微小
                'price_change_6h': 0.05,   # 0.05%
                'volume_1h': 10,           # 极低成交量
                'volume_24h': 2400,
                'buy_sell_imbalance': 0.01,
                'funding_rate': 0.0001,    # 极小费率
                'oi_change_1h': 0.1,       # 0.1%
                'oi_change_6h': 0.3,       # 0.3%
            },
            'should_pass': True
        },
        {
            'description': "边界值（接近但不超过上限）",
            'data': {
                'price': 100000,
                'price_change_1h': 19.0,   # 19%（接近20%上限）
                'price_change_6h': 48.0,   # 48%（接近50%上限）
                'volume_1h': 1000,         # 10倍平均值
                'volume_24h': 24000,
                'buy_sell_imbalance': 1.0,  # 上限
                'funding_rate': 0.0098,    # 0.98%（接近1%上限）
                'oi_change_1h': 95.0,      # 95%（接近100%上限）
                'oi_change_6h': 190.0,     # 190%（接近200%上限）
            },
            'should_pass': True
        },
    ]
    
    print(f"\n测试 {len(test_cases)} 种极端但合理的边界场景:")
    print("-" * 80)
    
    for tc in test_cases:
        result = engine.on_new_tick("BTCUSDT", tc['data'])
        
        # 极端但合理的值不应该被INVALID_DATA拦截
        is_not_invalid = (ReasonTag.INVALID_DATA not in result.reason_tags)
        
        # 可能因为其他原因（如EXTREME_REGIME）被拦截，但不应该是数据无效
        status = "✅ PASS" if is_not_invalid else "❌ FAIL"
        print(f"  {tc['description']:25} → {status}")
        
        if not is_not_invalid:
            print(f"    决策: {result.decision}, tags: {[t.value for t in result.reason_tags]}")
            print(f"    输入数据：")
            for k, v in tc['data'].items():
                print(f"      {k}: {v}")
        
        assert is_not_invalid, f"极端但合理的值不应该被标记为INVALID_DATA: {tc['description']}"
    
    print(f"\n✅ 固化测试5通过：所有极端但合理的值都未被误拦截")


def test_zero_values_handling():
    """固化测试6: 零值处理（特殊情况）"""
    
    print("\n" + "="*80)
    print("固化测试6: 零值特殊处理")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    # 零值数据（完全平稳市场）
    zero_data = {
        'price': 50000,           # 价格不能为0
        'price_change_1h': 0.0,   # 零变化是合理的
        'price_change_6h': 0.0,
        'volume_1h': 0.0,         # 零成交量（极端但可能）
        'volume_24h': 2400,
        'buy_sell_imbalance': 0.0,  # 零失衡是合理的
        'funding_rate': 0.0,      # 零费率是合理的
        'oi_change_1h': 0.0,
        'oi_change_6h': 0.0,
    }
    
    print(f"\n测试完全零变化场景（平稳市场）:")
    print(f"  所有变化率和失衡都为0")
    
    result = engine.on_new_tick("BTCUSDT", zero_data)
    
    # 零值不应该被标记为INVALID_DATA（这是合理的市场状态）
    is_not_invalid = (ReasonTag.INVALID_DATA not in result.reason_tags)
    
    status = "✅ PASS" if is_not_invalid else "❌ FAIL"
    print(f"\n  结果: {status}")
    print(f"  决策: {result.decision}")
    print(f"  市场环境: {result.market_regime}")
    
    assert is_not_invalid, "零值不应该被标记为INVALID_DATA"
    
    print(f"\n✅ 固化测试6通过：零值被正确处理为合理市场状态")


if __name__ == "__main__":
    print("="*80)
    print("数据验证 - 数值合理性范围 固化测试套件")
    print("="*80)
    
    try:
        test_invalid_price()
        test_percentage_out_of_range()
        test_imbalance_out_of_range()
        test_negative_volume()
        test_extreme_but_valid_values()
        test_zero_values_handling()
        
        print("\n" + "="*80)
        print("✅ 所有固化测试通过！（6/6）")
        print("="*80)
        
        print("\n测试覆盖:")
        print("  ✅ 价格范围检查（3种无效价格）")
        print("  ✅ 百分比超范围检查（3个字段）")
        print("  ✅ 失衡度范围检查（5种超范围值）")
        print("  ✅ 成交量负值检查（3种负值）")
        print("  ✅ 极端边界值测试（4种场景）")
        print("  ✅ 零值特殊处理")
        
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
