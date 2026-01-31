"""
MarketDataFetcher - 统一市场数据获取入口

职责：
1. 组合 BinanceDataFetcher 和 CoinglassBridge
2. 提供统一的 fetch_market_data 方法
3. 返回符合 FeatureBuilder 输入规范的数据（带 _metadata）

P0修复：解决模块引用断裂问题
"""

import logging
from typing import Dict, Optional

from binance_data_fetcher import BinanceDataFetcher
from l1_engine.coinglass_bridge import CoinglassBridge

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """
    统一市场数据获取器
    
    组合多个数据源，提供标准化输出
    """
    
    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        coinglass_api_key: str = None,
        enable_coinglass: bool = True
    ):
        """
        初始化数据获取器
        
        Args:
            api_key: Binance API Key（可选）
            api_secret: Binance API Secret（可选）
            coinglass_api_key: Coinglass API Key（可选）
            enable_coinglass: 是否启用Coinglass数据
        """
        # 初始化Binance数据源
        self.binance_fetcher = BinanceDataFetcher(api_key, api_secret)
        
        # 初始化Coinglass数据源（可选）
        self.coinglass_bridge = None
        if enable_coinglass and coinglass_api_key:
            try:
                self.coinglass_bridge = CoinglassBridge(coinglass_api_key)
                logger.info("MarketDataFetcher: Coinglass enabled")
            except Exception as e:
                logger.warning(f"MarketDataFetcher: Coinglass init failed: {e}")
        
        logger.info("MarketDataFetcher initialized")
    
    def fetch_market_data(self, symbol: str) -> Optional[Dict]:
        """
        获取市场数据（统一入口）
        
        Args:
            symbol: 币种符号（如 'BTC' 或 'BTCUSDT'）
        
        Returns:
            市场数据字典，包含：
            - price, volume_24h, funding_rate, open_interest
            - price_change_*, oi_change_*, volume_ratio_*
            - taker_imbalance_*, cvd_*, atr_*
            - _metadata: 元数据
            
            如果获取失败返回 None
        """
        try:
            # 从Binance获取基础数据
            data = self.binance_fetcher.fetch_futures_data(symbol)
            
            if data is None:
                logger.warning(f"MarketDataFetcher: No data for {symbol}")
                return None
            
            # 确保有 _metadata
            if '_metadata' not in data:
                data['_metadata'] = {
                    'percentage_format': 'percent_point',
                    'source': 'market_data_fetcher',
                    'version': '1.0'
                }
            
            return data
            
        except Exception as e:
            logger.error(f"MarketDataFetcher.fetch_market_data failed for {symbol}: {e}")
            return None
    
    def fetch_coinglass_data(self, symbol: str) -> Optional[Dict]:
        """
        获取Coinglass数据（可选）
        
        Args:
            symbol: 币种符号
        
        Returns:
            Coinglass数据字典或None
        """
        if self.coinglass_bridge is None:
            return None
        
        try:
            return self.coinglass_bridge.get_all_data(symbol)
        except Exception as e:
            logger.warning(f"MarketDataFetcher: Coinglass fetch failed for {symbol}: {e}")
            return None
    
    def fetch_all(self, symbol: str) -> Dict:
        """
        获取所有数据（Binance + Coinglass）
        
        Args:
            symbol: 币种符号
        
        Returns:
            {
                'market_data': Binance数据,
                'coinglass_data': Coinglass数据（可能为None）
            }
        """
        return {
            'market_data': self.fetch_market_data(symbol),
            'coinglass_data': self.fetch_coinglass_data(symbol)
        }


# 便捷函数：创建默认实例
def create_default_fetcher() -> MarketDataFetcher:
    """创建默认配置的数据获取器"""
    import os
    return MarketDataFetcher(
        api_key=os.getenv('BINANCE_API_KEY'),
        api_secret=os.getenv('BINANCE_API_SECRET'),
        coinglass_api_key=os.getenv('COINGLASS_API_KEY'),
        enable_coinglass=bool(os.getenv('COINGLASS_API_KEY'))
    )
