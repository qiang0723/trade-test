"""
Pipeline Repository - 管道步骤数据访问
"""

from typing import List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class PipelineRepository:
    """管道步骤数据访问"""
    
    def __init__(self, connection):
        """
        初始化Repository
        
        Args:
            connection: DatabaseConnection实例
        """
        self.connection = connection
    
    def save(self, advisory_id: int, symbol: str, steps: List[dict]):
        """
        保存决策管道步骤
        
        Args:
            advisory_id: 关联的advisory_result记录ID
            symbol: 交易对符号
            steps: 管道步骤列表
        """
        try:
            with self.connection.connect() as conn:
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
    
    def get(self, advisory_id: int) -> List[dict]:
        """
        获取指定决策的管道步骤
        
        Args:
            advisory_id: advisory_result记录ID
        
        Returns:
            步骤列表
        """
        try:
            with self.connection.connect() as conn:
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
    
    def cleanup_old(self, days: int = 7) -> int:
        """
        清理N天前的旧管道步骤
        
        Args:
            days: 保留天数
        
        Returns:
            int: 删除的记录数
        """
        try:
            cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()
            
            with self.connection.connect() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    DELETE FROM l1_pipeline_steps
                    WHERE timestamp < ?
                ''', (cutoff_time,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                logger.info(f"Cleaned up {deleted_count} old pipeline steps (older than {days} days)")
                return deleted_count
        
        except Exception as e:
            logger.error(f"Error cleaning up pipeline steps: {e}")
            return 0
