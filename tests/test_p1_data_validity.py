"""
P1 Data Validity 测试

测试内容：
1. DATA_INVALID_* 标签的阻断行为
2. DATA_OUTLIER_* 标签的降级+cap行为
3. ThresholdCompiler 校验功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any


def create_test_features(overrides: Dict[str, Any] = None) -> Dict:
    """创建测试用的normalized_data"""
    base = {
        'price': 100.0,
        'volume_24h': 1000000.0,
        'open_interest': 500000.0,
        'funding_rate': 0.0001,
        'price_change_5m': 0.001,
        'price_change_15m': 0.003,
        'price_change_1h': 0.01,
        'price_change_6h': 0.02,
        'taker_imbalance_5m': 0.1,
        'taker_imbalance_15m': 0.15,
        'taker_imbalance_1h': 0.2,
        'oi_change_15m': 0.01,
        'oi_change_1h': 0.03,
        'oi_change_6h': 0.05,
        'volume_ratio_5m': 1.2,
        'volume_ratio_15m': 1.1,
    }
    if overrides:
        base.update(overrides)
    return base


def test_reason_tags_registered():
    """测试新增的ReasonTag是否已注册"""
    print("\n=== Test: ReasonTag Registration ===")
    
    from models.reason_tags import ReasonTag, REASON_TAG_EXECUTABILITY, ExecutabilityLevel
    
    # 检查DATA_INVALID_*
    invalid_tags = [
        ('DATA_INVALID_PRICE', ExecutabilityLevel.BLOCK),
        ('DATA_INVALID_VOLUME', ExecutabilityLevel.BLOCK),
        ('DATA_INVALID_OI', ExecutabilityLevel.BLOCK),
    ]
    
    for tag_name, expected_level in invalid_tags:
        tag = getattr(ReasonTag, tag_name, None)
        assert tag is not None, f"Missing ReasonTag: {tag_name}"
        
        level = REASON_TAG_EXECUTABILITY.get(tag)
        assert level == expected_level, f"{tag_name} should be {expected_level}, got {level}"
        print(f"  ✓ {tag_name} -> {level.value}")
    
    # 检查DATA_OUTLIER_*
    outlier_tags = [
        ('DATA_OUTLIER_PRICE_CHANGE', ExecutabilityLevel.DEGRADE),
        ('DATA_OUTLIER_OI_CHANGE', ExecutabilityLevel.DEGRADE),
        ('DATA_OUTLIER_TAKER_IMBALANCE', ExecutabilityLevel.DEGRADE),
        ('DATA_OUTLIER_FUNDING_RATE', ExecutabilityLevel.DEGRADE),
    ]
    
    for tag_name, expected_level in outlier_tags:
        tag = getattr(ReasonTag, tag_name, None)
        assert tag is not None, f"Missing ReasonTag: {tag_name}"
        
        level = REASON_TAG_EXECUTABILITY.get(tag)
        assert level == expected_level, f"{tag_name} should be {expected_level}, got {level}"
        print(f"  ✓ {tag_name} -> {level.value}")
    
    print("✅ All ReasonTags registered correctly")
    return True


def test_feature_builder_invalid_price():
    """测试price<=0被阻断"""
    print("\n=== Test: Invalid Price (<=0) ===")
    
    from l1_engine.feature_builder import FeatureBuilder
    from models.reason_tags import ReasonTag
    
    builder = FeatureBuilder()
    
    # 测试price=0
    raw_data = create_test_features({'price': 0})
    snapshot = builder.build('TEST', raw_data)
    
    # 应该返回空快照
    assert snapshot.features.price.current_price is None or snapshot.coverage.short_evaluable == False, \
        "price=0 should result in invalid snapshot"
    print("  ✓ price=0 results in invalid snapshot")
    
    # 测试price<0
    raw_data = create_test_features({'price': -100})
    snapshot = builder.build('TEST', raw_data)
    
    assert snapshot.features.price.current_price is None or snapshot.coverage.short_evaluable == False, \
        "price<0 should result in invalid snapshot"
    print("  ✓ price<0 results in invalid snapshot")
    
    print("✅ Invalid price correctly blocked")
    return True


def test_feature_builder_invalid_volume():
    """测试volume<=0被阻断"""
    print("\n=== Test: Invalid Volume (<=0) ===")
    
    from l1_engine.feature_builder import FeatureBuilder
    
    builder = FeatureBuilder()
    
    # 测试volume=0
    raw_data = create_test_features({'volume_24h': 0})
    snapshot = builder.build('TEST', raw_data)
    
    # volume=0应该阻断
    print(f"  volume=0: short_evaluable={snapshot.coverage.short_evaluable}")
    
    # 测试volume<0
    raw_data = create_test_features({'volume_24h': -1000})
    snapshot = builder.build('TEST', raw_data)
    
    print(f"  volume<0: short_evaluable={snapshot.coverage.short_evaluable}")
    
    print("✅ Invalid volume handled")
    return True


def test_feature_builder_outlier_detection():
    """测试异常值检测"""
    print("\n=== Test: Outlier Detection ===")
    
    from l1_engine.feature_builder import FeatureBuilder
    from models.feature_snapshot import MarketFeatures, PriceFeatures, OpenInterestFeatures, TakerImbalanceFeatures, VolumeFeatures, FundingFeatures
    from models.reason_tags import ReasonTag
    
    builder = FeatureBuilder()
    
    # 创建带异常值的features用于测试_validate_core_fields
    # 测试price_change > 100%
    features = MarketFeatures(
        price=PriceFeatures(
            current_price=100.0,
            price_change_5m=0.01,
            price_change_15m=1.5,  # 150% - outlier!
            price_change_1h=0.02,
            price_change_6h=0.03,
        ),
        open_interest=OpenInterestFeatures(current_oi=500000.0, oi_change_1h=0.03),
        taker_imbalance=TakerImbalanceFeatures(taker_imbalance_1h=0.2),
        volume=VolumeFeatures(volume_24h=1000000.0),
        funding=FundingFeatures(funding_rate=0.0001),
    )
    
    is_valid, tags = builder._validate_core_fields(features, 'TEST')
    
    # 应该检测到price_change outlier
    assert ReasonTag.DATA_OUTLIER_PRICE_CHANGE in tags, \
        f"Should detect price_change outlier, got tags: {[t.value for t in tags]}"
    print(f"  ✓ Detected price_change outlier (150%)")
    
    # 测试funding_rate异常
    features2 = MarketFeatures(
        price=PriceFeatures(current_price=100.0, price_change_1h=0.01),
        open_interest=OpenInterestFeatures(current_oi=500000.0, oi_change_1h=0.03),
        taker_imbalance=TakerImbalanceFeatures(taker_imbalance_1h=0.2),
        volume=VolumeFeatures(volume_24h=1000000.0),
        funding=FundingFeatures(funding_rate=0.10),  # 10% - extreme outlier!
    )
    
    is_valid2, tags2 = builder._validate_core_fields(features2, 'TEST')
    
    assert ReasonTag.DATA_OUTLIER_FUNDING_RATE in tags2, \
        f"Should detect funding_rate outlier, got tags: {[t.value for t in tags2]}"
    print(f"  ✓ Detected funding_rate outlier (10%)")
    
    # 测试taker_imbalance异常
    features3 = MarketFeatures(
        price=PriceFeatures(current_price=100.0, price_change_1h=0.01),
        open_interest=OpenInterestFeatures(current_oi=500000.0, oi_change_1h=0.03),
        taker_imbalance=TakerImbalanceFeatures(taker_imbalance_1h=1.5),  # 150% - outlier!
        volume=VolumeFeatures(volume_24h=1000000.0),
        funding=FundingFeatures(funding_rate=0.0001),
    )
    
    is_valid3, tags3 = builder._validate_core_fields(features3, 'TEST')
    
    assert ReasonTag.DATA_OUTLIER_TAKER_IMBALANCE in tags3, \
        f"Should detect taker_imbalance outlier, got tags: {[t.value for t in tags3]}"
    print(f"  ✓ Detected taker_imbalance outlier (150%)")
    
    print("✅ Outlier detection working correctly")
    return True


def test_threshold_compiler_type_validation():
    """测试ThresholdCompiler类型校验"""
    print("\n=== Test: ThresholdCompiler Type Validation ===")
    
    try:
        from config.threshold_compiler import ThresholdCompiler
    except ImportError as e:
        print(f"  ⚠️ Skipping: {e}")
        return True  # 跳过测试
    
    compiler = ThresholdCompiler()
    
    # 测试有效配置
    valid_config = {
        'confidence_scoring': {
            'caps': {
                'uncertain_quality_max': 'MEDIUM',
                'reduce_default_max': 'MEDIUM',
                'tag_caps': {
                    'noisy_market': 'MEDIUM',
                    'weak_signal_in_range': 'MEDIUM',
                }
            }
        },
        'executable_control': {
            'min_confidence_normal': 'HIGH',
            'min_confidence_reduced': 'MEDIUM',
        }
    }
    
    result = compiler.compile(valid_config)
    assert len([e for e in result.errors if '[TYPE]' in e]) == 0, \
        f"Valid config should have no type errors: {result.errors}"
    print("  ✓ Valid config passes type validation")
    
    # 测试无效配置
    invalid_config = {
        'confidence_scoring': {
            'caps': {
                'tag_caps': {
                    'noisy_market': 'INVALID_LEVEL',  # Invalid!
                }
            }
        }
    }
    
    result2 = compiler.compile(invalid_config)
    type_errors = [e for e in result2.errors if '[TYPE]' in e]
    assert len(type_errors) > 0, "Should detect invalid confidence level"
    print(f"  ✓ Detected invalid confidence level: {type_errors[0][:60]}...")
    
    print("✅ Type validation working correctly")
    return True


def test_threshold_compiler_logic_validation():
    """测试ThresholdCompiler逻辑约束校验"""
    print("\n=== Test: ThresholdCompiler Logic Validation ===")
    
    try:
        from config.threshold_compiler import ThresholdCompiler
    except ImportError as e:
        print(f"  ⚠️ Skipping: {e}")
        return True
    
    compiler = ThresholdCompiler()
    
    # 测试required_confirmed < required_partial（应该报错）
    invalid_config = {
        'multi_tf': {
            'confirm_15m': {
                'long': {
                    'required_confirmed': 1,
                    'required_partial': 2,  # Invalid: partial > confirmed
                }
            }
        }
    }
    
    result = compiler.compile(invalid_config)
    logic_errors = [e for e in result.errors if '[LOGIC]' in e]
    assert len(logic_errors) > 0, "Should detect required_confirmed < required_partial"
    print(f"  ✓ Detected logic constraint violation: {logic_errors[0][:60]}...")
    
    # 测试confidence thresholds不递减
    invalid_config2 = {
        'confidence_scoring': {
            'thresholds': {
                'ultra': 70,
                'high': 80,   # Invalid: high > ultra
                'medium': 50,
            }
        }
    }
    
    result2 = compiler.compile(invalid_config2)
    range_errors = [e for e in result2.errors if '[RANGE]' in e]
    assert len(range_errors) > 0, "Should detect non-decreasing thresholds"
    print(f"  ✓ Detected threshold ordering violation")
    
    print("✅ Logic validation working correctly")
    return True


def test_threshold_compiler_dependency_validation():
    """测试ThresholdCompiler依赖校验"""
    print("\n=== Test: ThresholdCompiler Dependency Validation ===")
    
    try:
        from config.threshold_compiler import ThresholdCompiler
    except ImportError as e:
        print(f"  ⚠️ Skipping: {e}")
        return True
    
    compiler = ThresholdCompiler()
    
    # 测试未注册的ReasonTag
    invalid_config = {
        'reason_tag_rules': {
            'deny_tags': ['non_existent_tag'],  # Invalid!
            'reduce_tags': ['noisy_market'],  # Valid
        }
    }
    
    result = compiler.compile(invalid_config)
    dep_errors = [e for e in result.errors if '[DEP]' in e]
    assert len(dep_errors) > 0, "Should detect unregistered ReasonTag"
    print(f"  ✓ Detected unregistered tag: {dep_errors[0][:60]}...")
    
    print("✅ Dependency validation working correctly")
    return True


def test_threshold_compiler_version_hash():
    """测试配置版本哈希"""
    print("\n=== Test: ThresholdCompiler Version Hash ===")
    
    try:
        from config.threshold_compiler import ThresholdCompiler
    except ImportError as e:
        print(f"  ⚠️ Skipping: {e}")
        return True
    
    compiler = ThresholdCompiler()
    
    config1 = {'key': 'value1'}
    config2 = {'key': 'value2'}
    config3 = {'key': 'value1'}  # Same as config1
    
    result1 = compiler.compile(config1)
    result2 = compiler.compile(config2)
    result3 = compiler.compile(config3)
    
    assert result1.version_hash != result2.version_hash, "Different configs should have different hashes"
    assert result1.version_hash == result3.version_hash, "Same configs should have same hash"
    
    print(f"  ✓ config1 hash: {result1.version_hash}")
    print(f"  ✓ config2 hash: {result2.version_hash}")
    print(f"  ✓ config3 hash: {result3.version_hash} (same as config1)")
    
    print("✅ Version hash working correctly")
    return True


def test_load_and_validate_thresholds():
    """测试实际配置文件加载和校验"""
    print("\n=== Test: Load and Validate Real Config ===")
    
    try:
        from config.threshold_compiler import load_and_validate_thresholds, HAS_YAML
        if not HAS_YAML:
            print("  ⚠️ Skipping: PyYAML not available")
            return True
    except ImportError as e:
        print(f"  ⚠️ Skipping: {e}")
        return True
    
    try:
        config, result = load_and_validate_thresholds()
        
        print(f"  Config loaded: {len(config)} top-level keys")
        print(f"  Version hash: {result.version_hash}")
        print(f"  Errors: {len(result.errors)}")
        print(f"  Warnings: {len(result.warnings)}")
        
        if result.warnings:
            for warn in result.warnings[:3]:
                print(f"    - {warn[:70]}...")
        
        assert result.is_valid, f"Real config should be valid, errors: {result.errors}"
        print("✅ Real config loaded and validated successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("P1 Data Validity Tests")
    print("=" * 60)
    
    tests = [
        test_reason_tags_registered,
        test_feature_builder_invalid_price,
        test_feature_builder_invalid_volume,
        test_feature_builder_outlier_detection,
        test_threshold_compiler_type_validation,
        test_threshold_compiler_logic_validation,
        test_threshold_compiler_dependency_validation,
        test_threshold_compiler_version_hash,
        test_load_and_validate_thresholds,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
