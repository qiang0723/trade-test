"""
测试：数据验证 - 字段完整性

验证所有必填字段的完整性检查，确保缺失任何字段都能被正确拦截。
这是数据准确性的第一道防线。

固化测试用例：
1. 缺失每个必填字段分别测试
2. 缺失多个字段组合测试
3. 所有字段完整测试（基准）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision
from models.reason_tags import ReasonTag


# 标准完整数据模板
STANDARD_COMPLETE_DATA = {
    'price': 50000,
    'price_change_1h': 0.5,    # 0.5% (百分比点)
    'price_change_6h': 2.0,    # 2% (百分比点)
    'volume_1h': 100,          # BTC
    'volume_24h': 2400,        # BTC
    'buy_sell_imbalance': 0.3,
    'funding_rate': 0.01,      # 0.01% (百分比点)
    'oi_change_1h': 1.0,       # 1% (百分比点)
    'oi_change_6h': 5.0        # 5% (百分比点)
}

# 必填字段列表
REQUIRED_FIELDS = [
    'price',
    'price_change_1h',
    'price_change_6h',
    'volume_1h',
    'volume_24h',
    'buy_sell_imbalance',
    'funding_rate',
    'oi_change_1h',
    'oi_change_6h'
]


def test_all_required_fields_missing_individually():
    """固化测试1: 逐个缺失每个必填字段，必须全部被拦截"""
    
    print("\n" + "="*80)
    print("固化测试1: 逐个缺失必填字段")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    failed_count = 0
    
    print(f"\n共有 {len(REQUIRED_FIELDS)} 个必填字段，逐个测试缺失情况:")
    print("-" * 80)
    
    for field in REQUIRED_FIELDS:
        # 复制完整数据
        test_data = STANDARD_COMPLETE_DATA.copy()
        # 删除当前测试字段
        del test_data[field]
        
        # 执行决策
        result = engine.on_new_tick("BTCUSDT", test_data)
        
        # 验证
        is_blocked = (result.decision == Decision.NO_TRADE and 
                     ReasonTag.INVALID_DATA in result.reason_tags)
        
        status = "✅ PASS" if is_blocked else "❌ FAIL"
        print(f"  {field:25} → {status}")
        
        if not is_blocked:
            failed_count += 1
            print(f"    ⚠️ 应该被拦截但未拦截！")
    
    print("-" * 80)
    print(f"\n测试结果: {len(REQUIRED_FIELDS) - failed_count}/{len(REQUIRED_FIELDS)} 通过")
    
    assert failed_count == 0, f"{failed_count}个字段缺失未被正确拦截"
    print(f"✅ 固化测试1通过：所有必填字段缺失都被正确拦截")


def test_multiple_fields_missing():
    """固化测试2: 多字段同时缺失"""
    
    print("\n" + "="*80)
    print("固化测试2: 多字段同时缺失")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    test_cases = [
        (['price', 'price_change_1h'], "价格相关字段"),
        (['volume_1h', 'volume_24h'], "成交量字段"),
        (['oi_change_1h', 'oi_change_6h'], "持仓量变化字段"),
        (['price_change_6h', 'oi_change_6h'], "6小时变化字段"),
    ]
    
    print(f"\n测试 {len(test_cases)} 种多字段缺失组合:")
    print("-" * 80)
    
    for missing_fields, description in test_cases:
        test_data = STANDARD_COMPLETE_DATA.copy()
        for field in missing_fields:
            del test_data[field]
        
        result = engine.on_new_tick("BTCUSDT", test_data)
        
        is_blocked = (result.decision == Decision.NO_TRADE and 
                     ReasonTag.INVALID_DATA in result.reason_tags)
        
        status = "✅ PASS" if is_blocked else "❌ FAIL"
        print(f"  {description:25} → {status}")
        print(f"    缺失字段: {', '.join(missing_fields)}")
        
        assert is_blocked, f"多字段缺失应该被拦截: {missing_fields}"
    
    print(f"\n✅ 固化测试2通过：所有多字段缺失组合都被正确拦截")


def test_all_fields_present_baseline():
    """固化测试3: 所有字段完整（基准测试）"""
    
    print("\n" + "="*80)
    print("固化测试3: 所有字段完整（基准）")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    # 使用完整数据
    result = engine.on_new_tick("BTCUSDT", STANDARD_COMPLETE_DATA)
    
    print(f"\n输入数据:")
    for k, v in STANDARD_COMPLETE_DATA.items():
        print(f"  {k}: {v}")
    
    print(f"\n决策结果:")
    print(f"  decision: {result.decision}")
    print(f"  market_regime: {result.market_regime}")
    print(f"  confidence: {result.confidence}")
    print(f"  reason_tags: {[tag.value for tag in result.reason_tags]}")
    
    # 验证：不应该因为字段问题被拦截
    assert ReasonTag.INVALID_DATA not in result.reason_tags, \
        "完整数据不应该被标记为INVALID_DATA"
    
    print(f"\n✅ 固化测试3通过：完整数据不会被错误拦截")


def test_field_with_none_value():
    """固化测试4: 字段存在但值为None"""
    
    print("\n" + "="*80)
    print("固化测试4: 字段值为None")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    print(f"\n测试每个字段值为None的情况:")
    print("-" * 80)
    
    failed_count = 0
    
    for field in REQUIRED_FIELDS:
        test_data = STANDARD_COMPLETE_DATA.copy()
        test_data[field] = None  # 设置为None而不是删除
        
        result = engine.on_new_tick("BTCUSDT", test_data)
        
        is_blocked = (result.decision == Decision.NO_TRADE and 
                     ReasonTag.INVALID_DATA in result.reason_tags)
        
        status = "✅ PASS" if is_blocked else "❌ FAIL"
        print(f"  {field:25} = None → {status}")
        
        if not is_blocked:
            failed_count += 1
            print(f"    ⚠️ None值应该被拦截但未拦截！")
    
    print("-" * 80)
    print(f"\n测试结果: {len(REQUIRED_FIELDS) - failed_count}/{len(REQUIRED_FIELDS)} 通过")
    
    assert failed_count == 0, f"{failed_count}个None值未被正确拦截"
    print(f"\n✅ 固化测试4通过：所有None值都被正确拦截")


def test_extra_fields_allowed():
    """固化测试5: 额外字段应该被允许"""
    
    print("\n" + "="*80)
    print("固化测试5: 额外字段不应影响验证")
    print("="*80)
    
    engine = L1AdvisoryEngine()
    
    # 添加额外字段
    test_data = STANDARD_COMPLETE_DATA.copy()
    test_data['extra_field_1'] = 'test'
    test_data['extra_field_2'] = 12345
    test_data['metadata'] = {'source': 'test'}
    
    print(f"\n输入数据（包含3个额外字段）:")
    for k in ['extra_field_1', 'extra_field_2', 'metadata']:
        print(f"  {k}: {test_data[k]}")
    
    result = engine.on_new_tick("BTCUSDT", test_data)
    
    # 验证：额外字段不应导致INVALID_DATA
    assert ReasonTag.INVALID_DATA not in result.reason_tags, \
        "额外字段不应导致验证失败"
    
    print(f"\n决策结果: {result.decision}")
    print(f"✅ 固化测试5通过：额外字段不影响验证")


if __name__ == "__main__":
    print("="*80)
    print("数据验证 - 字段完整性 固化测试套件")
    print("="*80)
    
    try:
        test_all_required_fields_missing_individually()
        test_multiple_fields_missing()
        test_all_fields_present_baseline()
        test_field_with_none_value()
        test_extra_fields_allowed()
        
        print("\n" + "="*80)
        print("✅ 所有固化测试通过！（5/5）")
        print("="*80)
        
        print("\n测试覆盖:")
        print("  ✅ 9个必填字段逐个缺失测试")
        print("  ✅ 4种多字段缺失组合")
        print("  ✅ 完整数据基准测试")
        print("  ✅ None值处理测试")
        print("  ✅ 额外字段容错测试")
        
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
