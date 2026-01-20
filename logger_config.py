#!/usr/bin/env python
# coding: utf-8

"""
日志配置模块
提供统一的日志管理，减少不必要的日志输出
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
import os


class LoggerConfig:
    """日志配置类"""
    
    # 日志级别配置
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'WARNING')  # 默认只输出WARNING及以上
    
    # 日志文件配置
    LOG_FILE = os.getenv('LOG_FILE', None)  # 默认不写入文件
    LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB
    LOG_BACKUP_COUNT = 2  # 保留2个备份
    
    # 日志格式
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    @classmethod
    def setup_logger(cls, name='trade-info'):
        """设置日志器
        
        Args:
            name: 日志器名称
            
        Returns:
            logging.Logger: 配置好的日志器
        """
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, cls.LOG_LEVEL.upper()))
        
        # 避免重复添加handler
        if logger.handlers:
            return logger
        
        # 创建格式化器
        formatter = logging.Formatter(
            fmt=cls.LOG_FORMAT,
            datefmt=cls.LOG_DATE_FORMAT
        )
        
        # 控制台Handler（只在开发模式或DEBUG级别时输出详细信息）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)  # 控制台只输出WARNING及以上
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 文件Handler（如果配置了日志文件）
        if cls.LOG_FILE:
            try:
                log_dir = os.path.dirname(cls.LOG_FILE)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                
                file_handler = RotatingFileHandler(
                    cls.LOG_FILE,
                    maxBytes=cls.LOG_MAX_BYTES,
                    backupCount=cls.LOG_BACKUP_COUNT,
                    encoding='utf-8'
                )
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                logger.error(f"无法创建日志文件: {e}")
        
        return logger


class QuietLogger:
    """静默日志器 - 用于替换print语句"""
    
    def __init__(self, logger=None):
        self.logger = logger or LoggerConfig.setup_logger()
    
    def startup_info(self, message):
        """启动信息（只在启动时显示）"""
        print(message)
    
    def info(self, message):
        """一般信息（记录到日志，不在控制台显示）"""
        self.logger.info(message)
    
    def warning(self, message):
        """警告信息（显示在控制台）"""
        self.logger.warning(message)
    
    def error(self, message):
        """错误信息（显示在控制台）"""
        self.logger.error(message)
    
    def debug(self, message):
        """调试信息（只在DEBUG模式显示）"""
        self.logger.debug(message)


# 全局日志器实例
_logger_instance = None

def get_logger(name='trade-info'):
    """获取全局日志器实例"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = QuietLogger(LoggerConfig.setup_logger(name))
    return _logger_instance
