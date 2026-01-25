"""
P0级单测：DecisionGate频控逻辑测试

测试DecisionGate的频率控制逻辑，确保冷却期和最小间隔正确工作。

测试覆盖：
1. 冷却期（相同方向重复信号被阻断）
2. 最小间隔（两次决策时间过短被阻断）
3. 方向翻转（允许）
4. 首次决策（允许）
5. NO_TRADE不受频控限制
"""

import pytest
from datetime import datetime, timedelta
from l1_engine.decision_gate import DecisionGate
from l1_engine.state_store import InMemoryStateStore, DualTimeframeStateStore
from models.decision_core_dto import TimeframeDecisionDraft, FrequencyControlResult
from models.thresholds import Thresholds, DualDecisionControl
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, ExecutionPermission, Timeframe
from models.reason_tags import ReasonTag


# ============================================
# 测试辅助函数
# ============================================

def create_mock_thresholds() -> Thresholds:
    """创建模拟的阈值配置（包含频控参数）"""
    return Thresholds(
        symbol_universe=None,
        periodic_update=None,
        data_retention=None,
        error_handling=None,
        data_quality=None,
        decision_control=None,
        market_regime=None,
        risk_exposure=None,
        trade_quality=None,
        confidence_scoring=None,
        dual_decision_control=DualDecisionControl(
            short_term_interval_seconds=60,
            short_term_flip_cooldown_seconds=300,
            medium_term_interval_seconds=300,
            medium_term_flip_cooldown_seconds=600
        )
    )


def create_draft(
    decision: Decision = Decision.LONG,
    confidence: Confidence = Confidence.MEDIUM,
    execution_permission: ExecutionPermission = ExecutionPermission.ALLOW
) -> TimeframeDecisionDraft:
    """创建模拟的决策草稿"""
    return TimeframeDecisionDraft(
        decision=decision,
        confidence=confidence,
        market_regime=MarketRegime.TREND,
        trade_quality=TradeQuality.GOOD,
        execution_permission=execution_permission,
        reason_tags=[],
        key_metrics={}
    )


# ============================================
# 测试1：首次决策（总是允许）
# ============================================

def test_first_decision_allowed():
    """测试首次决策总是允许"""
    gate = DecisionGate(InMemoryStateStore())
    draft = create_draft(decision=Decision.LONG)
    now = datetime.now()
    thresholds = create_mock_thresholds()
    
    final = gate.apply(draft, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    
    assert final.executable == True
    assert final.freq_control.is_blocked == False


# ============================================
# 测试2：冷却期检查（相同方向）
# ============================================

def test_cooling_period_blocks_same_direction():
    """测试相同方向在冷却期内被阻断"""
    gate = DecisionGate(InMemoryStateStore())
    draft = create_draft(decision=Decision.LONG)
    thresholds = create_mock_thresholds()
    now = datetime.now()
    
    # 第一次决策
    final1 = gate.apply(draft, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True
    
    # 10秒后，相同方向（LONG）
    now2 = now + timedelta(seconds=10)
    final2 = gate.apply(draft, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    # 应该被冷却期阻断
    assert final2.executable == False
    assert final2.freq_control.is_blocked == True
    assert final2.freq_control.is_cooling == True
    assert ReasonTag.FLIP_COOLDOWN_BLOCK in final2.freq_control.added_tags


def test_cooling_period_expires():
    """测试冷却期过后允许"""
    gate = DecisionGate(InMemoryStateStore())
    draft = create_draft(decision=Decision.LONG)
    thresholds = create_mock_thresholds()
    now = datetime.now()
    
    # 第一次决策
    final1 = gate.apply(draft, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True
    
    # 350秒后（超过冷却期300s），相同方向
    now2 = now + timedelta(seconds=350)
    final2 = gate.apply(draft, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    # 应该允许
    assert final2.executable == True
    assert final2.freq_control.is_blocked == False


# ============================================
# 测试3：最小间隔检查
# ============================================

def test_min_interval_blocks():
    """测试最小间隔被阻断"""
    gate = DecisionGate(InMemoryStateStore())
    thresholds = create_mock_thresholds()
    now = datetime.now()
    
    # 第一次：LONG
    draft1 = create_draft(decision=Decision.LONG)
    final1 = gate.apply(draft1, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True
    
    # 30秒后：SHORT（方向翻转，不受冷却期限制）
    # 但仍然受最小间隔限制（60s）
    draft2 = create_draft(decision=Decision.SHORT)
    now2 = now + timedelta(seconds=30)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    # 应该被最小间隔阻断
    assert final2.executable == False
    assert final2.freq_control.is_blocked == True
    assert final2.freq_control.min_interval_violated == True
    assert ReasonTag.MIN_INTERVAL_BLOCK in final2.freq_control.added_tags


def test_min_interval_expires():
    """测试最小间隔过后允许"""
    gate = DecisionGate(InMemoryStateStore())
    thresholds = create_mock_thresholds()
    now = datetime.now()
    
    # 第一次：LONG
    draft1 = create_draft(decision=Decision.LONG)
    final1 = gate.apply(draft1, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True
    
    # 70秒后：SHORT（超过最小间隔60s）
    draft2 = create_draft(decision=Decision.SHORT)
    now2 = now + timedelta(seconds=70)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    # 应该允许
    assert final2.executable == True
    assert final2.freq_control.is_blocked == False


# ============================================
# 测试4：方向翻转允许
# ============================================

def test_direction_flip_allowed():
    """测试方向翻转允许（不受冷却期限制，但受最小间隔限制）"""
    gate = DecisionGate(InMemoryStateStore())
    thresholds = create_mock_thresholds()
    now = datetime.now()
    
    # 第一次：LONG
    draft1 = create_draft(decision=Decision.LONG)
    final1 = gate.apply(draft1, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True
    
    # 70秒后：SHORT（翻转，超过最小间隔）
    draft2 = create_draft(decision=Decision.SHORT)
    now2 = now + timedelta(seconds=70)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    # 应该允许（翻转不受冷却期限制）
    assert final2.executable == True
    assert final2.freq_control.is_blocked == False


# ============================================
# 测试5：NO_TRADE不受频控限制
# ============================================

def test_no_trade_always_allowed():
    """测试NO_TRADE总是允许（不受频控限制）"""
    gate = DecisionGate(InMemoryStateStore())
    thresholds = create_mock_thresholds()
    now = datetime.now()
    
    # 第一次：LONG
    draft1 = create_draft(decision=Decision.LONG)
    final1 = gate.apply(draft1, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True
    
    # 1秒后：NO_TRADE（应该不受任何频控限制）
    draft2 = create_draft(decision=Decision.NO_TRADE)
    now2 = now + timedelta(seconds=1)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    # 应该允许
    assert final2.executable == True
    assert final2.freq_control.is_blocked == False


# ============================================
# 测试6：双周期独立频控
# ============================================

def test_dual_timeframe_independent_control():
    """测试双周期独立频控"""
    dual_store = DualTimeframeStateStore()
    gate = DecisionGate(dual_store)
    thresholds = create_mock_thresholds()
    now = datetime.now()
    
    # 短期第一次：LONG
    draft1 = create_draft(decision=Decision.LONG)
    final1 = gate.apply(draft1, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True
    
    # 中期第一次：LONG（不受短期影响）
    draft2 = create_draft(decision=Decision.LONG)
    final2 = gate.apply(draft2, "BTC", now, thresholds, Timeframe.MEDIUM_TERM)
    assert final2.executable == True
    
    # 10秒后，短期再次LONG（被冷却期阻断）
    now2 = now + timedelta(seconds=10)
    final3 = gate.apply(draft1, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    assert final3.executable == False
    
    # 但中期再次LONG仍然可以（独立频控）
    final4 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.MEDIUM_TERM)
    assert final4.executable == False  # 也被冷却期阻断（中期自己的冷却期）


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
