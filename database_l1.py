"""
database_l1.py - L1数据库兼容入口

P1修复：提供旧测试代码兼容的导入路径
"""

# 从database模块导入L1DatabaseModular并提供别名
from database import L1DatabaseModular

# 兼容别名
L1Database = L1DatabaseModular

__all__ = ['L1Database', 'L1DatabaseModular']
