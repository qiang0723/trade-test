"""
Scheduler Service - 定时任务服务

职责：
1. 管理定时任务（定期决策更新、数据清理）
2. 封装APScheduler逻辑
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 可选依赖：APScheduler
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("apscheduler not installed, auto cleanup disabled")


class SchedulerService:
    """定时任务服务"""
    
    def __init__(self, advisory_engine, l1_db, binance_fetcher, config):
        """
        初始化定时任务服务
        
        Args:
            advisory_engine: L1AdvisoryEngine实例
            l1_db: L1Database实例
            binance_fetcher: BinanceDataFetcher实例
            config: 配置字典
        """
        self.advisory_engine = advisory_engine
        self.l1_db = l1_db
        self.binance_fetcher = binance_fetcher
        self.config = config
        self.scheduler = None
    
    def start(self) -> Optional[object]:
        """启动定时任务调度器"""
        if not APSCHEDULER_AVAILABLE:
            logger.warning("APScheduler not available, skipping scheduler")
            return None
        
        try:
            # 缓存预热：启动时从Binance获取历史数据
            self._warmup_cache()
            
            periodic_config = self.config.get('periodic_update', {})
            
            if not periodic_config.get('enabled', True):
                logger.warning("Periodic advisory update is disabled in config")
                return None
            
            self.scheduler = BackgroundScheduler()
            
            # 任务1: 定时自动获取决策并保存
            interval_minutes = periodic_config.get('interval_minutes', 1)
            from datetime import datetime
            self.scheduler.add_job(
                func=self._periodic_advisory_update,
                trigger='interval',
                minutes=interval_minutes,
                id='periodic_advisory',
                name=f'Periodic L1 advisory update (every {interval_minutes} minute(s))',
                max_instances=1,
                next_run_time=datetime.now()  # 立即开始执行
            )
            
            # 任务2: 定期清理旧数据
            retention_config = self.config.get('data_retention', {})
            cleanup_interval = retention_config.get('cleanup_interval_hours', 6)
            self.scheduler.add_job(
                func=self._cleanup_old_records_job,
                trigger='cron',
                hour=f'*/{cleanup_interval}',
                minute=0,
                id='cleanup_old_records',
                name=f'Cleanup old L1 advisory records (every {cleanup_interval}h)'
            )
            
            self.scheduler.start()
            logger.info("⏰ Scheduler started:")
            logger.info(f"  - Periodic advisory update: Every {interval_minutes} minute(s)")
            logger.info(f"  - Cleanup old records: Every {cleanup_interval} hours")
            
            return self.scheduler
        
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
            return None
    
    def stop(self):
        """停止调度器"""
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    def _warmup_cache(self):
        """预热缓存：从Binance获取历史数据填充缓存"""
        try:
            symbols = self.config.get('symbols', ['BTCUSDT'])
            warmup_hours = 6  # 预热6小时历史数据
            
            logger.info(f"🔥 Starting cache warmup for {len(symbols)} symbols...")
            
            # 调用binance_fetcher的预热方法
            if hasattr(self.binance_fetcher, 'warmup_cache'):
                results = self.binance_fetcher.warmup_cache(symbols, hours=warmup_hours)
                
                # 统计结果
                success_count = sum(1 for r in results.values() if r.get('success'))
                logger.info(f"🔥 Cache warmup completed: {success_count}/{len(symbols)} symbols warmed up")
            else:
                logger.warning("BinanceDataFetcher does not have warmup_cache method, skipping warmup")
        
        except Exception as e:
            logger.error(f"Error during cache warmup: {e}", exc_info=True)
    
    def _periodic_advisory_update(self):
        """定时更新任务：每分钟自动获取市场数据并生成决策"""
        try:
            logger.info("⏰ Running periodic advisory update...")
            
            symbols = self.config.get('symbols', ['BTCUSDT'])
            market_type = self.config.get('periodic_update', {}).get('market_type', 'futures')
            
            error_config = self.config.get('error_handling', {})
            max_retries = error_config.get('max_retries', 3)
            retry_delay = error_config.get('retry_delay_seconds', 5)
            continue_on_error = error_config.get('continue_on_error', True)
            
            if not symbols:
                logger.warning("No symbols configured for monitoring")
                return
            
            for symbol in symbols:
                market_data = None
                last_error = None
                
                # 重试逻辑
                for attempt in range(max_retries):
                    try:
                        market_data = self.binance_fetcher.fetch_market_data(symbol, market_type=market_type)
                        
                        if market_data:
                            break
                        else:
                            last_error = f"No market data returned for {symbol}"
                            if attempt < max_retries - 1:
                                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {symbol}, retrying...")
                                import time
                                time.sleep(retry_delay)
                        
                    except Exception as e:
                        last_error = str(e)
                        if attempt < max_retries - 1:
                            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {symbol}: {e}")
                            import time
                            time.sleep(retry_delay)
                        else:
                            logger.error(f"All {max_retries} attempts failed for {symbol}: {e}", exc_info=True)
                
                if not market_data:
                    logger.error(f"❌ Failed to fetch {symbol} after {max_retries} attempts: {last_error}")
                    if continue_on_error:
                        continue
                    else:
                        break
                
                # 生成L1双周期决策并保存
                try:
                    # 统一使用不带USDT后缀的符号名（数据库一致性）
                    db_symbol = symbol.replace('USDT', '') if symbol.endswith('USDT') else symbol
                    
                    result = self.advisory_engine.on_new_tick_dual(db_symbol, market_data)
                    self.l1_db.save_dual_advisory_result(db_symbol, result)
                    
                    logger.info(
                        f"✅ Periodic update saved: {db_symbol} → {result.alignment.recommended_action.value} "
                        f"(short: {result.short_term.decision.value}, medium: {result.medium_term.decision.value})"
                    )
                
                except Exception as e:
                    logger.error(f"Error processing decision for {symbol}: {e}", exc_info=True)
                    if continue_on_error:
                        continue
                    else:
                        break
        
        except Exception as e:
            logger.error(f"Error in periodic_advisory_update: {e}", exc_info=True)
    
    def _cleanup_old_records_job(self):
        """定时清理旧记录的任务（保留24小时）"""
        try:
            deleted = self.l1_db.cleanup_old_records(days=1)
            logger.info(f"🗑️  Auto cleanup completed: {deleted} old records deleted")
        except Exception as e:
            logger.error(f"Error in auto cleanup job: {e}", exc_info=True)
