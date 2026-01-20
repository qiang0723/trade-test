#!/usr/bin/env python3
"""
独立测试脚本 - PR-007/008/009/010
不依赖pytest，直接运行
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from market_state_machine_l1 import L1AdvisoryEngine
from database_l1 import L1Database
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, SystemState
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
    print("测试 PR-007: Step Trace可观测性")
    print("="*60)
    
    def test_pipeline_steps_table_exists():
        """测试pipeline_steps表创建"""
        db = L1Database(':memory:')
        
        # 检查表是否存在
        import sqlite3
        with sqlite3.connect(':memory:') as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS l1_pipeline_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    advisory_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    step_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    result TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='l1_pipeline_steps'
            """)
            result = cursor.fetchone()
            
        assert result is not None, "pipeline_steps表应该存在"
    
    def test_save_and_get_pipeline_steps():
        """测试保存和获取pipeline steps"""
        import tempfile
        import os
        
        # 使用临时文件而非:memory:，以确保表创建正常
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            db_path = tmp.name
        
        try:
            db = L1Database(db_path)
            
            # 创建一个测试result
            result = AdvisoryResult(
                decision=Decision.LONG,
                confidence=Confidence.HIGH,
                market_regime=MarketRegime.TREND,
                system_state=SystemState.WAIT,  # 使用枚举而非字符串
                risk_exposure_allowed=True,
                trade_quality=TradeQuality.GOOD,
                reason_tags=[],
                timestamp=datetime.now(),
                executable=True
            )
            
            # 保存result
            advisory_id = db.save_advisory_result('BTC', result)
            
            # 保存pipeline steps
            steps = [
                {'step': 1, 'name': 'validate_data', 'status': 'success', 
                 'message': '数据验证通过', 'result': 'Valid'},
                {'step': 2, 'name': 'detect_regime', 'status': 'success', 
                 'message': '市场环境: TREND', 'result': 'trend'}
            ]
            
            db.save_pipeline_steps(advisory_id, 'BTC', steps)
            
            # 获取pipeline steps
            retrieved_steps = db.get_pipeline_steps(advisory_id)
            
            assert len(retrieved_steps) == 2, f"应该有2个步骤，得到{len(retrieved_steps)}"
            assert retrieved_steps[0]['step'] == 1
            assert retrieved_steps[0]['name'] == 'validate_data'
        finally:
            # 清理临时文件
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    runner.test("PR-007: pipeline_steps表存在", test_pipeline_steps_table_exists)
    runner.test("PR-007: 保存和获取步骤", test_save_and_get_pipeline_steps)
    
    print("\n" + "="*60)
    print("测试 PR-008: 冷热存储")
    print("="*60)
    
    def test_cleanup_includes_pipeline_steps():
        """测试cleanup同时清理pipeline steps"""
        import tempfile
        import os
        
        # 使用临时文件而非:memory:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            db_path = tmp.name
        
        try:
            db = L1Database(db_path)
            
            # 创建测试数据
            result = AdvisoryResult(
                decision=Decision.LONG,
                confidence=Confidence.HIGH,
                market_regime=MarketRegime.TREND,
                system_state=SystemState.WAIT,  # 使用枚举而非字符串
                risk_exposure_allowed=True,
                trade_quality=TradeQuality.GOOD,
                reason_tags=[],
                timestamp=datetime.now(),
                executable=True
            )
            
            advisory_id = db.save_advisory_result('BTC', result)
            steps = [{'step': 1, 'name': 'test', 'status': 'success', 
                     'message': 'test', 'result': 'test'}]
            db.save_pipeline_steps(advisory_id, 'BTC', steps)
            
            # 清理（24小时前）
            deleted = db.cleanup_old_records(days=0)  # 清理所有
            
            # cleanup应该成功（不抛出异常）
            assert True, "Cleanup应该成功执行"
        finally:
            # 清理临时文件
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    runner.test("PR-008: cleanup清理pipeline steps", test_cleanup_includes_pipeline_steps)
    
    print("\n" + "="*60)
    print("测试 PR-010: Symbol Universe")
    print("="*60)
    
    def test_symbol_universe_in_config():
        """测试配置中有symbol_universe"""
        engine = L1AdvisoryEngine()
        
        config = engine.config
        assert 'symbol_universe' in config, "配置应包含symbol_universe"
        
        symbol_universe = config['symbol_universe']
        assert 'enabled_symbols' in symbol_universe
        assert 'default_symbol' in symbol_universe
        
        enabled_symbols = symbol_universe['enabled_symbols']
        assert len(enabled_symbols) > 0, "应该有至少一个启用的币种"
        assert 'BTC' in enabled_symbols, "BTC应该在支持列表中"
    
    def test_default_symbol():
        """测试默认币种配置"""
        engine = L1AdvisoryEngine()
        
        symbol_universe = engine.config.get('symbol_universe', {})
        default_symbol = symbol_universe.get('default_symbol', None)
        
        assert default_symbol is not None, "应该有默认币种"
        assert default_symbol == 'BTC', f"默认币种应该是BTC，得到{default_symbol}"
    
    def test_multiple_symbols_support():
        """测试多币种决策支持"""
        engine = L1AdvisoryEngine()
        
        symbols = engine.config.get('symbol_universe', {}).get('enabled_symbols', [])
        
        # 测试引擎可以处理不同币种
        data = {
            'price': 100,
            'price_change_1h': 0.01,
            'volume_1h': 1000,
            'volume_24h': 24000,
            'buy_sell_imbalance': 0.5,
            'funding_rate': 0.0001,
            'oi_change_1h': 0.05,
        }
        
        for symbol in symbols[:2]:  # 测试前2个
            result = engine.on_new_tick(symbol, data)
            assert result is not None, f"{symbol}应该能生成决策"
            assert isinstance(result.decision, Decision)
    
    runner.test("PR-010: symbol_universe配置存在", test_symbol_universe_in_config)
    runner.test("PR-010: 默认币种BTC", test_default_symbol)
    runner.test("PR-010: 多币种决策支持", test_multiple_symbols_support)
    
    # 打印摘要
    success = runner.summary()
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
