"""
Database Connection - 数据库连接管理
"""

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """数据库连接管理器"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，默认为 data/db/l1_advisory.db
        """
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            db_dir = os.path.join(base_dir, 'data', 'db')
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, 'l1_advisory.db')
        
        self.db_path = db_path
        logger.info(f"DatabaseConnection initialized: {self.db_path}")
    
    def connect(self):
        """创建新的数据库连接"""
        return sqlite3.connect(self.db_path)
    
    def close(self):
        """预留方法（实际使用with语句管理连接）"""
        pass
