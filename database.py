"""
市场信号数据库模块
用途：记录历史市场分析信号，用于策略评估和统计
"""

import sqlite3
import json
from datetime import datetime
import os
import logging

# 配置日志（减少输出）
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

class SignalDatabase:
    """市场信号数据库管理类"""
    
    def __init__(self, db_path='market_signals.db'):
        """初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，默认为当前目录下的market_signals.db
        """
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 创建信号记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    symbol VARCHAR(10) NOT NULL,
                    trade_action VARCHAR(10) NOT NULL,
                    state_reason TEXT,
                    long_score FLOAT,
                    short_score FLOAT,
                    price FLOAT,
                    price_change_24h FLOAT,
                    price_trend_6h FLOAT,
                    volume_change_6h FLOAT,
                    oi_change_6h FLOAT,
                    funding_rate FLOAT,
                    buy_ratio_1h FLOAT,
                    sell_ratio_1h FLOAT,
                    total_amount_1h FLOAT,
                    risk_warnings TEXT,
                    long_reasons TEXT,
                    short_reasons TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建索引以提高查询性能
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_timestamp 
                ON market_signals(symbol, timestamp DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trade_action 
                ON market_signals(trade_action)
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"数据库初始化成功: {self.db_path}")
            
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
    
    def save_signal(self, analysis_result):
        """保存市场分析信号
        
        Args:
            analysis_result: analyze_futures_market方法返回的结果字典
            
        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            if not analysis_result.get('success'):
                return False
            
            symbol = analysis_result.get('symbol', 'UNKNOWN')
            analysis = analysis_result.get('analysis', {})
            
            # 提取数据
            trade_action = analysis.get('trade_action', 'NO_TRADE')
            state_reason = analysis.get('state_reason', '')
            data_summary = analysis.get('data_summary', {})
            risk_warning = analysis.get('risk_warning', [])
            internal_scores = analysis.get('_internal_scores', {})
            
            # 准备插入数据
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            long_score = internal_scores.get('long_score', 0)
            short_score = internal_scores.get('short_score', 0)
            long_reasons = json.dumps(internal_scores.get('long_reasons', []), ensure_ascii=False)
            short_reasons = json.dumps(internal_scores.get('short_reasons', []), ensure_ascii=False)
            risk_warnings_json = json.dumps(risk_warning, ensure_ascii=False)
            
            # 插入数据库
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO market_signals (
                    timestamp, symbol, trade_action, state_reason,
                    long_score, short_score,
                    price, price_change_24h, price_trend_6h,
                    volume_change_6h, oi_change_6h, funding_rate,
                    buy_ratio_1h, sell_ratio_1h, total_amount_1h,
                    risk_warnings, long_reasons, short_reasons
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                symbol,
                trade_action,
                state_reason,
                long_score,
                short_score,
                data_summary.get('price', 0),
                data_summary.get('price_change_24h', 0),
                data_summary.get('price_trend_6h', 0),
                data_summary.get('volume_change_6h', 0),
                data_summary.get('oi_change_6h', 0),
                data_summary.get('funding_rate', 0),
                data_summary.get('buy_ratio_1h', 0),
                data_summary.get('sell_ratio_1h', 0),
                data_summary.get('total_amount_1h', 0),
                risk_warnings_json,
                long_reasons,
                short_reasons
            ))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.warning(f"保存信号到数据库失败: {str(e)}")
            return False
    
    def get_latest_signals(self, symbol=None, limit=10):
        """获取最近的信号记录
        
        Args:
            symbol: 币种符号，None表示所有币种
            limit: 返回记录数量
            
        Returns:
            list: 信号记录列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # 返回字典格式
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute("""
                    SELECT * FROM market_signals 
                    WHERE symbol = ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (symbol, limit))
            else:
                cursor.execute("""
                    SELECT * FROM market_signals 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            # 转换为字典列表
            results = []
            for row in rows:
                results.append(dict(row))
            
            return results
    
    def get_signals_last_48h(self, symbol=None):
        """获取最近48小时的信号记录
        
        Args:
            symbol: 币种符号，None表示所有币种
            
        Returns:
            list: 信号记录列表
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 计算48小时前的时间
            from datetime import datetime, timedelta
            time_48h_ago = (datetime.now() - timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')
            
            if symbol:
                cursor.execute("""
                    SELECT * FROM market_signals 
                    WHERE symbol = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                """, (symbol, time_48h_ago))
            else:
                cursor.execute("""
                    SELECT * FROM market_signals 
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                """, (time_48h_ago,))
            
            rows = cursor.fetchall()
            conn.close()
            
            results = []
            for row in rows:
                results.append(dict(row))
            
            return results
        
        except Exception as e:
            logger.warning(f"查询48小时信号失败: {str(e)}")
            return []
    
    def cleanup_old_signals(self, hours=48):
        """清理超过指定小时数的旧信号
        
        Args:
            hours: 保留小时数，默认48小时
            
        Returns:
            int: 删除的记录数
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            from datetime import datetime, timedelta
            time_threshold = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute("""
                DELETE FROM market_signals 
                WHERE timestamp < ?
            """, (time_threshold,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"清理了{deleted_count}条旧信号记录（超过{hours}小时）")
            
            return deleted_count
        
        except Exception as e:
            logger.warning(f"清理旧信号失败: {str(e)}")
            return 0
    
    def get_signal_accuracy_analysis(self, symbol=None, hours=48):
        """分析信号准确性（简化版本）
        
        Args:
            symbol: 币种符号
            hours: 分析时间范围
            
        Returns:
            dict: 准确性分析结果
        """
        try:
            signals = self.get_signals_last_48h(symbol)
            
            if not signals:
                return {
                    'total_signals': 0,
                    'long_count': 0,
                    'short_count': 0,
                    'no_trade_count': 0,
                    'long_percentage': 0,
                    'short_percentage': 0,
                    'no_trade_percentage': 0
                }
            
            # 统计各类型信号
            total = len(signals)
            long_count = sum(1 for s in signals if s['trade_action'] == 'LONG')
            short_count = sum(1 for s in signals if s['trade_action'] == 'SHORT')
            no_trade_count = sum(1 for s in signals if s['trade_action'] == 'NO_TRADE')
            
            return {
                'total_signals': total,
                'long_count': long_count,
                'short_count': short_count,
                'no_trade_count': no_trade_count,
                'long_percentage': round(long_count / total * 100, 2) if total > 0 else 0,
                'short_percentage': round(short_count / total * 100, 2) if total > 0 else 0,
                'no_trade_percentage': round(no_trade_count / total * 100, 2) if total > 0 else 0,
                'time_range_hours': hours,
                'oldest_signal': signals[-1]['timestamp'] if signals else None,
                'newest_signal': signals[0]['timestamp'] if signals else None
            }
        
        except Exception as e:
            logger.warning(f"分析信号准确性失败: {str(e)}")
            return {}
            
        except Exception as e:
            logger.warning(f"查询信号记录失败: {str(e)}")
            return []
    
    def get_signal_stats(self, symbol=None, days=7):
        """获取信号统计数据
        
        Args:
            symbol: 币种符号，None表示所有币种
            days: 统计最近多少天的数据
            
        Returns:
            dict: 统计结果
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 计算时间范围
            time_filter = f"datetime('now', '-{days} days')"
            
            if symbol:
                # 单个币种统计
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as total_count,
                        SUM(CASE WHEN trade_action = 'LONG' THEN 1 ELSE 0 END) as long_count,
                        SUM(CASE WHEN trade_action = 'SHORT' THEN 1 ELSE 0 END) as short_count,
                        SUM(CASE WHEN trade_action = 'NO_TRADE' THEN 1 ELSE 0 END) as no_trade_count,
                        AVG(long_score) as avg_long_score,
                        AVG(short_score) as avg_short_score,
                        AVG(price_change_24h) as avg_price_change
                    FROM market_signals
                    WHERE symbol = ? AND timestamp >= {time_filter}
                """, (symbol,))
            else:
                # 所有币种统计
                cursor.execute(f"""
                    SELECT 
                        COUNT(*) as total_count,
                        SUM(CASE WHEN trade_action = 'LONG' THEN 1 ELSE 0 END) as long_count,
                        SUM(CASE WHEN trade_action = 'SHORT' THEN 1 ELSE 0 END) as short_count,
                        SUM(CASE WHEN trade_action = 'NO_TRADE' THEN 1 ELSE 0 END) as no_trade_count,
                        AVG(long_score) as avg_long_score,
                        AVG(short_score) as avg_short_score,
                        AVG(price_change_24h) as avg_price_change
                    FROM market_signals
                    WHERE timestamp >= {time_filter}
                """)
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                total = row[0] or 0
                return {
                    'total_count': total,
                    'long_count': row[1] or 0,
                    'short_count': row[2] or 0,
                    'no_trade_count': row[3] or 0,
                    'long_percentage': round((row[1] or 0) / total * 100, 2) if total > 0 else 0,
                    'short_percentage': round((row[2] or 0) / total * 100, 2) if total > 0 else 0,
                    'no_trade_percentage': round((row[3] or 0) / total * 100, 2) if total > 0 else 0,
                    'avg_long_score': round(row[4] or 0, 2),
                    'avg_short_score': round(row[5] or 0, 2),
                    'avg_price_change': round(row[6] or 0, 2)
                }
            else:
                return {
                    'total_count': 0,
                    'long_count': 0,
                    'short_count': 0,
                    'no_trade_count': 0,
                    'long_percentage': 0,
                    'short_percentage': 0,
                    'no_trade_percentage': 0,
                    'avg_long_score': 0,
                    'avg_short_score': 0,
                    'avg_price_change': 0
                }
            
        except Exception as e:
            logger.warning(f"统计信号数据失败: {str(e)}")
            return None
    
    def get_database_info(self):
        """获取数据库基本信息
        
        Returns:
            dict: 数据库信息
        """
        try:
            # 文件大小
            file_size = 0
            if os.path.exists(self.db_path):
                file_size = os.path.getsize(self.db_path)
            
            # 记录数量
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM market_signals")
            total_records = cursor.fetchone()[0]
            
            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM market_signals")
            time_range = cursor.fetchone()
            
            cursor.execute("SELECT DISTINCT symbol FROM market_signals")
            symbols = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            
            return {
                'db_path': self.db_path,
                'file_size_mb': round(file_size / 1024 / 1024, 2),
                'total_records': total_records,
                'first_record': time_range[0],
                'last_record': time_range[1],
                'symbols': symbols,
                'symbol_count': len(symbols)
            }
            
        except Exception as e:
            logger.warning(f"获取数据库信息失败: {str(e)}")
            return None


# 全局数据库实例（单例模式）
_db_instance = None

def get_signal_db():
    """获取全局数据库实例"""
    global _db_instance
    if _db_instance is None:
        import os
        # 数据库存储在 /app/db 目录（Docker挂载点）
        db_dir = os.getenv('DB_DIR', '/app/db')
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, 'market_signals.db')
        _db_instance = SignalDatabase(db_path=db_path)
    return _db_instance
