"""
Coinglass 数据获取器

职责：
1. 安全调用Coinglass API
2. 获取清算热力图、聚合OI、实时爆仓等数据
3. 数据格式标准化
4. 错误处理和重试机制

API文档：https://coinglass.com/api

安全说明：
- API Key从环境变量或.env文件读取
- 绝不在代码中硬编码密钥
- 日志中仅显示掩码后的Key
"""

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from l1_engine.secrets_manager import get_secrets_manager

logger = logging.getLogger(__name__)

# 全局缓存（简单实现）
_coinglass_cache: Dict[str, Any] = {}
_cache_timestamps: Dict[str, datetime] = {}


@dataclass
class LiquidationLevel:
    """清算价位数据"""
    price: float                    # 价格位
    liquidation_value: float        # 清算价值(USD)
    long_liquidation: float         # 多头清算量
    short_liquidation: float        # 空头清算量
    leverage_distribution: Dict     # 杠杆分布


@dataclass
class AggregatedOI:
    """聚合持仓量数据"""
    timestamp: datetime
    total_oi: float                 # 总OI(USD)
    oi_change_1h: Optional[float]   # 1h变化率
    oi_change_24h: Optional[float]  # 24h变化率
    exchange_breakdown: Dict        # 各交易所分布


@dataclass
class LiquidationEvent:
    """爆仓事件"""
    timestamp: datetime
    exchange: str
    symbol: str
    side: str                       # LONG/SHORT
    size: float                     # 数量
    price: float                    # 爆仓价格
    value_usd: float               # 美元价值


@dataclass
class CoinglassMetrics:
    """Coinglass综合指标"""
    symbol: str
    timestamp: datetime
    
    # 清算热力图
    liquidation_levels: List[LiquidationLevel]
    nearest_long_liquidation: Optional[float]   # 最近多头清算位
    nearest_short_liquidation: Optional[float]  # 最近空头清算位
    liquidation_imbalance: Optional[float]      # 多空清算不平衡度
    
    # 聚合OI
    aggregated_oi: Optional[AggregatedOI]
    
    # 实时爆仓
    recent_liquidations: List[LiquidationEvent]
    liquidation_dominance: Optional[str]        # 近期爆仓主导方向
    
    # OI加权资金费率
    oi_weighted_funding_rate: Optional[float]
    
    # STARTUP套餐新增字段
    long_short_ratio: Optional[Dict] = None     # 多空比数据
    oi_history: Optional[Dict] = None           # OI历史数据
    funding_rate_history: Optional[Dict] = None # 资金费率历史
    fear_greed: Optional[Dict] = None           # 恐惧贪婪指数
    liquidation_summary: Optional[Dict] = None  # 清算汇总
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'nearest_long_liquidation': self.nearest_long_liquidation,
            'nearest_short_liquidation': self.nearest_short_liquidation,
            'liquidation_imbalance': self.liquidation_imbalance,
            'aggregated_oi': self.aggregated_oi.total_oi if self.aggregated_oi else None,
            'aggregated_oi_change_1h': self.aggregated_oi.oi_change_1h if self.aggregated_oi else None,
            'liquidation_dominance': self.liquidation_dominance,
            'oi_weighted_funding_rate': self.oi_weighted_funding_rate,
            'recent_liquidation_count': len(self.recent_liquidations)
        }


class CoinglassDataFetcher:
    """
    Coinglass数据获取器
    
    使用示例：
        fetcher = CoinglassDataFetcher()
        metrics = fetcher.fetch_all_metrics("BTC")
    """
    
    # API端点 (Coinglass Open API v4)
    # 文档: https://docs.coinglass.com/reference
    ENDPOINTS = {
        # HOBBYIST套餐可用端点 ($29/月)
        'supported_coins': '/api/futures/supported-coins',
        'supported_pairs': '/api/futures/supported-exchange-pairs',
        'fear_greed': '/api/index/fear-greed-history',
        'liquidation_coins': '/api/futures/liquidation/coin-list',  # 清算汇总数据
        
        # STARTUP套餐端点 ($79/月) - 已验证可用
        'oi_history': '/api/futures/open-interest/history',           # ✅ OI历史
        'funding_rate': '/api/futures/funding-rate/history',          # ✅ 费率历史
        'long_short_ratio': '/api/futures/global-long-short-account-ratio/history',  # ✅ 多空比
        
        # 高级端点（可能需要更高套餐）
        'aggregated_oi': '/api/futures/open-interest/aggregated-history',
        'liquidation_heatmap': '/api/futures/liquidation-heatmap',
        'liquidation_history': '/api/futures/liquidation/history',
    }
    
    # Symbol映射（Coinglass使用的格式）
    SYMBOL_MAP = {
        'BTC': 'BTC',
        'ETH': 'ETH',
        'SOL': 'SOL',
        'BTCUSDT': 'BTC',
        'ETHUSDT': 'ETH',
        'SOLUSDT': 'SOL',
    }
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """
        初始化Coinglass数据获取器
        
        Args:
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.secrets = get_secrets_manager()
        self.base_url = self.secrets.get_coinglass_base_url()
        self.timeout = timeout
        self.max_retries = max_retries
        
        # 配置重试策略
        self.session = self._create_session()
        
        # 速率限制
        self._last_request_time = 0
        self._min_request_interval = 0.2  # 200ms间隔
        
        # 验证配置
        self._api_key = None
        self._enabled = self.secrets.is_coinglass_enabled()
        
        if self._enabled:
            try:
                self._api_key = self.secrets.get_coinglass_api_key(required=True)
                logger.info("Coinglass data fetcher initialized successfully")
            except ValueError as e:
                logger.warning(f"Coinglass disabled: {e}")
                self._enabled = False
    
    def _create_session(self) -> requests.Session:
        """创建带重试机制的HTTP会话"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def _rate_limit(self):
        """速率限制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """
        发送API请求
        
        Args:
            endpoint: API端点
            params: 请求参数
        
        Returns:
            响应数据或None
        """
        if not self._enabled or not self._api_key:
            logger.debug("Coinglass is disabled or not configured")
            return None
        
        self._rate_limit()
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "accept": "application/json",
            "CG-API-KEY": self._api_key  # Coinglass使用此header
        }
        
        try:
            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') or data.get('code') == '0':
                    return data.get('data', data)
                else:
                    logger.warning(f"Coinglass API error: {data.get('msg', 'Unknown error')}")
                    return None
            elif response.status_code == 401:
                logger.error("Coinglass API authentication failed - check API key")
                return None
            elif response.status_code == 429:
                logger.warning("Coinglass API rate limit exceeded")
                return None
            else:
                logger.warning(f"Coinglass API request failed: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"Coinglass API timeout: {endpoint}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Coinglass API request error: {e}")
            return None
    
    def _normalize_symbol(self, symbol: str) -> str:
        """规范化Symbol格式"""
        return self.SYMBOL_MAP.get(symbol.upper(), symbol.upper())
    
    def fetch_liquidation_heatmap(self, symbol: str) -> List[LiquidationLevel]:
        """
        获取清算热力图
        
        Args:
            symbol: 交易对符号
        
        Returns:
            清算价位列表
        """
        cg_symbol = self._normalize_symbol(symbol)
        
        data = self._make_request(
            self.ENDPOINTS['liquidation_heatmap'],
            params={'symbol': cg_symbol}
        )
        
        if not data:
            return []
        
        levels = []
        try:
            for item in data:
                level = LiquidationLevel(
                    price=float(item.get('price', 0)),
                    liquidation_value=float(item.get('liquidationValue', 0)),
                    long_liquidation=float(item.get('longLiquidation', 0)),
                    short_liquidation=float(item.get('shortLiquidation', 0)),
                    leverage_distribution=item.get('leverageDistribution', {})
                )
                levels.append(level)
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse liquidation heatmap: {e}")
        
        logger.debug(f"Fetched {len(levels)} liquidation levels for {symbol}")
        return levels
    
    def fetch_aggregated_oi(self, symbol: str) -> Optional[AggregatedOI]:
        """
        获取聚合持仓量
        
        Args:
            symbol: 交易对符号
        
        Returns:
            聚合OI数据
        """
        cg_symbol = self._normalize_symbol(symbol)
        
        # 使用OI历史端点
        data = self._make_request(
            self.ENDPOINTS['oi_history'],
            params={
                'symbol': cg_symbol,
                'interval': 'h1',  # 1小时K线
                'limit': 2  # 获取最近2条用于计算变化
            }
        )
        
        if not data:
            return None
        
        try:
            # Coinglass v4 响应格式可能是 {data: [...]} 或直接是数组
            data_list = data.get('data', data) if isinstance(data, dict) else data
            
            if not data_list or len(data_list) == 0:
                return None
            
            latest = data_list[-1] if isinstance(data_list, list) else data_list
            
            # 计算变化率
            oi_change_1h = None
            if isinstance(data_list, list) and len(data_list) >= 2:
                current_oi = float(latest.get('o', latest.get('openInterest', 0)))  # o=open
                prev_oi = float(data_list[-2].get('o', data_list[-2].get('openInterest', 0)))
                if prev_oi > 0:
                    oi_change_1h = (current_oi - prev_oi) / prev_oi
            
            return AggregatedOI(
                timestamp=datetime.fromtimestamp(latest.get('t', latest.get('timestamp', 0)) / 1000),
                total_oi=float(latest.get('c', latest.get('close', latest.get('openInterest', 0)))),  # c=close
                oi_change_1h=oi_change_1h,
                oi_change_24h=None,  # 需要更多数据点
                exchange_breakdown={}
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse aggregated OI: {e}")
            return None
    
    def fetch_recent_liquidations(self, symbol: str, limit: int = 50) -> List[LiquidationEvent]:
        """
        获取近期爆仓事件
        
        Args:
            symbol: 交易对符号
            limit: 获取数量
        
        Returns:
            爆仓事件列表
        """
        cg_symbol = self._normalize_symbol(symbol)
        
        data = self._make_request(
            self.ENDPOINTS['liquidation_history'],
            params={
                'symbol': cg_symbol,
                'limit': limit
            }
        )
        
        if not data:
            return []
        
        events = []
        try:
            # 处理响应格式
            data_list = data.get('data', data) if isinstance(data, dict) else data
            if not isinstance(data_list, list):
                data_list = [data_list]
            
            for item in data_list:
                event = LiquidationEvent(
                    timestamp=datetime.fromtimestamp(item.get('t', item.get('timestamp', 0)) / 1000),
                    exchange=item.get('exchangeName', item.get('exchange', 'UNKNOWN')),
                    symbol=item.get('symbol', cg_symbol),
                    side=item.get('side', 'UNKNOWN').upper(),
                    size=float(item.get('size', item.get('volUsd', 0))),
                    price=float(item.get('price', 0)),
                    value_usd=float(item.get('volUsd', item.get('valueUsd', 0)))
                )
                events.append(event)
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse liquidation events: {e}")
        
        logger.debug(f"Fetched {len(events)} recent liquidations for {symbol}")
        return events
    
    def fetch_long_short_ratio(self, symbol: str, limit: int = 24) -> Optional[Dict]:
        """
        获取多空比数据（STARTUP可用）
        
        Args:
            symbol: 交易对符号
            limit: 获取数量
        
        Returns:
            多空比数据
        """
        cg_symbol = self._normalize_symbol(symbol)
        
        data = self._make_request(
            self.ENDPOINTS['long_short_ratio'],
            params={
                'exchange': 'Binance',
                'symbol': f'{cg_symbol}USDT',
                'interval': 'h1',
                'limit': limit
            }
        )
        
        if not data:
            return None
        
        try:
            data_list = data.get('data', data) if isinstance(data, dict) else data
            
            if isinstance(data_list, list) and len(data_list) > 0:
                latest = data_list[0]
                long_pct = float(latest.get('global_account_long_percent', 50))
                short_pct = float(latest.get('global_account_short_percent', 50))
                
                # 计算趋势（多头占比变化）
                trend = None
                if len(data_list) >= 6:
                    recent_avg = sum(d.get('global_account_long_percent', 50) for d in data_list[:3]) / 3
                    older_avg = sum(d.get('global_account_long_percent', 50) for d in data_list[3:6]) / 3
                    trend = recent_avg - older_avg  # 正值=多头增加，负值=空头增加
                
                return {
                    'long_percent': long_pct,
                    'short_percent': short_pct,
                    'long_short_ratio': long_pct / short_pct if short_pct > 0 else 0,
                    'trend': trend,
                    'sentiment': 'extremely_long' if long_pct > 70 else 'long' if long_pct > 55 else 'neutral' if long_pct > 45 else 'short' if long_pct > 30 else 'extremely_short',
                    'history': [(d.get('global_account_long_percent', 50), d.get('global_account_short_percent', 50)) for d in data_list[:12]]
                }
            
            return None
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse long/short ratio: {e}")
            return None
    
    def fetch_oi_history(self, symbol: str, limit: int = 24) -> Optional[Dict]:
        """
        获取OI历史数据（STARTUP可用）
        
        Args:
            symbol: 交易对符号
            limit: 获取数量
        
        Returns:
            OI历史数据
        """
        cg_symbol = self._normalize_symbol(symbol)
        
        data = self._make_request(
            self.ENDPOINTS['oi_history'],
            params={
                'exchange': 'Binance',
                'symbol': f'{cg_symbol}USDT',
                'interval': 'h1',
                'limit': limit
            }
        )
        
        if not data:
            return None
        
        try:
            data_list = data.get('data', data) if isinstance(data, dict) else data
            
            if isinstance(data_list, list) and len(data_list) > 0:
                latest_oi = float(data_list[0].get('close', 0))
                
                # 计算OI变化
                oi_change_1h = None
                oi_change_4h = None
                oi_change_24h = None
                
                if len(data_list) >= 2:
                    prev_oi = float(data_list[1].get('close', 0))
                    if prev_oi > 0:
                        oi_change_1h = (latest_oi - prev_oi) / prev_oi
                
                if len(data_list) >= 5:
                    oi_4h_ago = float(data_list[4].get('close', 0))
                    if oi_4h_ago > 0:
                        oi_change_4h = (latest_oi - oi_4h_ago) / oi_4h_ago
                
                if len(data_list) >= 24:
                    oi_24h_ago = float(data_list[23].get('close', 0))
                    if oi_24h_ago > 0:
                        oi_change_24h = (latest_oi - oi_24h_ago) / oi_24h_ago
                
                return {
                    'current_oi': latest_oi,
                    'current_oi_usd': latest_oi,  # 已经是USD
                    'oi_change_1h': oi_change_1h,
                    'oi_change_4h': oi_change_4h,
                    'oi_change_24h': oi_change_24h,
                    'trend': 'increasing' if oi_change_4h and oi_change_4h > 0.02 else 'decreasing' if oi_change_4h and oi_change_4h < -0.02 else 'stable',
                }
            
            return None
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse OI history: {e}")
            return None
    
    def fetch_funding_rate_history(self, symbol: str, limit: int = 24) -> Optional[Dict]:
        """
        获取资金费率历史（STARTUP可用）
        
        Args:
            symbol: 交易对符号
            limit: 获取数量
        
        Returns:
            资金费率历史数据
        """
        cg_symbol = self._normalize_symbol(symbol)
        
        data = self._make_request(
            self.ENDPOINTS['funding_rate'],
            params={
                'exchange': 'Binance',
                'symbol': f'{cg_symbol}USDT',
                'interval': 'h1',
                'limit': limit
            }
        )
        
        if not data:
            return None
        
        try:
            data_list = data.get('data', data) if isinstance(data, dict) else data
            
            if isinstance(data_list, list) and len(data_list) > 0:
                latest_rate = float(data_list[0].get('close', 0))
                
                # 计算平均费率
                rates = [float(d.get('close', 0)) for d in data_list]
                avg_rate = sum(rates) / len(rates) if rates else 0
                max_rate = max(rates) if rates else 0
                min_rate = min(rates) if rates else 0
                
                # 费率趋势
                trend = None
                if len(data_list) >= 6:
                    recent_avg = sum(float(d.get('close', 0)) for d in data_list[:3]) / 3
                    older_avg = sum(float(d.get('close', 0)) for d in data_list[3:6]) / 3
                    trend = 'increasing' if recent_avg > older_avg * 1.1 else 'decreasing' if recent_avg < older_avg * 0.9 else 'stable'
                
                return {
                    'current_rate': latest_rate,
                    'avg_rate': avg_rate,
                    'max_rate': max_rate,
                    'min_rate': min_rate,
                    'trend': trend,
                    'sentiment': 'extremely_bullish' if latest_rate > 0.001 else 'bullish' if latest_rate > 0.0003 else 'neutral' if latest_rate > -0.0003 else 'bearish' if latest_rate > -0.001 else 'extremely_bearish',
                    'history': rates[:12]
                }
            
            return None
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse funding rate history: {e}")
            return None
    
    def fetch_oi_weighted_funding_rate(self, symbol: str) -> Optional[float]:
        """
        获取当前资金费率（需要付费套餐）
        
        Args:
            symbol: 交易对符号
        
        Returns:
            资金费率或None（如果端点不可用）
        """
        cg_symbol = self._normalize_symbol(symbol)
        
        data = self._make_request(
            self.ENDPOINTS['funding_rate'],
            params={
                'exchange': 'Binance',
                'symbol': f'{cg_symbol}USDT',
                'interval': 'h1',
                'limit': 1
            }
        )
        
        if not data:
            return None
        
        try:
            data_obj = data.get('data', data) if isinstance(data, dict) else data
            
            if isinstance(data_obj, list) and len(data_obj) > 0:
                return float(data_obj[-1].get('close', data_obj[-1].get('fundingRate', 0)))
            elif isinstance(data_obj, dict):
                return float(data_obj.get('fundingRate', 0))
            
            return None
        except (KeyError, TypeError, ValueError, IndexError) as e:
            logger.warning(f"Failed to parse funding rate: {e}")
            return None
    
    def fetch_liquidation_summary(self, symbol: str = None) -> Optional[Dict]:
        """
        获取清算汇总数据（HOBBYIST可用）
        
        Args:
            symbol: 币种符号（可选，不传则返回所有币种）
        
        Returns:
            清算汇总数据
        """
        params = {'symbol': symbol} if symbol else {}
        
        data = self._make_request(
            self.ENDPOINTS['liquidation_coins'],
            params=params
        )
        
        if not data:
            return None
        
        try:
            data_list = data.get('data', data) if isinstance(data, dict) else data
            
            if not isinstance(data_list, list):
                return None
            
            # 如果指定了symbol，找到对应数据
            if symbol:
                for item in data_list:
                    if item.get('symbol', '').upper() == symbol.upper():
                        return self._parse_liquidation_item(item)
                return None
            
            # 返回所有币种数据
            result = {
                'total_liquidation_24h': sum(item.get('liquidation_usd_24h', 0) for item in data_list),
                'total_long_liquidation_24h': sum(item.get('long_liquidation_usd_24h', 0) for item in data_list),
                'total_short_liquidation_24h': sum(item.get('short_liquidation_usd_24h', 0) for item in data_list),
                'top_coins': [self._parse_liquidation_item(item) for item in data_list[:10]],
                'long_dominance': None,  # 多头爆仓占比
            }
            
            # 计算多头爆仓占比
            if result['total_liquidation_24h'] > 0:
                result['long_dominance'] = result['total_long_liquidation_24h'] / result['total_liquidation_24h']
            
            return result
            
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse liquidation summary: {e}")
            return None
    
    def _parse_liquidation_item(self, item: Dict) -> Dict:
        """解析单个清算数据项"""
        liq_24h = item.get('liquidation_usd_24h', 0)
        long_liq = item.get('long_liquidation_usd_24h', 0)
        short_liq = item.get('short_liquidation_usd_24h', 0)
        
        return {
            'symbol': item.get('symbol', 'UNKNOWN'),
            'liquidation_24h': liq_24h,
            'long_liquidation_24h': long_liq,
            'short_liquidation_24h': short_liq,
            'long_ratio': long_liq / liq_24h if liq_24h > 0 else 0,
            'liquidation_intensity': 'high' if liq_24h > 100_000_000 else 'medium' if liq_24h > 10_000_000 else 'low',
        }
    
    def fetch_fear_greed_index(self, limit: int = 30) -> Optional[Dict]:
        """
        获取恐惧贪婪指数（免费端点）
        
        Args:
            limit: 获取数量
        
        Returns:
            恐惧贪婪指数数据
        """
        data = self._make_request(
            self.ENDPOINTS['fear_greed'],
            params={'limit': limit}
        )
        
        if not data:
            return None
        
        try:
            data_obj = data.get('data', data) if isinstance(data, dict) else data
            
            if isinstance(data_obj, dict):
                data_list = data_obj.get('data_list', [])
                if data_list:
                    current_value = data_list[0] if data_list else None
                    
                    # 判断市场情绪
                    sentiment = 'neutral'
                    if current_value is not None:
                        if current_value <= 25:
                            sentiment = 'extreme_fear'
                        elif current_value <= 45:
                            sentiment = 'fear'
                        elif current_value <= 55:
                            sentiment = 'neutral'
                        elif current_value <= 75:
                            sentiment = 'greed'
                        else:
                            sentiment = 'extreme_greed'
                    
                    return {
                        'current': current_value,
                        'sentiment': sentiment,
                        'history': data_list[:7],  # 最近7天
                        'avg_7d': sum(data_list[:7]) / len(data_list[:7]) if len(data_list) >= 7 else None
                    }
            
            return None
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Failed to parse fear greed index: {e}")
            return None
    
    def check_api_permissions(self) -> Dict:
        """
        检查API权限状态
        
        Returns:
            权限检查结果
        """
        results = {
            'api_key_valid': False,
            'plan_level': 'unknown',
            'available_endpoints': [],
            'unavailable_endpoints': [],
            'recommendations': []
        }
        
        if not self._enabled or not self._api_key:
            results['recommendations'].append('请配置COINGLASS_API_KEY环境变量')
            return results
        
        # 测试各端点
        test_endpoints = [
            ('supported_coins', 'HOBBYIST-币种列表', {}),
            ('fear_greed', 'HOBBYIST-恐惧贪婪指数', {'limit': 1}),
            ('liquidation_coins', 'HOBBYIST-清算汇总', {}),
            ('oi_history', 'STARTUP-OI历史', {'exchange': 'Binance', 'symbol': 'BTCUSDT', 'interval': 'h1', 'limit': 1}),
            ('funding_rate', 'STARTUP-费率历史', {'exchange': 'Binance', 'symbol': 'BTCUSDT', 'interval': 'h1', 'limit': 1}),
            ('long_short_ratio', 'STARTUP-多空比', {'exchange': 'Binance', 'symbol': 'BTCUSDT', 'interval': 'h1', 'limit': 1}),
        ]
        
        for key, name, params in test_endpoints:
            endpoint = self.ENDPOINTS.get(key)
            if not endpoint:
                continue
                
            data = self._make_request(endpoint, params)
            if data is not None:
                results['available_endpoints'].append(name)
                results['api_key_valid'] = True
            else:
                results['unavailable_endpoints'].append(name)
        
        # 判断套餐级别
        hobbyist_endpoints = ['HOBBYIST-币种列表', 'HOBBYIST-恐惧贪婪指数', 'HOBBYIST-清算汇总']
        startup_endpoints = ['STARTUP-OI历史', 'STARTUP-费率历史']
        
        hobbyist_count = sum(1 for ep in results['available_endpoints'] if any(h in ep for h in hobbyist_endpoints))
        startup_count = sum(1 for ep in results['available_endpoints'] if any(s in ep for s in startup_endpoints))
        
        if startup_count > 0:
            results['plan_level'] = 'STARTUP+'
            results['recommendations'].append('已启用STARTUP+套餐，可获取完整数据')
        elif hobbyist_count >= 2:
            results['plan_level'] = 'HOBBYIST'
            results['recommendations'].append('HOBBYIST套餐已激活，可使用清算汇总和恐惧贪婪指数')
        elif hobbyist_count >= 1:
            results['plan_level'] = 'HOBBYIST (部分)'
            results['recommendations'].append('部分HOBBYIST端点可用，建议检查账户状态')
        else:
            results['plan_level'] = 'INVALID'
            results['recommendations'].append('API Key无效或已过期，请检查')
        
        return results
    
    # 主流币种列表（获取完整数据）
    MAJOR_SYMBOLS = ['BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'DOGE', 'ADA', 'AVAX', 'LINK', 'DOT']
    
    def fetch_all_metrics(self, symbol: str, current_price: Optional[float] = None) -> Optional[CoinglassMetrics]:
        """
        获取Coinglass指标（平衡版：充分利用API配额）
        
        优化策略：
        1. 主流币种（BTC/ETH/SOL等）：完整数据 + 30秒缓存
        2. 其他币种：基础数据 + 60秒缓存
        3. 恐惧贪婪：全局数据 + 3分钟缓存
        
        API配额：STARTUP 80次/分钟
        预估使用：
        - 主流币种(10个)：5端点 × 2次/分钟 = 100次 → 通过缓存降至~50次
        - 恐惧贪婪：0.3次/分钟
        - 总计：~50次/分钟（利用率~60%）
        
        Args:
            symbol: 交易对符号
            current_price: 当前价格
        
        Returns:
            综合指标对象
        """
        global _coinglass_cache, _cache_timestamps
        
        if not self._enabled:
            return None
        
        # 判断是否主流币种
        is_major = symbol.upper() in self.MAJOR_SYMBOLS
        
        # 缓存策略：主流币种30秒，其他60秒
        cache_key = f"metrics_{symbol}"
        cache_ttl = 30 if is_major else 60
        
        if cache_key in _coinglass_cache:
            cache_time = _cache_timestamps.get(cache_key)
            if cache_time and (datetime.now() - cache_time).total_seconds() < cache_ttl:
                logger.debug(f"Using cached Coinglass data for {symbol}")
                return _coinglass_cache[cache_key]
        
        endpoints_count = 5 if is_major else 3
        logger.info(f"Fetching Coinglass metrics for {symbol} ({'major' if is_major else 'other'}: {endpoints_count} endpoints)")
        
        # ========================================
        # 核心端点：所有币种都获取
        # ========================================
        
        # 1. 清算汇总（最有价值：多空清算比例）
        liquidation_summary = self.fetch_liquidation_summary(symbol)
        
        # 2. 多空比（拥挤检测）
        long_short_ratio = self.fetch_long_short_ratio(symbol)
        
        # 3. 恐惧贪婪指数（市场情绪，全局数据，3分钟缓存）
        fear_greed = None
        fear_greed_cache_key = "fear_greed_global"
        if fear_greed_cache_key in _coinglass_cache:
            fg_time = _cache_timestamps.get(fear_greed_cache_key)
            if fg_time and (datetime.now() - fg_time).total_seconds() < 180:  # 3分钟缓存
                fear_greed = _coinglass_cache[fear_greed_cache_key]
        
        if fear_greed is None:
            fear_greed = self.fetch_fear_greed_index(limit=7)
            if fear_greed:
                _coinglass_cache[fear_greed_cache_key] = fear_greed
                _cache_timestamps[fear_greed_cache_key] = datetime.now()
        
        # ========================================
        # 详细端点：仅主流币种获取
        # ========================================
        oi_history = None
        funding_rate_history = None
        
        if is_major:
            # OI历史（2分钟缓存）
            oi_cache_key = f"oi_{symbol}"
            if oi_cache_key in _coinglass_cache:
                oi_time = _cache_timestamps.get(oi_cache_key)
                if oi_time and (datetime.now() - oi_time).total_seconds() < 120:
                    oi_history = _coinglass_cache[oi_cache_key]
            
            if oi_history is None:
                oi_history = self.fetch_oi_history(symbol)
                if oi_history:
                    _coinglass_cache[oi_cache_key] = oi_history
                    _cache_timestamps[oi_cache_key] = datetime.now()
            
            # 费率历史（2分钟缓存）
            fr_cache_key = f"fr_{symbol}"
            if fr_cache_key in _coinglass_cache:
                fr_time = _cache_timestamps.get(fr_cache_key)
                if fr_time and (datetime.now() - fr_time).total_seconds() < 120:
                    funding_rate_history = _coinglass_cache[fr_cache_key]
            
            if funding_rate_history is None:
                funding_rate_history = self.fetch_funding_rate_history(symbol)
                if funding_rate_history:
                    _coinglass_cache[fr_cache_key] = funding_rate_history
                    _cache_timestamps[fr_cache_key] = datetime.now()
        
        # 从清算汇总计算多空不平衡
        liquidation_imbalance = None
        liquidation_dominance = None
        
        if liquidation_summary:
            long_ratio = liquidation_summary.get('long_ratio', 0)
            if long_ratio > 0.6:
                liquidation_dominance = 'LONG'
                liquidation_imbalance = long_ratio - 0.5
            elif long_ratio < 0.4:
                liquidation_dominance = 'SHORT'
                liquidation_imbalance = 0.5 - long_ratio
        
        logger.info(f"Coinglass[{symbol}]: liq={liquidation_summary is not None}, ls={long_short_ratio is not None}, oi={oi_history is not None}, fr={funding_rate_history is not None}")
        
        # 构建结果
        result = CoinglassMetrics(
            symbol=symbol,
            timestamp=datetime.now(),
            liquidation_levels=None,  # 不再调用（需要更高套餐）
            nearest_long_liquidation=None,
            nearest_short_liquidation=None,
            liquidation_imbalance=liquidation_imbalance,
            aggregated_oi=None,  # 不再调用（需要更高套餐）
            recent_liquidations=[],  # 不再调用（需要更高套餐）
            liquidation_dominance=liquidation_dominance,
            oi_weighted_funding_rate=None,
            long_short_ratio=long_short_ratio,
            oi_history=oi_history,
            funding_rate_history=funding_rate_history,
            fear_greed=fear_greed,
            liquidation_summary=liquidation_summary
        )
        
        # 缓存结果
        _coinglass_cache[cache_key] = result
        _cache_timestamps[cache_key] = datetime.now()
        
        return result
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self._enabled
    
    def get_status(self) -> Dict:
        """获取状态信息"""
        global _coinglass_cache, _cache_timestamps
        
        # 统计缓存状态
        cache_stats = {}
        now = datetime.now()
        for key, ts in _cache_timestamps.items():
            age = (now - ts).total_seconds()
            cache_stats[key] = f"{age:.0f}s ago"
        
        return {
            'enabled': self._enabled,
            'base_url': self.base_url,
            'api_key_configured': bool(self._api_key),
            'endpoints': list(self.ENDPOINTS.keys()),
            'cache_entries': len(_coinglass_cache),
            'cache_details': cache_stats,
            'rate_limit': '80 req/min (STARTUP)',
            'optimized_calls': '3 endpoints/request'
        }
    
    @staticmethod
    def clear_cache():
        """清理所有缓存"""
        global _coinglass_cache, _cache_timestamps
        _coinglass_cache.clear()
        _cache_timestamps.clear()
        logger.info("Coinglass cache cleared")


# ========================================
# 单例模式
# ========================================
_coinglass_fetcher_instance: Optional[CoinglassDataFetcher] = None


def get_coinglass_fetcher() -> CoinglassDataFetcher:
    """
    获取Coinglass数据获取器单例
    
    使用单例模式确保：
    1. 缓存在所有调用之间共享
    2. 避免重复初始化
    3. 节省API配额
    """
    global _coinglass_fetcher_instance
    if _coinglass_fetcher_instance is None:
        _coinglass_fetcher_instance = CoinglassDataFetcher()
        logger.info("CoinglassDataFetcher singleton created")
    return _coinglass_fetcher_instance


def preload_major_symbols_data(fetcher: Optional[CoinglassDataFetcher] = None) -> Dict[str, Any]:
    """
    预加载主流币种数据（充分利用API配额）
    
    目的：即使主要交易BTC，也获取ETH/SOL等数据作为市场情绪参考
    
    API配额计算：
    - 主流币种(10个) × 5端点 = 50次
    - 每30秒刷新一次 = 100次/分钟 → 通过缓存控制到 ~40次/分钟
    - 利用率：50%（安全边际）
    """
    if fetcher is None:
        fetcher = get_coinglass_fetcher()
    
    if not fetcher.is_enabled():
        return {}
    
    results = {}
    major_symbols = CoinglassDataFetcher.MAJOR_SYMBOLS[:5]  # 只预加载前5个主流币种
    
    logger.info(f"Preloading Coinglass data for major symbols: {major_symbols}")
    
    for symbol in major_symbols:
        try:
            metrics = fetcher.fetch_all_metrics(symbol)
            if metrics:
                results[symbol] = {
                    'liquidation_summary': metrics.liquidation_summary,
                    'long_short_ratio': metrics.long_short_ratio,
                    'oi_history': metrics.oi_history,
                    'funding_rate_history': metrics.funding_rate_history
                }
        except Exception as e:
            logger.warning(f"Failed to preload {symbol}: {e}")
    
    logger.info(f"Preloaded {len(results)} symbols: {list(results.keys())}")
    return results


def get_market_sentiment_summary(fetcher: Optional[CoinglassDataFetcher] = None) -> Dict[str, Any]:
    """
    获取市场整体情绪汇总（基于主流币种数据）
    
    返回：
    - overall_fear_greed: 恐惧贪婪指数
    - btc_dominance: BTC清算主导方向
    - eth_dominance: ETH清算主导方向  
    - major_ls_bias: 主流币种多空比平均偏向
    - funding_sentiment: 资金费率整体情绪
    """
    if fetcher is None:
        fetcher = get_coinglass_fetcher()
    
    if not fetcher.is_enabled():
        return {}
    
    # 预加载数据（会使用缓存）
    preloaded = preload_major_symbols_data(fetcher)
    
    summary = {
        'fear_greed': None,
        'btc_liquidation_dominance': None,
        'eth_liquidation_dominance': None,
        'major_ls_bias': None,
        'major_funding_avg': None,
        'symbols_analyzed': list(preloaded.keys())
    }
    
    # 恐惧贪婪指数
    fg_cache_key = "fear_greed_global"
    if fg_cache_key in _coinglass_cache:
        fg_data = _coinglass_cache[fg_cache_key]
        if fg_data:
            # fg_data可能是列表或字典
            if isinstance(fg_data, list) and len(fg_data) > 0:
                summary['fear_greed'] = fg_data[0].get('value')
            elif isinstance(fg_data, dict):
                summary['fear_greed'] = fg_data.get('value') or fg_data.get('fear_greed_value')
    
    # BTC/ETH清算主导
    for sym in ['BTC', 'ETH']:
        if sym in preloaded:
            liq = preloaded[sym].get('liquidation_summary', {})
            if liq:
                long_ratio = liq.get('long_ratio', 0.5)
                if long_ratio > 0.6:
                    summary[f'{sym.lower()}_liquidation_dominance'] = 'LONG'
                elif long_ratio < 0.4:
                    summary[f'{sym.lower()}_liquidation_dominance'] = 'SHORT'
                else:
                    summary[f'{sym.lower()}_liquidation_dominance'] = 'NEUTRAL'
    
    # 主流币种多空比平均
    ls_values = []
    for sym, data in preloaded.items():
        ls = data.get('long_short_ratio', {})
        if ls:
            # long_percent是百分比（0-100），转换为比率（0-1）
            long_pct = ls.get('long_percent')
            if long_pct is not None:
                ls_values.append(long_pct / 100)
    
    if ls_values:
        avg_ls = sum(ls_values) / len(ls_values)
        if avg_ls > 0.55:
            summary['major_ls_bias'] = 'LONG_CROWDED'
        elif avg_ls < 0.45:
            summary['major_ls_bias'] = 'SHORT_CROWDED'
        else:
            summary['major_ls_bias'] = 'BALANCED'
        summary['major_ls_avg'] = round(avg_ls, 3)
    
    # 资金费率平均
    fr_values = []
    for sym, data in preloaded.items():
        fr = data.get('funding_rate_history', {})
        if fr and 'current_rate' in fr:
            fr_values.append(fr['current_rate'])
    
    if fr_values:
        avg_fr = sum(fr_values) / len(fr_values)
        summary['major_funding_avg'] = round(avg_fr * 100, 4)  # 转为百分比
        if avg_fr > 0.0005:  # 0.05%
            summary['funding_sentiment'] = 'VERY_BULLISH'
        elif avg_fr > 0.0001:  # 0.01%
            summary['funding_sentiment'] = 'BULLISH'
        elif avg_fr < -0.0005:
            summary['funding_sentiment'] = 'VERY_BEARISH'
        elif avg_fr < -0.0001:
            summary['funding_sentiment'] = 'BEARISH'
        else:
            summary['funding_sentiment'] = 'NEUTRAL'
    
    logger.info(f"Market sentiment: FG={summary.get('fear_greed')}, LS={summary.get('major_ls_bias')}, FR={summary.get('funding_sentiment')}")
    return summary
