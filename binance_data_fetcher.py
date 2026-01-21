"""
Binance数据获取器 - 为L1提供真实市场数据

职责：
1. 调用Binance API获取实时市场数据
2. 提取L1所需的关键字段
3. 与MarketDataCache集成，计算历史变化率
4. 处理异常和错误
"""

from binance.client import Client
from data_cache import get_cache
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BinanceDataFetcher:
    """
    Binance数据获取器
    
    负责从Binance API获取数据并格式化为L1所需格式
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None):
        """
        初始化Binance客户端
        
        Args:
            api_key: API Key（可选，公开数据不需要）
            api_secret: API Secret（可选）
        """
        if api_key and api_secret:
            self.client = Client(api_key, api_secret)
        else:
            # 公开数据不需要API密钥
            self.client = Client("", "")
        
        # 获取全局缓存实例
        self.cache = get_cache()
        
        logger.info("BinanceDataFetcher initialized")
    
    def fetch_futures_data(self, symbol: str) -> Optional[dict]:
        """
        获取合约市场数据
        
        Args:
            symbol: 币种符号（如 "BTC"，会自动转换为 "BTCUSDT"）
        
        Returns:
            市场数据字典或None
        """
        trading_symbol = f"{symbol}USDT"
        
        try:
            # 1. 获取24h ticker
            ticker = self.client.futures_ticker(symbol=trading_symbol)
            
            # 2. 获取资金费率
            funding_rate_info = self.client.futures_funding_rate(symbol=trading_symbol, limit=1)
            funding_rate = float(funding_rate_info[0]['fundingRate']) if funding_rate_info else 0.0
            
            # 3. 获取持仓量
            oi_info = self.client.futures_open_interest(symbol=trading_symbol)
            open_interest = float(oi_info['openInterest']) if oi_info else 0.0
            
            # 4. 获取最近成交（用于计算买卖失衡）
            recent_trades = self.client.futures_recent_trades(symbol=trading_symbol, limit=500)
            
            # 计算买卖量
            buy_volume = sum(float(t['qty']) for t in recent_trades if t['isBuyerMaker'] == False)
            sell_volume = sum(float(t['qty']) for t in recent_trades if t['isBuyerMaker'] == True)
            
            # 提取基础数据
            current_data = {
                'price': float(ticker['lastPrice']),
                'volume': float(ticker['volume']),
                # P0-BugFix-3: 统一单位为基础币数量（BTC）
                # volume_1h 来自 volume 差值（BTC数量）
                # volume_24h 也必须使用 volume（BTC数量），而非 quoteVolume（USDT金额）
                # 否则单位不一致，volume_1h vs volume_24h 的比较完全失效
                'volume_24h': float(ticker['volume']),  # 24h成交量（BTC数量）
                'open_interest': open_interest,
                'funding_rate': funding_rate,
                'buy_volume': buy_volume,
                'sell_volume': sell_volume
            }
            
            logger.info(f"Fetched futures data for {symbol}: price={current_data['price']:.2f}, "
                       f"funding_rate={funding_rate:.6f}, OI={open_interest:.0f}")
            
            # 5. 使用缓存计算历史变化率
            enhanced_data = self.cache.get_enhanced_market_data(symbol, current_data)
            
            return enhanced_data
        
        except Exception as e:
            logger.error(f"Error fetching futures data for {symbol}: {e}", exc_info=True)
            return None
    
    def fetch_spot_data(self, symbol: str) -> Optional[dict]:
        """
        获取现货市场数据
        
        Args:
            symbol: 币种符号（如 "BTC"）
        
        Returns:
            市场数据字典或None
        """
        trading_symbol = f"{symbol}USDT"
        
        try:
            # 1. 获取24h ticker
            ticker = self.client.get_ticker(symbol=trading_symbol)
            
            # 2. 获取最近成交（用于计算买卖失衡）
            recent_trades = self.client.get_recent_trades(symbol=trading_symbol, limit=500)
            
            # 计算买卖量
            buy_volume = sum(float(t['qty']) for t in recent_trades if t['isBuyerMaker'] == False)
            sell_volume = sum(float(t['qty']) for t in recent_trades if t['isBuyerMaker'] == True)
            
            # 提取基础数据
            current_data = {
                'price': float(ticker['lastPrice']),
                'volume': float(ticker['volume']),
                # P0-BugFix-3: 统一单位为基础币数量
                'volume_24h': float(ticker['volume']),  # 24h成交量（基础币数量）
                'open_interest': 0.0,  # 现货无持仓量
                'funding_rate': 0.0,   # 现货无资金费率
                'buy_volume': buy_volume,
                'sell_volume': sell_volume
            }
            
            logger.info(f"Fetched spot data for {symbol}: price={current_data['price']:.2f}")
            
            # 使用缓存计算历史变化率
            enhanced_data = self.cache.get_enhanced_market_data(symbol, current_data)
            
            return enhanced_data
        
        except Exception as e:
            logger.error(f"Error fetching spot data for {symbol}: {e}", exc_info=True)
            return None
    
    def fetch_market_data(self, symbol: str, market_type: str = 'futures') -> Optional[dict]:
        """
        获取市场数据（统一接口）
        
        Args:
            symbol: 币种符号（如 "BTC"）
            market_type: 市场类型（'futures' 或 'spot'）
        
        Returns:
            增强的市场数据字典或None
        """
        if market_type == 'futures':
            return self.fetch_futures_data(symbol)
        elif market_type == 'spot':
            return self.fetch_spot_data(symbol)
        else:
            logger.error(f"Unknown market type: {market_type}")
            return None
    
    def get_cache_info(self, symbol: str) -> dict:
        """
        获取缓存信息（用于调试）
        
        Args:
            symbol: 币种符号
        
        Returns:
            缓存信息字典
        """
        return self.cache.get_cache_info(symbol)


# 全局fetcher实例（单例模式）
_global_fetcher = None

def get_fetcher() -> BinanceDataFetcher:
    """
    获取全局fetcher实例
    
    Returns:
        BinanceDataFetcher实例
    """
    global _global_fetcher
    if _global_fetcher is None:
        _global_fetcher = BinanceDataFetcher()
    return _global_fetcher


# 测试代码
if __name__ == '__main__':
    import time
    
    logging.basicConfig(level=logging.INFO)
    
    fetcher = BinanceDataFetcher()
    
    print("=" * 60)
    print("Testing BinanceDataFetcher")
    print("=" * 60)
    
    # 测试获取合约数据
    print("\n测试1: 获取BTC合约数据")
    data = fetcher.fetch_futures_data('BTC')
    if data:
        print(f"价格: {data['price']:.2f}")
        print(f"1h价格变化: {data['price_change_1h']:.2f}%")
        print(f"6h价格变化: {data['price_change_6h']:.2f}%")
        print(f"买卖失衡: {data['buy_sell_imbalance']:.2f}")
        print(f"资金费率: {data['funding_rate']:.6f}")
    
    # 等待一段时间，再获取一次（测试缓存）
    print("\n等待10秒后再次获取...")
    time.sleep(10)
    
    print("\n测试2: 再次获取BTC合约数据（应该能计算变化率）")
    data2 = fetcher.fetch_futures_data('BTC')
    if data2:
        print(f"价格: {data2['price']:.2f}")
        print(f"1h价格变化: {data2['price_change_1h']:.2f}%")
        print(f"6h价格变化: {data2['price_change_6h']:.2f}%")
        print(f"买卖失衡: {data2['buy_sell_imbalance']:.2f}")
    
    # 缓存信息
    print(f"\n缓存信息: {fetcher.get_cache_info('BTC')}")
    
    print("\n测试完成！")
