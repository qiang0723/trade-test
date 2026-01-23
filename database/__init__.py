"""
Database Layer - 数据访问层

将原始database_l1.py拆分为多个Repository模块：
- connection: 数据库连接管理
- advisory_repository: L1单周期决策数据访问
- dual_advisory_repository: 双周期决策数据访问  
- pipeline_repository: 管道步骤数据访问
- migrations: 数据库迁移
"""

from .connection import DatabaseConnection
from .advisory_repository import AdvisoryRepository
from .dual_advisory_repository import DualAdvisoryRepository
from .pipeline_repository import PipelineRepository
from .migrations import DatabaseMigrations

__all__ = [
    'DatabaseConnection',
    'AdvisoryRepository',
    'DualAdvisoryRepository',
    'PipelineRepository',
    'DatabaseMigrations',
]


class L1DatabaseModular:
    """
    L1数据库访问层（模块化版本）
    
    聚合所有Repository，提供统一接口
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库
        
        Args:
            db_path: 数据库文件路径
        """
        # 创建连接管理器
        self.connection = DatabaseConnection(db_path)
        self.db_path = self.connection.db_path
        
        # 初始化表结构
        migrations = DatabaseMigrations(self.connection)
        migrations.init_all_tables()
        
        # 创建各Repository
        self.advisory = AdvisoryRepository(self.connection)
        self.dual_advisory = DualAdvisoryRepository(self.connection)
        self.pipeline = PipelineRepository(self.connection)
    
    # ========================================
    # 向后兼容方法（兼容旧API）
    # ========================================
    
    def save_advisory_result(self, symbol: str, result):
        """兼容旧API：保存单周期决策结果"""
        return self.advisory.save(symbol, result)
    
    def save_dual_advisory_result(self, symbol: str, result):
        """兼容旧API：保存双周期决策结果"""
        return self.dual_advisory.save(symbol, result)
    
    def save_pipeline_steps(self, advisory_id: int, symbol: str, steps: list):
        """兼容旧API：保存管道步骤"""
        return self.pipeline.save(advisory_id, symbol, steps)
    
    def get_advisory_history(self, symbol: str, hours: int = 24, limit: int = 1000):
        """兼容旧API：获取单周期历史"""
        return self.advisory.get_history(symbol, hours, limit)
    
    def get_dual_advisory_history(self, symbol: str, hours: int = 24, limit: int = 1000):
        """兼容旧API：获取双周期历史"""
        return self.dual_advisory.get_history(symbol, hours, limit)
    
    def close(self):
        """关闭数据库连接"""
        self.connection.close()
