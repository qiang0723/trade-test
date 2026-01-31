"""
Coinglass数据桥接模块

P3-1 模块化重构：从decision_core.py中提取Coinglass数据获取逻辑
"""

import logging
from typing import Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class CoinglassBridge:
    """
    Coinglass数据桥接器
    
    负责：
    1. 从配置读取Coinglass设置
    2. 获取和缓存Coinglass数据
    3. 获取市场整体情绪
    """
    
    _instance: Optional['CoinglassBridge'] = None
    
    def __init__(self, config: Dict = None):
        """
        初始化桥接器
        
        Args:
            config: Coinglass配置（来自l1_thresholds.yaml的coinglass部分）
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', False)
        self._fetcher = None
        
        if self.enabled:
            logger.info("CoinglassBridge initialized (enabled)")
        else:
            logger.debug("CoinglassBridge initialized (disabled)")
    
    @classmethod
    def get_instance(cls, config: Dict = None) -> 'CoinglassBridge':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance
    
    @classmethod
    def reset(cls):
        """重置单例（用于测试）"""
        cls._instance = None
    
    def _get_fetcher(self):
        """延迟获取Coinglass fetcher"""
        if self._fetcher is None and self.enabled:
            try:
                from coinglass_data_fetcher import get_coinglass_fetcher
                self._fetcher = get_coinglass_fetcher()
            except ImportError:
                logger.warning("coinglass_data_fetcher not available")
                self.enabled = False
            except Exception as e:
                logger.warning(f"Failed to initialize CoinglassFetcher: {e}")
                self.enabled = False
        return self._fetcher
    
    def fetch_symbol_data(
        self, 
        symbol: str, 
        current_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        获取指定币种的Coinglass数据
        
        Args:
            symbol: 币种符号
            current_price: 当前价格
            
        Returns:
            {
                'liquidation_summary': ...,
                'fear_greed': ...,
                'long_short_ratio': ...,
                'oi_history': ...,
                'funding_history': ...,
            }
        """
        result = {
            'liquidation_summary': None,
            'fear_greed': None,
            'long_short_ratio': None,
            'oi_history': None,
            'funding_history': None,
        }
        
        if not self.enabled:
            return result
        
        fetcher = self._get_fetcher()
        if fetcher is None or not fetcher.is_enabled():
            return result
        
        try:
            cg_metrics = fetcher.fetch_all_metrics(symbol, current_price)
            
            if cg_metrics:
                result['liquidation_summary'] = cg_metrics.liquidation_summary
                result['fear_greed'] = cg_metrics.fear_greed
                result['long_short_ratio'] = cg_metrics.long_short_ratio
                result['oi_history'] = cg_metrics.oi_history
                result['funding_history'] = cg_metrics.funding_rate_history
                
        except Exception as e:
            logger.warning(f"Failed to fetch Coinglass data for {symbol}: {e}")
        
        return result
    
    def get_market_sentiment(self) -> Dict[str, Any]:
        """
        获取市场整体情绪
        
        Returns:
            {
                'fear_greed': ...,
                'major_ls_bias': ...,
                'funding_sentiment': ...,
                'btc_liquidation_dominance': ...,
            }
        """
        if not self.enabled:
            return {}
        
        fetcher = self._get_fetcher()
        if fetcher is None or not fetcher.is_enabled():
            return {}
        
        try:
            from coinglass_data_fetcher import get_market_sentiment_summary
            return get_market_sentiment_summary(fetcher)
        except Exception as e:
            logger.warning(f"Failed to get market sentiment: {e}")
            return {}


def get_coinglass_bridge(config: Dict = None) -> CoinglassBridge:
    """
    获取CoinglassBridge单例
    
    Args:
        config: Coinglass配置（首次调用时使用）
        
    Returns:
        CoinglassBridge实例
    """
    return CoinglassBridge.get_instance(config)
