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
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class BinanceDataFetcher:
    """
    Binance数据获取器
    
    负责从Binance API获取数据并格式化为L1所需格式
    """
    
    def __init__(self, api_key: str = None, api_secret: str = None, test_connection: bool = False):
        """
        初始化Binance客户端
        
        Args:
            api_key: API Key（可选，公开数据不需要）
            api_secret: API Secret（可选）
            test_connection: 是否在初始化时测试连接（默认False，延迟到实际使用）
        """
        if api_key and api_secret:
            self.client = Client(api_key, api_secret)
        else:
            # 公开数据不需要API密钥
            self.client = Client("", "")
        
        # 获取全局缓存实例
        self.cache = get_cache()
        
        # 可选：测试连接
        if test_connection:
            try:
                self.client.ping()
                logger.info("BinanceDataFetcher initialized (connection tested)")
            except Exception as e:
                logger.warning(f"BinanceDataFetcher initialized (connection test failed: {e})")
        else:
            logger.info("BinanceDataFetcher initialized (connection will be tested on first use)")
    
    def fetch_futures_data(self, symbol: str) -> Optional[dict]:
        """
        获取合约市场数据（PR-001重构：使用klines）
        
        Args:
            symbol: 币种符号
                - 基础币种格式：如 "BTC" → 自动转换为 "BTCUSDT"
                - 完整交易对格式：如 "BTCUSDT" → 直接使用
        
        Returns:
            市场数据字典或None
        """
        # 智能识别：避免重复拼接 USDT
        if symbol.endswith('USDT'):
            trading_symbol = symbol  # 已经是完整交易对，直接使用
            cache_symbol = symbol.replace('USDT', '')  # 缓存使用不带后缀的符号
        else:
            trading_symbol = f"{symbol}USDT"  # 基础币种，拼接 USDT
            cache_symbol = symbol  # 缓存使用原符号
        
        try:
            # 1. 获取24h ticker
            ticker = self.client.futures_ticker(symbol=trading_symbol)
            
            # 2. 获取资金费率
            funding_rate_info = self.client.futures_funding_rate(symbol=trading_symbol, limit=1)
            funding_rate = float(funding_rate_info[0]['fundingRate']) if funding_rate_info else 0.0
            
            # 3. 获取持仓量
            oi_info = self.client.futures_open_interest(symbol=trading_symbol)
            open_interest = float(oi_info['openInterest']) if oi_info else 0.0
            
            # 4. PR-001: 获取1分钟K线数据（用于精确计算volume和买卖失衡）
            klines = self.client.futures_klines(
                symbol=trading_symbol,
                interval='1m',
                limit=60  # 获取最近60根1分钟K线（覆盖1小时）
            )
            
            # PR-001: 从klines计算多周期volume和买卖失衡
            volume_data = self._calculate_volume_from_klines(klines)
            imbalance_data = self._calculate_imbalance_from_klines(klines)  # PR-002
            
            # 提取基础数据（PR-001重构）
            current_data = {
                'price': float(ticker['lastPrice']),
                'volume_24h': float(ticker['volume']),  # 24h累计成交量（基础币数量）
                'open_interest': open_interest,
                'funding_rate': funding_rate,
                # PR-001: 多周期volume数据（从klines精确计算）
                'volume_5m': volume_data.get('volume_5m'),
                'volume_15m': volume_data.get('volume_15m'),
                'volume_1h': volume_data.get('volume_1h'),
                'volume_ratio_5m': volume_data.get('volume_ratio_5m'),
                'volume_ratio_15m': volume_data.get('volume_ratio_15m'),
                'volume_ratio_1h': volume_data.get('volume_ratio_1h'),
                # PR-002: 多周期taker买卖失衡（从klines精确计算）
                'taker_imbalance_5m': imbalance_data.get('taker_imbalance_5m'),
                'taker_imbalance_15m': imbalance_data.get('taker_imbalance_15m'),
                'taker_imbalance_1h': imbalance_data.get('taker_imbalance_1h'),
            }
            
            # PR-003: 检查数据完整性
            data_complete = all([
                current_data.get('volume_5m') is not None,
                current_data.get('volume_1h') is not None,
                current_data.get('taker_imbalance_5m') is not None
            ])
            
            if data_complete:
                logger.info(f"Fetched futures data for {symbol}: price={current_data['price']:.2f}, "
                           f"volume_1h={current_data.get('volume_1h', 0):.2f}, "
                           f"funding_rate={funding_rate:.6f}, OI={open_interest:.0f}")
            else:
                logger.warning(f"Incomplete klines data for {symbol}, some fields may be None")
            
            # 5. 使用缓存计算历史变化率（使用不带USDT后缀的符号名）
            enhanced_data = self.cache.get_enhanced_market_data(cache_symbol, current_data)
            
            # PR-003: 标注数据完整性
            enhanced_data['_data_complete'] = data_complete
            
            return enhanced_data
        
        except Exception as e:
            logger.error(f"Error fetching futures data for {symbol}: {e}", exc_info=True)
            return None
    
    def _calculate_volume_from_klines(self, klines: list) -> dict:
        """
        PR-001: 从1分钟K线精确计算多周期volume和volume_ratio
        
        Args:
            klines: 1分钟K线数据列表（最近60根）
                每根K线格式：[时间, 开, 高, 低, 收, 成交量, ...]
                索引5: volume（基础币数量）
        
        Returns:
            dict: {
                'volume_5m': 5分钟成交量,
                'volume_15m': 15分钟成交量,
                'volume_1h': 1小时成交量,
                'volume_ratio_5m': 5分钟成交量比率,
                'volume_ratio_15m': 15分钟成交量比率,
                'volume_ratio_1h': 1小时成交量比率
            }
        """
        if not klines or len(klines) < 5:
            logger.warning("Insufficient klines data for volume calculation")
            return {
                'volume_5m': None, 'volume_15m': None, 'volume_1h': None,
                'volume_ratio_5m': None, 'volume_ratio_15m': None, 'volume_ratio_1h': None
            }
        
        try:
            # 计算多周期volume（聚合1分钟K线）
            volume_5m = sum(float(k[5]) for k in klines[-5:]) if len(klines) >= 5 else None
            volume_15m = sum(float(k[5]) for k in klines[-15:]) if len(klines) >= 15 else None
            volume_1h = sum(float(k[5]) for k in klines[-60:]) if len(klines) >= 60 else None
            
            # 计算历史平均volume（用于ratio计算）
            # 使用前60根K线的平均，作为1h的历史基准
            eps = 1e-6  # 防止除零
            
            # 如果有足够的历史数据，使用前60根的均值作为基准
            # 否则用当前1h作为基准（启动初期）
            if len(klines) >= 120:
                # 有2小时数据：用第1-60根作为历史均值
                historical_1h = sum(float(k[5]) for k in klines[0:60])
                avg_volume_per_min = historical_1h / 60
            elif volume_1h and volume_1h > 0:
                # 只有1小时数据：用当前1h的均值
                avg_volume_per_min = volume_1h / 60
            else:
                avg_volume_per_min = None
            
            # 计算各周期的volume ratio
            if avg_volume_per_min and avg_volume_per_min > 0:
                expected_5m = avg_volume_per_min * 5
                expected_15m = avg_volume_per_min * 15
                expected_1h = avg_volume_per_min * 60
                
                volume_ratio_5m = volume_5m / max(expected_5m, eps) if volume_5m else None
                volume_ratio_15m = volume_15m / max(expected_15m, eps) if volume_15m else None
                volume_ratio_1h = volume_1h / max(expected_1h, eps) if volume_1h else None
            else:
                volume_ratio_5m = None
                volume_ratio_15m = None
                volume_ratio_1h = None
            
            return {
                'volume_5m': volume_5m,
                'volume_15m': volume_15m,
                'volume_1h': volume_1h,
                'volume_ratio_5m': volume_ratio_5m,
                'volume_ratio_15m': volume_ratio_15m,
                'volume_ratio_1h': volume_ratio_1h
            }
        
        except Exception as e:
            logger.error(f"Error calculating volume from klines: {e}")
            return {
                'volume_5m': None, 'volume_15m': None, 'volume_1h': None,
                'volume_ratio_5m': None, 'volume_ratio_15m': None, 'volume_ratio_1h': None
            }
    
    def _calculate_imbalance_from_klines(self, klines: list) -> dict:
        """
        PR-002: 从1分钟K线精确计算多周期taker买卖失衡
        
        Args:
            klines: 1分钟K线数据列表
                索引5: volume（总成交量）
                索引9: takerBuyBaseAssetVolume（主动买入量）
        
        Returns:
            dict: {
                'taker_imbalance_5m': 5分钟taker失衡度,
                'taker_imbalance_15m': 15分钟taker失衡度,
                'taker_imbalance_1h': 1小时taker失衡度
            }
        """
        if not klines or len(klines) < 5:
            logger.warning("Insufficient klines data for imbalance calculation")
            return {
                'taker_imbalance_5m': None,
                'taker_imbalance_15m': None,
                'taker_imbalance_1h': None
            }
        
        try:
            eps = 1e-6
            
            # 计算多周期taker imbalance
            def calc_imbalance(window_klines):
                if not window_klines:
                    return None
                taker_buy = sum(float(k[9]) for k in window_klines)  # takerBuyBaseAssetVolume
                total = sum(float(k[5]) for k in window_klines)      # volume
                if total < eps:
                    return 0.0
                # taker_imbalance = (2*taker_buy - total) / total
                # 范围 [-1, 1]: -1=全是主动卖, 0=平衡, 1=全是主动买
                return (2 * taker_buy - total) / max(total, eps)
            
            taker_imbalance_5m = calc_imbalance(klines[-5:]) if len(klines) >= 5 else None
            taker_imbalance_15m = calc_imbalance(klines[-15:]) if len(klines) >= 15 else None
            taker_imbalance_1h = calc_imbalance(klines[-60:]) if len(klines) >= 60 else None
            
            return {
                'taker_imbalance_5m': taker_imbalance_5m,
                'taker_imbalance_15m': taker_imbalance_15m,
                'taker_imbalance_1h': taker_imbalance_1h
            }
        
        except Exception as e:
            logger.error(f"Error calculating imbalance from klines: {e}")
            return {
                'taker_imbalance_5m': None,
                'taker_imbalance_15m': None,
                'taker_imbalance_1h': None
            }
    
    def fetch_spot_data(self, symbol: str) -> Optional[dict]:
        """
        获取现货市场数据
        
        Args:
            symbol: 币种符号
                - 基础币种格式：如 "BTC" → 自动转换为 "BTCUSDT"
                - 完整交易对格式：如 "BTCUSDT" → 直接使用
        
        Returns:
            市场数据字典或None
        """
        # 智能识别：避免重复拼接 USDT
        if symbol.endswith('USDT'):
            trading_symbol = symbol  # 已经是完整交易对，直接使用
        else:
            trading_symbol = f"{symbol}USDT"  # 基础币种，拼接 USDT
        
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
    
    def warmup_cache(self, symbols: list, hours: int = 6) -> dict:
        """
        预热缓存：从Binance获取历史K线数据填充缓存
        
        Args:
            symbols: 币种符号列表（如 ['BTC', 'ETH']）
            hours: 预热的历史数据时长（默认6小时）
        
        Returns:
            dict: 预热结果 {symbol: {'success': bool, 'ticks': int, 'error': str}}
        """
        from datetime import datetime, timedelta
        
        results = {}
        logger.info(f"🔥 Starting cache warmup for {len(symbols)} symbols, {hours} hours each...")
        
        for symbol in symbols:
            try:
                # 统一使用不带USDT后缀的符号名
                cache_symbol = symbol.replace('USDT', '') if symbol.endswith('USDT') else symbol
                trading_symbol = f"{cache_symbol}USDT"
                
                # 获取历史K线数据（1分钟K线）
                # 6小时 = 360根K线，用limit参数获取
                limit = hours * 60
                
                klines = self.client.futures_klines(
                    symbol=trading_symbol,
                    interval='1m',
                    limit=min(limit, 1500)  # Binance最大限制1500
                )
                
                if not klines:
                    results[cache_symbol] = {'success': False, 'ticks': 0, 'error': 'No klines returned'}
                    continue
                
                # 同时获取当前OI和资金费率（用于填充tick数据）
                try:
                    oi_info = self.client.futures_open_interest(symbol=trading_symbol)
                    current_oi = float(oi_info['openInterest']) if oi_info else 0.0
                    
                    funding_info = self.client.futures_funding_rate(symbol=trading_symbol, limit=1)
                    current_funding = float(funding_info[0]['fundingRate']) if funding_info else 0.0
                except:
                    current_oi = 0.0
                    current_funding = 0.0
                
                # 将K线数据转换为tick并存入缓存
                ticks_stored = 0
                for kline in klines:
                    # K线格式: [open_time, open, high, low, close, volume, close_time, ...]
                    timestamp = datetime.fromtimestamp(kline[0] / 1000)  # 转换毫秒时间戳
                    close_price = float(kline[4])
                    volume = float(kline[5])
                    
                    tick_data = {
                        'price': close_price,
                        'volume_24h': volume,  # 这里用K线volume作为近似
                        'open_interest': current_oi,  # 用当前OI（近似）
                        'funding_rate': current_funding
                    }
                    
                    self.cache.store_tick(cache_symbol, tick_data, timestamp)
                    ticks_stored += 1
                
                results[cache_symbol] = {'success': True, 'ticks': ticks_stored, 'error': None}
                logger.info(f"✅ Warmup completed for {cache_symbol}: {ticks_stored} ticks stored")
                
            except Exception as e:
                results[cache_symbol] = {'success': False, 'ticks': 0, 'error': str(e)}
                logger.error(f"❌ Warmup failed for {symbol}: {e}")
        
        # 汇总结果
        success_count = sum(1 for r in results.values() if r['success'])
        total_ticks = sum(r['ticks'] for r in results.values())
        logger.info(f"🔥 Cache warmup completed: {success_count}/{len(symbols)} symbols, {total_ticks} total ticks")
        
        return results


# 全局fetcher实例（单例模式，线程安全）
_global_fetcher = None
_fetcher_lock = threading.Lock()

def get_fetcher() -> BinanceDataFetcher:
    """
    获取全局fetcher实例（线程安全）
    
    Returns:
        BinanceDataFetcher实例
    """
    global _global_fetcher
    if _global_fetcher is None:
        with _fetcher_lock:
            # 双重检查锁定模式（Double-Checked Locking）
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
