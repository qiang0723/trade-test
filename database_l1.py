"""
L1 Advisory Layer - 数据库访问层

负责L1决策结果的持久化和查询：
- 保存AdvisoryResult到SQLite
- 查询历史决策（48小时）
- 数据清理和维护
"""

import sqlite3
import json
import os
from typing import List, Optional
from datetime import datetime, timedelta
from models.advisory_result import AdvisoryResult
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, SystemState, ExecutionPermission
from models.reason_tags import ReasonTag
import logging

logger = logging.getLogger(__name__)


class L1Database:
    """
    L1 Advisory Layer 数据库访问层
    
    负责：
    - 创建和管理L1决策结果表
    - 保存AdvisoryResult
    - 查询历史决策
    - 数据清理
    """
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，默认为 data/db/l1_advisory.db
        """
        if db_path is None:
            # 默认路径
            base_dir = os.path.dirname(__file__)
            db_dir = os.path.join(base_dir, 'data', 'db')
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, 'l1_advisory.db')
        
        self.db_path = db_path
        self._init_database()
        logger.info(f"L1Database initialized: {self.db_path}")
    
    def _init_database(self):
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建L1决策结果表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS l1_advisory_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    market_regime TEXT NOT NULL,
                    system_state TEXT NOT NULL,
                    risk_exposure_allowed INTEGER NOT NULL,
                    trade_quality TEXT NOT NULL,
                    reason_tags TEXT NOT NULL,
                    execution_permission TEXT DEFAULT 'allow',
                    executable INTEGER DEFAULT 0,
                    signal_decision TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            ''')
            
            # 迁移：为已存在的表添加 execution_permission 字段（向后兼容）
            self._migrate_add_execution_permission(cursor)
            
            # 迁移：为已存在的表添加 signal_decision 字段（PR-004）
            self._migrate_add_signal_decision(cursor)
            
            # 创建索引（优化查询性能）
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_l1_symbol_timestamp 
                ON l1_advisory_results(symbol, timestamp DESC)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_l1_created_at 
                ON l1_advisory_results(created_at DESC)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_l1_decision 
                ON l1_advisory_results(decision)
            ''')
            
            # PR-007: 创建Step Trace表（pipeline执行步骤）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS l1_pipeline_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    advisory_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    step_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    result TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (advisory_id) REFERENCES l1_advisory_results(id)
                )
            ''')
            
            # Step Trace索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_l1_steps_advisory 
                ON l1_pipeline_steps(advisory_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_l1_steps_symbol_timestamp 
                ON l1_pipeline_steps(symbol, timestamp DESC)
            ''')
            
            conn.commit()
            logger.info("Database tables initialized")
    
    def _migrate_add_execution_permission(self, cursor):
        """
        数据库迁移：添加 execution_permission 字段
        
        向后兼容处理：
        - 检测字段是否存在
        - 如不存在，添加字段并设置默认值为 'allow'
        - 老数据自动获得默认值
        """
        try:
            # 检查字段是否存在
            cursor.execute("PRAGMA table_info(l1_advisory_results)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'execution_permission' not in columns:
                logger.info("Migrating database: adding execution_permission column")
                cursor.execute('''
                    ALTER TABLE l1_advisory_results 
                    ADD COLUMN execution_permission TEXT DEFAULT 'allow'
                ''')
                logger.info("✅ Database migration completed: execution_permission added")
            else:
                logger.debug("execution_permission column already exists, skipping migration")
        
        except Exception as e:
            logger.error(f"Error during database migration: {e}")
            # 非致命错误，继续运行（新表创建时已包含该字段）
    
    def _migrate_add_signal_decision(self, cursor):
        """
        数据库迁移：添加 signal_decision 字段（PR-004 信号透明化）
        
        向后兼容处理：
        - 检测字段是否存在
        - 如不存在，添加字段（可为NULL，因为NO_TRADE没有原始信号）
        - 老数据自动获得NULL值
        """
        try:
            # 检查字段是否存在
            cursor.execute("PRAGMA table_info(l1_advisory_results)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'signal_decision' not in columns:
                logger.info("Migrating database: adding signal_decision column")
                cursor.execute('''
                    ALTER TABLE l1_advisory_results 
                    ADD COLUMN signal_decision TEXT
                ''')
                logger.info("✅ Database migration completed: signal_decision added")
            else:
                logger.debug("signal_decision column already exists, skipping migration")
        
        except Exception as e:
            logger.error(f"Error during database migration: {e}")
            # 非致命错误，继续运行（新表创建时已包含该字段）
    
    def save_advisory_result(self, symbol: str, result: AdvisoryResult) -> int:
        """
        保存决策结果到数据库
        
        Args:
            symbol: 交易对符号（如 "BTC"）
            result: AdvisoryResult对象
        
        Returns:
            int: 插入记录的ID
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO l1_advisory_results 
                    (symbol, timestamp, decision, confidence, market_regime, system_state, 
                     risk_exposure_allowed, trade_quality, reason_tags, execution_permission, executable, signal_decision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    result.timestamp.isoformat(),
                    result.decision.value,
                    result.confidence.value,
                    result.market_regime.value,
                    result.system_state.value,
                    1 if result.risk_exposure_allowed else 0,
                    result.trade_quality.value,
                    json.dumps([tag.value for tag in result.reason_tags]),
                    result.execution_permission.value,  # 方案D新增
                    1 if result.executable else 0,
                    result.signal_decision.value if result.signal_decision else None  # PR-004新增
                ))
                
                conn.commit()
                record_id = cursor.lastrowid
                logger.info(f"Saved advisory result for {symbol}: {result.decision.value} (id={record_id})")
                return record_id
        
        except Exception as e:
            logger.error(f"Error saving advisory result: {e}")
            raise
    
    def save_pipeline_steps(self, advisory_id: int, symbol: str, steps: List[dict]):
        """
        保存决策管道步骤（PR-007）
        
        Args:
            advisory_id: 关联的advisory_result记录ID
            symbol: 交易对符号
            steps: 管道步骤列表，每个步骤包含 {step, name, status, message, result}
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for step_info in steps:
                    cursor.execute('''
                        INSERT INTO l1_pipeline_steps 
                        (advisory_id, symbol, step_number, step_name, status, message, result, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        advisory_id,
                        symbol,
                        step_info.get('step', 0),
                        step_info.get('name', ''),
                        step_info.get('status', ''),
                        step_info.get('message', ''),
                        str(step_info.get('result', '')),
                        datetime.now().isoformat()
                    ))
                
                conn.commit()
                logger.info(f"Saved {len(steps)} pipeline steps for advisory_id={advisory_id}")
        
        except Exception as e:
            logger.error(f"Error saving pipeline steps: {e}")
            # 不抛出异常，避免影响主流程
    
    def get_pipeline_steps(self, advisory_id: int) -> List[dict]:
        """
        获取指定决策的管道步骤（PR-007）
        
        Args:
            advisory_id: advisory_result记录ID
        
        Returns:
            步骤列表
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT step_number, step_name, status, message, result, timestamp
                    FROM l1_pipeline_steps
                    WHERE advisory_id = ?
                    ORDER BY step_number ASC
                ''', (advisory_id,))
                
                rows = cursor.fetchall()
                
                steps = []
                for row in rows:
                    steps.append({
                        'step': row[0],
                        'name': row[1],
                        'status': row[2],
                        'message': row[3],
                        'result': row[4],
                        'timestamp': row[5]
                    })
                
                return steps
        
        except Exception as e:
            logger.error(f"Error getting pipeline steps: {e}")
            return []
    
    def get_latest_advisory(self, symbol: str) -> Optional[AdvisoryResult]:
        """
        获取指定币种的最新决策
        
        Args:
            symbol: 交易对符号
        
        Returns:
            AdvisoryResult或None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT decision, confidence, market_regime, system_state,
                           risk_exposure_allowed, trade_quality, reason_tags, 
                           execution_permission, executable, signal_decision, timestamp
                    FROM l1_advisory_results
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                ''', (symbol,))
                
                row = cursor.fetchone()
                if row:
                    return AdvisoryResult(
                        decision=Decision(row[0]),
                        confidence=Confidence(row[1]),
                        market_regime=MarketRegime(row[2]),
                        system_state=SystemState(row[3]),
                        risk_exposure_allowed=bool(row[4]),
                        trade_quality=TradeQuality(row[5]),
                        reason_tags=[ReasonTag(tag) for tag in json.loads(row[6])],
                        execution_permission=ExecutionPermission(row[7] or 'allow'),  # 向后兼容
                        executable=bool(row[8]),
                        signal_decision=Decision(row[9]) if row[9] else None,  # PR-004新增
                        timestamp=datetime.fromisoformat(row[10])
                    )
                return None
        
        except Exception as e:
            logger.error(f"Error getting latest advisory: {e}")
            return None
    
    def get_history_advisory(
        self, 
        symbol: str, 
        hours: int = 48, 
        limit: int = 100
    ) -> List[dict]:
        """
        获取历史决策（最近N小时）
        
        Args:
            symbol: 交易对符号
            hours: 回溯小时数（默认48小时）
            limit: 最大返回条数（默认100条）
        
        Returns:
            List[dict]: 历史决策列表（JSON可序列化）
        """
        try:
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT decision, confidence, market_regime, system_state,
                           risk_exposure_allowed, trade_quality, reason_tags, 
                           execution_permission, executable, signal_decision, timestamp
                    FROM l1_advisory_results
                    WHERE symbol = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (symbol, cutoff_time, limit))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'decision': row[0],
                        'confidence': row[1],
                        'market_regime': row[2],
                        'system_state': row[3],
                        'risk_exposure_allowed': bool(row[4]),
                        'trade_quality': row[5],
                        'reason_tags': json.loads(row[6]),
                        'execution_permission': row[7] or 'allow',  # 向后兼容
                        'executable': bool(row[8]),
                        'signal_decision': row[9],  # PR-004新增
                        'timestamp': row[10]
                    })
                
                logger.info(f"Retrieved {len(results)} history records for {symbol}")
                return results
        
        except Exception as e:
            logger.error(f"Error getting history advisory: {e}")
            return []
    
    def get_decision_stats(
        self, 
        symbol: str, 
        hours: int = 24
    ) -> dict:
        """
        获取决策统计信息（最近N小时）
        
        Args:
            symbol: 交易对符号
            hours: 统计时间范围（小时）
        
        Returns:
            dict: 统计信息
            {
                'total': 总决策数,
                'long': LONG决策数,
                'short': SHORT决策数,
                'no_trade': NO_TRADE决策数,
                'high_confidence': 高置信度决策数,
                ...
            }
        """
        try:
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 总决策数
                cursor.execute('''
                    SELECT COUNT(*) FROM l1_advisory_results
                    WHERE symbol = ? AND timestamp >= ?
                ''', (symbol, cutoff_time))
                total = cursor.fetchone()[0]
                
                # 按决策类型统计
                cursor.execute('''
                    SELECT decision, COUNT(*) FROM l1_advisory_results
                    WHERE symbol = ? AND timestamp >= ?
                    GROUP BY decision
                ''', (symbol, cutoff_time))
                decision_counts = {row[0]: row[1] for row in cursor.fetchall()}
                
                # 按置信度统计
                cursor.execute('''
                    SELECT confidence, COUNT(*) FROM l1_advisory_results
                    WHERE symbol = ? AND timestamp >= ?
                    GROUP BY confidence
                ''', (symbol, cutoff_time))
                confidence_counts = {row[0]: row[1] for row in cursor.fetchall()}
                
                return {
                    'total': total,
                    'long': decision_counts.get('long', 0),
                    'short': decision_counts.get('short', 0),
                    'no_trade': decision_counts.get('no_trade', 0),
                    'high_confidence': confidence_counts.get('high', 0),
                    'medium_confidence': confidence_counts.get('medium', 0),
                    'low_confidence': confidence_counts.get('low', 0)
                }
        
        except Exception as e:
            logger.error(f"Error getting decision stats: {e}")
            return {}
    
    def cleanup_old_records(self, days: int = 7) -> int:
        """
        清理N天前的旧记录（PR-008: 冷热存储）
        
        Args:
            days: 保留天数（默认7天，热存储为1天）
        
        Returns:
            int: 删除的记录数
        """
        try:
            cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 删除旧的advisory results
                cursor.execute('''
                    DELETE FROM l1_advisory_results
                    WHERE created_at < ?
                ''', (cutoff_time,))
                
                deleted_advisory_count = cursor.rowcount
                
                # PR-007/008: 清理关联的pipeline steps
                cursor.execute('''
                    DELETE FROM l1_pipeline_steps
                    WHERE timestamp < ?
                ''', (cutoff_time,))
                
                deleted_steps_count = cursor.rowcount
                
                conn.commit()
                
                logger.info(f"Cleaned up {deleted_advisory_count} old advisory records "
                           f"and {deleted_steps_count} pipeline steps (older than {days} days)")
                return deleted_advisory_count
        
        except Exception as e:
            logger.error(f"Error cleaning up old records: {e}")
            return 0
    
    def save_advisory_results_batch(self, results: List[tuple]) -> int:
        """
        批量保存决策结果（提高写入性能）
        
        Args:
            results: 元组列表，每个元组为 (symbol, result)
        
        Returns:
            int: 成功保存的记录数
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                data = []
                for symbol, result in results:
                    data.append((
                        symbol,
                        result.timestamp.isoformat(),
                        result.decision.value,
                        result.confidence.value,
                        result.market_regime.value,
                        result.system_state.value,
                        1 if result.risk_exposure_allowed else 0,
                        result.trade_quality.value,
                        json.dumps([tag.value for tag in result.reason_tags]),
                        result.execution_permission.value,  # 方案D新增
                        1 if result.executable else 0,
                        result.signal_decision.value if result.signal_decision else None  # PR-004新增
                    ))
                
                cursor.executemany('''
                    INSERT INTO l1_advisory_results 
                    (symbol, timestamp, decision, confidence, market_regime, system_state, 
                     risk_exposure_allowed, trade_quality, reason_tags, execution_permission, executable, signal_decision)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', data)
                
                conn.commit()
                count = len(data)
                logger.info(f"Batch saved {count} advisory results")
                return count
        
        except Exception as e:
            logger.error(f"Error batch saving advisory results: {e}")
            return 0
    
    def close(self):
        """关闭数据库连接（实际上使用with语句管理连接，此方法预留）"""
        pass


# 测试代码
if __name__ == '__main__':
    # 测试数据库功能
    db = L1Database()
    
    # 创建测试决策结果
    test_result = AdvisoryResult(
        decision=Decision.LONG,
        confidence=Confidence.HIGH,
        market_regime=MarketRegime.TREND,
        system_state=SystemState.LONG_ACTIVE,
        risk_exposure_allowed=True,
        trade_quality=TradeQuality.GOOD,
        reason_tags=[ReasonTag.STRONG_BUY_PRESSURE, ReasonTag.OI_GROWING],
        timestamp=datetime.now()
    )
    
    # 保存
    record_id = db.save_advisory_result("BTC", test_result)
    print(f"Saved test record: id={record_id}")
    
    # 查询最新
    latest = db.get_latest_advisory("BTC")
    if latest:
        print(f"Latest advisory: {latest}")
    
    # 查询历史
    history = db.get_history_advisory("BTC", hours=24, limit=10)
    print(f"History records: {len(history)}")
    
    # 统计
    stats = db.get_decision_stats("BTC", hours=24)
    print(f"Decision stats: {stats}")
