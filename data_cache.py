"""
L1 Advisory Layer - 市场数据缓存机制

负责：
1. 存储历史tick数据（最少6小时）
2. 计算1h、6h价格变化率
3. 计算1h、6h持仓量变化率
4. 计算1h成交量
5. 提供数据查询接口

使用内存缓存（简单dict），未来可扩展为Redis
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import threading

logger = logging.getLogger(__name__)


class TickData:
    """单个tick数据"""
    def __init__(self, timestamp: datetime, data: dict):
        self.timestamp = timestamp
        self.price = data.get('price', 0)
        self.volume = data.get('volume', 0)
        self.open_interest = data.get('open_interest', 0)
        self.funding_rate = data.get('funding_rate', 0)
        self.buy_volume = data.get('buy_volume', 0)
        self.sell_volume = data.get('sell_volume', 0)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'price': self.price,
            'volume': self.volume,
            'open_interest': self.open_interest,
            'funding_rate': self.funding_rate,
            'buy_volume': self.buy_volume,
            'sell_volume': self.sell_volume
        }


class MarketDataCache:
    """
    市场数据缓存
    
    使用内存deque存储，自动清理6小时以前的数据
    线程安全
    """
    
    def __init__(self, max_hours: int = 6):
        """
        初始化缓存
        
        Args:
            max_hours: 最大保留小时数（默认6小时）
        """
        self.max_hours = max_hours
        # 每个symbol一个deque
        self.cache: Dict[str, deque] = {}
        # 线程锁
        self.lock = threading.Lock()
        
        logger.info(f"MarketDataCache initialized (max_hours={max_hours})")
    
    def store_tick(self, symbol: str, data: dict, timestamp: datetime = None):
        """
        存储一个tick数据
        
        Args:
            symbol: 币种符号（如 "BTC"）
            data: tick数据字典
            timestamp: 时间戳（默认为当前时间）
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        tick = TickData(timestamp, data)
        
        with self.lock:
            # 如果symbol不存在，创建新的deque
            if symbol not in self.cache:
                self.cache[symbol] = deque()
            
            # 添加新数据
            self.cache[symbol].append(tick)
            
            # 清理旧数据
            self._cleanup_old_data(symbol)
            
            logger.debug(f"Stored tick for {symbol}: price={tick.price}, cache_size={len(self.cache[symbol])}")
    
    def _cleanup_old_data(self, symbol: str):
        """
        清理超过max_hours的旧数据
        
        Args:
            symbol: 币种符号
        """
        if symbol not in self.cache:
            return
        
        cutoff_time = datetime.now() - timedelta(hours=self.max_hours)
        
        # 从队列头部删除旧数据
        while self.cache[symbol] and self.cache[symbol][0].timestamp < cutoff_time:
            self.cache[symbol].popleft()
    
    def get_latest_tick(self, symbol: str) -> Optional[TickData]:
        """
        获取最新的tick数据
        
        Args:
            symbol: 币种符号
        
        Returns:
            TickData或None
        """
        with self.lock:
            if symbol not in self.cache or len(self.cache[symbol]) == 0:
                return None
            
            return self.cache[symbol][-1]
    
    def get_historical_ticks(self, symbol: str, hours: float) -> List[TickData]:
        """
        获取最近N小时的tick数据
        
        Args:
            symbol: 币种符号
            hours: 小时数
        
        Returns:
            TickData列表（按时间升序）
        """
        with self.lock:
            if symbol not in self.cache:
                return []
            
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            # 过滤符合时间范围的数据
            return [tick for tick in self.cache[symbol] if tick.timestamp >= cutoff_time]
    
    def _find_closest_tick(self, symbol: str, target_time: datetime) -> Optional[TickData]:
        """
        查找最接近目标时间的tick
        
        Args:
            symbol: 币种符号
            target_time: 目标时间
        
        Returns:
            最接近的TickData或None
        """
        if symbol not in self.cache or len(self.cache[symbol]) == 0:
            return None
        
        # 找到最接近target_time的tick
        closest_tick = None
        min_diff = None
        
        for tick in self.cache[symbol]:
            diff = abs((tick.timestamp - target_time).total_seconds())
            if min_diff is None or diff < min_diff:
                min_diff = diff
                closest_tick = tick
        
        return closest_tick
    
    def calculate_price_change(self, symbol: str, hours: float) -> Optional[float]:
        """
        计算价格变化率
        
        Args:
            symbol: 币种符号
            hours: 小时数（如1表示1小时，6表示6小时）
        
        Returns:
            变化率（百分比）或None
        """
        with self.lock:
            if symbol not in self.cache or len(self.cache[symbol]) < 2:
                return None
            
            current_tick = self.cache[symbol][-1]
            target_time = current_tick.timestamp - timedelta(hours=hours)
            
            past_tick = self._find_closest_tick(symbol, target_time)
            
            if past_tick is None or past_tick.price == 0:
                return None
            
            change_percent = ((current_tick.price - past_tick.price) / past_tick.price) * 100
            
            return change_percent
    
    def calculate_oi_change(self, symbol: str, hours: float) -> Optional[float]:
        """
        计算持仓量变化率
        
        Args:
            symbol: 币种符号
            hours: 小时数
        
        Returns:
            变化率（百分比）或None
        """
        with self.lock:
            if symbol not in self.cache or len(self.cache[symbol]) < 2:
                return None
            
            current_tick = self.cache[symbol][-1]
            target_time = current_tick.timestamp - timedelta(hours=hours)
            
            past_tick = self._find_closest_tick(symbol, target_time)
            
            if past_tick is None or past_tick.open_interest == 0:
                return None
            
            change_percent = ((current_tick.open_interest - past_tick.open_interest) / past_tick.open_interest) * 100
            
            return change_percent
    
    def calculate_volume_1h(self, symbol: str) -> Optional[float]:
        """
        计算1小时成交量（取最新累计量与1小时前累计量的差值）
        
        重要：Binance ticker['volume'] 是24h累计成交量，不是单tick量
        因此必须取差值，而不是累加
        
        Args:
            symbol: 币种符号
        
        Returns:
            1小时总成交量或None
        """
        with self.lock:
            if symbol not in self.cache or len(self.cache[symbol]) < 2:
                return None
            
            # 获取最新tick和1小时前的tick
            current_tick = self.cache[symbol][-1]
            target_time = current_tick.timestamp - timedelta(hours=1.0)
            past_tick = self._find_closest_tick(symbol, target_time)
            
            if past_tick is None:
                return None
            
            # P0-BugFix-2: volume是24h累计量，必须取差值
            # 不能累加，否则会高估几十倍
            volume_1h = current_tick.volume - past_tick.volume
            
            # 如果差值为负（可能是24h窗口滚动导致），返回None
            if volume_1h < 0:
                logger.warning(f"Negative volume_1h for {symbol}: {volume_1h}. "
                             f"Current: {current_tick.volume}, Past: {past_tick.volume}")
                return None
            
            return volume_1h
    
    def calculate_buy_sell_imbalance(self, symbol: str, hours: float = 1.0) -> Optional[float]:
        """
        计算买卖失衡度
        
        Args:
            symbol: 币种符号
            hours: 统计时间范围（默认1小时）
        
        Returns:
            失衡度（-1到1之间）或None
            正值表示买方强势，负值表示卖方强势
        """
        ticks = self.get_historical_ticks(symbol, hours=hours)
        
        if len(ticks) == 0:
            return None
        
        total_buy = sum(tick.buy_volume for tick in ticks)
        total_sell = sum(tick.sell_volume for tick in ticks)
        
        total = total_buy + total_sell
        
        if total == 0:
            return 0.0
        
        # 失衡度 = (买量 - 卖量) / 总量
        imbalance = (total_buy - total_sell) / total
        
        # 限制在[-1, 1]范围内
        imbalance = max(-1.0, min(1.0, imbalance))
        
        return imbalance
    
    def get_enhanced_market_data(self, symbol: str, current_data: dict) -> dict:
        """
        基于当前数据和历史缓存，生成增强的市场数据（包含所有L1需要的字段）
        
        Args:
            symbol: 币种符号
            current_data: 当前tick数据（来自Binance API）
        
        Returns:
            增强的市场数据字典（包含price_change_1h等计算字段）
        """
        # 先存储当前数据
        self.store_tick(symbol, current_data)
        
        # 计算变化率
        price_change_1h = self.calculate_price_change(symbol, hours=1.0)
        price_change_6h = self.calculate_price_change(symbol, hours=6.0)
        oi_change_1h = self.calculate_oi_change(symbol, hours=1.0)
        oi_change_6h = self.calculate_oi_change(symbol, hours=6.0)
        volume_1h = self.calculate_volume_1h(symbol)
        buy_sell_imbalance = self.calculate_buy_sell_imbalance(symbol, hours=1.0)
        
        # 获取源时间戳（来自最新tick）
        source_timestamp = None
        with self.lock:
            if symbol in self.cache and len(self.cache[symbol]) > 0:
                source_timestamp = self.cache[symbol][-1].timestamp
        
        # 构造增强数据
        enhanced_data = {
            'price': current_data.get('price', 0),
            'price_change_1h': price_change_1h if price_change_1h is not None else 0.0,
            'price_change_6h': price_change_6h if price_change_6h is not None else 0.0,
            'volume_1h': volume_1h if volume_1h is not None else 0.0,
            'volume_24h': current_data.get('volume_24h', 0),
            'buy_sell_imbalance': buy_sell_imbalance if buy_sell_imbalance is not None else 0.0,
            'funding_rate': current_data.get('funding_rate', 0),
            'oi_change_1h': oi_change_1h if oi_change_1h is not None else 0.0,
            'oi_change_6h': oi_change_6h if oi_change_6h is not None else 0.0,
            # PR-002: 添加时间戳信息（用于新鲜度检查）
            'source_timestamp': source_timestamp,
            'computed_at': datetime.now()
        }
        
        logger.info(f"Enhanced data for {symbol}: "
                   f"price_change_1h={enhanced_data['price_change_1h']:.2f}%, "
                   f"imbalance={enhanced_data['buy_sell_imbalance']:.2f}")
        
        return enhanced_data
    
    def get_cache_info(self, symbol: str) -> dict:
        """
        获取缓存信息（用于调试）
        
        Args:
            symbol: 币种符号
        
        Returns:
            缓存信息字典
        """
        with self.lock:
            if symbol not in self.cache:
                return {'symbol': symbol, 'size': 0, 'oldest': None, 'newest': None}
            
            size = len(self.cache[symbol])
            oldest = self.cache[symbol][0].timestamp if size > 0 else None
            newest = self.cache[symbol][-1].timestamp if size > 0 else None
            
            return {
                'symbol': symbol,
                'size': size,
                'oldest': oldest.isoformat() if oldest else None,
                'newest': newest.isoformat() if newest else None,
                'hours_span': (newest - oldest).total_seconds() / 3600 if (oldest and newest) else 0
            }
    
    def clear_cache(self, symbol: str = None):
        """
        清空缓存
        
        Args:
            symbol: 币种符号（None表示清空所有）
        """
        with self.lock:
            if symbol is None:
                self.cache.clear()
                logger.info("All cache cleared")
            elif symbol in self.cache:
                del self.cache[symbol]
                logger.info(f"Cache cleared for {symbol}")


# 全局缓存实例（单例模式）
_global_cache = None

def get_cache() -> MarketDataCache:
    """
    获取全局缓存实例
    
    Returns:
        MarketDataCache实例
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = MarketDataCache(max_hours=6)
    return _global_cache


# 测试代码
if __name__ == '__main__':
    import time
    
    logging.basicConfig(level=logging.INFO)
    
    cache = MarketDataCache(max_hours=6)
    
    # 模拟存储一些tick数据
    print("=" * 60)
    print("Testing MarketDataCache")
    print("=" * 60)
    
    base_time = datetime.now() - timedelta(hours=2)
    
    # 存储2小时的模拟数据（每分钟一个tick）
    for i in range(120):
        timestamp = base_time + timedelta(minutes=i)
        data = {
            'price': 50000 + i * 10,  # 价格逐渐上涨
            'volume': 1000 + i,
            'open_interest': 100000 + i * 100,
            'funding_rate': 0.0001,
            'buy_volume': 600 + i,
            'sell_volume': 400
        }
        cache.store_tick('BTC', data, timestamp)
    
    print(f"\n缓存信息: {cache.get_cache_info('BTC')}")
    
    # 计算变化率
    print(f"\n1h价格变化: {cache.calculate_price_change('BTC', 1.0):.2f}%")
    print(f"2h价格变化: {cache.calculate_price_change('BTC', 2.0):.2f}%")
    print(f"1h持仓量变化: {cache.calculate_oi_change('BTC', 1.0):.2f}%")
    print(f"买卖失衡度: {cache.calculate_buy_sell_imbalance('BTC', 1.0):.2f}")
    
    # 测试增强数据
    print("\n测试增强数据生成：")
    current_data = {
        'price': 51500,
        'volume': 2000,
        'volume_24h': 50000,
        'open_interest': 112000,
        'funding_rate': 0.0002,
        'buy_volume': 1200,
        'sell_volume': 800
    }
    
    enhanced = cache.get_enhanced_market_data('BTC', current_data)
    print(f"增强数据: {enhanced}")
    
    print("\n测试完成！")
