"""
PR-M: MetricsNormalizer 元数据格式标注测试

验证方案B（元数据标注）的正确性：
1. percent_point 格式正确转换
2. decimal 格式跳过转换
3. 异常检测适配不同格式
4. 向后兼容（无元数据时默认行为）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics_normalizer import MetricsNormalizer


def test_percent_point_format():
    """测试 percent_point 格式（有元数据标注）"""
    print("=" * 60)
    print("测试1: percent_point 格式（有元数据）")
    print("=" * 60)
    
    data = {
        'price': 50000.0,
        'price_change_1h': 3.0,      # 3% in percent-point
        'price_change_6h': 5.5,      # 5.5% in percent-point
        'oi_change_1h': 10.0,        # 10% in percent-point
        'oi_change_6h': 15.0,        # 15% in percent-point
        'funding_rate': 0.0001,      # 0.01% in decimal (already)
        'buy_sell_imbalance': 0.3,
        '_metadata': {
            'percentage_format': 'percent_point',
            'source': 'test'
        }
    }
    
    normalized, is_valid, error_msg = MetricsNormalizer.normalize(data)
    
    assert is_valid, f"验证失败: {error_msg}"
    assert abs(normalized['price_change_1h'] - 0.03) < 1e-6, \
        f"price_change_1h 转换错误: {normalized['price_change_1h']} (期望 0.03)"
    assert abs(normalized['price_change_6h'] - 0.055) < 1e-6, \
        f"price_change_6h 转换错误: {normalized['price_change_6h']} (期望 0.055)"
    assert abs(normalized['oi_change_1h'] - 0.10) < 1e-6, \
        f"oi_change_1h 转换错误: {normalized['oi_change_1h']} (期望 0.10)"
    assert '_metadata' not in normalized, "元数据应该被移除"
    
    print("✅ percent_point 格式转换正确")
    print(f"   price_change_1h: 3.0% → {normalized['price_change_1h']:.6f}")
    print(f"   price_change_6h: 5.5% → {normalized['price_change_6h']:.6f}")
    print(f"   oi_change_1h: 10.0% → {normalized['oi_change_1h']:.6f}")
    print()


def test_decimal_format():
    """测试 decimal 格式（有元数据标注）"""
    print("=" * 60)
    print("测试2: decimal 格式（有元数据）")
    print("=" * 60)
    
    data = {
        'price': 50000.0,
        'price_change_1h': 0.03,     # 3% in decimal
        'price_change_6h': 0.055,    # 5.5% in decimal
        'oi_change_1h': 0.10,        # 10% in decimal
        'oi_change_6h': 0.15,        # 15% in decimal
        'funding_rate': 0.0001,      # 0.01% in decimal
        'buy_sell_imbalance': 0.3,
        '_metadata': {
            'percentage_format': 'decimal',
            'source': 'test'
        }
    }
    
    normalized, is_valid, error_msg = MetricsNormalizer.normalize(data)
    
    assert is_valid, f"验证失败: {error_msg}"
    assert abs(normalized['price_change_1h'] - 0.03) < 1e-6, \
        f"price_change_1h 不应转换: {normalized['price_change_1h']} (期望 0.03)"
    assert abs(normalized['price_change_6h'] - 0.055) < 1e-6, \
        f"price_change_6h 不应转换: {normalized['price_change_6h']} (期望 0.055)"
    assert abs(normalized['oi_change_1h'] - 0.10) < 1e-6, \
        f"oi_change_1h 不应转换: {normalized['oi_change_1h']} (期望 0.10)"
    assert '_metadata' not in normalized, "元数据应该被移除"
    
    print("✅ decimal 格式无需转换，保持原值")
    print(f"   price_change_1h: {normalized['price_change_1h']:.6f} (未转换)")
    print(f"   price_change_6h: {normalized['price_change_6h']:.6f} (未转换)")
    print(f"   oi_change_1h: {normalized['oi_change_1h']:.6f} (未转换)")
    print()


def test_backward_compatibility():
    """测试向后兼容（无元数据）"""
    print("=" * 60)
    print("测试3: 向后兼容（无元数据，默认 percent_point）")
    print("=" * 60)
    
    # 无 _metadata 字段
    data = {
        'price': 50000.0,
        'price_change_1h': 3.0,      # 3%
        'price_change_6h': 5.5,      # 5.5%
        'oi_change_1h': 10.0,        # 10%
        'oi_change_6h': 15.0,        # 15%
    }
    
    normalized, is_valid, error_msg = MetricsNormalizer.normalize(data)
    
    assert is_valid, f"验证失败: {error_msg}"
    assert abs(normalized['price_change_1h'] - 0.03) < 1e-6, \
        f"默认应按 percent_point 转换: {normalized['price_change_1h']}"
    
    print("✅ 向后兼容：无元数据时默认按 percent_point 处理")
    print(f"   price_change_1h: 3.0% → {normalized['price_change_1h']:.6f}")
    print()


def test_anomaly_detection_percent_point():
    """测试异常检测（percent_point 格式）"""
    print("=" * 60)
    print("测试4: 异常检测（percent_point 格式）")
    print("=" * 60)
    
    # 异常大的值（1500% 在 percent_point 格式下）
    data = {
        'price': 50000.0,
        'price_change_1h': 1500.0,   # 1500% - 异常！
        '_metadata': {
            'percentage_format': 'percent_point'
        }
    }
    
    normalized, is_valid, error_msg = MetricsNormalizer.normalize(data)
    
    assert not is_valid, "应该检测到异常值"
    assert "1500.00%" in error_msg, f"错误信息应包含百分比值: {error_msg}"
    print(f"✅ 正确检测异常值（percent_point）: {error_msg}")
    print()


def test_anomaly_detection_decimal():
    """测试异常检测（decimal 格式）"""
    print("=" * 60)
    print("测试5: 异常检测（decimal 格式）")
    print("=" * 60)
    
    # 异常大的值（15.0 在 decimal 格式下表示 1500%）
    data = {
        'price': 50000.0,
        'price_change_1h': 15.0,     # 1500% in decimal - 异常！
        '_metadata': {
            'percentage_format': 'decimal'
        }
    }
    
    normalized, is_valid, error_msg = MetricsNormalizer.normalize(data)
    
    assert not is_valid, "应该检测到异常值"
    assert "1500.00%" in error_msg, f"错误信息应包含百分比值: {error_msg}"
    print(f"✅ 正确检测异常值（decimal）: {error_msg}")
    print()


def test_invalid_format():
    """测试无效的格式声明"""
    print("=" * 60)
    print("测试6: 无效格式声明")
    print("=" * 60)
    
    data = {
        'price': 50000.0,
        'price_change_1h': 3.0,
        '_metadata': {
            'percentage_format': 'invalid_format'  # 无效！
        }
    }
    
    normalized, is_valid, error_msg = MetricsNormalizer.normalize(data)
    
    assert not is_valid, "应该拒绝无效格式"
    assert "invalid_format" in error_msg.lower(), f"错误信息应指出无效格式: {error_msg}"
    print(f"✅ 正确拒绝无效格式: {error_msg}")
    print()


def test_validate_ranges():
    """测试范围验证（与格式无关）"""
    print("=" * 60)
    print("测试7: 范围验证（格式无关）")
    print("=" * 60)
    
    # percent_point 格式，转换后超出合理范围
    data_pp = {
        'price': 50000.0,
        'price_change_1h': 25.0,  # 25% in percent_point → 0.25 (decimal) - 超出20%限制
        '_metadata': {'percentage_format': 'percent_point'}
    }
    
    normalized_pp, _, _ = MetricsNormalizer.normalize(data_pp)
    is_valid_pp, error_pp = MetricsNormalizer.validate_ranges(normalized_pp)
    
    assert not is_valid_pp, f"应该检测到超出合理范围，但通过了: {normalized_pp['price_change_1h']}"
    print(f"✅ percent_point 格式范围验证: {error_pp}")
    
    # decimal 格式，直接超出合理范围
    data_dec = {
        'price': 50000.0,
        'price_change_1h': 0.25,  # 0.25 (decimal) = 25% - 超出20%限制
        '_metadata': {'percentage_format': 'decimal'}
    }
    
    normalized_dec, _, _ = MetricsNormalizer.normalize(data_dec)
    is_valid_dec, error_dec = MetricsNormalizer.validate_ranges(normalized_dec)
    
    assert not is_valid_dec, f"应该检测到超出合理范围，但通过了: {normalized_dec['price_change_1h']}"
    print(f"✅ decimal 格式范围验证: {error_dec}")
    print()


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("PR-M: 元数据格式标注测试套件")
    print("=" * 60)
    print()
    
    try:
        test_percent_point_format()
        test_decimal_format()
        test_backward_compatibility()
        test_anomaly_detection_percent_point()
        test_anomaly_detection_decimal()
        test_invalid_format()
        test_validate_ranges()
        
        print("=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        print()
        print("方案B（元数据标注）验证成功：")
        print("  ✅ percent_point 格式正确转换")
        print("  ✅ decimal 格式跳过转换")
        print("  ✅ 异常检测适配不同格式")
        print("  ✅ 向后兼容（无元数据时默认行为）")
        print("  ✅ 范围验证正常工作")
        print()
        return True
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print("❌ 测试失败")
        print("=" * 60)
        print(f"错误: {e}")
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
