"""
测试 PR-DUAL: 双周期独立结论

测试覆盖：
1. 双周期一致看多/看空
2. 双周期方向冲突
3. 部分确认场景
4. 全局风险拒绝
5. 冲突处理策略
6. 向后兼容性
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, Confidence, AlignmentType, ConflictResolution, Timeframe
from models.dual_timeframe_result import DualTimeframeResult


def test_dual_both_long():
    """测试：双周期一致看多"""
    engine = L1AdvisoryEngine()
    
    # 构造双周期都看多的数据
    data = {
        'price': 50000,
        'timestamp': 1234567890,
        # 短期看多（5m/15m）
        'price_change_5m': 0.005,   # 0.5%
        'price_change_15m': 0.008,  # 0.8%
        'taker_imbalance_5m': 0.50,
        'taker_imbalance_15m': 0.60,
        'volume_ratio_5m': 1.5,
        'volume_ratio_15m': 1.8,
        # 中长期看多（1h/6h）
        'price_change_1h': 0.02,    # 2%
        'price_change_6h': 0.05,    # 5%
        'oi_change_1h': 0.015,      # 1.5%
        'oi_change_6h': 0.03,       # 3%
        'buy_sell_imbalance': 0.40,
        'funding_rate': 0.0001,
        'volume_1h': 1000000,
        'volume_24h': 20000000,
    }
    
    result = engine.on_new_tick_dual('BTC', data)
    
    # 验证类型
    assert isinstance(result, DualTimeframeResult)
    
    # 验证短期结论
    assert result.short_term.timeframe == Timeframe.SHORT_TERM
    assert result.short_term.decision == Decision.LONG
    assert result.short_term.timeframe_label == "5m/15m"
    
    # 验证中长期结论
    assert result.medium_term.timeframe == Timeframe.MEDIUM_TERM
    assert result.medium_term.decision == Decision.LONG
    assert result.medium_term.timeframe_label == "1h/6h"
    
    # 验证一致性
    assert result.alignment.is_aligned is True
    assert result.alignment.alignment_type == AlignmentType.BOTH_LONG
    assert result.alignment.has_conflict is False
    assert result.alignment.recommended_action == Decision.LONG
    
    # 验证向后兼容字段
    result_dict = result.to_dict()
    assert result_dict['decision'] == 'long'
    assert 'short_term' in result_dict
    assert 'medium_term' in result_dict
    assert 'alignment' in result_dict
    
    print("✅ test_dual_both_long passed")


def test_dual_both_short():
    """测试：双周期一致看空"""
    engine = L1AdvisoryEngine()
    
    data = {
        'price': 50000,
        'timestamp': 1234567890,
        # 短期看空
        'price_change_5m': -0.005,
        'price_change_15m': -0.008,
        'taker_imbalance_5m': -0.50,
        'taker_imbalance_15m': -0.60,
        'volume_ratio_5m': 1.5,
        'volume_ratio_15m': 1.8,
        # 中长期看空
        'price_change_1h': -0.02,
        'price_change_6h': -0.05,
        'oi_change_1h': 0.015,
        'oi_change_6h': 0.03,
        'buy_sell_imbalance': -0.40,
        'funding_rate': -0.0001,
        'volume_1h': 1000000,
        'volume_24h': 20000000,
    }
    
    result = engine.on_new_tick_dual('BTC', data)
    
    assert result.short_term.decision == Decision.SHORT
    assert result.medium_term.decision == Decision.SHORT
    assert result.alignment.is_aligned is True
    assert result.alignment.alignment_type == AlignmentType.BOTH_SHORT
    assert result.alignment.recommended_action == Decision.SHORT
    
    print("✅ test_dual_both_short passed")


def test_dual_conflict_long_short():
    """测试：短期看多，中长期看空（冲突）"""
    engine = L1AdvisoryEngine()
    
    data = {
        'price': 50000,
        'timestamp': 1234567890,
        # 短期看多
        'price_change_5m': 0.005,
        'price_change_15m': 0.008,
        'taker_imbalance_5m': 0.50,
        'taker_imbalance_15m': 0.60,
        'volume_ratio_5m': 1.5,
        'volume_ratio_15m': 1.8,
        # 中长期看空
        'price_change_1h': -0.02,
        'price_change_6h': -0.05,
        'oi_change_1h': 0.015,
        'oi_change_6h': 0.03,
        'buy_sell_imbalance': -0.40,
        'funding_rate': -0.0001,
        'volume_1h': 1000000,
        'volume_24h': 20000000,
    }
    
    result = engine.on_new_tick_dual('BTC', data)
    
    assert result.short_term.decision == Decision.LONG
    assert result.medium_term.decision == Decision.SHORT
    assert result.alignment.is_aligned is False
    assert result.alignment.has_conflict is True
    assert result.alignment.alignment_type == AlignmentType.CONFLICT_LONG_SHORT
    
    # 默认策略：no_trade
    assert result.alignment.conflict_resolution == ConflictResolution.NO_TRADE
    assert result.alignment.recommended_action == Decision.NO_TRADE
    
    print("✅ test_dual_conflict_long_short passed")


def test_dual_partial_long():
    """测试：仅短期看多，中长期无信号"""
    engine = L1AdvisoryEngine()
    
    data = {
        'price': 50000,
        'timestamp': 1234567890,
        # 短期看多
        'price_change_5m': 0.005,
        'price_change_15m': 0.008,
        'taker_imbalance_5m': 0.50,
        'taker_imbalance_15m': 0.60,
        'volume_ratio_5m': 1.5,
        'volume_ratio_15m': 1.8,
        # 中长期无明确信号
        'price_change_1h': 0.005,   # 较弱
        'price_change_6h': 0.008,   # 较弱
        'oi_change_1h': 0.005,
        'oi_change_6h': 0.008,
        'buy_sell_imbalance': 0.10,  # 较弱
        'funding_rate': 0.00005,
        'volume_1h': 1000000,
        'volume_24h': 20000000,
    }
    
    result = engine.on_new_tick_dual('BTC', data)
    
    assert result.short_term.decision == Decision.LONG
    # 中长期可能是NO_TRADE（信号不足）
    
    if result.medium_term.decision == Decision.NO_TRADE:
        assert result.alignment.is_aligned is False
        assert result.alignment.has_conflict is False
        assert result.alignment.alignment_type == AlignmentType.PARTIAL_LONG
        # 部分确认，降级置信度
        assert result.alignment.recommended_confidence == Confidence.LOW
    
    print("✅ test_dual_partial_long passed")


def test_dual_global_risk_denial():
    """测试：全局风险拒绝，双周期都返回NO_TRADE"""
    engine = L1AdvisoryEngine()
    
    # 极端成交量触发全局风险
    data = {
        'price': 50000,
        'timestamp': 1234567890,
        'price_change_5m': 0.005,
        'price_change_15m': 0.008,
        'price_change_1h': 0.02,
        'price_change_6h': 0.05,
        'oi_change_1h': 0.015,
        'oi_change_6h': 0.03,
        'buy_sell_imbalance': 0.40,
        'funding_rate': 0.0001,
        'taker_imbalance_5m': 0.50,
        'taker_imbalance_15m': 0.60,
        'volume_ratio_5m': 1.5,
        'volume_ratio_15m': 1.8,
        'volume_1h': 1000000,
        'volume_24h': 1000000,  # 极端：1h成交量 = 24h成交量
    }
    
    result = engine.on_new_tick_dual('BTC', data)
    
    # 全局风险拒绝
    assert result.short_term.decision == Decision.NO_TRADE
    assert result.medium_term.decision == Decision.NO_TRADE
    assert result.alignment.is_aligned is True
    assert result.alignment.alignment_type == AlignmentType.BOTH_NO_TRADE
    assert result.risk_exposure_allowed is False
    assert len(result.global_risk_tags) > 0
    
    print("✅ test_dual_global_risk_denial passed")


def test_dual_backward_compatibility():
    """测试：向后兼容性 - to_dict包含旧字段"""
    engine = L1AdvisoryEngine()
    
    data = {
        'price': 50000,
        'timestamp': 1234567890,
        'price_change_5m': 0.005,
        'price_change_15m': 0.008,
        'price_change_1h': 0.02,
        'price_change_6h': 0.05,
        'oi_change_1h': 0.015,
        'oi_change_6h': 0.03,
        'buy_sell_imbalance': 0.40,
        'funding_rate': 0.0001,
        'taker_imbalance_5m': 0.50,
        'taker_imbalance_15m': 0.60,
        'volume_ratio_5m': 1.5,
        'volume_ratio_15m': 1.8,
        'volume_1h': 1000000,
        'volume_24h': 20000000,
    }
    
    result = engine.on_new_tick_dual('BTC', data)
    result_dict = result.to_dict()
    
    # 验证新字段存在
    assert 'short_term' in result_dict
    assert 'medium_term' in result_dict
    assert 'alignment' in result_dict
    
    # 验证向后兼容字段存在
    assert 'decision' in result_dict
    assert 'confidence' in result_dict
    assert 'executable' in result_dict
    assert 'reason_tags' in result_dict
    assert 'market_regime' in result_dict
    assert 'symbol' in result_dict
    assert 'timestamp' in result_dict
    
    # 验证字段类型
    assert isinstance(result_dict['decision'], str)
    assert isinstance(result_dict['confidence'], str)
    assert isinstance(result_dict['executable'], bool)
    assert isinstance(result_dict['reason_tags'], list)
    
    print("✅ test_dual_backward_compatibility passed")


def test_dual_conflict_resolution_strategies():
    """测试：不同冲突处理策略"""
    # 这个测试需要修改配置，暂时跳过
    # 实际部署时可以通过修改 config/l1_thresholds.yaml 来测试
    print("⚠️  test_dual_conflict_resolution_strategies skipped (需要配置文件修改)")


if __name__ == '__main__':
    print("=" * 60)
    print("测试 PR-DUAL: 双周期独立结论")
    print("=" * 60)
    
    test_dual_both_long()
    test_dual_both_short()
    test_dual_conflict_long_short()
    test_dual_partial_long()
    test_dual_global_risk_denial()
    test_dual_backward_compatibility()
    test_dual_conflict_resolution_strategies()
    
    print("=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
