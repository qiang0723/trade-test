"""
回测框架 - 历史数据加载器

功能：
1. 从Binance API加载历史K线数据
2. 计算多周期指标（5m/15m/1h/6h）
3. 数据缓存和增量更新
4. 数据质量验证

PR-ARCH-01改进：
- 集成FeatureBuilder，确保回测与线上特征口径一致
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

# PR-ARCH-01: 导入FeatureBuilder
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from l1_engine.feature_builder import build_features_from_dict
from models.feature_snapshot import FeatureSnapshot

logger = logging.getLogger(__name__)


class HistoricalDataLoader:
    """
    历史数据加载器
    
    支持：
    - Binance API实时获取
    - CSV文件加载
    - 数据缓存
    """
    
    def __init__(self, cache_dir: str = "backtest/cache"):
        """
        初始化数据加载器
        
        Args:
            cache_dir: 缓存目录
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        # 尝试导入Binance客户端
        try:
            from binance.client import Client
            self.binance_available = True
            # 使用公共API（无需API key）
            self.client = Client("", "")
        except ImportError:
            self.binance_available = False
            logger.warning("Binance API not available, will use cached data only")
    
    def load_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1m",
        use_cache: bool = True
    ) -> List[Dict]:
        """
        加载历史数据
        
        Args:
            symbol: 交易对（如 "BTCUSDT"）
            start_date: 开始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"
            interval: K线间隔（1m, 5m, 15m, 1h等）
            use_cache: 是否使用缓存
        
        Returns:
            List[Dict]: K线数据列表
        """
        cache_file = self._get_cache_file(symbol, start_date, end_date, interval)
        
        # 尝试从缓存加载
        if use_cache and os.path.exists(cache_file):
            logger.info(f"Loading from cache: {cache_file}")
            return self._load_from_cache(cache_file)
        
        # 从Binance API加载
        if not self.binance_available:
            raise RuntimeError("Binance API not available and no cache found")
        
        logger.info(f"Fetching {symbol} {interval} data from {start_date} to {end_date}")
        klines = self._fetch_from_binance(symbol, start_date, end_date, interval)
        
        # 保存到缓存
        if use_cache:
            self._save_to_cache(cache_file, klines)
        
        return klines
    
    def _fetch_from_binance(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str
    ) -> List[Dict]:
        """
        从Binance API获取数据
        """
        from binance.client import Client
        
        # 转换日期格式
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        
        all_klines = []
        current_ts = start_ts
        
        # 分批获取（每次最多1000条）
        while current_ts < end_ts:
            try:
                klines = self.client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    startTime=current_ts,
                    endTime=end_ts,
                    limit=1000
                )
                
                if not klines:
                    break
                
                # 转换为标准格式
                for k in klines:
                    all_klines.append({
                        'timestamp': k[0],
                        'open': float(k[1]),
                        'high': float(k[2]),
                        'low': float(k[3]),
                        'close': float(k[4]),
                        'volume': float(k[5]),
                        'close_time': k[6],
                        'quote_volume': float(k[7]),
                        'trades': int(k[8]),
                        'taker_buy_base': float(k[9]),
                        'taker_buy_quote': float(k[10])
                    })
                
                # 更新时间戳
                current_ts = klines[-1][0] + 1
                
                # 避免API限流
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error fetching data: {e}")
                break
        
        logger.info(f"Fetched {len(all_klines)} klines")
        return all_klines
    
    def _get_cache_file(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str
    ) -> str:
        """生成缓存文件路径"""
        filename = f"{symbol}_{interval}_{start_date}_{end_date}.json"
        return os.path.join(self.cache_dir, filename)
    
    def _load_from_cache(self, cache_file: str) -> List[Dict]:
        """从缓存加载数据"""
        with open(cache_file, 'r') as f:
            return json.load(f)
    
    def _save_to_cache(self, cache_file: str, data: List[Dict]):
        """保存数据到缓存"""
        with open(cache_file, 'w') as f:
            json.dump(data, f)
        logger.info(f"Saved to cache: {cache_file}")
    
    def prepare_market_data(
        self,
        klines_1m: List[Dict],
        timestamp: int
    ) -> Optional[Dict]:
        """
        准备L1决策所需的市场数据
        
        Args:
            klines_1m: 1分钟K线数据
            timestamp: 当前时间戳
        
        Returns:
            Dict: L1决策输入数据，包含多周期指标
        """
        # 找到当前时间点
        current_idx = None
        for i, k in enumerate(klines_1m):
            if k['timestamp'] == timestamp:
                current_idx = i
                break
        
        if current_idx is None or current_idx < 360:  # 需要至少6小时历史数据
            return None
        
        # 获取历史数据切片
        history = klines_1m[max(0, current_idx - 360):current_idx + 1]
        
        # 计算多周期指标
        current_price = history[-1]['close']
        
        # 5分钟变化
        price_5m_ago = history[-5]['close'] if len(history) >= 5 else current_price
        price_change_5m = (current_price - price_5m_ago) / price_5m_ago
        
        # 15分钟变化
        price_15m_ago = history[-15]['close'] if len(history) >= 15 else current_price
        price_change_15m = (current_price - price_15m_ago) / price_15m_ago
        
        # 1小时变化
        price_1h_ago = history[-60]['close'] if len(history) >= 60 else current_price
        price_change_1h = (current_price - price_1h_ago) / price_1h_ago
        
        # 6小时变化
        price_6h_ago = history[-360]['close'] if len(history) >= 360 else current_price
        price_change_6h = (current_price - price_6h_ago) / price_6h_ago
        
        # 计算成交量指标
        volume_5m = sum(k['volume'] for k in history[-5:])
        volume_15m = sum(k['volume'] for k in history[-15:])
        volume_1h = sum(k['volume'] for k in history[-60:])
        volume_24h = sum(k['volume'] for k in history[-1440:]) if len(history) >= 1440 else volume_1h * 24
        
        volume_ratio_5m = volume_5m / (volume_1h / 12) if volume_1h > 0 else 1.0
        volume_ratio_15m = volume_15m / (volume_1h / 4) if volume_1h > 0 else 1.0
        
        # 计算Taker买卖失衡（简化版，使用买入成交量占比）
        taker_buy_5m = sum(k['taker_buy_base'] for k in history[-5:])
        taker_sell_5m = volume_5m - taker_buy_5m
        taker_imbalance_5m = (taker_buy_5m - taker_sell_5m) / volume_5m if volume_5m > 0 else 0
        
        taker_buy_15m = sum(k['taker_buy_base'] for k in history[-15:])
        taker_sell_15m = volume_15m - taker_buy_15m
        taker_imbalance_15m = (taker_buy_15m - taker_sell_15m) / volume_15m if volume_15m > 0 else 0
        
        taker_buy_1h = sum(k['taker_buy_base'] for k in history[-60:])
        taker_sell_1h = volume_1h - taker_buy_1h
        buy_sell_imbalance = (taker_buy_1h - taker_sell_1h) / volume_1h if volume_1h > 0 else 0
        
        # ==================
        # OI变化估算（回测模式）
        # ==================
        # 原理：价格变化 + 成交量放大 → 新资金入场 → OI增长
        # 公式：oi_change ≈ |price_change| * volume_ratio * scaling_factor
        # 
        # 注意：这是近似估算，用于回测验证策略逻辑
        # 真实交易应使用Binance OI API数据
        
        # 计算前1小时/前6小时的平均成交量（作为基准）
        if len(history) >= 120:
            prev_volume_1h = sum(k['volume'] for k in history[-120:-60])
        else:
            prev_volume_1h = volume_1h
        
        if len(history) >= 720:
            prev_volume_6h = sum(k['volume'] for k in history[-720:-360])
        else:
            prev_volume_6h = volume_24h / 4  # 使用24h均值
        
        # OI变化估算
        # 规则1：价格大幅变动 + 成交量放大 → OI增长
        # 规则2：成交量萎缩 → OI可能下降
        # 规则3：添加随机因子模拟市场噪音
        
        import random
        noise_factor = 1 + (random.random() - 0.5) * 0.2  # ±10%噪音
        
        # 5分钟OI估算（scaling: 15x）
        vol_ratio_5m_vs_avg = volume_5m / (volume_1h / 12) if volume_1h > 0 else 1.0
        oi_change_5m = abs(price_change_5m) * vol_ratio_5m_vs_avg * 15.0 * noise_factor
        if vol_ratio_5m_vs_avg < 0.8:  # 成交量萎缩
            oi_change_5m = -oi_change_5m * 0.3
        
        # 15分钟OI估算（scaling: 12x）
        vol_ratio_15m_vs_avg = volume_15m / (volume_1h / 4) if volume_1h > 0 else 1.0
        oi_change_15m = abs(price_change_15m) * vol_ratio_15m_vs_avg * 12.0 * noise_factor
        if vol_ratio_15m_vs_avg < 0.8:
            oi_change_15m = -oi_change_15m * 0.3
        
        # 1小时OI估算（scaling: 10x）
        vol_ratio_1h = volume_1h / prev_volume_1h if prev_volume_1h > 0 else 1.0
        oi_change_1h = abs(price_change_1h) * vol_ratio_1h * 10.0 * noise_factor
        if vol_ratio_1h < 0.8:
            oi_change_1h = -oi_change_1h * 0.3
        
        # 6小时OI估算（scaling: 8x）
        volume_6h = sum(k['volume'] for k in history[-360:]) if len(history) >= 360 else volume_1h * 6
        vol_ratio_6h = volume_6h / prev_volume_6h if prev_volume_6h > 0 else 1.0
        oi_change_6h = abs(price_change_6h) * vol_ratio_6h * 8.0 * noise_factor
        if vol_ratio_6h < 0.8:
            oi_change_6h = -oi_change_6h * 0.3
        
        # 限制OI变化范围在合理区间 [-0.3, 0.5]
        oi_change_5m = max(-0.3, min(0.5, oi_change_5m))
        oi_change_15m = max(-0.3, min(0.5, oi_change_15m))
        oi_change_1h = max(-0.3, min(0.5, oi_change_1h))
        oi_change_6h = max(-0.3, min(0.5, oi_change_6h))
        
        # 构造原始特征数据（decimal格式）
        raw_features = {
            'price': current_price,
            'timestamp': timestamp,
            
            # 价格变化
            'price_change_5m': price_change_5m,
            'price_change_15m': price_change_15m,
            'price_change_1h': price_change_1h,
            'price_change_6h': price_change_6h,
            
            # 成交量
            'volume_1h': volume_1h,
            'volume_24h': volume_24h,
            'volume_ratio_5m': volume_ratio_5m,
            'volume_ratio_15m': volume_ratio_15m,
            
            # 买卖失衡
            'taker_imbalance_5m': taker_imbalance_5m,
            'taker_imbalance_15m': taker_imbalance_15m,
            'taker_imbalance_1h': buy_sell_imbalance,
            'buy_sell_imbalance': buy_sell_imbalance,
            
            # OI变化（回测模式：基于价格和成交量估算）
            'oi_change_1h': oi_change_1h,
            'oi_change_6h': oi_change_6h,
            'oi_change_5m': oi_change_5m,
            'oi_change_15m': oi_change_15m,
            
            # 资金费率（回测中使用默认值）
            'funding_rate': 0.0001,
            'open_interest': 0,
            
            # 元数据
            '_metadata': {
                'percentage_format': 'decimal',
                'source': 'backtest',
                'version': '1.0'
            }
        }
        
        # PR-ARCH-01: 使用FeatureBuilder规范化（确保与线上口径一致）
        try:
            feature_snapshot = build_features_from_dict(
                symbol="BACKTEST",
                features_dict=raw_features,
                coverage_dict=None
            )
            market_data = feature_snapshot.to_legacy_format()
            market_data['timestamp'] = timestamp
            market_data['price'] = current_price
        except Exception as e:
            logger.warning(f"FeatureBuilder failed in backtest: {e}, using raw features")
            market_data = raw_features
        
        return market_data
    
    def get_date_range(
        self,
        klines: List[Dict]
    ) -> Tuple[str, str]:
        """
        获取数据的日期范围
        
        Returns:
            (start_date, end_date)
        """
        if not klines:
            return ("", "")
        
        start_ts = klines[0]['timestamp']
        end_ts = klines[-1]['timestamp']
        
        start_date = datetime.fromtimestamp(start_ts / 1000).strftime("%Y-%m-%d")
        end_date = datetime.fromtimestamp(end_ts / 1000).strftime("%Y-%m-%d")
        
        return (start_date, end_date)
