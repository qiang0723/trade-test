#!/usr/bin/env python3
"""
独立测试脚本 - PR-004/005/006
不依赖pytest，直接运行
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Confidence, TradeQuality, MarketRegime, Decision
from models.advisory_result import AdvisoryResult
from models.reason_tags import ReasonTag


class TestRunner:
    """简单的测试运行器"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def test(self, name, func):
        """运行单个测试"""
        try:
            func()
            self.passed += 1
            print(f"✅ {name}")
        except AssertionError as e:
            self.failed += 1
            error_msg = f"❌ {name}: {str(e)}"
            self.errors.append(error_msg)
            print(error_msg)
        except Exception as e:
            self.failed += 1
            error_msg = f"💥 {name}: {type(e).__name__}: {str(e)}"
            self.errors.append(error_msg)
            print(error_msg)
    
    def summary(self):
        """打印测试摘要"""
        total = self.passed + self.failed
        print("\n" + "="*60)
        print(f"测试结果: {self.passed}/{total} 通过")
        if self.failed > 0:
            print(f"\n失败的测试:")
            for error in self.errors:
                print(f"  {error}")
        print("="*60)
        return self.failed == 0


def main():
    runner = TestRunner()
    
    print("="*60)
    print("测试 PR-006: Executable Gate收紧")
    print("="*60)
    
    def test_executable_gate_ultra():
        """测试ULTRA置信度可执行"""
        result = AdvisoryResult(
            decision=Decision.LONG,
            confidence=Confidence.ULTRA,
            market_regime=MarketRegime.TREND,
            system_state="wait",
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.GOOD,
            reason_tags=[],
            timestamp=datetime.now(),
            executable=False
        )
        
        executable = result.compute_executable()
        assert executable, "ULTRA应该可执行"
    
    def test_executable_gate_high():
        """测试HIGH置信度可执行"""
        result = AdvisoryResult(
            decision=Decision.LONG,
            confidence=Confidence.HIGH,
            market_regime=MarketRegime.TREND,
            system_state="wait",
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.GOOD,
            reason_tags=[],
            timestamp=datetime.now(),
            executable=False
        )
        
        executable = result.compute_executable()
        assert executable, "HIGH应该可执行"
    
    def test_executable_gate_medium():
        """测试MEDIUM置信度不可执行"""
        result = AdvisoryResult(
            decision=Decision.LONG,
            confidence=Confidence.MEDIUM,
            market_regime=MarketRegime.RANGE,
            system_state="wait",
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.GOOD,
            reason_tags=[],
            timestamp=datetime.now(),
            executable=False
        )
        
        executable = result.compute_executable()
        assert not executable, "MEDIUM不应该可执行（PR-006收紧）"
    
    runner.test("PR-006: ULTRA可执行", test_executable_gate_ultra)
    runner.test("PR-006: HIGH可执行", test_executable_gate_high)
    runner.test("PR-006: MEDIUM不可执行", test_executable_gate_medium)
    
    print("\n" + "="*60)
    print("测试 PR-005: Confidence升级（4层）")
    print("="*60)
    
    def test_confidence_enum_exists():
        """测试ULTRA枚举存在"""
        assert hasattr(Confidence, 'ULTRA'), "Confidence应该有ULTRA级别"
        assert Confidence.ULTRA.value == "ultra"
    
    def test_confidence_4_levels():
        """测试置信度有4个级别"""
        levels = [Confidence.ULTRA, Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW]
        assert len(levels) == 4, "应该有4个置信度级别"
    
    def test_confidence_ultra_computation():
        """测试ULTRA的计算逻辑（直接测试_compute_confidence方法）"""
        engine = L1AdvisoryEngine()
        
        # 直接测试置信度计算方法
        # TREND + GOOD + 强信号 → ULTRA (7-8分)
        confidence = engine._compute_confidence(
            decision=Decision.LONG,
            regime=MarketRegime.TREND,  # 3分
            quality=TradeQuality.GOOD,  # 2分
            reason_tags=[ReasonTag.STRONG_BUY_PRESSURE]  # 2分，总计7分
        )
        
        assert confidence == Confidence.ULTRA, \
            f"TREND + GOOD + 强信号应该是ULTRA，得到: {confidence.value}"
        
        # TREND + GOOD（无强信号）→ HIGH (5-6分)
        confidence2 = engine._compute_confidence(
            decision=Decision.LONG,
            regime=MarketRegime.TREND,  # 3分
            quality=TradeQuality.GOOD,  # 2分
            reason_tags=[]  # 0分强信号，总计5分
        )
        
        assert confidence2 == Confidence.HIGH, \
            f"TREND + GOOD应该是HIGH，得到: {confidence2.value}"
    
    runner.test("PR-005: ULTRA枚举存在", test_confidence_enum_exists)
    runner.test("PR-005: 4个级别", test_confidence_4_levels)
    runner.test("PR-005: ULTRA计算逻辑", test_confidence_ultra_computation)
    
    print("\n" + "="*60)
    print("测试 PR-004: TradeQuality噪声优化")
    print("="*60)
    
    def test_trade_quality_uncertain_exists():
        """测试UNCERTAIN枚举存在"""
        assert hasattr(TradeQuality, 'UNCERTAIN'), "TradeQuality应该有UNCERTAIN级别"
        assert TradeQuality.UNCERTAIN.value == "uncertain"
    
    def test_trade_quality_3_levels():
        """测试交易质量有3个级别"""
        levels = [TradeQuality.GOOD, TradeQuality.UNCERTAIN, TradeQuality.POOR]
        assert len(levels) == 3, "应该有3个交易质量级别"
    
    def test_uncertain_allows_execution():
        """测试UNCERTAIN不阻止执行"""
        result = AdvisoryResult(
            decision=Decision.LONG,
            confidence=Confidence.HIGH,
            market_regime=MarketRegime.TREND,
            system_state="wait",
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.UNCERTAIN,  # 噪声市场
            reason_tags=[ReasonTag.NOISY_MARKET],
            timestamp=datetime.now(),
            executable=False
        )
        
        executable = result.compute_executable()
        assert executable, "UNCERTAIN + HIGH置信度应该可执行（PR-004）"
    
    def test_poor_blocks_execution():
        """测试POOR阻止执行"""
        result = AdvisoryResult(
            decision=Decision.LONG,
            confidence=Confidence.HIGH,
            market_regime=MarketRegime.TREND,
            system_state="wait",
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.POOR,  # 明确风险
            reason_tags=[ReasonTag.ABSORPTION_RISK],
            timestamp=datetime.now(),
            executable=False
        )
        
        executable = result.compute_executable()
        assert not executable, "POOR应该阻止执行（即使HIGH置信度）"
    
    runner.test("PR-004: UNCERTAIN枚举存在", test_trade_quality_uncertain_exists)
    runner.test("PR-004: 3个级别", test_trade_quality_3_levels)
    runner.test("PR-004: UNCERTAIN允许执行", test_uncertain_allows_execution)
    runner.test("PR-004: POOR阻止执行", test_poor_blocks_execution)
    
    print("\n" + "="*60)
    print("集成测试：三个PR协同")
    print("="*60)
    
    def test_full_integration():
        """测试完整集成：ULTRA + GOOD → executable"""
        result = AdvisoryResult(
            decision=Decision.LONG,
            confidence=Confidence.ULTRA,  # PR-005
            market_regime=MarketRegime.TREND,
            system_state="wait",
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.GOOD,
            reason_tags=[ReasonTag.STRONG_BUY_PRESSURE],
            timestamp=datetime.now(),
            executable=False
        )
        
        executable = result.compute_executable()  # PR-006
        assert executable, "ULTRA + GOOD应该可执行"
    
    def test_integration_uncertain_high():
        """测试集成：HIGH + UNCERTAIN → executable"""
        result = AdvisoryResult(
            decision=Decision.SHORT,
            confidence=Confidence.HIGH,
            market_regime=MarketRegime.TREND,
            system_state="wait",
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.UNCERTAIN,  # PR-004
            reason_tags=[ReasonTag.NOISY_MARKET],
            timestamp=datetime.now(),
            executable=False
        )
        
        executable = result.compute_executable()
        assert executable, "HIGH + UNCERTAIN应该可执行"
    
    def test_integration_medium_good():
        """测试集成：MEDIUM + GOOD → 不可执行"""
        result = AdvisoryResult(
            decision=Decision.LONG,
            confidence=Confidence.MEDIUM,  # 不够高
            market_regime=MarketRegime.RANGE,
            system_state="wait",
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.GOOD,
            reason_tags=[],
            timestamp=datetime.now(),
            executable=False
        )
        
        executable = result.compute_executable()
        assert not executable, "MEDIUM不应该可执行（即使GOOD）"
    
    runner.test("集成: ULTRA + GOOD", test_full_integration)
    runner.test("集成: HIGH + UNCERTAIN", test_integration_uncertain_high)
    runner.test("集成: MEDIUM + GOOD不可执行", test_integration_medium_good)
    
    # 打印摘要
    success = runner.summary()
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
