"""
测试拆分后的L1引擎模块

测试内容：
1. 模块导入
2. DecisionMemory功能
3. DualDecisionMemory功能
4. ConfigManager功能
5. 与原系统兼容性
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta
from models.enums import Decision, AlignmentType


class TestModuleImports:
    """测试模块导入"""
    
    def test_import_memory_classes(self):
        """测试导入决策记忆类"""
        from l1_engine import DecisionMemory, DualDecisionMemory
        
        assert DecisionMemory is not None
        assert DualDecisionMemory is not None
    
    def test_import_config_manager(self):
        """测试导入配置管理器"""
        from l1_engine import ConfigManager
        
        assert ConfigManager is not None


class TestDecisionMemory:
    """测试DecisionMemory"""
    
    def test_init(self):
        """测试初始化"""
        from l1_engine import DecisionMemory
        
        memory = DecisionMemory()
        assert memory.get_last_decision('BTC') is None
    
    def test_update_and_get(self):
        """测试更新和获取决策"""
        from l1_engine import DecisionMemory
        
        memory = DecisionMemory()
        now = datetime.now()
        
        # 更新LONG决策
        memory.update_decision('BTC', Decision.LONG, now)
        last = memory.get_last_decision('BTC')
        
        assert last is not None
        assert last['side'] == Decision.LONG
        assert last['time'] == now
    
    def test_no_trade_not_recorded(self):
        """测试NO_TRADE不被记录"""
        from l1_engine import DecisionMemory
        
        memory = DecisionMemory()
        
        # 更新NO_TRADE
        memory.update_decision('BTC', Decision.NO_TRADE, datetime.now())
        
        # 应该没有记录
        assert memory.get_last_decision('BTC') is None
    
    def test_clear(self):
        """测试清除记忆"""
        from l1_engine import DecisionMemory
        
        memory = DecisionMemory()
        memory.update_decision('BTC', Decision.LONG, datetime.now())
        
        memory.clear('BTC')
        assert memory.get_last_decision('BTC') is None


class TestDualDecisionMemory:
    """测试DualDecisionMemory"""
    
    def test_init_with_config(self):
        """测试带配置初始化"""
        from l1_engine import DualDecisionMemory
        
        config = {
            'dual_decision_control': {
                'short_term_interval_seconds': 600,
                'medium_term_interval_seconds': 3600
            }
        }
        
        memory = DualDecisionMemory(config)
        assert memory.short_term_interval == 600
        assert memory.medium_term_interval == 3600
    
    def test_short_term_not_blocked_first_time(self):
        """测试首次短期决策不被阻断"""
        from l1_engine import DualDecisionMemory
        
        memory = DualDecisionMemory()
        blocked, reason = memory.should_block_short_term('BTC', Decision.LONG, datetime.now())
        
        assert not blocked
        assert reason == ""
    
    def test_short_term_blocked_by_interval(self):
        """测试短期决策被最小间隔阻断"""
        from l1_engine import DualDecisionMemory
        
        memory = DualDecisionMemory()
        now = datetime.now()
        
        # 第一次决策
        memory.update_short_term('BTC', Decision.LONG, now)
        
        # 立即第二次决策（间隔不足）
        blocked, reason = memory.should_block_short_term('BTC', Decision.LONG, now + timedelta(seconds=60))
        
        assert blocked
        assert '短期决策间隔不足' in reason
    
    def test_short_term_blocked_by_flip_cooldown(self):
        """测试短期决策被翻转冷却阻断"""
        from l1_engine import DualDecisionMemory
        
        memory = DualDecisionMemory()
        now = datetime.now()
        
        # 第一次决策：LONG
        memory.update_short_term('BTC', Decision.LONG, now)
        
        # 间隔足够但方向翻转（SHORT）
        blocked, reason = memory.should_block_short_term(
            'BTC', 
            Decision.SHORT, 
            now + timedelta(seconds=350)  # 超过300s间隔，但未超过450s翻转冷却
        )
        
        assert blocked
        assert '短期方向翻转冷却中' in reason
    
    def test_no_trade_never_blocked(self):
        """测试NO_TRADE永不被阻断"""
        from l1_engine import DualDecisionMemory
        
        memory = DualDecisionMemory()
        now = datetime.now()
        
        # 第一次决策
        memory.update_short_term('BTC', Decision.LONG, now)
        
        # 立即输出NO_TRADE（应不被阻断）
        blocked, reason = memory.should_block_short_term('BTC', Decision.NO_TRADE, now)
        
        assert not blocked
    
    def test_alignment_flip_blocked(self):
        """测试对齐类型翻转被阻断"""
        from l1_engine import DualDecisionMemory
        
        memory = DualDecisionMemory()
        now = datetime.now()
        
        # 第一次：BOTH_LONG
        memory.update_alignment('BTC', AlignmentType.BOTH_LONG, now)
        
        # 立即翻转为BOTH_SHORT（重大翻转）
        blocked, reason = memory.should_block_alignment_flip(
            'BTC',
            AlignmentType.BOTH_SHORT,
            now + timedelta(seconds=60)
        )
        
        assert blocked
        assert '对齐类型重大翻转冷却中' in reason


class TestConfigManager:
    """测试ConfigManager"""
    
    def test_load_config(self):
        """测试加载配置"""
        from l1_engine import ConfigManager
        
        config_mgr = ConfigManager('config/l1_thresholds.yaml')
        config = config_mgr.get_config()
        
        assert config is not None
        assert 'market_regime' in config
        assert 'risk_exposure' in config
    
    def test_get_thresholds(self):
        """测试获取扁平化阈值"""
        from l1_engine import ConfigManager
        
        config_mgr = ConfigManager('config/l1_thresholds.yaml')
        thresholds = config_mgr.get_thresholds()
        
        assert len(thresholds) > 0
        assert 'extreme_price_change_1h' in thresholds
        assert 'trend_price_change_6h' in thresholds
    
    def test_validation_pass(self):
        """测试配置校验通过"""
        from l1_engine import ConfigManager
        
        # 正常配置应该能通过所有校验
        config_mgr = ConfigManager('config/l1_thresholds.yaml')
        
        assert config_mgr.config is not None
        assert config_mgr.thresholds is not None


class TestBackwardCompatibility:
    """测试向后兼容性"""
    
    def test_original_system_still_works(self):
        """测试原系统仍然正常工作"""
        from market_state_machine_l1 import L1AdvisoryEngine
        
        # 原系统应该能正常初始化
        engine = L1AdvisoryEngine()
        
        assert engine is not None
        assert hasattr(engine, 'decision_memory')
        assert hasattr(engine, 'dual_decision_memory')
    
    def test_original_decision_memory_class_exists(self):
        """测试原文件中的DecisionMemory类仍存在"""
        from market_state_machine_l1 import DecisionMemory as OriginalDecisionMemory
        
        memory = OriginalDecisionMemory()
        assert memory is not None
    
    def test_original_dual_memory_class_exists(self):
        """测试原文件中的DualDecisionMemory类仍存在"""
        from market_state_machine_l1 import DualDecisionMemory as OriginalDualMemory
        
        memory = OriginalDualMemory()
        assert memory is not None


class TestModuleIndependence:
    """测试模块独立性"""
    
    def test_memory_module_standalone(self):
        """测试memory模块可独立使用"""
        # 只导入memory模块，不依赖其他
        from l1_engine.memory import DecisionMemory, DualDecisionMemory
        
        memory = DecisionMemory()
        dual_memory = DualDecisionMemory()
        
        assert memory is not None
        assert dual_memory is not None
    
    def test_config_manager_standalone(self):
        """测试ConfigManager可独立使用"""
        # 只导入config_manager，不依赖其他
        from l1_engine.config_manager import ConfigManager
        
        config_mgr = ConfigManager('config/l1_thresholds.yaml')
        
        assert config_mgr is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
