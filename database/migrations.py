"""
Database Migrations - 数据库迁移和表结构管理
"""

import logging

logger = logging.getLogger(__name__)


class DatabaseMigrations:
    """数据库迁移管理"""
    
    def __init__(self, connection):
        """
        初始化迁移管理器
        
        Args:
            connection: DatabaseConnection实例
        """
        self.connection = connection
    
    def init_all_tables(self):
        """初始化所有数据库表结构"""
        with self.connection.connect() as conn:
            cursor = conn.cursor()
            
            # 创建L1决策结果表
            self._create_advisory_table(cursor)
            
            # 创建管道步骤表
            self._create_pipeline_table(cursor)
            
            # 创建双周期表
            self._create_dual_advisory_table(cursor)
            
            # 执行迁移
            self._migrate_add_execution_permission(cursor)
            self._migrate_add_signal_decision(cursor)
            self._migrate_add_price(cursor)
            self._migrate_add_price_dual(cursor)
            
            # 创建索引
            self._create_indexes(cursor)
            
            conn.commit()
            logger.info("Database tables initialized")
    
    def _create_advisory_table(self, cursor):
        """创建L1决策结果表"""
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
                price REAL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')
    
    def _create_pipeline_table(self, cursor):
        """创建管道步骤表"""
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
    
    def _create_dual_advisory_table(self, cursor):
        """创建双周期独立结论表"""
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS l1_dual_advisory_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                price REAL,
                
                -- 短期结论（5m/15m）
                short_term_decision TEXT NOT NULL,
                short_term_confidence TEXT NOT NULL,
                short_term_executable INTEGER NOT NULL,
                short_term_regime TEXT NOT NULL,
                short_term_quality TEXT NOT NULL,
                
                -- 中长期结论（1h/6h）
                medium_term_decision TEXT NOT NULL,
                medium_term_confidence TEXT NOT NULL,
                medium_term_executable INTEGER NOT NULL,
                medium_term_regime TEXT NOT NULL,
                medium_term_quality TEXT NOT NULL,
                
                -- 一致性分析
                alignment_type TEXT NOT NULL,
                is_aligned INTEGER NOT NULL,
                has_conflict INTEGER NOT NULL,
                recommended_action TEXT NOT NULL,
                recommended_confidence TEXT NOT NULL,
                
                -- 完整JSON
                full_json TEXT NOT NULL,
                
                -- 元数据
                risk_exposure_allowed INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')
    
    def _create_indexes(self, cursor):
        """创建索引（优化查询性能）"""
        # L1 advisory索引
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
        
        # Pipeline索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_l1_steps_advisory 
            ON l1_pipeline_steps(advisory_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_l1_steps_symbol_timestamp 
            ON l1_pipeline_steps(symbol, timestamp DESC)
        ''')
        
        # Dual advisory索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_l1_dual_symbol_timestamp 
            ON l1_dual_advisory_results(symbol, timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_l1_dual_alignment_type 
            ON l1_dual_advisory_results(alignment_type)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_l1_dual_created_at 
            ON l1_dual_advisory_results(created_at DESC)
        ''')
    
    def _migrate_add_execution_permission(self, cursor):
        """迁移：添加 execution_permission 字段"""
        try:
            cursor.execute("PRAGMA table_info(l1_advisory_results)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'execution_permission' not in columns:
                logger.info("Migrating: adding execution_permission column")
                cursor.execute('''
                    ALTER TABLE l1_advisory_results 
                    ADD COLUMN execution_permission TEXT DEFAULT 'allow'
                ''')
                logger.info("✅ Migration completed: execution_permission added")
        except Exception as e:
            logger.error(f"Error during migration: {e}")
    
    def _migrate_add_signal_decision(self, cursor):
        """迁移：添加 signal_decision 字段"""
        try:
            cursor.execute("PRAGMA table_info(l1_advisory_results)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'signal_decision' not in columns:
                logger.info("Migrating: adding signal_decision column")
                cursor.execute('''
                    ALTER TABLE l1_advisory_results 
                    ADD COLUMN signal_decision TEXT
                ''')
                logger.info("✅ Migration completed: signal_decision added")
        except Exception as e:
            logger.error(f"Error during migration: {e}")
    
    def _migrate_add_price(self, cursor):
        """迁移：添加 price 字段"""
        try:
            cursor.execute("PRAGMA table_info(l1_advisory_results)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'price' not in columns:
                logger.info("Migrating: adding price column")
                cursor.execute('''
                    ALTER TABLE l1_advisory_results 
                    ADD COLUMN price REAL
                ''')
                logger.info("✅ Migration completed: price added")
        except Exception as e:
            logger.error(f"Error during migration: {e}")
    
    def _migrate_add_price_dual(self, cursor):
        """迁移：为双周期表添加 price 字段"""
        try:
            cursor.execute("PRAGMA table_info(l1_dual_advisory_results)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'price' not in columns:
                logger.info("Migrating dual: adding price column")
                cursor.execute('''
                    ALTER TABLE l1_dual_advisory_results 
                    ADD COLUMN price REAL
                ''')
                logger.info("✅ Dual migration completed: price added")
        except Exception as e:
            logger.error(f"Error during dual migration: {e}")
