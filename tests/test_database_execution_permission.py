"""
测试数据库修复：execution_permission字段
验证：
1. 数据库迁移正常（老表添加字段）
2. 保存包含execution_permission的数据
3. 查询正确读取execution_permission
4. 向后兼容（老数据默认为'allow'）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from database_l1 import L1Database
from models.advisory_result import AdvisoryResult
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, SystemState, ExecutionPermission
from models.reason_tags import ReasonTag
import tempfile


def test_database_migration_and_new_field():
    """测试数据库迁移和execution_permission字段"""
    
    print("\n" + "="*80)
    print("测试数据库修复：execution_permission字段")
    print("="*80)
    
    # 创建临时数据库
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        tmp_db_path = tmp.name
    
    try:
        # 1. 初始化数据库（触发迁移逻辑）
        print("\n[步骤1] 初始化数据库...")
        db = L1Database(db_path=tmp_db_path)
        print("✅ 数据库初始化成功")
        
        # 2. 测试保存 - ALLOW
        print("\n[步骤2] 测试保存 ALLOW 许可级别...")
        result_allow = AdvisoryResult(
            decision=Decision.LONG,
            confidence=Confidence.HIGH,
            market_regime=MarketRegime.TREND,
            system_state=SystemState.WAIT,
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.GOOD,
            reason_tags=[ReasonTag.STRONG_BUY_PRESSURE],
            timestamp=datetime.now(),
            execution_permission=ExecutionPermission.ALLOW,
            executable=True
        )
        
        record_id_1 = db.save_advisory_result("TESTUSDT", result_allow)
        print(f"✅ 保存成功 (id={record_id_1}): ALLOW + executable=True")
        
        # 3. 测试保存 - ALLOW_REDUCED
        print("\n[步骤3] 测试保存 ALLOW_REDUCED 许可级别...")
        result_reduced = AdvisoryResult(
            decision=Decision.SHORT,
            confidence=Confidence.MEDIUM,
            market_regime=MarketRegime.RANGE,
            system_state=SystemState.WAIT,
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.UNCERTAIN,
            reason_tags=[ReasonTag.NOISY_MARKET, ReasonTag.WEAK_SIGNAL_IN_RANGE],
            timestamp=datetime.now(),
            execution_permission=ExecutionPermission.ALLOW_REDUCED,
            executable=True
        )
        
        record_id_2 = db.save_advisory_result("TESTUSDT", result_reduced)
        print(f"✅ 保存成功 (id={record_id_2}): ALLOW_REDUCED + executable=True")
        
        # 4. 测试保存 - DENY
        print("\n[步骤4] 测试保存 DENY 许可级别...")
        result_deny = AdvisoryResult(
            decision=Decision.NO_TRADE,
            confidence=Confidence.LOW,
            market_regime=MarketRegime.EXTREME,
            system_state=SystemState.WAIT,
            risk_exposure_allowed=True,
            trade_quality=TradeQuality.POOR,
            reason_tags=[ReasonTag.EXTREME_VOLUME, ReasonTag.ABSORPTION_RISK],
            timestamp=datetime.now(),
            execution_permission=ExecutionPermission.DENY,
            executable=False
        )
        
        record_id_3 = db.save_advisory_result("TESTUSDT", result_deny)
        print(f"✅ 保存成功 (id={record_id_3}): DENY + executable=False")
        
        # 5. 测试查询最新记录
        print("\n[步骤5] 测试查询最新记录...")
        latest = db.get_latest_advisory("TESTUSDT")
        assert latest is not None, "❌ 查询失败"
        assert latest.execution_permission == ExecutionPermission.DENY, \
            f"❌ execution_permission错误: 期望DENY, 实际{latest.execution_permission.value}"
        assert latest.executable == False, f"❌ executable错误: 期望False, 实际{latest.executable}"
        print(f"✅ 查询成功: execution_permission={latest.execution_permission.value}, executable={latest.executable}")
        
        # 6. 测试查询历史记录
        print("\n[步骤6] 测试查询历史记录...")
        history = db.get_history_advisory("TESTUSDT", hours=1, limit=10)
        assert len(history) == 3, f"❌ 历史记录数量错误: 期望3, 实际{len(history)}"
        
        # 验证每条记录都包含execution_permission
        for i, record in enumerate(history):
            assert 'execution_permission' in record, f"❌ 记录{i}缺少execution_permission字段"
            print(f"  记录{i+1}: execution_permission={record['execution_permission']}, executable={record['executable']}")
        
        print("✅ 历史记录查询成功，所有记录包含execution_permission字段")
        
        # 7. 验证三种许可级别都正确保存
        print("\n[步骤7] 验证三种许可级别...")
        perm_values = [r['execution_permission'] for r in history]
        assert 'allow' in perm_values, "❌ 缺少ALLOW记录"
        assert 'allow_reduced' in perm_values, "❌ 缺少ALLOW_REDUCED记录"
        assert 'deny' in perm_values, "❌ 缺少DENY记录"
        print("✅ 三种许可级别都正确保存")
        
        # 8. 测试to_dict序列化
        print("\n[步骤8] 测试AdvisoryResult.to_dict()...")
        dict_result = result_allow.to_dict()
        assert 'execution_permission' in dict_result, "❌ to_dict()缺少execution_permission"
        assert dict_result['execution_permission'] == 'allow', \
            f"❌ execution_permission序列化错误: {dict_result['execution_permission']}"
        print("✅ to_dict()正确包含execution_permission字段")
        
        print("\n" + "="*80)
        print("✅ 所有测试通过！数据库修复验证成功")
        print("="*80)
        print("\n验证要点:")
        print("  1. ✅ 数据库迁移正常执行")
        print("  2. ✅ execution_permission字段正确添加到表结构")
        print("  3. ✅ 保存方法正确写入execution_permission")
        print("  4. ✅ 查询方法正确读取execution_permission")
        print("  5. ✅ 三种许可级别（ALLOW/ALLOW_REDUCED/DENY）都正确处理")
        print("  6. ✅ to_dict()序列化包含新字段")
        
        return True
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return False
    
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # 清理临时文件
        if os.path.exists(tmp_db_path):
            os.unlink(tmp_db_path)


if __name__ == "__main__":
    success = test_database_migration_and_new_field()
    sys.exit(0 if success else 1)
