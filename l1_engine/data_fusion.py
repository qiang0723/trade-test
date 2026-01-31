"""
L1 Advisory Engine - 数据融合层

职责：
1. 合并Binance和Coinglass数据
2. 生成增强型市场特征
3. 基于Coinglass数据生成额外信号

数据流：
    Binance数据 + Coinglass数据 → DataFusion → 增强型FeatureSnapshot
"""

import logging
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime

from coinglass_data_fetcher import CoinglassDataFetcher, CoinglassMetrics
from models.reason_tags import ReasonTag

logger = logging.getLogger(__name__)


@dataclass
class FusionResult:
    """数据融合结果"""
    enhanced_data: Dict              # 增强后的数据字典
    coinglass_tags: List[ReasonTag]  # Coinglass相关标签
    coinglass_boost: int             # Coinglass信号加分
    coinglass_available: bool        # Coinglass数据是否可用
    fusion_details: Dict             # 融合详情（用于调试）


class DataFusion:
    """
    数据融合器
    
    将Binance实时数据与Coinglass衍生品分析数据融合，
    生成增强型市场特征。
    """
    
    # Coinglass相关的ReasonTag（需要在reason_tags.py中定义）
    # 这里先定义常量，后续添加到枚举
    TAG_LIQUIDATION_CLUSTER_NEAR = "liquidation_cluster_near"
    TAG_LIQUIDATION_IMBALANCE_LONG = "liquidation_imbalance_long"
    TAG_LIQUIDATION_IMBALANCE_SHORT = "liquidation_imbalance_short"
    TAG_AGGREGATED_OI_SURGE = "aggregated_oi_surge"
    TAG_AGGREGATED_OI_DROP = "aggregated_oi_drop"
    TAG_LIQUIDATION_CASCADE_RISK = "liquidation_cascade_risk"
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化数据融合器
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        self._coinglass_fetcher: Optional[CoinglassDataFetcher] = None
        self._init_coinglass()
        
        # 融合参数
        self.liquidation_proximity_pct = self.config.get('liquidation_proximity_pct', 0.02)  # 2%
        self.oi_surge_threshold = self.config.get('oi_surge_threshold', 0.05)  # 5%
        self.oi_drop_threshold = self.config.get('oi_drop_threshold', -0.03)  # -3%
        self.imbalance_threshold = self.config.get('imbalance_threshold', 0.3)  # 30%
    
    def _init_coinglass(self):
        """初始化Coinglass获取器（懒加载）"""
        try:
            self._coinglass_fetcher = CoinglassDataFetcher()
            if self._coinglass_fetcher.is_enabled():
                logger.info("DataFusion: Coinglass integration enabled")
            else:
                logger.info("DataFusion: Coinglass integration disabled")
        except Exception as e:
            logger.warning(f"DataFusion: Failed to initialize Coinglass: {e}")
            self._coinglass_fetcher = None
    
    def is_coinglass_enabled(self) -> bool:
        """检查Coinglass是否可用"""
        return self._coinglass_fetcher is not None and self._coinglass_fetcher.is_enabled()
    
    def fuse_data(
        self,
        symbol: str,
        binance_data: Dict,
        fetch_coinglass: bool = True
    ) -> FusionResult:
        """
        融合Binance和Coinglass数据
        
        Args:
            symbol: 交易对符号
            binance_data: Binance原始数据
            fetch_coinglass: 是否获取Coinglass数据
        
        Returns:
            FusionResult对象
        """
        # 复制原始数据
        enhanced_data = dict(binance_data)
        coinglass_tags = []
        coinglass_boost = 0
        fusion_details = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'coinglass_fetched': False
        }
        
        # 如果Coinglass不可用或不需要获取，直接返回
        if not fetch_coinglass or not self.is_coinglass_enabled():
            return FusionResult(
                enhanced_data=enhanced_data,
                coinglass_tags=coinglass_tags,
                coinglass_boost=coinglass_boost,
                coinglass_available=False,
                fusion_details=fusion_details
            )
        
        # 获取当前价格
        current_price = binance_data.get('price')
        if not current_price:
            logger.warning(f"No price in binance_data for {symbol}, skipping Coinglass fusion")
            return FusionResult(
                enhanced_data=enhanced_data,
                coinglass_tags=coinglass_tags,
                coinglass_boost=coinglass_boost,
                coinglass_available=False,
                fusion_details=fusion_details
            )
        
        # 获取Coinglass数据
        try:
            cg_metrics = self._coinglass_fetcher.fetch_all_metrics(symbol, current_price)
            if cg_metrics:
                fusion_details['coinglass_fetched'] = True
                
                # 融合数据
                tags, boost, details = self._analyze_coinglass_signals(
                    cg_metrics, current_price, binance_data
                )
                coinglass_tags.extend(tags)
                coinglass_boost += boost
                fusion_details.update(details)
                
                # 将Coinglass数据添加到enhanced_data
                enhanced_data['_coinglass'] = cg_metrics.to_dict()
                
                # 如果有聚合OI，使用更准确的值
                if cg_metrics.aggregated_oi:
                    enhanced_data['aggregated_oi'] = cg_metrics.aggregated_oi.total_oi
                    enhanced_data['aggregated_oi_change_1h'] = cg_metrics.aggregated_oi.oi_change_1h
                
                # 如果有OI加权费率，添加为参考
                if cg_metrics.oi_weighted_funding_rate is not None:
                    enhanced_data['oi_weighted_funding_rate'] = cg_metrics.oi_weighted_funding_rate
                
        except Exception as e:
            logger.error(f"Failed to fetch/process Coinglass data: {e}")
            fusion_details['error'] = str(e)
        
        return FusionResult(
            enhanced_data=enhanced_data,
            coinglass_tags=coinglass_tags,
            coinglass_boost=coinglass_boost,
            coinglass_available=True,
            fusion_details=fusion_details
        )
    
    def _analyze_coinglass_signals(
        self,
        metrics: CoinglassMetrics,
        current_price: float,
        binance_data: Dict
    ) -> Tuple[List[str], int, Dict]:
        """
        分析Coinglass数据生成信号
        
        Args:
            metrics: Coinglass指标
            current_price: 当前价格
            binance_data: Binance数据（用于交叉验证）
        
        Returns:
            (标签列表, 加分, 详情字典)
        """
        tags = []
        boost = 0
        details = {}
        
        # 1. 清算位分析
        if metrics.nearest_long_liquidation or metrics.nearest_short_liquidation:
            liq_analysis = self._analyze_liquidation_proximity(
                current_price,
                metrics.nearest_long_liquidation,
                metrics.nearest_short_liquidation
            )
            tags.extend(liq_analysis['tags'])
            boost += liq_analysis['boost']
            details['liquidation'] = liq_analysis
        
        # 2. 清算不平衡分析
        if metrics.liquidation_imbalance is not None:
            imb_analysis = self._analyze_liquidation_imbalance(
                metrics.liquidation_imbalance
            )
            tags.extend(imb_analysis['tags'])
            boost += imb_analysis['boost']
            details['liquidation_imbalance'] = imb_analysis
        
        # 3. 聚合OI分析
        if metrics.aggregated_oi:
            oi_analysis = self._analyze_aggregated_oi(
                metrics.aggregated_oi,
                binance_data.get('oi_change_1h')
            )
            tags.extend(oi_analysis['tags'])
            boost += oi_analysis['boost']
            details['aggregated_oi'] = oi_analysis
        
        # 4. 爆仓主导方向分析
        if metrics.liquidation_dominance:
            dom_analysis = self._analyze_liquidation_dominance(
                metrics.liquidation_dominance,
                binance_data
            )
            tags.extend(dom_analysis['tags'])
            boost += dom_analysis['boost']
            details['liquidation_dominance'] = dom_analysis
        
        return tags, boost, details
    
    def _analyze_liquidation_proximity(
        self,
        current_price: float,
        nearest_long: Optional[float],
        nearest_short: Optional[float]
    ) -> Dict:
        """分析清算位接近度"""
        tags = []
        boost = 0
        
        proximity_long = None
        proximity_short = None
        
        if nearest_long:
            proximity_long = (current_price - nearest_long) / current_price
            if proximity_long < self.liquidation_proximity_pct:
                tags.append(self.TAG_LIQUIDATION_CLUSTER_NEAR)
                boost -= 5  # 接近清算区，风险提示
        
        if nearest_short:
            proximity_short = (nearest_short - current_price) / current_price
            if proximity_short < self.liquidation_proximity_pct:
                tags.append(self.TAG_LIQUIDATION_CLUSTER_NEAR)
                boost -= 5
        
        return {
            'tags': tags,
            'boost': boost,
            'nearest_long': nearest_long,
            'nearest_short': nearest_short,
            'proximity_long_pct': proximity_long,
            'proximity_short_pct': proximity_short
        }
    
    def _analyze_liquidation_imbalance(self, imbalance: float) -> Dict:
        """分析清算不平衡度"""
        tags = []
        boost = 0
        
        if imbalance > self.imbalance_threshold:
            tags.append(self.TAG_LIQUIDATION_IMBALANCE_LONG)
            # 多头清算聚集 → 价格下跌风险，做空机会
            boost += 3
        elif imbalance < -self.imbalance_threshold:
            tags.append(self.TAG_LIQUIDATION_IMBALANCE_SHORT)
            # 空头清算聚集 → 价格上涨风险，做多机会
            boost += 3
        
        return {
            'tags': tags,
            'boost': boost,
            'imbalance': imbalance,
            'threshold': self.imbalance_threshold
        }
    
    def _analyze_aggregated_oi(
        self,
        aggregated_oi,
        binance_oi_change: Optional[float]
    ) -> Dict:
        """分析聚合OI"""
        tags = []
        boost = 0
        
        oi_change = aggregated_oi.oi_change_1h
        
        if oi_change is not None:
            if oi_change > self.oi_surge_threshold:
                tags.append(self.TAG_AGGREGATED_OI_SURGE)
                boost += 5  # 全市场OI激增，趋势信号
            elif oi_change < self.oi_drop_threshold:
                tags.append(self.TAG_AGGREGATED_OI_DROP)
                boost -= 3  # 全市场OI下降，趋势可能终结
        
        # 交叉验证：Binance OI vs 聚合OI
        divergence = None
        if binance_oi_change is not None and oi_change is not None:
            divergence = oi_change - binance_oi_change
        
        return {
            'tags': tags,
            'boost': boost,
            'aggregated_oi_change_1h': oi_change,
            'binance_oi_change_1h': binance_oi_change,
            'divergence': divergence
        }
    
    def _analyze_liquidation_dominance(
        self,
        dominance: str,
        binance_data: Dict
    ) -> Dict:
        """分析爆仓主导方向"""
        tags = []
        boost = 0
        
        # 多头爆仓主导 → 市场可能触底反弹
        # 空头爆仓主导 → 市场可能见顶回落
        
        price_change = binance_data.get('price_change_1h', 0) or 0
        
        if dominance == 'LONG' and price_change < -0.01:
            # 多头爆仓 + 下跌 → 可能反弹
            tags.append(self.TAG_LIQUIDATION_CASCADE_RISK)
            boost += 3  # 逆势做多信号
        elif dominance == 'SHORT' and price_change > 0.01:
            # 空头爆仓 + 上涨 → 可能回落
            tags.append(self.TAG_LIQUIDATION_CASCADE_RISK)
            boost += 3  # 逆势做空信号
        
        return {
            'tags': tags,
            'boost': boost,
            'dominance': dominance,
            'price_change_1h': price_change
        }
    
    def get_status(self) -> Dict:
        """获取融合器状态"""
        return {
            'coinglass_enabled': self.is_coinglass_enabled(),
            'coinglass_status': self._coinglass_fetcher.get_status() if self._coinglass_fetcher else None,
            'config': {
                'liquidation_proximity_pct': self.liquidation_proximity_pct,
                'oi_surge_threshold': self.oi_surge_threshold,
                'oi_drop_threshold': self.oi_drop_threshold,
                'imbalance_threshold': self.imbalance_threshold
            }
        }
