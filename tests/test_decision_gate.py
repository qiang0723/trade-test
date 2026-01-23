"""
PR-ARCH-02 M6: DecisionGate频控单测

测试DecisionGate的频率控制逻辑和独立性。

测试覆盖：
1. 首次决策总是允许
2. 冷却期阻断测试
3. 最小间隔测试
4. 方向翻转允许测试
5. NO_TRADE总是允许
6. 双周期独立频控测试
"""

from datetime import datetime, timedelta

# 导入被测试的模块
from l1_engine.decision_gate import DecisionGate
from l1_engine.state_store import InMemoryStateStore, DualTimeframeStateStore
from l1_engine.threshold_compiler import ThresholdCompiler
from models.decision_core_dto import (
    TimeframeDecisionDraft, DualTimeframeDecisionDraft,
    FrequencyControlResult
)
from models.enums import (
    Decision, Confidence, MarketRegime, TradeQuality,
    ExecutionPermission, Timeframe
)
from models.reason_tags import ReasonTag
from models.thresholds import Thresholds


# ============================================
# Helper函数
# ============================================

def create_test_draft(decision=Decision.NO_TRADE, **kwargs) -> TimeframeDecisionDraft:
    """
    创建测试用的DecisionDraft
    
    Args:
        decision: 决策类型
        **kwargs: 覆盖默认值的字段
    
    Returns:
        TimeframeDecisionDraft
    """
    defaults = {
        'decision': decision,
        'confidence': Confidence.LOW,
        'market_regime': MarketRegime.RANGE,
        'trade_quality': TradeQuality.GOOD,
        'execution_permission': ExecutionPermission.ALLOW,
        'reason_tags': [],
        'key_metrics': {}
    }
    
    defaults.update(kwargs)
    
    return TimeframeDecisionDraft(**defaults)


def load_test_thresholds() -> Thresholds:
    """
    加载测试用的Thresholds配置
    
    Returns:
        Thresholds
    """
    compiler = ThresholdCompiler()
    config_path = 'config/l1_thresholds.yaml'
    return compiler.compile(config_path)


# ============================================
# Test 1: 首次决策总是允许
# ============================================

def test_first_decision_allowed():
    """测试第一次决策总是允许"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    draft = create_test_draft(decision=Decision.LONG)
    now = datetime.now()
    
    final = gate.apply(draft, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    
    assert final.executable == True, "首次决策应该允许"
    assert final.frequency_control.is_blocked == False
    assert final.frequency_control.is_cooling == False
    
    print("✅ 首次决策允许测试通过")


# ============================================
# Test 2: 冷却期阻断测试
# ============================================

def test_cooling_period_blocking():
    """测试冷却期阻断"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 第一次决策：LONG
    draft1 = create_test_draft(decision=Decision.LONG)
    now1 = datetime.now()
    final1 = gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True, "首次LONG应该允许"
    
    # 第二次决策：LONG（冷却期内，60秒 < 1800秒）
    draft2 = create_test_draft(decision=Decision.LONG)
    now2 = now1 + timedelta(seconds=60)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == False, "冷却期内重复决策应该阻断"
    assert final2.frequency_control.is_cooling == True
    assert ReasonTag.FLIP_COOLDOWN_BLOCK in final2.reason_tags
    
    print("✅ 冷却期阻断测试通过")


# ============================================
# Test 3: 最小间隔测试
# ============================================

def test_min_interval_violation():
    """测试最小间隔"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 第一次决策：LONG
    draft1 = create_test_draft(decision=Decision.LONG)
    now1 = datetime.now()
    gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    
    # 第二次决策：SHORT（方向翻转，但时间过短，60秒 < 600秒）
    draft2 = create_test_draft(decision=Decision.SHORT)
    now2 = now1 + timedelta(seconds=60)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == False, "最小间隔内决策应该阻断"
    assert final2.frequency_control.min_interval_violated == True
    assert ReasonTag.MIN_INTERVAL_BLOCK in final2.reason_tags
    
    print("✅ 最小间隔测试通过")


# ============================================
# Test 4: 方向翻转允许测试
# ============================================

def test_direction_flip_allowed():
    """测试方向翻转允许（超过最小间隔）"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 第一次决策：LONG
    draft1 = create_test_draft(decision=Decision.LONG)
    now1 = datetime.now()
    gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    
    # 第二次决策：SHORT（方向翻转，时间足够，700秒 > 600秒）
    draft2 = create_test_draft(decision=Decision.SHORT)
    now2 = now1 + timedelta(seconds=700)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == True, "超过最小间隔的方向翻转应该允许"
    # 方向翻转允许，无专用标签（只有日志记录）
    
    print("✅ 方向翻转允许测试通过")


# ============================================
# Test 5: NO_TRADE总是允许
# ============================================

def test_no_trade_always_executable():
    """测试NO_TRADE总是可执行"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 第一次决策：LONG
    draft1 = create_test_draft(decision=Decision.LONG)
    now1 = datetime.now()
    gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    
    # 第二次决策：NO_TRADE（冷却期内，但NO_TRADE总是允许）
    draft2 = create_test_draft(decision=Decision.NO_TRADE)
    now2 = now1 + timedelta(seconds=60)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == True, "NO_TRADE总是允许"
    assert final2.frequency_control.is_blocked == False
    
    print("✅ NO_TRADE总是允许测试通过")


# ============================================
# Test 6: 双周期独立频控测试
# ============================================

def test_dual_timeframe_independent_control():
    """测试双周期独立频控"""
    state_store = DualTimeframeStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 构建双周期draft
    draft = DualTimeframeDecisionDraft(
        short_term=create_test_draft(decision=Decision.LONG),
        medium_term=create_test_draft(decision=Decision.SHORT),
        global_risk_tags=[]
    )
    
    now = datetime.now()
    final = gate.apply_dual(draft, "BTC", now, thresholds)
    
    # 短期和中期都应该可执行（首次决策）
    assert final.short_term.executable == True, "首次短期决策应该允许"
    assert final.medium_term.executable == True, "首次中期决策应该允许"
    
    print("✅ 首次双周期决策允许")
    
    # 第二次：短期LONG（冷却期内），中期NO_TRADE（NO_TRADE总是允许）
    draft2 = DualTimeframeDecisionDraft(
        short_term=create_test_draft(decision=Decision.LONG),      # 冷却期内阻断
        medium_term=create_test_draft(decision=Decision.NO_TRADE), # NO_TRADE总是允许
        global_risk_tags=[]
    )
    
    now2 = now + timedelta(seconds=700)  # 700秒 < 短期冷却期(1800s)
    final2 = gate.apply_dual(draft2, "BTC", now2, thresholds)
    
    # 短期被冷却期阻断，中期允许（NO_TRADE + 独立频控）
    assert final2.short_term.executable == False, "短期冷却期内应该阻断"
    assert final2.medium_term.executable == True, "中期NO_TRADE应该允许（独立频控）"
    
    print("✅ 双周期独立频控测试通过")


# ============================================
# 运行所有测试
# ============================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("PR-ARCH-02 M6: DecisionGate频控单测")
    print("="*80 + "\n")
    
    try:
        print("Test 1: 首次决策总是允许")
        print("-" * 80)
        test_first_decision_allowed()
        print()
        
        print("Test 2: 冷却期阻断测试")
        print("-" * 80)
        test_cooling_period_blocking()
        print()
        
        print("Test 3: 最小间隔测试")
        print("-" * 80)
        test_min_interval_violation()
        print()
        
        print("Test 4: 方向翻转允许测试")
        print("-" * 80)
        test_direction_flip_allowed()
        print()
        
        print("Test 5: NO_TRADE总是允许")
        print("-" * 80)
        test_no_trade_always_executable()
        print()
        
        print("Test 6: 双周期独立频控测试")
        print("-" * 80)
        test_dual_timeframe_independent_control()
        print()
        
        print("="*80)
        print("✅ 所有测试通过！")
        print("="*80)
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        raise
    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        raise
