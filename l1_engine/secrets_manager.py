"""
L1 Advisory Engine - 密钥安全管理模块

安全原则：
1. API Key仅从环境变量或.env文件读取
2. 绝不在代码中硬编码密钥
3. 绝不在日志中输出完整密钥
4. 启动时验证密钥存在性
5. 支持密钥掩码显示（仅显示前4位）

使用方式：
    from l1_engine.secrets_manager import SecretsManager
    
    secrets = SecretsManager()
    api_key = secrets.get_coinglass_api_key()
"""

import os
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class SecretsManager:
    """
    密钥安全管理器
    
    优先级：
    1. 环境变量（Docker/生产环境）
    2. .env文件（本地开发）
    """
    
    # 支持的密钥配置
    COINGLASS_API_KEY = "COINGLASS_API_KEY"
    COINGLASS_BASE_URL = "COINGLASS_BASE_URL"
    COINGLASS_ENABLED = "COINGLASS_ENABLED"
    
    # 默认值 (Coinglass Open API v4)
    DEFAULT_COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com"
    
    def __init__(self, env_file: Optional[str] = None):
        """
        初始化密钥管理器
        
        Args:
            env_file: .env文件路径，None则自动查找
        """
        self._loaded = False
        self._env_file = env_file
        self._load_env_file()
    
    def _load_env_file(self):
        """
        从.env文件加载环境变量（如果存在）
        
        注意：环境变量优先级高于.env文件
        """
        if self._loaded:
            return
        
        # 确定.env文件路径
        if self._env_file:
            env_path = Path(self._env_file)
        else:
            # 查找项目根目录的.env
            current_dir = Path(__file__).parent.parent
            env_path = current_dir / ".env"
        
        if env_path.exists():
            logger.info(f"Loading secrets from: {env_path}")
            self._parse_env_file(env_path)
        else:
            logger.debug(f".env file not found at {env_path}, using environment variables only")
        
        self._loaded = True
    
    def _parse_env_file(self, env_path: Path):
        """
        解析.env文件
        
        仅设置尚未在环境中定义的变量（环境变量优先）
        """
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    
                    # 跳过空行和注释
                    if not line or line.startswith('#'):
                        continue
                    
                    # 解析KEY=VALUE
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # 移除引号
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        # 仅在环境变量未设置时才使用.env值
                        if key not in os.environ:
                            os.environ[key] = value
                            logger.debug(f"Loaded from .env: {key}={self._mask_value(value)}")
        except Exception as e:
            logger.warning(f"Failed to parse .env file: {e}")
    
    @staticmethod
    def _mask_value(value: str, show_chars: int = 4) -> str:
        """
        掩码敏感值（用于日志）
        
        Args:
            value: 原始值
            show_chars: 显示前几个字符
        
        Returns:
            掩码后的值，如 "sk-1***"
        """
        if not value or len(value) <= show_chars:
            return "***"
        return f"{value[:show_chars]}{'*' * (len(value) - show_chars)}"
    
    def get_coinglass_api_key(self, required: bool = True) -> Optional[str]:
        """
        获取Coinglass API Key
        
        Args:
            required: 是否必需，True时缺失会抛出异常
        
        Returns:
            API Key或None
        
        Raises:
            ValueError: required=True但Key未配置时
        """
        api_key = os.environ.get(self.COINGLASS_API_KEY)
        
        if not api_key or api_key == "your_api_key_here":
            if required:
                raise ValueError(
                    f"Coinglass API Key not configured!\n"
                    f"Please set {self.COINGLASS_API_KEY} environment variable or create .env file.\n"
                    f"See .env.example for reference."
                )
            return None
        
        logger.info(f"Coinglass API Key loaded: {self._mask_value(api_key)}")
        return api_key
    
    def get_coinglass_base_url(self) -> str:
        """
        获取Coinglass API基础URL
        
        Returns:
            基础URL
        """
        return os.environ.get(
            self.COINGLASS_BASE_URL, 
            self.DEFAULT_COINGLASS_BASE_URL
        )
    
    def is_coinglass_enabled(self) -> bool:
        """
        检查Coinglass数据源是否启用
        
        Returns:
            是否启用
        """
        enabled = os.environ.get(self.COINGLASS_ENABLED, "true")
        return enabled.lower() in ("true", "1", "yes", "on")
    
    def validate_coinglass_config(self) -> dict:
        """
        验证Coinglass配置完整性
        
        Returns:
            验证结果字典
        """
        result = {
            "enabled": self.is_coinglass_enabled(),
            "api_key_configured": False,
            "base_url": self.get_coinglass_base_url(),
            "errors": []
        }
        
        if not result["enabled"]:
            result["errors"].append("Coinglass is disabled")
            return result
        
        try:
            api_key = self.get_coinglass_api_key(required=False)
            result["api_key_configured"] = bool(api_key)
            if not api_key:
                result["errors"].append("API Key not configured")
        except ValueError as e:
            result["errors"].append(str(e))
        
        return result


# 单例实例（便于全局使用）
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """获取密钥管理器单例"""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager
