"""
L1 Advisory Layer - 市场数据缓存机制（PATCH-2增强版）

负责：
1. 存储历史tick数据（最少6小时）
2. 计算1h、6h价格变化率
3. 计算1h、6h持仓量变化率
4. 计算1h成交量
5. 提供数据查询接口

PATCH-2 改进：
- ✅ Floor查找：只允许 timestamp <= target_time（禁止未来点）
- ✅ Gap guardrail：定义容忍阈值，超过则返回 None
- ✅ Coverage输出：记录实际查到的点、gap秒数、缺失窗口

使用内存缓存（简单dict），未来可扩展为Redis
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, field
import threading

logger = logging.getLogger(__name__)


@dataclass
class LookbackResult:
    """Lookback查询结果（PATCH-2）"""
    tick: Optional['TickData']              # 查到的tick（None表示未找到）
    target_time: datetime                   # 目标时间
    actual_time: Optional[datetime]         # 实际查到的时间
    gap_seconds: Optional[float]            # gap秒数（实际时间与目标时间的差）
    is_valid: bool                          # 是否在容忍范围内
    error_reason: Optional[str] = None      # 失败原因
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'target_time': self.target_time.isoformat() if self.target_time else None,
            'actual_time': self.actual_time.isoformat() if self.actual_time else None,
            'gap_seconds': self.gap_seconds,
            'is_valid': self.is_valid,
            'error_reason': self.error_reason
        }


class TickData:
    """
    单个tick数据
    
    PATCH-P0-1改进：
    - volume优先读取volume_24h（权威来源），兼容旧volume键
    - buy_volume/sell_volume标记为已废弃（fetcher不再提供）
    """
    def __init__(self, timestamp: datetime, data: dict):
        self.timestamp = timestamp
        self.price = data.get('price', 0)
        
        # PATCH-P0-1: volume优先读取volume_24h，兼容旧volume键
        self.volume = data.get('volume_24h') or data.get('volume', 0)
        
        # PATCH-P0-1: 如果两个键都缺失，记录警告（显性化缺失）
        if self.volume == 0 and 'volume_24h' not in data and 'volume' not in data:
            logger.debug(f"Volume data missing at {timestamp}")
            self._incomplete = True
        else:
            self._incomplete = False
        
        self.open_interest = data.get('open_interest', 0)
        self.funding_rate = data.get('funding_rate', 0)
        
        # PATCH-P0-1: buy_volume/sell_volume已废弃（fetcher不再提供）
        # 保留字段仅用于向后兼容，但标记为不可信
        self.buy_volume = data.get('buy_volume', 0)  # ⚠️ DEPRECATED
        self.sell_volume = data.get('sell_volume', 0)  # ⚠️ DEPRECATED
        
        if self.buy_volume > 0 or self.sell_volume > 0:
            logger.warning(f"buy_volume/sell_volume are deprecated and should not be used (at {timestamp})")
    
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
    市场数据缓存（PATCH-2增强版）
    
    使用内存deque存储，自动清理6小时以前的数据
    线程安全
    """
    
    # PATCH-2: Gap容忍阈值配置（秒）
    GAP_TOLERANCE = {
        '5m': 90,      # 5分钟窗口：容忍90秒（1.5分钟）
        '15m': 300,    # 15分钟窗口：容忍5分钟
        '1h': 600,     # 1小时窗口：容忍10分钟
        '6h': 1800,    # 6小时窗口：容忍30分钟
    }
    
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
        
        logger.info(f"MarketDataCache initialized (max_hours={max_hours}, PATCH-2 enabled)")
    
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
    
    def _find_floor_tick(self, symbol: str, target_time: datetime, tolerance_seconds: float) -> LookbackResult:
        """
        查找 floor tick（PATCH-2核心改进）
        
        规则：
        1. 只允许 tick.timestamp <= target_time（禁止未来点）
        2. 选择最接近 target_time 的历史点
        3. 如果 gap > tolerance，返回 None 并记录原因
        
        Args:
            symbol: 币种符号
            target_time: 目标时间
            tolerance_seconds: gap容忍阈值（秒）
        
        Returns:
            LookbackResult
        """
        if symbol not in self.cache or len(self.cache[symbol]) == 0:
            return LookbackResult(
                tick=None,
                target_time=target_time,
                actual_time=None,
                gap_seconds=None,
                is_valid=False,
                error_reason='NO_DATA'
            )
        
        # 找到 timestamp <= target_time 的最近点（floor）
        floor_tick = None
        min_gap = None
        
        for tick in self.cache[symbol]:
            if tick.timestamp <= target_time:  # ✅ PATCH-2: 只允许历史点
                gap = (target_time - tick.timestamp).total_seconds()
                if min_gap is None or gap < min_gap:
                    min_gap = gap
                    floor_tick = tick
        
        # 未找到任何历史点
        if floor_tick is None:
            return LookbackResult(
                tick=None,
                target_time=target_time,
                actual_time=None,
                gap_seconds=None,
                is_valid=False,
                error_reason='NO_HISTORICAL_DATA'
            )
        
        # 检查 gap 是否在容忍范围内
        gap_seconds = (target_time - floor_tick.timestamp).total_seconds()
        is_valid = gap_seconds <= tolerance_seconds
        
        if not is_valid:
            return LookbackResult(
                tick=None,  # gap超出范围，不返回tick
                target_time=target_time,
                actual_time=floor_tick.timestamp,
                gap_seconds=gap_seconds,
                is_valid=False,
                error_reason=f'GAP_TOO_LARGE (gap={gap_seconds:.0f}s > tolerance={tolerance_seconds}s)'
            )
        
        # 成功
        return LookbackResult(
            tick=floor_tick,
            target_time=target_time,
            actual_time=floor_tick.timestamp,
            gap_seconds=gap_seconds,
            is_valid=True,
            error_reason=None
        )
    
    def _find_closest_tick(self, symbol: str, target_time: datetime) -> Optional[TickData]:
        """
        查找最接近目标时间的tick（向后兼容旧接口）
        
        ⚠️  已弃用：请使用 _find_floor_tick 以获得 PATCH-2 增强功能
        
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
        计算价格变化率（PATCH-2增强：使用 floor 查找）
        
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
            
            # PATCH-2: 使用 floor 查找，带 gap tolerance
            window_key = self._hours_to_window_key(hours)
            tolerance = self.GAP_TOLERANCE.get(window_key, 600)  # 默认10分钟
            
            result = self._find_floor_tick(symbol, target_time, tolerance)
            
            if not result.is_valid or result.tick is None:
                logger.debug(f"Price change lookback failed for {symbol} ({hours}h): {result.error_reason}")
                return None
            
            past_tick = result.tick
            
            if past_tick.price == 0:
                return None
            
            change_percent = ((current_tick.price - past_tick.price) / past_tick.price) * 100
            
            return change_percent
    
    def calculate_oi_change(self, symbol: str, hours: float) -> Optional[float]:
        """
        计算持仓量变化率（PATCH-2增强：使用 floor 查找）
        
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
            
            # PATCH-2: 使用 floor 查找
            window_key = self._hours_to_window_key(hours)
            tolerance = self.GAP_TOLERANCE.get(window_key, 600)
            
            result = self._find_floor_tick(symbol, target_time, tolerance)
            
            if not result.is_valid or result.tick is None:
                logger.debug(f"OI change lookback failed for {symbol} ({hours}h): {result.error_reason}")
                return None
            
            past_tick = result.tick
            
            if past_tick.open_interest == 0:
                return None
            
            change_percent = ((current_tick.open_interest - past_tick.open_interest) / past_tick.open_interest) * 100
            
            return change_percent
    
    def _hours_to_window_key(self, hours: float) -> str:
        """将小时数转换为窗口key"""
        if abs(hours - 0.0833) < 0.01:  # ~5分钟
            return '5m'
        elif abs(hours - 0.25) < 0.01:  # 15分钟
            return '15m'
        elif abs(hours - 1.0) < 0.01:
            return '1h'
        elif abs(hours - 6.0) < 0.01:
            return '6h'
        else:
            return '1h'  # 默认
    
    def calculate_price_change_15m(self, symbol: str) -> Optional[float]:
        """
        计算15分钟价格变化率（PR-005-DATA）
        
        Args:
            symbol: 币种符号
        
        Returns:
            变化率（百分比）或None
        """
        return self.calculate_price_change(symbol, hours=0.25)  # 15分钟 = 0.25小时
    
    def calculate_price_change_5m(self, symbol: str) -> Optional[float]:
        """
        计算5分钟价格变化率（PR-005-DATA）
        
        Args:
            symbol: 币种符号
        
        Returns:
            变化率（百分比）或None
        """
        return self.calculate_price_change(symbol, hours=5/60)  # 5分钟 ≈ 0.0833小时
    
    def calculate_oi_change_15m(self, symbol: str) -> Optional[float]:
        """
        计算15分钟持仓量变化率（PR-005-DATA）
        
        Args:
            symbol: 币种符号
        
        Returns:
            变化率（百分比）或None
        """
        return self.calculate_oi_change(symbol, hours=0.25)  # 15分钟 = 0.25小时
    
    def calculate_oi_change_5m(self, symbol: str) -> Optional[float]:
        """
        计算5分钟持仓量变化率（PR-005-DATA）
        
        Args:
            symbol: 币种符号
        
        Returns:
            变化率（百分比）或None
        """
        return self.calculate_oi_change(symbol, hours=5/60)  # 5分钟 ≈ 0.0833小时
    
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
            
            # PATCH-2: 使用 floor 查找
            result = self._find_floor_tick(symbol, target_time, self.GAP_TOLERANCE['1h'])
            
            if not result.is_valid or result.tick is None:
                logger.debug(f"Volume 1h lookback failed for {symbol}: {result.error_reason}")
                return None
            
            past_tick = result.tick
            
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
        
        ⚠️  DEPRECATED (PATCH-P0-1)
        ====================================
        本方法依赖buy_volume/sell_volume字段，但这些字段已废弃（fetcher不再提供）。
        
        推荐替代：使用 taker_imbalance_* 字段（klines聚合，权威来源）
        PATCH-P0-2将全面替换为taker_imbalance_1h
        ====================================
        
        Args:
            symbol: 币种符号
            hours: 统计时间范围（默认1小时）
        
        Returns:
            失衡度（-1到1之间）或None
        """
        ticks = self.get_historical_ticks(symbol, hours=hours)
        
        if len(ticks) == 0:
            return None
        
        total_buy = sum(tick.buy_volume for tick in ticks)
        total_sell = sum(tick.sell_volume for tick in ticks)
        
        total = total_buy + total_sell
        
        # PATCH-P0-1: buy/sell全为0时返回None（显性化缺失）
        if total == 0:
            logger.debug(f"buy/sell volumes all zero for {symbol}, returning None [DEPRECATED]")
            return None
        
        # 失衡度 = (买量 - 卖量) / 总量
        imbalance = (total_buy - total_sell) / total
        
        # 限制在[-1, 1]范围内
        imbalance = max(-1.0, min(1.0, imbalance))
        
        return imbalance
    
    def get_lookback_coverage(self, symbol: str) -> dict:
        """
        获取 lookback 覆盖信息（PATCH-2新增）
        
        用于诊断和可观测性，返回各个窗口的 lookback 结果
        
        Args:
            symbol: 币种符号
        
        Returns:
            coverage信息字典
        """
        with self.lock:
            if symbol not in self.cache or len(self.cache[symbol]) == 0:
                return {
                    'has_data': False,
                    'windows': {}
                }
            
            current_tick = self.cache[symbol][-1]
            current_time = current_tick.timestamp
            
            windows = {}
            for window_key, tolerance in self.GAP_TOLERANCE.items():
                if window_key == '5m':
                    hours = 5/60
                elif window_key == '15m':
                    hours = 0.25
                elif window_key == '1h':
                    hours = 1.0
                elif window_key == '6h':
                    hours = 6.0
                else:
                    continue
                
                target_time = current_time - timedelta(hours=hours)
                result = self._find_floor_tick(symbol, target_time, tolerance)
                
                windows[window_key] = {
                    'target_time': target_time.isoformat(),
                    'actual_time': result.actual_time.isoformat() if result.actual_time else None,
                    'gap_seconds': result.gap_seconds,
                    'is_valid': result.is_valid,
                    'error_reason': result.error_reason
                }
            
            return {
                'has_data': True,
                'current_time': current_time.isoformat(),
                'cache_size': len(self.cache[symbol]),
                'windows': windows
            }
    
    def get_enhanced_market_data(self, symbol: str, current_data: dict) -> dict:
        """
        基于当前数据和历史缓存，生成增强的市场数据（包含所有L1需要的字段）
        
        ⚠️  重要规范（PR-M 建议A）：
        ====================================
        本方法是系统中 **唯一** 注入 _metadata 的地方！
        
        职责边界：
        - MarketDataCache：负责计算百分比变化率，并标注输出格式（percent_point）
        - BinanceDataFetcher：只负责调用API和调用cache，不注入元数据
        - L1Engine：只负责消费数据，不修改元数据
        
        如果需要支持新的数据源：
        1. 新数据源必须通过 MarketDataCache 或等价的"格式标注层"
        2. 禁止在业务逻辑层（L1Engine）注入或修改_metadata
        3. 保持"数据源层注入、业务层消费"的清晰边界
        ====================================
        
        Args:
            symbol: 币种符号
            current_data: 当前tick数据（来自Binance API）
        
        Returns:
            增强的市场数据字典（包含price_change_1h等计算字段 + _metadata + PATCH-2 coverage）
        """
        # 先存储当前数据
        self.store_tick(symbol, current_data)
        
        # 计算变化率（包含PR-005新增的5m/15m）
        price_change_1h = self.calculate_price_change(symbol, hours=1.0)
        price_change_6h = self.calculate_price_change(symbol, hours=6.0)
        price_change_15m = self.calculate_price_change(symbol, hours=0.25)  # PR-005: 15分钟
        price_change_5m = self.calculate_price_change(symbol, hours=0.0833)  # PR-005: 5分钟
        
        oi_change_1h = self.calculate_oi_change(symbol, hours=1.0)
        oi_change_6h = self.calculate_oi_change(symbol, hours=6.0)
        oi_change_15m = self.calculate_oi_change(symbol, hours=0.25)  # PR-005: 15分钟
        oi_change_5m = self.calculate_oi_change(symbol, hours=0.0833)  # PR-005: 5分钟
        
        # PATCH-P0-2: volume_1h优先使用klines聚合（权威来源）
        volume_1h_klines = current_data.get('volume_1h')  # klines聚合
        volume_1h_calculated = self.calculate_volume_1h(symbol)  # 24h ticker差分（fallback）
        
        # 优先使用klines，fallback到calculate
        volume_1h = volume_1h_klines if volume_1h_klines is not None else volume_1h_calculated
        
        # PATCH-P0-2: buy_sell_imbalance改为taker_imbalance_1h的alias（唯一真相）
        taker_imbalance_1h_value = current_data.get('taker_imbalance_1h')  # klines聚合（权威）
        buy_sell_imbalance_legacy = self.calculate_buy_sell_imbalance(symbol, hours=1.0)  # 旧计算（DEPRECATED）
        
        # 优先使用taker_imbalance_1h，fallback到旧计算（向后兼容）
        imbalance_value = taker_imbalance_1h_value if taker_imbalance_1h_value is not None else buy_sell_imbalance_legacy
        
        # PATCH-2: 获取 lookback coverage
        coverage = self.get_lookback_coverage(symbol)
        
        # 获取源时间戳（来自最新tick）
        source_timestamp = None
        with self.lock:
            if symbol in self.cache and len(self.cache[symbol]) > 0:
                source_timestamp = self.cache[symbol][-1].timestamp
        
        # 构造增强数据（PR-005 + PATCH-P0-3: 缺失不填0）
        enhanced_data = {
            'price': current_data.get('price', 0),
            
            # PATCH-P0-3: 关键字段缺失保留None，不填0（消除"伪中性"）
            # 中长期字段（1h/6h）- 缺失时返回None
            'price_change_1h': price_change_1h,  # None-aware
            'price_change_6h': price_change_6h,  # None-aware
            'oi_change_1h': oi_change_1h,        # None-aware
            'oi_change_6h': oi_change_6h,        # None-aware
            'volume_1h': volume_1h,              # None-aware
            
            # 短期字段（5m/15m）- 已经是None-aware（PR-005）
            'price_change_15m': price_change_15m,  # None-aware
            'price_change_5m': price_change_5m,    # None-aware
            'oi_change_15m': oi_change_15m,        # None-aware
            'oi_change_5m': oi_change_5m,          # None-aware
            
            # PATCH-P0-2: buy_sell_imbalance改为taker_imbalance_1h的alias
            'buy_sell_imbalance': imbalance_value,  # alias of taker_imbalance_1h
            
            # 非关键字段（可填默认值）
            'volume_24h': current_data.get('volume_24h', 0),
            'funding_rate': current_data.get('funding_rate', 0),
            # PR-002: 添加时间戳信息（用于新鲜度检查）
            'source_timestamp': source_timestamp,
            'computed_at': datetime.now(),
            # PR-001/002: 从klines获取的多周期数据（直接传递）
            'volume_5m': current_data.get('volume_5m'),
            'volume_15m': current_data.get('volume_15m'),
            'volume_ratio_5m': current_data.get('volume_ratio_5m'),
            'volume_ratio_15m': current_data.get('volume_ratio_15m'),
            'volume_ratio_1h': current_data.get('volume_ratio_1h'),
            'taker_imbalance_5m': current_data.get('taker_imbalance_5m'),
            'taker_imbalance_15m': current_data.get('taker_imbalance_15m'),
            'taker_imbalance_1h': current_data.get('taker_imbalance_1h'),
            # PR-M (方案B): 元数据标注 - 声明百分比字段的输出格式
            '_metadata': {
                'percentage_format': 'percent_point',  # 百分比字段为 percent-point 格式（已乘100）
                'source': 'market_data_cache',
                'version': '1.1',  # PATCH-2
                'lookback_coverage': coverage  # PATCH-2: 添加 coverage 信息
            }
        }
        
        # PATCH-P0-03: None-safe日志输出 + 字段名对齐
        price_change = enhanced_data.get('price_change_1h')
        imbalance = enhanced_data.get('taker_imbalance_1h')
        
        price_change_str = f"{price_change:.2f}%" if price_change is not None else 'NA'
        imbalance_str = f"{imbalance:.2f}" if imbalance is not None else 'NA'
        
        logger.info(f"Enhanced data for {symbol}: "
                   f"price_change_1h={price_change_str}, "
                   f"taker_imbalance_1h={imbalance_str}")
        
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


# 全局缓存实例（单例模式，线程安全）
_global_cache = None
_cache_lock = threading.Lock()

def get_cache() -> MarketDataCache:
    """
    获取全局缓存实例（线程安全）
    
    Returns:
        MarketDataCache实例
    """
    global _global_cache
    if _global_cache is None:
        with _cache_lock:
            # 双重检查锁定模式（Double-Checked Locking）
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
    print("Testing MarketDataCache (PATCH-2)")
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
    # PATCH-P0-03: calculate_buy_sell_imbalance已弃用（DEPRECATED）
    # print(f"买卖失衡度: {cache.calculate_buy_sell_imbalance('BTC', 1.0):.2f}")
    
    # PATCH-2: 测试 lookback coverage
    print("\nPATCH-2 Lookback Coverage:")
    coverage = cache.get_lookback_coverage('BTC')
    for window, info in coverage.get('windows', {}).items():
        print(f"  {window}: valid={info['is_valid']}, gap={info['gap_seconds']}s, reason={info['error_reason']}")
    
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
    print(f"增强数据: price_change_1h={enhanced['price_change_1h']:.2f}%")
    print(f"Coverage: {enhanced['_metadata']['lookback_coverage']['has_data']}")
    
    print("\n测试完成！")
