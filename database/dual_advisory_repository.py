"""
Dual Advisory Repository - 双周期决策数据访问
"""

import json
import sqlite3
from typing import List, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class DualAdvisoryRepository:
    """双周期决策数据访问"""
    
    def __init__(self, connection):
        """
        初始化Repository
        
        Args:
            connection: DatabaseConnection实例
        """
        self.connection = connection
    
    def save(self, symbol: str, result) -> int:
        """
        保存双周期独立结论到数据库
        
        Args:
            symbol: 交易对符号
            result: DualTimeframeResult 双周期结论
        
        Returns:
            result_id: 插入记录的ID
        """
        try:
            short = result.short_term
            medium = result.medium_term
            align = result.alignment
            
            with self.connection.connect() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO l1_dual_advisory_results (
                        symbol, timestamp, price,
                        short_term_decision, short_term_confidence, short_term_executable,
                        short_term_regime, short_term_quality,
                        medium_term_decision, medium_term_confidence, medium_term_executable,
                        medium_term_regime, medium_term_quality,
                        alignment_type, is_aligned, has_conflict,
                        recommended_action, recommended_confidence,
                        full_json, risk_exposure_allowed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    result.timestamp.isoformat(),
                    result.price,
                    short.decision.value,
                    short.confidence.value,
                    1 if short.executable else 0,
                    short.market_regime.value,
                    short.trade_quality.value,
                    medium.decision.value,
                    medium.confidence.value,
                    1 if medium.executable else 0,
                    medium.market_regime.value,
                    medium.trade_quality.value,
                    align.alignment_type.value,
                    1 if align.is_aligned else 0,
                    1 if align.has_conflict else 0,
                    align.recommended_action.value,
                    align.recommended_confidence.value,
                    json.dumps(result.to_dict()),
                    1 if result.risk_exposure_allowed else 0
                ))
                
                conn.commit()
                result_id = cursor.lastrowid
                
                logger.debug(f"[{symbol}] Saved dual advisory result: id={result_id}")
                return result_id
        
        except Exception as e:
            logger.error(f"Error saving dual advisory result: {e}")
            return 0
    
    def get_history(
        self, 
        symbol: str, 
        hours: int = 24, 
        limit: int = 1500
    ) -> List[Dict]:
        """
        获取双周期独立结论历史记录
        
        Args:
            symbol: 交易对符号
            hours: 回溯小时数
            limit: 最大返回条数
        
        Returns:
            历史记录列表（从新到旧）
        """
        try:
            time_cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            with self.connection.connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM l1_dual_advisory_results
                    WHERE symbol = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (symbol, time_cutoff, limit))
                
                rows = cursor.fetchall()
                
                results = []
                for row in rows:
                    full_data = json.loads(row['full_json'])
                    results.append(full_data)
                
                logger.debug(f"[{symbol}] Retrieved {len(results)} dual advisory records ({hours}h)")
                return results
        
        except Exception as e:
            logger.error(f"Error getting dual advisory history: {e}")
            return []
    
    def get_stats(self, symbol: str) -> Dict:
        """
        获取双周期决策统计信息
        
        Args:
            symbol: 交易对符号
        
        Returns:
            统计信息字典
        """
        try:
            with self.connection.connect() as conn:
                cursor = conn.cursor()
                
                # 统计1: alignment_type分布
                cursor.execute('''
                    SELECT 
                        alignment_type,
                        COUNT(*) as count,
                        COUNT(*) * 100.0 / (SELECT COUNT(*) FROM l1_dual_advisory_results WHERE symbol = ?) as percentage
                    FROM l1_dual_advisory_results
                    WHERE symbol = ?
                    GROUP BY alignment_type
                    ORDER BY count DESC
                ''', (symbol, symbol))
                
                alignment_stats = {}
                for row in cursor.fetchall():
                    alignment_stats[row[0]] = {
                        'count': row[1],
                        'percentage': round(row[2], 2)
                    }
                
                # 统计2: 短期决策分布
                cursor.execute('''
                    SELECT short_term_decision, COUNT(*) as count
                    FROM l1_dual_advisory_results
                    WHERE symbol = ?
                    GROUP BY short_term_decision
                ''', (symbol,))
                
                short_term_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                # 统计3: 中长期决策分布
                cursor.execute('''
                    SELECT medium_term_decision, COUNT(*) as count
                    FROM l1_dual_advisory_results
                    WHERE symbol = ?
                    GROUP BY medium_term_decision
                ''', (symbol,))
                
                medium_term_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                return {
                    'symbol': symbol,
                    'alignment_type_distribution': alignment_stats,
                    'short_term_decision_distribution': short_term_stats,
                    'medium_term_decision_distribution': medium_term_stats
                }
        
        except Exception as e:
            logger.error(f"Error getting dual decision stats: {e}")
            return {}
