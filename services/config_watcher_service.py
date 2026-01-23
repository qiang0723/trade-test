"""
Config Watcher Service - 配置文件监控服务

职责：
1. 监控配置文件变化
2. 自动重载配置（热更新）
"""

import os
import yaml
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 可选依赖：Watchdog
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog not installed, config hot reload disabled")


class ConfigReloader(FileSystemEventHandler):
    """配置文件监控和热更新"""
    
    def __init__(self, engine, config_path: str):
        self.engine = engine
        self.config_path = config_path
    
    def on_modified(self, event):
        """文件修改时触发"""
        if not event.is_directory and event.src_path.endswith('l1_thresholds.yaml'):
            logger.info(f"Config file modified: {event.src_path}")
            self._reload_config()
    
    def _reload_config(self):
        """重载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                new_config = yaml.safe_load(f)
            
            # 扁平化阈值
            new_thresholds = self.engine._flatten_thresholds(new_config)
            
            # 更新引擎阈值
            self.engine.update_thresholds(new_thresholds)
            
            logger.info(f"✅ Config reloaded successfully: {len(new_thresholds)} thresholds updated")
            
        except Exception as e:
            logger.error(f"❌ Error reloading config: {e}", exc_info=True)


class ConfigWatcherService:
    """配置文件监控服务"""
    
    def __init__(self, advisory_engine, config_dir: str):
        """
        初始化配置监控服务
        
        Args:
            advisory_engine: L1AdvisoryEngine实例
            config_dir: 配置目录路径
        """
        self.advisory_engine = advisory_engine
        self.config_dir = config_dir
        self.observer = None
    
    def start(self) -> Optional[object]:
        """启动配置文件监控"""
        if not WATCHDOG_AVAILABLE:
            logger.warning("Watchdog not available, skipping config file watcher")
            return None
        
        try:
            if not os.path.exists(self.config_dir):
                logger.warning(f"Config directory not found: {self.config_dir}")
                return None
            
            self.observer = Observer()
            config_path = os.path.join(self.config_dir, 'l1_thresholds.yaml')
            event_handler = ConfigReloader(self.advisory_engine, config_path)
            self.observer.schedule(event_handler, self.config_dir, recursive=False)
            self.observer.start()
            
            logger.info(f"📁 Config file watcher started: {self.config_dir}")
            return self.observer
        
        except Exception as e:
            logger.error(f"Error starting config watcher: {e}")
            return None
    
    def stop(self):
        """停止监控"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("Config watcher stopped")
