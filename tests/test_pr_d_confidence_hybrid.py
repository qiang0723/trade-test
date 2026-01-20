"""
PR-D测试：Confidence混合模式

测试内容：
1. 基础加分制（保持现有）
2. 硬降级上限（UNCERTAIN≤MEDIUM）
3. 强信号突破（+1档）
4. 不可突破cap限制
"""

import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, Confidence, TradeQuality, MarketRegime
from models.reason_tags import ReasonTag


def test_basic_scoring():
    """测试基础加分制"""
    print("\n=== Test 1: 基础加分制 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 场景1: TREND + GOOD + 强信号 = 30+30+30+10=100 → ULTRA
    c1 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.TREND,
        quality=TradeQuality.GOOD,
        reason_tags=[ReasonTag.STRONG_BUY_PRESSURE]
    )
    print(f"TREND+GOOD+强信号: {c1.value} (期望: ULTRA)")
    assert c1 == Confidence.ULTRA
    
    # 场景2: TREND + GOOD（无强信号） = 30+30+30=90 → ULTRA
    c2 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.TREND,
        quality=TradeQuality.GOOD,
        reason_tags=[]
    )
    print(f"TREND+GOOD: {c2.value} (期望: ULTRA)")
    assert c2 == Confidence.ULTRA
    
    # 场景3: RANGE + GOOD = 30+10+30=70 → HIGH
    c3 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.RANGE,
        quality=TradeQuality.GOOD,
        reason_tags=[]
    )
    print(f"RANGE+GOOD: {c3.value} (期望: HIGH)")
    assert c3 == Confidence.HIGH
    
    print("✅ 基础加分制正常")


def test_uncertain_cap():
    """测试UNCERTAIN质量上限"""
    print("\n=== Test 2: UNCERTAIN质量上限 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # TREND + UNCERTAIN + 强信号 = 30+30+15+10=85
    # 初始档位: HIGH (65-89)
    # 但UNCERTAIN → cap到MEDIUM
    c1 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.TREND,
        quality=TradeQuality.UNCERTAIN,
        reason_tags=[ReasonTag.STRONG_BUY_PRESSURE]
    )
    print(f"TREND+UNCERTAIN+强信号: {c1.value} (期望: ≤MEDIUM)")
    assert c1 in [Confidence.MEDIUM, Confidence.LOW]
    
    # RANGE + UNCERTAIN = 30+10+15=55
    # 初始档位: MEDIUM
    # UNCERTAIN → cap到MEDIUM（不变）
    c2 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.RANGE,
        quality=TradeQuality.UNCERTAIN,
        reason_tags=[]
    )
    print(f"RANGE+UNCERTAIN: {c2.value} (期望: ≤MEDIUM)")
    assert c2 in [Confidence.MEDIUM, Confidence.LOW]
    
    print("✅ UNCERTAIN质量上限生效")


def test_tag_cap():
    """测试降级标签上限"""
    print("\n=== Test 3: 降级标签上限 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # TREND + GOOD + 强信号 + NOISY = 100分
    # 初始: ULTRA
    # NOISY标签 → cap到MEDIUM
    c1 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.TREND,
        quality=TradeQuality.GOOD,
        reason_tags=[
            ReasonTag.STRONG_BUY_PRESSURE,
            ReasonTag.NOISY_MARKET
        ]
    )
    print(f"高分+NOISY标签: {c1.value} (期望: ≤MEDIUM)")
    assert c1 == Confidence.MEDIUM
    
    print("✅ 降级标签上限生效")


def test_strong_signal_boost():
    """测试强信号突破"""
    print("\n=== Test 4: 强信号突破 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 场景1: RANGE + GOOD（无强信号）= 30+10+30=70 → HIGH
    c1 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.RANGE,
        quality=TradeQuality.GOOD,
        reason_tags=[]
    )
    print(f"RANGE+GOOD（无强信号）: {c1.value}")
    assert c1 == Confidence.HIGH
    
    # 场景2: RANGE + GOOD + 强信号 = 30+10+30+10=80 → HIGH
    # 强信号+1档 → ULTRA
    c2 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.RANGE,
        quality=TradeQuality.GOOD,
        reason_tags=[ReasonTag.STRONG_BUY_PRESSURE]
    )
    print(f"RANGE+GOOD+强信号: {c2.value} (期望: ULTRA，因为强信号突破)")
    assert c2 == Confidence.ULTRA
    
    print("✅ 强信号突破功能正常")


def test_boost_cannot_break_cap():
    """测试强信号不可突破cap"""
    print("\n=== Test 5: 强信号不可突破cap ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # TREND + UNCERTAIN + 强信号 = 30+30+15+10=85
    # 初始: HIGH
    # UNCERTAIN cap → MEDIUM
    # 强信号尝试+1档 → HIGH，但被cap限制 → 保持MEDIUM
    c1 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.TREND,
        quality=TradeQuality.UNCERTAIN,
        reason_tags=[ReasonTag.STRONG_BUY_PRESSURE]
    )
    print(f"TREND+UNCERTAIN+强信号: {c1.value} (期望: MEDIUM，强信号无法突破cap)")
    assert c1 == Confidence.MEDIUM
    
    print("✅ 强信号无法突破cap限制")


def test_confidence_level_comparison():
    """测试置信度档位比较"""
    print("\n=== Test 6: 置信度档位比较 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    assert engine._confidence_level(Confidence.LOW) < engine._confidence_level(Confidence.MEDIUM)
    assert engine._confidence_level(Confidence.MEDIUM) < engine._confidence_level(Confidence.HIGH)
    assert engine._confidence_level(Confidence.HIGH) < engine._confidence_level(Confidence.ULTRA)
    print("✅ 档位比较功能正常")


def test_string_to_confidence():
    """测试字符串转换"""
    print("\n=== Test 7: 字符串转置信度 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    assert engine._string_to_confidence("LOW") == Confidence.LOW
    assert engine._string_to_confidence("MEDIUM") == Confidence.MEDIUM
    assert engine._string_to_confidence("HIGH") == Confidence.HIGH
    assert engine._string_to_confidence("ULTRA") == Confidence.ULTRA
    assert engine._string_to_confidence("low") == Confidence.LOW
    print("✅ 字符串转换功能正常")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("PR-D: Confidence混合模式测试")
    print("=" * 60)
    
    try:
        test_basic_scoring()
        test_uncertain_cap()
        test_tag_cap()
        test_strong_signal_boost()
        test_boost_cannot_break_cap()
        test_confidence_level_comparison()
        test_string_to_confidence()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
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
