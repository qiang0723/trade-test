"""
Advisory Repository - L1单周期决策数据访问
"""

import json
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from models.advisory_result import AdvisoryResult
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, SystemState, ExecutionPermission
from models.reason_tags import ReasonTag
import logging

logger = logging.getLogger(__name__)


class AdvisoryRepository:
    """L1单周期决策数据访问"""
    
    def __init__(self, connection):
        """
        初始化Repository
        
        Args:
            connection: DatabaseConnection实例
        """
        self.connection = connection
    
    def save(self, symbol: str, result: AdvisoryResult) -> int:
        """
        保存决策结果到数据库
        
        Args:
            symbol: 交易对符号
            result: AdvisoryResult对象
        
        Returns:
            int: 插入记录的ID
        """
        try:
            with self.connection.connect() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO l1_advisory_results 
                    (symbol, timestamp, decision, confidence, market_regime, system_state, 
                     risk_exposure_allowed, trade_quality, reason_tags, execution_permission, executable, signal_decision, price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    result.execution_permission.value,
                    1 if result.executable else 0,
                    result.signal_decision.value if result.signal_decision else None,
                    result.price
                ))
                
                conn.commit()
                record_id = cursor.lastrowid
                logger.info(f"Saved advisory result for {symbol}: {result.decision.value} (id={record_id})")
                return record_id
        
        except Exception as e:
            logger.error(f"Error saving advisory result: {e}")
            raise
    
    def get_latest(self, symbol: str) -> Optional[AdvisoryResult]:
        """
        获取指定币种的最新决策
        
        Args:
            symbol: 交易对符号
        
        Returns:
            AdvisoryResult或None
        """
        try:
            with self.connection.connect() as conn:
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
                        execution_permission=ExecutionPermission(row[7] or 'allow'),
                        executable=bool(row[8]),
                        signal_decision=Decision(row[9]) if row[9] else None,
                        timestamp=datetime.fromisoformat(row[10])
                    )
                return None
        
        except Exception as e:
            logger.error(f"Error getting latest advisory: {e}")
            return None
    
    def get_history(
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
            List[dict]: 历史决策列表
        """
        try:
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            with self.connection.connect() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT decision, confidence, market_regime, system_state,
                           risk_exposure_allowed, trade_quality, reason_tags, 
                           execution_permission, executable, signal_decision, timestamp, price
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
                        'execution_permission': row[7] or 'allow',
                        'executable': bool(row[8]),
                        'signal_decision': row[9],
                        'timestamp': row[10],
                        'price': row[11] if len(row) > 11 else None
                    })
                
                logger.info(f"Retrieved {len(results)} history records for {symbol}")
                return results
        
        except Exception as e:
            logger.error(f"Error getting history advisory: {e}")
            return []
    
    def get_stats(
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
        """
        try:
            cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            with self.connection.connect() as conn:
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
    
    def save_batch(self, results: List[tuple]) -> int:
        """
        批量保存决策结果（提高写入性能）
        
        Args:
            results: 元组列表，每个元组为 (symbol, result)
        
        Returns:
            int: 成功保存的记录数
        """
        try:
            with self.connection.connect() as conn:
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
                        result.execution_permission.value,
                        1 if result.executable else 0,
                        result.signal_decision.value if result.signal_decision else None,
                        result.price
                    ))
                
                cursor.executemany('''
                    INSERT INTO l1_advisory_results 
                    (symbol, timestamp, decision, confidence, market_regime, system_state, 
                     risk_exposure_allowed, trade_quality, reason_tags, execution_permission, executable, signal_decision, price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', data)
                
                conn.commit()
                count = len(data)
                logger.info(f"Batch saved {count} advisory results")
                return count
        
        except Exception as e:
            logger.error(f"Error batch saving advisory results: {e}")
            return 0
