"""
P0 CodeFix 验收测试

测试内容：
- P0-CodeFix-1: short gap不吞medium
- P0-CodeFix-2: 6h缺口降级为1h-only

创建时间: 2026-01-23
验收标准: 所有8个测试用例必须通过
"""

import pytest
import sys
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, Confidence, ExecutionPermission
from models.reason_tags import ReasonTag


class TestP0CodeFix1ShortGapNoSwallowMedium:
    """P0-CodeFix-1: 短期gap不吞中线"""
    
    @pytest.fixture
    def engine(self):
        """创建L1引擎实例"""
        config_path = project_root / 'config' / 'l1_thresholds.yaml'
        return L1AdvisoryEngine(config_path=str(config_path))
    
    def test_5m_gap_medium_still_evaluates(self, engine):
        """
        验收Case A1: 5m gap但medium数据完整
        
        预期：
        - short_term: NO_TRADE (DATA_GAP_5M或DATA_INCOMPLETE_LTF)
        - medium_term: 正常输出（不是None，不被吞）
        """
        # Given: 5m缺失，但1h/6h完整且强势
        data = {
            'price': 50000,
            'volume_24h': 1000000,
            # 短期字段缺失（模拟5m gap）
            # 'price_change_5m': None,  # 缺失
            'price_change_15m': 0.008,  # 存在但不影响5m gap
            'taker_imbalance_15m': 0.55,
            'volume_ratio_15m': 1.8,
            'oi_change_15m': 0.03,
            # 中期字段完整且强势
            'price_change_1h': 0.03,  # 3%上涨
            'price_change_6h': 0.05,  # 5%上涨
            'oi_change_1h': 0.06,  # 6%增长
            'oi_change_6h': 0.10,  # 10%增长
            'taker_imbalance_1h': 0.75,  # 75%买压
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        # When
        result = engine.on_new_tick_dual('BTC', data)
        
        # Then: short_term被阻断
        assert result.short_term.decision == Decision.NO_TRADE, \
            "5m gap应该阻断short_term"
        assert (ReasonTag.DATA_GAP_5M in result.short_term.reason_tags or
                ReasonTag.DATA_INCOMPLETE_LTF in result.short_term.reason_tags), \
            f"short_term应该有DATA_GAP_5M或DATA_INCOMPLETE_LTF标签，实际标签: {result.short_term.reason_tags}"
        assert result.short_term.executable is False, \
            "short_term不可执行"
        
        # Then: medium_term仍正常输出（不被吞）
        assert result.medium_term is not None, \
            "medium_term不应该是None"
        assert result.medium_term.decision is not None, \
            "medium_term应该有决策输出"
        # 由于medium数据强势，可能输出LONG或其他决策
        assert result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE], \
            "medium_term应该有明确的决策（不被short gap影响）"
        
        print(f"✅ Test A1 passed: short_term={result.short_term.decision.value}, "
              f"medium_term={result.medium_term.decision.value}")
    
    def test_15m_gap_medium_still_evaluates(self, engine):
        """
        验收Case A2: 15m gap但medium数据完整
        
        预期：
        - short_term: NO_TRADE (DATA_GAP_15M或DATA_INCOMPLETE_LTF)
        - medium_term: 正常输出
        """
        data = {
            'price': 50000,
            'volume_24h': 1000000,
            # 短期字段部分缺失（15m gap）
            'price_change_5m': 0.003,
            # 'price_change_15m': None,  # 缺失
            'taker_imbalance_5m': 0.65,
            'volume_ratio_5m': 2.0,
            'oi_change_5m': 0.02,
            # 中期字段完整
            'price_change_1h': 0.025,
            'price_change_6h': 0.04,
            'oi_change_1h': 0.05,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.70,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # short_term被阻断
        assert result.short_term.decision == Decision.NO_TRADE, \
            "15m gap应该阻断short_term"
        assert (ReasonTag.DATA_GAP_15M in result.short_term.reason_tags or
                ReasonTag.DATA_INCOMPLETE_LTF in result.short_term.reason_tags), \
            f"short_term应该有DATA_GAP_15M或DATA_INCOMPLETE_LTF标签，实际: {result.short_term.reason_tags}"
        
        # medium_term仍输出
        assert result.medium_term is not None, \
            "medium_term不应该是None"
        assert result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE], \
            "medium_term应该有明确决策"
        
        print(f"✅ Test A2 passed: short_term={result.short_term.decision.value}, "
              f"medium_term={result.medium_term.decision.value}")
    
    def test_both_short_and_medium_can_coexist(self, engine):
        """
        验收Case A3: short和medium同时有数据，都正常输出
        
        确保独立评估机制生效
        """
        data = {
            'price': 50000,
            'volume_24h': 1000000,
            # 短期字段完整
            'price_change_5m': 0.003,
            'price_change_15m': 0.008,
            'taker_imbalance_5m': 0.60,
            'taker_imbalance_15m': 0.55,
            'volume_ratio_5m': 2.0,
            'volume_ratio_15m': 1.8,
            'oi_change_5m': 0.02,
            'oi_change_15m': 0.03,
            # 中期字段完整
            'price_change_1h': 0.025,
            'price_change_6h': 0.04,
            'oi_change_1h': 0.05,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.70,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # 两者都应该有输出（不一定是LONG，但应该是明确的决策）
        assert result.short_term is not None
        assert result.medium_term is not None
        assert result.short_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE]
        assert result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE]
        
        print(f"✅ Test A3 passed: short_term={result.short_term.decision.value}, "
              f"medium_term={result.medium_term.decision.value}")


class TestP0CodeFix26hDegradeTo1hOnly:
    """P0-CodeFix-2: 6h缺口降级为1h-only"""
    
    @pytest.fixture
    def engine(self):
        config_path = project_root / 'config' / 'l1_thresholds.yaml'
        return L1AdvisoryEngine(config_path=str(config_path))
    
    def test_6h_missing_degrade_to_1h_only(self, engine):
        """
        验收Case B1: 6h缺失但1h完整且有明确方向
        
        预期：
        - medium_term: 输出方向（LONG/SHORT或明确NO_TRADE）
        - reason_tags: 包含MTF_DEGRADED_TO_1H或DATA_GAP_6H
        - execution_permission: ALLOW_REDUCED（降级）
        - confidence: 被cap（不超过HIGH）
        """
        # Given: 6h缺失，但1h完整且强势
        data = {
            'price': 50000,
            'volume_24h': 1000000,
            # 短期字段完整（便于观察medium独立性）
            'price_change_5m': 0.003,
            'price_change_15m': 0.008,
            'taker_imbalance_5m': 0.60,
            'taker_imbalance_15m': 0.55,
            'volume_ratio_5m': 2.0,
            'volume_ratio_15m': 1.8,
            'oi_change_5m': 0.02,
            'oi_change_15m': 0.03,
            # 中期字段：1h完整且强势，6h缺失
            'price_change_1h': 0.025,  # 2.5%上涨
            # 'price_change_6h': None,  # 缺失
            'oi_change_1h': 0.06,  # 6%增长
            # 'oi_change_6h': None,  # 缺失
            'taker_imbalance_1h': 0.75,  # 75%买压
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        # When
        result = engine.on_new_tick_dual('BTC', data)
        
        # Then: medium_term仍输出方向（不硬失败）
        assert result.medium_term is not None, \
            "6h缺失时medium_term不应该None"
        assert result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE], \
            "medium_term应该有决策输出"
        
        # Then: 降级标签
        assert (ReasonTag.MTF_DEGRADED_TO_1H in result.medium_term.reason_tags or
                ReasonTag.DATA_GAP_6H in result.medium_term.reason_tags), \
            f"应该有降级标签（MTF_DEGRADED_TO_1H或DATA_GAP_6H），实际: {result.medium_term.reason_tags}"
        
        # Then: 降级执行许可
        assert result.medium_term.execution_permission in [
            ExecutionPermission.ALLOW_REDUCED,
            ExecutionPermission.DENY  # 如果其他原因也阻断
        ], f"降级模式下执行许可应该至少为ALLOW_REDUCED，实际: {result.medium_term.execution_permission}"
        
        # Then: 置信度上限
        assert result.medium_term.confidence in [
            Confidence.LOW,
            Confidence.MEDIUM,
            Confidence.HIGH
            # 不应该是ULTRA（降级后被cap）
        ], f"降级模式下confidence应该被cap（不超过HIGH），实际: {result.medium_term.confidence}"
        
        # Then: timeframe_label应该显示降级
        assert '1h' in result.medium_term.timeframe_label.lower(), \
            f"timeframe_label应该显示1h-only，实际: {result.medium_term.timeframe_label}"
        
        print(f"✅ Test B1 passed: medium_term={result.medium_term.decision.value}, "
              f"conf={result.medium_term.confidence.value}, "
              f"exec_perm={result.medium_term.execution_permission.value}, "
              f"label={result.medium_term.timeframe_label}")
    
    def test_1h_missing_still_hard_fail(self, engine):
        """
        验收Case B2: 1h缺失时仍然硬失败（不降级）
        
        确保降级只发生在6h缺失场景，1h缺失仍然NO_TRADE
        """
        data = {
            'price': 50000,
            'volume_24h': 1000000,
            # 短期字段完整
            'price_change_5m': 0.003,
            'price_change_15m': 0.008,
            'taker_imbalance_5m': 0.60,
            'taker_imbalance_15m': 0.55,
            'volume_ratio_5m': 2.0,
            'volume_ratio_15m': 1.8,
            'oi_change_5m': 0.02,
            'oi_change_15m': 0.03,
            # 1h缺失
            # 'price_change_1h': None,
            'price_change_6h': 0.05,  # 6h存在
            # 'oi_change_1h': None,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.70,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # 1h缺失 → 硬失败
        assert result.medium_term.decision == Decision.NO_TRADE, \
            "1h缺失应该硬失败NO_TRADE"
        assert ReasonTag.DATA_INCOMPLETE_MTF in result.medium_term.reason_tags, \
            f"应该有DATA_INCOMPLETE_MTF标签，实际: {result.medium_term.reason_tags}"
        assert result.medium_term.executable is False, \
            "1h缺失不可执行"
        
        print(f"✅ Test B2 passed: 1h缺失硬失败，medium_term={result.medium_term.decision.value}")
    
    def test_6h_degraded_confidence_cap(self, engine):
        """
        验收Case B3: 6h降级时置信度上限验证
        
        即使1h信号很强，降级后confidence也不应超过HIGH
        """
        data = {
            'price': 50000,
            'volume_24h': 1000000,
            # 短期字段完整
            'price_change_5m': 0.005,
            'price_change_15m': 0.012,
            'taker_imbalance_5m': 0.70,
            'taker_imbalance_15m': 0.65,
            'volume_ratio_5m': 2.5,
            'volume_ratio_15m': 2.0,
            'oi_change_5m': 0.03,
            'oi_change_15m': 0.04,
            # 中期：1h极强信号，但6h缺失
            'price_change_1h': 0.04,  # 4%上涨（极强）
            # 'price_change_6h': None,
            'oi_change_1h': 0.08,  # 8%增长（极强）
            # 'oi_change_6h': None,
            'taker_imbalance_1h': 0.85,  # 85%买压（极强）
            'funding_rate': 0.0002,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # 降级后置信度不应该是ULTRA
        assert result.medium_term.confidence != Confidence.ULTRA, \
            f"降级模式下confidence应该被cap到HIGH，不应该是ULTRA，实际: {result.medium_term.confidence}"
        
        # 应该有降级标签
        assert (ReasonTag.MTF_DEGRADED_TO_1H in result.medium_term.reason_tags or
                ReasonTag.DATA_GAP_6H in result.medium_term.reason_tags), \
            "应该有降级标签"
        
        print(f"✅ Test B3 passed: 降级后confidence被cap，实际={result.medium_term.confidence.value}")


class TestP0CodeFixIntegration:
    """集成测试：两个CodeFix组合"""
    
    @pytest.fixture
    def engine(self):
        config_path = project_root / 'config' / 'l1_thresholds.yaml'
        return L1AdvisoryEngine(config_path=str(config_path))
    
    def test_short_gap_and_medium_6h_gap(self, engine):
        """
        集成Case: short gap + medium 6h gap
        
        预期：
        - short_term: NO_TRADE (DATA_GAP_5M/INCOMPLETE_LTF)
        - medium_term: 降级评估（1h-only），输出方向
        """
        data = {
            'price': 50000,
            'volume_24h': 1000000,
            # 短期缺失
            # 'price_change_5m': None,
            'price_change_15m': 0.008,
            'taker_imbalance_15m': 0.55,
            'volume_ratio_15m': 1.8,
            'oi_change_15m': 0.03,
            # 中期：1h完整，6h缺失
            'price_change_1h': 0.025,
            # 'price_change_6h': None,
            'oi_change_1h': 0.06,
            # 'oi_change_6h': None,
            'taker_imbalance_1h': 0.75,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # short_term被阻断
        assert result.short_term.decision == Decision.NO_TRADE, \
            "short gap应该阻断short_term"
        assert (ReasonTag.DATA_GAP_5M in result.short_term.reason_tags or
                ReasonTag.DATA_INCOMPLETE_LTF in result.short_term.reason_tags), \
            "short_term应该有gap标签"
        
        # medium_term降级但仍输出
        assert result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE], \
            "medium_term应该有决策（降级评估）"
        assert (ReasonTag.MTF_DEGRADED_TO_1H in result.medium_term.reason_tags or
                ReasonTag.DATA_GAP_6H in result.medium_term.reason_tags), \
            "medium_term应该有降级标签"
        
        print(f"✅ Integration test passed: short={result.short_term.decision.value}, "
              f"medium={result.medium_term.decision.value} (degraded)")
    
    def test_cold_start_scenario_5_minutes(self, engine):
        """
        冷启动场景测试（5分钟）：只有部分数据
        
        模拟服务刚启动5分钟的场景
        """
        data = {
            'price': 50000,
            'volume_24h': 1000000,
            # 只有5m数据
            'price_change_5m': 0.003,
            'taker_imbalance_5m': 0.60,
            'volume_ratio_5m': 2.0,
            'oi_change_5m': 0.02,
            # 15m及以上都缺失
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # short和medium都应该NO_TRADE（数据不足）
        assert result.short_term.decision == Decision.NO_TRADE
        assert result.medium_term.decision == Decision.NO_TRADE
        
        print(f"✅ Cold start (5min) test passed: both NO_TRADE as expected")


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v', '--tb=short', '-s'])
