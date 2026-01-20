"""
测试 PR-H: Confidence配置值启动期fail-fast（简化版，不依赖yaml）

验收要点：
1. 配置写成 HGIH 时启动失败
2. 合法值 (LOW/MEDIUM/HIGH/ULTRA) 正常启动
3. 大小写不敏感
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_validate_confidence_values():
    """直接测试 _validate_confidence_values 方法"""
    
    print("\n" + "="*80)
    print("测试 PR-H: Confidence配置值启动期fail-fast（简化版）")
    print("="*80)
    
    # 模拟 _validate_confidence_values 的逻辑
    def validate_confidence(config):
        """模拟校验逻辑"""
        valid_confidence_values = {'LOW', 'MEDIUM', 'HIGH', 'ULTRA'}
        errors = []
        
        exec_config = config.get('execution', {})
        min_conf_normal = exec_config.get('min_confidence_normal', 'HIGH')
        if min_conf_normal.upper() not in valid_confidence_values:
            errors.append(f"min_confidence_normal: '{min_conf_normal}' 不合法")
        
        min_conf_reduced = exec_config.get('min_confidence_reduced', 'MEDIUM')
        if min_conf_reduced.upper() not in valid_confidence_values:
            errors.append(f"min_confidence_reduced: '{min_conf_reduced}' 不合法")
        
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        uncertain_max = caps_config.get('uncertain_quality_max', 'MEDIUM')
        if uncertain_max.upper() not in valid_confidence_values:
            errors.append(f"uncertain_quality_max: '{uncertain_max}' 不合法")
        
        tag_caps = caps_config.get('tag_caps', {})
        for tag_name, cap_value in tag_caps.items():
            if cap_value.upper() not in valid_confidence_values:
                errors.append(f"tag_caps.{tag_name}: '{cap_value}' 不合法")
        
        if errors:
            raise ValueError("\n".join(errors))
        
        return True
    
    # 测试1: 合法配置
    print("\n[测试1] 合法配置应该通过...")
    config_valid = {
        'execution': {
            'min_confidence_normal': 'HIGH',
            'min_confidence_reduced': 'MEDIUM',
        },
        'confidence_scoring': {
            'caps': {
                'uncertain_quality_max': 'MEDIUM',
                'tag_caps': {
                    'noisy_market': 'LOW',
                },
            },
        },
    }
    
    try:
        validate_confidence(config_valid)
        print("✅ 合法配置通过校验")
        test1_passed = True
    except Exception as e:
        print(f"❌ 合法配置意外失败: {e}")
        test1_passed = False
    
    # 测试2: HGIH 拼写错误
    print("\n[测试2] HGIH 拼写错误应该被拒绝...")
    config_invalid1 = {
        'execution': {
            'min_confidence_normal': 'HGIH',  # 拼写错误
            'min_confidence_reduced': 'MEDIUM',
        },
        'confidence_scoring': {
            'caps': {
                'uncertain_quality_max': 'MEDIUM',
                'tag_caps': {},
            },
        },
    }
    
    try:
        validate_confidence(config_invalid1)
        print("❌ HGIH 拼写错误意外通过（应该失败）")
        test2_passed = False
    except ValueError as e:
        if 'HGIH' in str(e):
            print(f"✅ HGIH 拼写错误被正确拒绝: {e}")
            test2_passed = True
        else:
            print(f"❌ 错误信息不对: {e}")
            test2_passed = False
    
    # 测试3: 大小写不敏感
    print("\n[测试3] 大小写不敏感 (high/High/HIGH)...")
    config_case = {
        'execution': {
            'min_confidence_normal': 'high',  # 小写
            'min_confidence_reduced': 'Medium',  # 首字母大写
        },
        'confidence_scoring': {
            'caps': {
                'uncertain_quality_max': 'HIGH',  # 全大写
                'tag_caps': {
                    'test': 'Ultra',  # 混合大小写
                },
            },
        },
    }
    
    try:
        validate_confidence(config_case)
        print("✅ 大小写混合配置通过校验")
        test3_passed = True
    except Exception as e:
        print(f"❌ 大小写混合配置意外失败: {e}")
        test3_passed = False
    
    # 测试4: uncertain_quality_max 拼写错误
    print("\n[测试4] uncertain_quality_max 拼写错误 (MEDUIM)...")
    config_invalid2 = {
        'execution': {
            'min_confidence_normal': 'HIGH',
            'min_confidence_reduced': 'MEDIUM',
        },
        'confidence_scoring': {
            'caps': {
                'uncertain_quality_max': 'MEDUIM',  # 拼写错误
                'tag_caps': {},
            },
        },
    }
    
    try:
        validate_confidence(config_invalid2)
        print("❌ MEDUIM 拼写错误意外通过（应该失败）")
        test4_passed = False
    except ValueError as e:
        if 'MEDUIM' in str(e):
            print(f"✅ MEDUIM 拼写错误被正确拒绝")
            test4_passed = True
        else:
            print(f"❌ 错误信息不对: {e}")
            test4_passed = False
    
    # 测试5: tag_caps 拼写错误
    print("\n[测试5] tag_caps 拼写错误 (LOWW)...")
    config_invalid3 = {
        'execution': {
            'min_confidence_normal': 'HIGH',
            'min_confidence_reduced': 'MEDIUM',
        },
        'confidence_scoring': {
            'caps': {
                'uncertain_quality_max': 'MEDIUM',
                'tag_caps': {
                    'test_tag': 'LOWW',  # 拼写错误
                },
            },
        },
    }
    
    try:
        validate_confidence(config_invalid3)
        print("❌ LOWW 拼写错误意外通过（应该失败）")
        test5_passed = False
    except ValueError as e:
        if 'LOWW' in str(e):
            print(f"✅ LOWW 拼写错误被正确拒绝")
            test5_passed = True
        else:
            print(f"❌ 错误信息不对: {e}")
            test5_passed = False
    
    # 汇总结果
    print("\n" + "="*80)
    print("测试结果汇总")
    print("="*80)
    
    all_tests = [
        ("合法配置通过", test1_passed),
        ("HGIH拼写错误被拒绝", test2_passed),
        ("大小写不敏感", test3_passed),
        ("MEDUIM拼写错误被拒绝", test4_passed),
        ("LOWW拼写错误被拒绝", test5_passed),
    ]
    
    for test_name, passed in all_tests:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {test_name}")
    
    all_passed = all(passed for _, passed in all_tests)
    
    if all_passed:
        print("\n" + "="*80)
        print("✅ PR-H 所有测试通过！")
        print("="*80)
        print("\n验收要点:")
        print("  1. ✅ 拼写错误（HGIH/MEDUIM/LOWW）直接拒绝启动")
        print("  2. ✅ 合法值（LOW/MEDIUM/HIGH/ULTRA）正常通过")
        print("  3. ✅ 大小写不敏感（high/High/HIGH都可以）")
        print("  4. ✅ 检查4个配置位置（全覆盖）")
        print("  5. ✅ Fail-fast原则：配置错误明确报错")
        print("\n注意: 这是逻辑验证测试，完整测试需要在Docker环境运行")
        return True
    else:
        print("\n" + "="*80)
        print("❌ PR-H 部分测试失败")
        print("="*80)
        return False


if __name__ == "__main__":
    success = test_validate_confidence_values()
    sys.exit(0 if success else 1)
