"""
PR-B测试：TradeQuality语义钉死

测试内容：
1. POOR质量硬短路为NO_TRADE
2. UNCERTAIN质量降级但允许继续
3. 降级标签限制置信度上限
4. executable综合判定（has_blocking_tags）
"""

import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, Confidence, TradeQuality, MarketRegime
from models.reason_tags import (
    ReasonTag, ExecutabilityLevel, REASON_TAG_EXECUTABILITY,
    has_blocking_tags, has_degrading_tags
)
from models.advisory_result import AdvisoryResult


def test_executability_level_mapping():
    """测试ReasonTag的executability映射"""
    print("\n=== Test 1: ExecutabilityLevel映射 ===")
    
    # BLOCK级别
    assert REASON_TAG_EXECUTABILITY[ReasonTag.ABSORPTION_RISK] == ExecutabilityLevel.BLOCK
    assert REASON_TAG_EXECUTABILITY[ReasonTag.LIQUIDATION_PHASE] == ExecutabilityLevel.BLOCK
    assert REASON_TAG_EXECUTABILITY[ReasonTag.DATA_STALE] == ExecutabilityLevel.BLOCK
    print("✅ BLOCK级别标签正确")
    
    # DEGRADE级别
    assert REASON_TAG_EXECUTABILITY[ReasonTag.NOISY_MARKET] == ExecutabilityLevel.DEGRADE
    assert REASON_TAG_EXECUTABILITY[ReasonTag.WEAK_SIGNAL_IN_RANGE] == ExecutabilityLevel.DEGRADE
    print("✅ DEGRADE级别标签正确")
    
    # ALLOW级别
    assert REASON_TAG_EXECUTABILITY[ReasonTag.STRONG_BUY_PRESSURE] == ExecutabilityLevel.ALLOW
    assert REASON_TAG_EXECUTABILITY[ReasonTag.OI_GROWING] == ExecutabilityLevel.ALLOW
    print("✅ ALLOW级别标签正确")


def test_has_blocking_tags():
    """测试has_blocking_tags函数"""
    print("\n=== Test 2: has_blocking_tags函数 ===")
    
    # 无阻断标签
    tags1 = [ReasonTag.OI_GROWING, ReasonTag.STRONG_BUY_PRESSURE]
    assert has_blocking_tags(tags1) == False
    print("✅ 无阻断标签: False")
    
    # 有阻断标签
    tags2 = [ReasonTag.ABSORPTION_RISK, ReasonTag.OI_GROWING]
    assert has_blocking_tags(tags2) == True
    print("✅ 有阻断标签: True")
    
    # 有降级标签（不是阻断）
    tags3 = [ReasonTag.NOISY_MARKET, ReasonTag.OI_GROWING]
    assert has_blocking_tags(tags3) == False
    print("✅ 有降级标签但无阻断: False")


def test_has_degrading_tags():
    """测试has_degrading_tags函数"""
    print("\n=== Test 3: has_degrading_tags函数 ===")
    
    # 无降级标签
    tags1 = [ReasonTag.OI_GROWING, ReasonTag.STRONG_BUY_PRESSURE]
    assert has_degrading_tags(tags1) == False
    print("✅ 无降级标签: False")
    
    # 有降级标签
    tags2 = [ReasonTag.NOISY_MARKET, ReasonTag.OI_GROWING]
    assert has_degrading_tags(tags2) == True
    print("✅ 有降级标签: True")
    
    # 有阻断标签（不是降级）
    tags3 = [ReasonTag.ABSORPTION_RISK, ReasonTag.OI_GROWING]
    assert has_degrading_tags(tags3) == False
    print("✅ 有阻断标签但无降级: False")


def test_poor_quality_short_circuit():
    """测试POOR质量硬短路"""
    print("\n=== Test 4: POOR质量硬短路 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 构造ABSORPTION_RISK的数据（高失衡+低成交量）
    poor_data = {
        'symbol': 'BTC',
        'price': 50000,
        'price_change_1h': 0.01,
        'price_change_6h': 0.02,
        'volume_1h': 10000,      # 极低成交量
        'volume_24h': 20000000,   # 24h成交量很高
        'buy_sell_imbalance': 0.9,  # 极高失衡
        'funding_rate': 0.0001,
        'oi_change_1h': 0.05,
        'oi_change_6h': 0.08,
        'timestamp': datetime.now().isoformat()
    }
    
    result = engine.on_new_tick('BTC', poor_data)
    print(f"决策: {result.decision.value}, 质量: {result.trade_quality.value}")
    
    assert result.decision == Decision.NO_TRADE
    assert result.trade_quality == TradeQuality.POOR
    assert ReasonTag.ABSORPTION_RISK in result.reason_tags
    assert result.executable == False
    print("✅ POOR质量硬短路为NO_TRADE")


def test_uncertain_quality_downgrade():
    """测试UNCERTAIN质量降级"""
    print("\n=== Test 5: UNCERTAIN质量降级 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 先构造一个决策，然后手动设置UNCERTAIN+降级标签
    # 注意：实际测试中，NOISY_MARKET标签应该通过数据触发
    # 这里我们通过检查confidence计算逻辑
    
    # 测试confidence计算：UNCERTAIN应该只得1分
    confidence = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.TREND,  # 3分
        quality=TradeQuality.UNCERTAIN,  # 1分（而非GOOD的2分）
        reason_tags=[]
    )
    
    # TREND(3) + UNCERTAIN(1) = 4分 → MEDIUM
    assert confidence in [Confidence.MEDIUM, Confidence.LOW]
    print(f"✅ UNCERTAIN质量降级: TREND+UNCERTAIN={confidence.value}")


def test_degrading_tags_cap():
    """测试降级标签限制置信度上限"""
    print("\n=== Test 6: 降级标签限制置信度上限 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 测试1：无降级标签，高分→HIGH或ULTRA
    confidence1 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.TREND,  # 3分
        quality=TradeQuality.GOOD,   # 2分
        reason_tags=[ReasonTag.STRONG_BUY_PRESSURE]  # 2分
    )
    print(f"无降级标签: {confidence1.value}")
    assert confidence1 in [Confidence.HIGH, Confidence.ULTRA]
    
    # 测试2：有降级标签，最高MEDIUM
    confidence2 = engine._compute_confidence(
        decision=Decision.LONG,
        regime=MarketRegime.TREND,  # 3分
        quality=TradeQuality.GOOD,   # 2分
        reason_tags=[
            ReasonTag.STRONG_BUY_PRESSURE,  # 2分
            ReasonTag.NOISY_MARKET  # 降级标签
        ]
    )
    print(f"有降级标签: {confidence2.value}")
    assert confidence2 == Confidence.MEDIUM  # 被cap到MEDIUM
    print("✅ 降级标签成功限制置信度上限")


def test_executable_comprehensive():
    """测试executable综合判定"""
    print("\n=== Test 7: executable综合判定 ===")
    
    # 测试1：所有条件满足 → executable=True
    result1 = AdvisoryResult(
        decision=Decision.LONG,
        confidence=Confidence.HIGH,
        market_regime=MarketRegime.TREND,
        system_state='wait',
        risk_exposure_allowed=True,
        trade_quality=TradeQuality.GOOD,
        reason_tags=[ReasonTag.STRONG_BUY_PRESSURE],
        timestamp=datetime.now()
    )
    assert result1.compute_executable() == True
    print("✅ 所有条件满足: executable=True")
    
    # 测试2：有阻断标签 → executable=False
    result2 = AdvisoryResult(
        decision=Decision.LONG,
        confidence=Confidence.HIGH,
        market_regime=MarketRegime.TREND,
        system_state='wait',
        risk_exposure_allowed=True,
        trade_quality=TradeQuality.GOOD,
        reason_tags=[ReasonTag.ABSORPTION_RISK],  # 阻断标签
        timestamp=datetime.now()
    )
    assert result2.compute_executable() == False
    print("✅ 有阻断标签: executable=False")
    
    # 测试3：有降级标签但置信度HIGH → executable=True
    result3 = AdvisoryResult(
        decision=Decision.LONG,
        confidence=Confidence.HIGH,
        market_regime=MarketRegime.RANGE,
        system_state='wait',
        risk_exposure_allowed=True,
        trade_quality=TradeQuality.UNCERTAIN,
        reason_tags=[ReasonTag.NOISY_MARKET],  # 降级标签（不阻断）
        timestamp=datetime.now()
    )
    # 注意：虽然有NOISY_MARKET，但confidence=HIGH且无阻断标签
    assert result3.compute_executable() == True
    print("✅ 降级标签+HIGH置信度: executable=True")
    
    # 测试4：置信度MEDIUM → executable=False
    result4 = AdvisoryResult(
        decision=Decision.LONG,
        confidence=Confidence.MEDIUM,
        market_regime=MarketRegime.RANGE,
        system_state='wait',
        risk_exposure_allowed=True,
        trade_quality=TradeQuality.GOOD,
        reason_tags=[],
        timestamp=datetime.now()
    )
    assert result4.compute_executable() == False
    print("✅ 置信度MEDIUM: executable=False")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("PR-B: TradeQuality语义钉死测试")
    print("=" * 60)
    
    try:
        test_executability_level_mapping()
        test_has_blocking_tags()
        test_has_degrading_tags()
        test_poor_quality_short_circuit()
        test_uncertain_quality_downgrade()
        test_degrading_tags_cap()
        test_executable_comprehensive()
        
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
