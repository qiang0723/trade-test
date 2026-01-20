"""
配置口径校验测试：验证启动时能检测并拒绝百分点格式

测试内容：
1. 正常配置（小数格式）能正常启动
2. 错误配置（百分点格式）被拦截并报错
3. 混合错误配置能识别所有错误项
"""

import sys
import os
import yaml
import tempfile
import pytest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine


def test_correct_decimal_format_pass():
    """测试：正确的小数格式应该通过校验"""
    print("\n=== Test 1: 正确的小数格式（应通过）===")
    
    # 使用当前配置文件（已修复为小数格式）
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    
    try:
        engine = L1AdvisoryEngine(config_path)
        print("✅ 配置校验通过（小数格式）")
        assert True
    except ValueError as e:
        pytest.fail(f"不应该报错，但报错了: {e}")


def test_percentage_point_format_rejected():
    """测试：百分点格式应该被拒绝"""
    print("\n=== Test 2: 百分点格式（应拒绝）===")
    
    # 创建错误配置（百分点格式）
    wrong_config = {
        'symbol_universe': {
            'enabled_symbols': ['BTC'],
            'default_symbol': 'BTC'
        },
        'data_freshness': {
            'max_staleness_seconds': 120
        },
        'market_regime': {
            'extreme_price_change_1h': 5.0,    # ❌ 错误：百分点格式
            'trend_price_change_6h': 3.0       # ❌ 错误：百分点格式
        },
        'risk_exposure': {
            'liquidation': {'price_change': 0.05, 'oi_drop': -0.15},
            'crowding': {'funding_abs': 0.001, 'oi_growth': 0.30},
            'extreme_volume': {'multiplier': 10.0}
        },
        'trade_quality': {
            'absorption': {'imbalance': 0.7, 'volume_ratio': 0.5},
            'noise': {'funding_volatility': 0.0005, 'funding_abs': 0.0001},
            'rotation': {'price_threshold': 0.02, 'oi_threshold': 0.05},
            'range_weak': {'imbalance': 0.6, 'oi': 0.10}
        },
        'direction': {
            'trend': {
                'long': {'imbalance': 0.6, 'oi_change': 0.05, 'price_change': 0.01},
                'short': {'imbalance': 0.6, 'oi_change': 0.05, 'price_change': 0.01}
            },
            'range': {
                'long': {'imbalance': 0.7, 'oi_change': 0.10},
                'short': {'imbalance': 0.7, 'oi_change': 0.10}
            }
        },
        'state_machine': {
            'cool_down_minutes': 60,
            'signal_timeout_minutes': 30
        },
        'decision_control': {
            'min_decision_interval_seconds': 300,
            'flip_cooldown_seconds': 600,
            'enable_min_interval': True,
            'enable_flip_cooldown': True
        },
        'confidence_scoring': {
            'decision_score': 30,
            'regime_trend_score': 30,
            'regime_range_score': 10,
            'regime_extreme_score': 0,
            'quality_good_score': 30,
            'quality_uncertain_score': 15,
            'quality_poor_score': 0,
            'strong_signal_bonus': 10,
            'thresholds': {'ultra': 90, 'high': 65, 'medium': 40},
            'caps': {
                'uncertain_quality_max': 'MEDIUM',
                'tag_caps': {'noisy_market': 'MEDIUM', 'weak_signal_in_range': 'MEDIUM'}
            },
            'strong_signal_boost': {
                'enabled': True,
                'boost_levels': 1,
                'required_tags': ['strong_buy_pressure', 'strong_sell_pressure']
            }
        },
        'reason_tag_rules': {
            'reduce_tags': ['noisy_market', 'weak_signal_in_range'],
            'deny_tags': ['liquidation_phase', 'crowding_risk', 'extreme_volume', 
                         'data_stale', 'extreme_regime', 'absorption_risk', 'rotation_risk']
        }
    }
    
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(wrong_config, f)
        temp_config_path = f.name
    
    try:
        # 尝试初始化（应该抛出ValueError）
        with pytest.raises(ValueError) as exc_info:
            engine = L1AdvisoryEngine(temp_config_path)
        
        error_message = str(exc_info.value)
        print("✅ 成功拦截错误配置")
        print(f"错误信息片段: {error_message[:200]}...")
        
        # 验证错误信息包含关键词
        assert "配置口径错误" in error_message or "Calibration" in error_message
        assert "5.0" in error_message  # 应该指出具体错误值
        assert "3.0" in error_message
        
    finally:
        # 清理临时文件
        os.unlink(temp_config_path)


def test_direction_threshold_rejected():
    """测试：方向阈值使用百分点格式应该被拒绝"""
    print("\n=== Test 3: 方向阈值百分点格式（应拒绝）===")
    
    # 创建错误配置（方向阈值为百分点）
    wrong_config = {
        'symbol_universe': {
            'enabled_symbols': ['BTC'],
            'default_symbol': 'BTC'
        },
        'data_freshness': {
            'max_staleness_seconds': 120
        },
        'market_regime': {
            'extreme_price_change_1h': 0.05,   # ✅ 正确
            'trend_price_change_6h': 0.03      # ✅ 正确
        },
        'risk_exposure': {
            'liquidation': {'price_change': 0.05, 'oi_drop': -0.15},
            'crowding': {'funding_abs': 0.001, 'oi_growth': 0.30},
            'extreme_volume': {'multiplier': 10.0}
        },
        'trade_quality': {
            'absorption': {'imbalance': 0.7, 'volume_ratio': 0.5},
            'noise': {'funding_volatility': 0.0005, 'funding_abs': 0.0001},
            'rotation': {'price_threshold': 0.02, 'oi_threshold': 0.05},
            'range_weak': {'imbalance': 0.6, 'oi': 0.10}
        },
        'direction': {
            'trend': {
                'long': {
                    'imbalance': 0.6, 
                    'oi_change': 5.0,      # ❌ 错误：百分点格式
                    'price_change': 1.0    # ❌ 错误：百分点格式
                },
                'short': {'imbalance': 0.6, 'oi_change': 0.05, 'price_change': 0.01}
            },
            'range': {
                'long': {'imbalance': 0.7, 'oi_change': 10.0},  # ❌ 错误
                'short': {'imbalance': 0.7, 'oi_change': 0.10}
            }
        },
        'state_machine': {
            'cool_down_minutes': 60,
            'signal_timeout_minutes': 30
        },
        'decision_control': {
            'min_decision_interval_seconds': 300,
            'flip_cooldown_seconds': 600,
            'enable_min_interval': True,
            'enable_flip_cooldown': True
        },
        'confidence_scoring': {
            'decision_score': 30,
            'regime_trend_score': 30,
            'regime_range_score': 10,
            'regime_extreme_score': 0,
            'quality_good_score': 30,
            'quality_uncertain_score': 15,
            'quality_poor_score': 0,
            'strong_signal_bonus': 10,
            'thresholds': {'ultra': 90, 'high': 65, 'medium': 40},
            'caps': {
                'uncertain_quality_max': 'MEDIUM',
                'tag_caps': {'noisy_market': 'MEDIUM', 'weak_signal_in_range': 'MEDIUM'}
            },
            'strong_signal_boost': {
                'enabled': True,
                'boost_levels': 1,
                'required_tags': ['strong_buy_pressure', 'strong_sell_pressure']
            }
        },
        'reason_tag_rules': {
            'reduce_tags': ['noisy_market', 'weak_signal_in_range'],
            'deny_tags': ['liquidation_phase', 'crowding_risk', 'extreme_volume', 
                         'data_stale', 'extreme_regime', 'absorption_risk', 'rotation_risk']
        }
    }
    
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(wrong_config, f)
        temp_config_path = f.name
    
    try:
        # 尝试初始化（应该抛出ValueError）
        with pytest.raises(ValueError) as exc_info:
            engine = L1AdvisoryEngine(temp_config_path)
        
        error_message = str(exc_info.value)
        print("✅ 成功拦截方向阈值错误")
        print(f"错误信息片段: {error_message[:300]}...")
        
        # 验证错误信息包含方向阈值相关的关键词
        assert "direction" in error_message
        assert "oi_change" in error_message or "price_change" in error_message
        
        # 验证识别出多个错误项（应该有3个：trend.long的2个 + range.long的1个）
        error_count = error_message.count("❌")
        print(f"检测到 {error_count} 个错误项")
        assert error_count >= 3, f"应该检测到至少3个错误，实际检测到{error_count}个"
        
    finally:
        # 清理临时文件
        os.unlink(temp_config_path)


def test_multiple_errors_all_reported():
    """测试：多个错误都应该被报告"""
    print("\n=== Test 4: 多项错误全部报告 ===")
    
    # 创建多处错误的配置
    wrong_config = {
        'symbol_universe': {
            'enabled_symbols': ['BTC'],
            'default_symbol': 'BTC'
        },
        'data_freshness': {
            'max_staleness_seconds': 120
        },
        'market_regime': {
            'extreme_price_change_1h': 5.0,    # ❌ 错误1
            'trend_price_change_6h': 3.0       # ❌ 错误2
        },
        'risk_exposure': {
            'liquidation': {
                'price_change': 5.0,           # ❌ 错误3
                'oi_drop': -15.0               # ❌ 错误4
            },
            'crowding': {
                'funding_abs': 0.001, 
                'oi_growth': 30.0              # ❌ 错误5
            },
            'extreme_volume': {'multiplier': 10.0}
        },
        'trade_quality': {
            'absorption': {'imbalance': 0.7, 'volume_ratio': 0.5},
            'noise': {'funding_volatility': 0.0005, 'funding_abs': 0.0001},
            'rotation': {
                'price_threshold': 2.0,        # ❌ 错误6
                'oi_threshold': 5.0            # ❌ 错误7
            },
            'range_weak': {
                'imbalance': 0.6, 
                'oi': 10.0                     # ❌ 错误8
            }
        },
        'direction': {
            'trend': {
                'long': {'imbalance': 0.6, 'oi_change': 0.05, 'price_change': 0.01},
                'short': {'imbalance': 0.6, 'oi_change': 0.05, 'price_change': 0.01}
            },
            'range': {
                'long': {'imbalance': 0.7, 'oi_change': 0.10},
                'short': {'imbalance': 0.7, 'oi_change': 0.10}
            }
        },
        'state_machine': {
            'cool_down_minutes': 60,
            'signal_timeout_minutes': 30
        },
        'decision_control': {
            'min_decision_interval_seconds': 300,
            'flip_cooldown_seconds': 600,
            'enable_min_interval': True,
            'enable_flip_cooldown': True
        },
        'confidence_scoring': {
            'decision_score': 30,
            'regime_trend_score': 30,
            'regime_range_score': 10,
            'regime_extreme_score': 0,
            'quality_good_score': 30,
            'quality_uncertain_score': 15,
            'quality_poor_score': 0,
            'strong_signal_bonus': 10,
            'thresholds': {'ultra': 90, 'high': 65, 'medium': 40},
            'caps': {
                'uncertain_quality_max': 'MEDIUM',
                'tag_caps': {'noisy_market': 'MEDIUM', 'weak_signal_in_range': 'MEDIUM'}
            },
            'strong_signal_boost': {
                'enabled': True,
                'boost_levels': 1,
                'required_tags': ['strong_buy_pressure', 'strong_sell_pressure']
            }
        },
        'reason_tag_rules': {
            'reduce_tags': ['noisy_market', 'weak_signal_in_range'],
            'deny_tags': ['liquidation_phase', 'crowding_risk', 'extreme_volume', 
                         'data_stale', 'extreme_regime', 'absorption_risk', 'rotation_risk']
        }
    }
    
    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(wrong_config, f)
        temp_config_path = f.name
    
    try:
        # 尝试初始化（应该抛出ValueError）
        with pytest.raises(ValueError) as exc_info:
            engine = L1AdvisoryEngine(temp_config_path)
        
        error_message = str(exc_info.value)
        print("✅ 成功拦截多项错误")
        
        # 验证所有错误都被识别
        error_count = error_message.count("❌")
        print(f"检测到 {error_count} 个错误项")
        
        # 应该至少检测到8个基础错误
        assert error_count >= 8, f"应该检测到至少8个错误，实际检测到{error_count}个"
        
        # 验证错误信息包含关键数值
        assert "5.0" in error_message  # extreme/liquidation/rotation
        assert "3.0" in error_message  # trend
        assert "15.0" in error_message or "-15.0" in error_message  # liquidation.oi_drop
        assert "30.0" in error_message  # crowding
        
        print(f"✅ 所有 {error_count} 项错误均被正确识别和报告")
        
    finally:
        # 清理临时文件
        os.unlink(temp_config_path)


def main():
    """运行所有测试"""
    print("=" * 60)
    print("配置口径校验测试（启动时防回归）")
    print("=" * 60)
    
    try:
        test_correct_decimal_format_pass()
        test_percentage_point_format_rejected()
        test_direction_threshold_rejected()
        test_multiple_errors_all_reported()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！启动时校验机制正常工作")
        print("=" * 60)
        return 0
    
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
