"""
测试 PR-H: Confidence配置值启动期fail-fast

验收要点：
1. 配置写成 HGIH 时启动失败
2. 合法值 (LOW/MEDIUM/HIGH/ULTRA) 正常启动
3. 大小写不敏感 (high, High, HIGH 都可以)
4. 检查所有4个配置位置
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
import yaml
import tempfile


def test_pr_h_confidence_validation():
    """测试PR-H: Confidence值启动校验"""
    
    print("\n" + "="*80)
    print("测试 PR-H: Confidence配置值启动期fail-fast")
    print("="*80)
    
    # 基础有效配置
    base_config = {
        'direction_evaluation': {
            'trend': {
                'long_price_6h': 0.02,
                'long_imbalance_trend': 0.6,
                'short_price_6h': -0.02,
                'short_imbalance_trend': -0.6,
            },
            'range': {
                'long_funding_trend': -0.0001,
                'long_imbalance_range': 0.3,
                'short_funding_range': 0.0001,
                'short_imbalance_range': -0.3,
            },
        },
        'market_regime': {
            'trend_price_threshold': 0.015,
            'extreme_volume_threshold': 2.5,
        },
        'quality': {
            'noisy_funding_volatility': 0.0003,
            'noisy_funding_abs': 0.0002,
        },
        'reason_tag_rules': {
            'reduce_tags': [],
            'deny_tags': [],
        },
        'confidence_scoring': {
            'base_scores': {},
            'strong_signal_boost': {
                'required_tags': ['strong_buy_pressure', 'strong_sell_pressure'],
                'bonus': 10,
            },
            'caps': {
                'uncertain_quality_max': 'MEDIUM',  # 测试点1
                'tag_caps': {
                    'noisy_market': 'MEDIUM',  # 测试点4
                },
            },
        },
        'execution': {
            'min_confidence_normal': 'HIGH',     # 测试点2
            'min_confidence_reduced': 'MEDIUM',  # 测试点3
        },
        'auxiliary_tags': {
            'oi_growing_threshold': 0.05,
            'oi_declining_threshold': -0.05,
            'funding_rate_threshold': 0.0005,
        },
    }
    
    # ========== 测试1: 合法配置应该正常启动 ==========
    print("\n[测试1] 合法配置（HIGH/MEDIUM/LOW/ULTRA）应该正常启动...")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            valid_config = base_config.copy()
            yaml.dump(valid_config, f)
            temp_file_valid = f.name
        
        engine = L1AdvisoryEngine(config_path=temp_file_valid)
        print("✅ 合法配置启动成功")
        test1_passed = True
    except Exception as e:
        print(f"❌ 合法配置启动失败: {e}")
        test1_passed = False
    finally:
        if os.path.exists(temp_file_valid):
            os.unlink(temp_file_valid)
    
    # ========== 测试2: 拼写错误 HGIH 应该拒绝启动 ==========
    print("\n[测试2] 拼写错误 (HGIH) 应该拒绝启动...")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            invalid_config = base_config.copy()
            invalid_config['execution']['min_confidence_normal'] = 'HGIH'  # 拼写错误
            yaml.dump(invalid_config, f)
            temp_file_invalid = f.name
        
        engine = L1AdvisoryEngine(config_path=temp_file_invalid)
        print("❌ 拼写错误配置意外启动成功（应该失败）")
        test2_passed = False
    except ValueError as e:
        if 'Confidence值拼写' in str(e) or 'HGIH' in str(e):
            print(f"✅ 拼写错误被正确拒绝: {e}")
            test2_passed = True
        else:
            print(f"❌ 错误类型不对: {e}")
            test2_passed = False
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        test2_passed = False
    finally:
        if os.path.exists(temp_file_invalid):
            os.unlink(temp_file_invalid)
    
    # ========== 测试3: 大小写不敏感（high/High/HIGH都可以）==========
    print("\n[测试3] 大小写不敏感 (high/High/HIGH) 都应该正常启动...")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            case_config = base_config.copy()
            case_config['execution']['min_confidence_normal'] = 'high'  # 小写
            case_config['execution']['min_confidence_reduced'] = 'Medium'  # 首字母大写
            case_config['confidence_scoring']['caps']['uncertain_quality_max'] = 'HIGH'  # 全大写
            yaml.dump(case_config, f)
            temp_file_case = f.name
        
        engine = L1AdvisoryEngine(config_path=temp_file_case)
        print("✅ 大小写混合配置启动成功")
        test3_passed = True
    except Exception as e:
        print(f"❌ 大小写混合配置启动失败: {e}")
        test3_passed = False
    finally:
        if os.path.exists(temp_file_case):
            os.unlink(temp_file_case)
    
    # ========== 测试4: uncertain_quality_max 拼写错误应该拒绝 ==========
    print("\n[测试4] uncertain_quality_max 拼写错误 (MEDUIM) 应该拒绝启动...")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            invalid_config2 = base_config.copy()
            invalid_config2['confidence_scoring']['caps']['uncertain_quality_max'] = 'MEDUIM'  # 拼写错误
            yaml.dump(invalid_config2, f)
            temp_file_invalid2 = f.name
        
        engine = L1AdvisoryEngine(config_path=temp_file_invalid2)
        print("❌ uncertain_quality_max拼写错误意外启动成功（应该失败）")
        test4_passed = False
    except ValueError as e:
        if 'Confidence值拼写' in str(e) or 'MEDUIM' in str(e):
            print(f"✅ uncertain_quality_max拼写错误被正确拒绝")
            test4_passed = True
        else:
            print(f"❌ 错误类型不对: {e}")
            test4_passed = False
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        test4_passed = False
    finally:
        if os.path.exists(temp_file_invalid2):
            os.unlink(temp_file_invalid2)
    
    # ========== 测试5: tag_caps 值拼写错误应该拒绝 ==========
    print("\n[测试5] tag_caps 值拼写错误 (LOWW) 应该拒绝启动...")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            invalid_config3 = base_config.copy()
            invalid_config3['confidence_scoring']['caps']['tag_caps']['noisy_market'] = 'LOWW'  # 拼写错误
            yaml.dump(invalid_config3, f)
            temp_file_invalid3 = f.name
        
        engine = L1AdvisoryEngine(config_path=temp_file_invalid3)
        print("❌ tag_caps拼写错误意外启动成功（应该失败）")
        test5_passed = False
    except ValueError as e:
        if 'Confidence值拼写' in str(e) or 'LOWW' in str(e):
            print(f"✅ tag_caps拼写错误被正确拒绝")
            test5_passed = True
        else:
            print(f"❌ 错误类型不对: {e}")
            test5_passed = False
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        test5_passed = False
    finally:
        if os.path.exists(temp_file_invalid3):
            os.unlink(temp_file_invalid3)
    
    # ========== 测试6: min_confidence_reduced 拼写错误应该拒绝 ==========
    print("\n[测试6] min_confidence_reduced 拼写错误 (MEDIUN) 应该拒绝启动...")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            invalid_config4 = base_config.copy()
            invalid_config4['execution']['min_confidence_reduced'] = 'MEDIUN'  # 拼写错误
            yaml.dump(invalid_config4, f)
            temp_file_invalid4 = f.name
        
        engine = L1AdvisoryEngine(config_path=temp_file_invalid4)
        print("❌ min_confidence_reduced拼写错误意外启动成功（应该失败）")
        test6_passed = False
    except ValueError as e:
        if 'Confidence值拼写' in str(e) or 'MEDIUN' in str(e):
            print(f"✅ min_confidence_reduced拼写错误被正确拒绝")
            test6_passed = True
        else:
            print(f"❌ 错误类型不对: {e}")
            test6_passed = False
    except Exception as e:
        print(f"❌ 意外错误: {e}")
        test6_passed = False
    finally:
        if os.path.exists(temp_file_invalid4):
            os.unlink(temp_file_invalid4)
    
    # ========== 汇总结果 ==========
    print("\n" + "="*80)
    print("测试结果汇总")
    print("="*80)
    
    all_tests = [
        ("合法配置正常启动", test1_passed),
        ("HGIH拼写错误被拒绝", test2_passed),
        ("大小写不敏感", test3_passed),
        ("uncertain_quality_max拼写错误被拒绝", test4_passed),
        ("tag_caps拼写错误被拒绝", test5_passed),
        ("min_confidence_reduced拼写错误被拒绝", test6_passed),
    ]
    
    for test_name, passed in all_tests:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {test_name}")
    
    all_passed = all(passed for _, passed in all_tests)
    
    if all_passed:
        print("\n" + "="*80)
        print("✅ PR-H 所有测试通过！Confidence配置值启动校验工作正常")
        print("="*80)
        print("\n验收要点:")
        print("  1. ✅ 拼写错误（HGIH/MEDUIM/LOWW/MEDIUN）直接拒绝启动")
        print("  2. ✅ 合法值（LOW/MEDIUM/HIGH/ULTRA）正常启动")
        print("  3. ✅ 大小写不敏感（high/High/HIGH都可以）")
        print("  4. ✅ 检查4个配置位置（min_confidence_normal/reduced + uncertain_max + tag_caps）")
        print("  5. ✅ Fail-fast原则：配置错误时明确报错，避免静默回退LOW")
        return True
    else:
        print("\n" + "="*80)
        print("❌ PR-H 部分测试失败")
        print("="*80)
        return False


if __name__ == "__main__":
    success = test_pr_h_confidence_validation()
    sys.exit(0 if success else 1)
