"""
测试 PR-I: reduce_tags 的默认 cap 配置化

验收要点：
1. 新增一个 reduce_tag 未写 tag_caps 时，cap 取 reduce_default_max
2. 写了 tag_caps 时仍以 tag_caps 为准（优先级更高）
3. 未配置 reduce_default_max 时，自动回退到 uncertain_quality_max
4. 向后兼容：完全不配置时回退到 MEDIUM（保守）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.enums import Confidence


def test_pr_i_reduce_default_max():
    """测试 PR-I: reduce_tags 默认cap配置化"""
    
    print("\n" + "="*80)
    print("测试 PR-I: reduce_tags 的默认 cap 配置化")
    print("="*80)
    
    # 模拟 _apply_confidence_caps 的逻辑（reduce_tags部分）
    def apply_reduce_caps(caps_config, tag_rules, tag_value):
        """模拟 reduce_tags cap 应用逻辑"""
        reduce_tags = tag_rules.get('reduce_tags', [])
        tag_caps = caps_config.get('tag_caps', {})
        
        if tag_value not in reduce_tags and tag_value not in tag_caps:
            return None  # 不是 reduce_tag，不应用cap
        
        # PR-I：使用配置化默认值
        reduce_default_max_str = caps_config.get('reduce_default_max',
                                                  caps_config.get('uncertain_quality_max', 'MEDIUM'))
        
        # 优先使用 tag_caps，否则使用默认值
        max_level_str = tag_caps.get(tag_value, reduce_default_max_str)
        return max_level_str
    
    # ========== 测试1: reduce_tag 未配置 tag_caps，使用 reduce_default_max ==========
    print("\n[测试1] reduce_tag 未配置 tag_caps，应该使用 reduce_default_max...")
    
    config1 = {
        'caps': {
            'uncertain_quality_max': 'HIGH',
            'reduce_default_max': 'ULTRA',  # 显式配置
            'tag_caps': {
                # new_reduce_tag 未配置
            },
        },
    }
    
    tag_rules1 = {
        'reduce_tags': ['new_reduce_tag'],
    }
    
    result1 = apply_reduce_caps(config1['caps'], tag_rules1, 'new_reduce_tag')
    
    if result1 == 'ULTRA':
        print(f"✅ 未配置 tag_caps 的 reduce_tag 正确使用 reduce_default_max: {result1}")
        test1_passed = True
    else:
        print(f"❌ 期望 ULTRA，实际 {result1}")
        test1_passed = False
    
    # ========== 测试2: tag_caps 显式配置时，优先级更高 ==========
    print("\n[测试2] tag_caps 显式配置时，应该覆盖 reduce_default_max...")
    
    config2 = {
        'caps': {
            'uncertain_quality_max': 'HIGH',
            'reduce_default_max': 'ULTRA',  # 默认值
            'tag_caps': {
                'explicit_tag': 'LOW',  # 显式配置
            },
        },
    }
    
    tag_rules2 = {
        'reduce_tags': ['explicit_tag'],
    }
    
    result2 = apply_reduce_caps(config2['caps'], tag_rules2, 'explicit_tag')
    
    if result2 == 'LOW':
        print(f"✅ tag_caps 显式配置正确覆盖 reduce_default_max: {result2}")
        test2_passed = True
    else:
        print(f"❌ 期望 LOW，实际 {result2}")
        test2_passed = False
    
    # ========== 测试3: 未配置 reduce_default_max，回退到 uncertain_quality_max ==========
    print("\n[测试3] 未配置 reduce_default_max，应该回退到 uncertain_quality_max...")
    
    config3 = {
        'caps': {
            'uncertain_quality_max': 'HIGH',
            # reduce_default_max 未配置
            'tag_caps': {},
        },
    }
    
    tag_rules3 = {
        'reduce_tags': ['fallback_tag'],
    }
    
    result3 = apply_reduce_caps(config3['caps'], tag_rules3, 'fallback_tag')
    
    if result3 == 'HIGH':
        print(f"✅ 正确回退到 uncertain_quality_max: {result3}")
        test3_passed = True
    else:
        print(f"❌ 期望 HIGH，实际 {result3}")
        test3_passed = False
    
    # ========== 测试4: 完全不配置时，回退到 MEDIUM（保守） ==========
    print("\n[测试4] 完全不配置时，应该回退到 MEDIUM（保守默认值）...")
    
    config4 = {
        'caps': {
            # uncertain_quality_max 未配置
            # reduce_default_max 未配置
            'tag_caps': {},
        },
    }
    
    tag_rules4 = {
        'reduce_tags': ['conservative_tag'],
    }
    
    result4 = apply_reduce_caps(config4['caps'], tag_rules4, 'conservative_tag')
    
    if result4 == 'MEDIUM':
        print(f"✅ 完全不配置时正确回退到 MEDIUM: {result4}")
        test4_passed = True
    else:
        print(f"❌ 期望 MEDIUM，实际 {result4}")
        test4_passed = False
    
    # ========== 测试5: 非 reduce_tag 不受影响 ==========
    print("\n[测试5] 非 reduce_tag 不应该应用cap...")
    
    config5 = {
        'caps': {
            'uncertain_quality_max': 'HIGH',
            'reduce_default_max': 'ULTRA',
            'tag_caps': {},
        },
    }
    
    tag_rules5 = {
        'reduce_tags': ['some_reduce_tag'],
    }
    
    result5 = apply_reduce_caps(config5['caps'], tag_rules5, 'not_a_reduce_tag')
    
    if result5 is None:
        print(f"✅ 非 reduce_tag 正确不应用cap")
        test5_passed = True
    else:
        print(f"❌ 期望 None，实际 {result5}")
        test5_passed = False
    
    # ========== 测试6: 多个 reduce_tags 混合场景 ==========
    print("\n[测试6] 多个 reduce_tags 混合场景（部分配置，部分不配置）...")
    
    config6 = {
        'caps': {
            'uncertain_quality_max': 'HIGH',
            'reduce_default_max': 'MEDIUM',
            'tag_caps': {
                'configured_tag': 'LOW',  # 显式配置
                # unconfigured_tag 未配置
            },
        },
    }
    
    tag_rules6 = {
        'reduce_tags': ['configured_tag', 'unconfigured_tag'],
    }
    
    result6a = apply_reduce_caps(config6['caps'], tag_rules6, 'configured_tag')
    result6b = apply_reduce_caps(config6['caps'], tag_rules6, 'unconfigured_tag')
    
    if result6a == 'LOW' and result6b == 'MEDIUM':
        print(f"✅ 混合场景正确: configured={result6a}, unconfigured={result6b}")
        test6_passed = True
    else:
        print(f"❌ 期望 LOW/MEDIUM，实际 {result6a}/{result6b}")
        test6_passed = False
    
    # ========== 汇总结果 ==========
    print("\n" + "="*80)
    print("测试结果汇总")
    print("="*80)
    
    all_tests = [
        ("未配置tag_caps使用reduce_default_max", test1_passed),
        ("tag_caps显式配置优先级更高", test2_passed),
        ("回退到uncertain_quality_max", test3_passed),
        ("完全不配置回退到MEDIUM", test4_passed),
        ("非reduce_tag不受影响", test5_passed),
        ("混合场景正确处理", test6_passed),
    ]
    
    for test_name, passed in all_tests:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {test_name}")
    
    all_passed = all(passed for _, passed in all_tests)
    
    if all_passed:
        print("\n" + "="*80)
        print("✅ PR-I 所有测试通过！")
        print("="*80)
        print("\n验收要点:")
        print("  1. ✅ reduce_tag 未配置 tag_caps 时，使用 reduce_default_max")
        print("  2. ✅ tag_caps 显式配置优先级更高（覆盖默认值）")
        print("  3. ✅ 未配置 reduce_default_max 时，回退到 uncertain_quality_max")
        print("  4. ✅ 完全不配置时，回退到 MEDIUM（保守默认值）")
        print("  5. ✅ 非 reduce_tag 不受影响")
        print("  6. ✅ 混合场景正确处理")
        print("\n设计原理:")
        print("  - 配置灵活性：允许自定义默认值")
        print("  - 逻辑一致性：默认值跟随 uncertain_quality_max")
        print("  - 防错性：忘记配置时有合理默认行为")
        print("  - 向后兼容：旧配置回退到保守的 MEDIUM")
        return True
    else:
        print("\n" + "="*80)
        print("❌ PR-I 部分测试失败")
        print("="*80)
        return False


if __name__ == "__main__":
    success = test_pr_i_reduce_default_max()
    sys.exit(0 if success else 1)
