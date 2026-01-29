"""
Whitelist Repository - 动态白名单数据访问层

职责：
1. 存储和查询白名单状态
2. 记录历史胜率变化
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class WhitelistRepository:
    """白名单数据访问"""
    
    def __init__(self, connection):
        """
        初始化Repository
        
        Args:
            connection: DatabaseConnection实例
        """
        self.connection = connection
        self._init_tables()
    
    def _init_tables(self):
        """创建白名单相关表"""
        with self.connection.connect() as conn:
            cursor = conn.cursor()
            
            # 白名单状态表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS l1_whitelist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    
                    -- 统计数据
                    total_signals INTEGER DEFAULT 0,
                    win_count INTEGER DEFAULT 0,
                    loss_count INTEGER DEFAULT 0,
                    win_rate REAL DEFAULT 0.0,
                    avg_profit REAL DEFAULT 0.0,
                    avg_loss REAL DEFAULT 0.0,
                    
                    -- 白名单状态
                    in_whitelist INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'observation',
                    
                    -- 元数据
                    last_signal_at TEXT,
                    updated_at TEXT DEFAULT (datetime('now')),
                    created_at TEXT DEFAULT (datetime('now')),
                    
                    UNIQUE(symbol, direction)
                )
            ''')
            
            # 白名单历史记录表（用于追踪变化）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS l1_whitelist_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    win_rate REAL NOT NULL,
                    total_signals INTEGER NOT NULL,
                    in_whitelist INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            ''')
            
            # 创建索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_whitelist_symbol_direction 
                ON l1_whitelist(symbol, direction)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_whitelist_status 
                ON l1_whitelist(in_whitelist, status)
            ''')
            
            conn.commit()
            logger.info("Whitelist tables initialized")
    
    def get_all(self) -> List[Dict]:
        """
        获取所有白名单记录
        
        Returns:
            白名单记录列表
        """
        with self.connection.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, direction, total_signals, win_count, loss_count,
                       win_rate, avg_profit, avg_loss, in_whitelist, status,
                       last_signal_at, updated_at
                FROM l1_whitelist
                ORDER BY in_whitelist DESC, win_rate DESC
            ''')
            
            rows = cursor.fetchall()
            return [
                {
                    'symbol': row[0],
                    'direction': row[1],
                    'total_signals': row[2],
                    'win_count': row[3],
                    'loss_count': row[4],
                    'win_rate': row[5],
                    'avg_profit': row[6],
                    'avg_loss': row[7],
                    'in_whitelist': bool(row[8]),
                    'status': row[9],
                    'last_signal_at': row[10],
                    'updated_at': row[11]
                }
                for row in rows
            ]
    
    def get_whitelist_only(self) -> List[Dict]:
        """
        只获取在白名单中的记录
        
        Returns:
            白名单记录列表
        """
        with self.connection.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, direction, win_rate, total_signals, status
                FROM l1_whitelist
                WHERE in_whitelist = 1
                ORDER BY win_rate DESC
            ''')
            
            rows = cursor.fetchall()
            return [
                {
                    'symbol': row[0],
                    'direction': row[1],
                    'win_rate': row[2],
                    'total_signals': row[3],
                    'status': row[4]
                }
                for row in rows
            ]
    
    def get_blacklist(self) -> List[Dict]:
        """
        获取黑名单（低胜率或观察中的记录）
        
        Returns:
            黑名单记录列表
        """
        with self.connection.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, direction, win_rate, total_signals, status
                FROM l1_whitelist
                WHERE in_whitelist = 0 AND status != 'observation'
                ORDER BY win_rate ASC
            ''')
            
            rows = cursor.fetchall()
            return [
                {
                    'symbol': row[0],
                    'direction': row[1],
                    'win_rate': row[2],
                    'total_signals': row[3],
                    'status': row[4]
                }
                for row in rows
            ]
    
    def is_in_whitelist(self, symbol: str, direction: str) -> bool:
        """
        检查是否在白名单中
        
        Args:
            symbol: 币种
            direction: 方向 (long/short)
            
        Returns:
            是否在白名单中
        """
        with self.connection.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT in_whitelist FROM l1_whitelist
                WHERE symbol = ? AND direction = ?
            ''', (symbol.upper(), direction.lower()))
            
            row = cursor.fetchone()
            return bool(row[0]) if row else False
    
    def get_status(self, symbol: str, direction: str) -> Optional[Dict]:
        """
        获取特定币种+方向的白名单状态
        
        Args:
            symbol: 币种
            direction: 方向 (long/short)
            
        Returns:
            状态信息字典
        """
        with self.connection.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symbol, direction, total_signals, win_count, loss_count,
                       win_rate, avg_profit, avg_loss, in_whitelist, status,
                       last_signal_at, updated_at
                FROM l1_whitelist
                WHERE symbol = ? AND direction = ?
            ''', (symbol.upper(), direction.lower()))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                'symbol': row[0],
                'direction': row[1],
                'total_signals': row[2],
                'win_count': row[3],
                'loss_count': row[4],
                'win_rate': row[5],
                'avg_profit': row[6],
                'avg_loss': row[7],
                'in_whitelist': bool(row[8]),
                'status': row[9],
                'last_signal_at': row[10],
                'updated_at': row[11]
            }
    
    def upsert(self, symbol: str, direction: str, stats: Dict) -> bool:
        """
        更新或插入白名单记录
        
        Args:
            symbol: 币种
            direction: 方向 (long/short)
            stats: 统计数据字典
            
        Returns:
            是否成功
        """
        try:
            with self.connection.connect() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO l1_whitelist 
                    (symbol, direction, total_signals, win_count, loss_count,
                     win_rate, avg_profit, avg_loss, in_whitelist, status,
                     last_signal_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(symbol, direction) DO UPDATE SET
                        total_signals = excluded.total_signals,
                        win_count = excluded.win_count,
                        loss_count = excluded.loss_count,
                        win_rate = excluded.win_rate,
                        avg_profit = excluded.avg_profit,
                        avg_loss = excluded.avg_loss,
                        in_whitelist = excluded.in_whitelist,
                        status = excluded.status,
                        last_signal_at = excluded.last_signal_at,
                        updated_at = datetime('now')
                ''', (
                    symbol.upper(),
                    direction.lower(),
                    stats.get('total_signals', 0),
                    stats.get('win_count', 0),
                    stats.get('loss_count', 0),
                    stats.get('win_rate', 0.0),
                    stats.get('avg_profit', 0.0),
                    stats.get('avg_loss', 0.0),
                    1 if stats.get('in_whitelist', False) else 0,
                    stats.get('status', 'observation'),
                    stats.get('last_signal_at')
                ))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error upserting whitelist: {e}")
            return False
    
    def record_history(self, symbol: str, direction: str, stats: Dict, reason: str = None):
        """
        记录白名单变更历史
        
        Args:
            symbol: 币种
            direction: 方向
            stats: 统计数据
            reason: 变更原因
        """
        try:
            with self.connection.connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO l1_whitelist_history
                    (symbol, direction, win_rate, total_signals, in_whitelist, status, reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol.upper(),
                    direction.lower(),
                    stats.get('win_rate', 0.0),
                    stats.get('total_signals', 0),
                    1 if stats.get('in_whitelist', False) else 0,
                    stats.get('status', 'observation'),
                    reason
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error recording whitelist history: {e}")
    
    def get_history(self, symbol: str = None, direction: str = None, limit: int = 100) -> List[Dict]:
        """
        获取白名单变更历史
        
        Args:
            symbol: 币种（可选）
            direction: 方向（可选）
            limit: 最大记录数
            
        Returns:
            历史记录列表
        """
        with self.connection.connect() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT symbol, direction, win_rate, total_signals, 
                       in_whitelist, status, reason, created_at
                FROM l1_whitelist_history
            '''
            params = []
            
            if symbol or direction:
                conditions = []
                if symbol:
                    conditions.append('symbol = ?')
                    params.append(symbol.upper())
                if direction:
                    conditions.append('direction = ?')
                    params.append(direction.lower())
                query += ' WHERE ' + ' AND '.join(conditions)
            
            query += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                {
                    'symbol': row[0],
                    'direction': row[1],
                    'win_rate': row[2],
                    'total_signals': row[3],
                    'in_whitelist': bool(row[4]),
                    'status': row[5],
                    'reason': row[6],
                    'created_at': row[7]
                }
                for row in rows
            ]
