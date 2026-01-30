"""
L1 Advisory Engine - 动态阈值调整模块

P1-1优化：基于市场波动率动态调整阈值

设计原则：
1. 高波动市场：放宽阈值，避免过度敏感
2. 低波动市场：收紧阈值，捕捉微弱信号
3. 保持阈值在合理范围内（有上下限）
"""

from typing import Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class VolatilityRegime:
    """波动率区间"""
    LOW = "low"          # 低波动（< 0.5%/1h）
    NORMAL = "normal"    # 正常波动（0.5% - 1.5%/1h）
    HIGH = "high"        # 高波动（> 1.5%/1h）
    EXTREME = "extreme"  # 极端波动（> 3%/1h）


@dataclass
class DynamicThresholdConfig:
    """动态阈值配置"""
    # 波动率区间划分
    low_volatility: float = 0.005      # 0.5%
    normal_volatility: float = 0.015   # 1.5%
    high_volatility: float = 0.03      # 3%
    
    # 调整系数
    low_vol_multiplier: float = 0.7    # 低波动时收紧阈值
    high_vol_multiplier: float = 1.3   # 高波动时放宽阈值
    extreme_vol_multiplier: float = 1.6  # 极端波动时大幅放宽
    
    # 阈值上下限（防止过度调整）
    min_multiplier: float = 0.5        # 最小调整系数
    max_multiplier: float = 2.0        # 最大调整系数


class DynamicThresholdAdjuster:
    """
    动态阈值调整器
    
    根据市场波动率动态调整以下阈值：
    - 价格变化阈值（price_change_*）
    - OI变化阈值（oi_change_*）
    - 放量阈值（volume_ratio_*）
    """
    
    # 可调整的阈值键
    ADJUSTABLE_KEYS = [
        # MultiTF阈值
        'min_price_change',
        'max_price_change',
        'min_oi_change',
        # 信号增强阈值
        'divergence_price_threshold',
        'divergence_oi_threshold',
        # 弱信号阈值
        'range_weak_imbalance',
        'range_weak_oi',
    ]
    
    def __init__(self, config: Optional[DynamicThresholdConfig] = None):
        """
        初始化动态阈值调整器
        
        Args:
            config: 配置对象，None则使用默认配置
        """
        self.config = config or DynamicThresholdConfig()
        self._volatility_history = []  # 历史波动率记录
        self._max_history = 60  # 保留最近60个数据点
    
    def estimate_volatility(
        self,
        price_change_1h: Optional[float],
        price_change_15m: Optional[float] = None,
        price_change_5m: Optional[float] = None
    ) -> float:
        """
        估算当前市场波动率
        
        使用多周期价格变化的加权平均：
        - 1h权重最高（代表中期波动）
        - 15m次之
        - 5m权重最低
        
        Args:
            price_change_1h: 1小时价格变化（小数格式）
            price_change_15m: 15分钟价格变化
            price_change_5m: 5分钟价格变化
        
        Returns:
            估算的波动率（绝对值，小数格式）
        """
        volatilities = []
        weights = []
        
        if price_change_1h is not None:
            volatilities.append(abs(price_change_1h))
            weights.append(0.5)  # 1h权重50%
        
        if price_change_15m is not None:
            # 15m变化年化到1h（乘以4）
            volatilities.append(abs(price_change_15m) * 2)
            weights.append(0.3)  # 15m权重30%
        
        if price_change_5m is not None:
            # 5m变化年化到1h（乘以12）
            volatilities.append(abs(price_change_5m) * 4)
            weights.append(0.2)  # 5m权重20%
        
        if not volatilities:
            # 无数据时返回默认波动率
            return self.config.normal_volatility
        
        # 加权平均
        total_weight = sum(weights)
        weighted_volatility = sum(v * w for v, w in zip(volatilities, weights)) / total_weight
        
        return weighted_volatility
    
    def get_volatility_regime(self, volatility: float) -> str:
        """
        判断波动率区间
        
        Args:
            volatility: 波动率值
        
        Returns:
            波动率区间标识
        """
        if volatility >= self.config.high_volatility:
            return VolatilityRegime.EXTREME
        elif volatility >= self.config.normal_volatility:
            return VolatilityRegime.HIGH
        elif volatility >= self.config.low_volatility:
            return VolatilityRegime.NORMAL
        else:
            return VolatilityRegime.LOW
    
    def get_adjustment_multiplier(self, volatility: float) -> float:
        """
        根据波动率获取阈值调整系数
        
        Args:
            volatility: 当前波动率
        
        Returns:
            调整系数（>1表示放宽，<1表示收紧）
        """
        regime = self.get_volatility_regime(volatility)
        
        if regime == VolatilityRegime.EXTREME:
            multiplier = self.config.extreme_vol_multiplier
        elif regime == VolatilityRegime.HIGH:
            multiplier = self.config.high_vol_multiplier
        elif regime == VolatilityRegime.LOW:
            multiplier = self.config.low_vol_multiplier
        else:
            multiplier = 1.0  # 正常波动不调整
        
        # 应用上下限
        multiplier = max(self.config.min_multiplier, 
                        min(self.config.max_multiplier, multiplier))
        
        return multiplier
    
    def adjust_thresholds(
        self,
        base_thresholds: Dict,
        price_change_1h: Optional[float],
        price_change_15m: Optional[float] = None,
        price_change_5m: Optional[float] = None
    ) -> Dict:
        """
        根据市场波动率调整阈值
        
        Args:
            base_thresholds: 基础阈值字典
            price_change_1h: 1小时价格变化
            price_change_15m: 15分钟价格变化
            price_change_5m: 5分钟价格变化
        
        Returns:
            调整后的阈值字典
        """
        # 估算波动率
        volatility = self.estimate_volatility(
            price_change_1h, price_change_15m, price_change_5m
        )
        
        # 获取调整系数
        multiplier = self.get_adjustment_multiplier(volatility)
        regime = self.get_volatility_regime(volatility)
        
        # 复制阈值字典
        adjusted = dict(base_thresholds)
        
        # 记录调整信息
        adjusted['_dynamic_adjustment'] = {
            'volatility': volatility,
            'regime': regime,
            'multiplier': multiplier
        }
        
        # 只有在非正常波动时才调整
        if multiplier != 1.0:
            for key in self.ADJUSTABLE_KEYS:
                if key in adjusted:
                    original = adjusted[key]
                    adjusted[key] = original * multiplier
                    logger.debug(f"Dynamic adjust: {key} {original:.4f} -> {adjusted[key]:.4f} (x{multiplier:.2f})")
        
        logger.info(f"Dynamic threshold: volatility={volatility:.4f}, regime={regime}, multiplier={multiplier:.2f}")
        
        return adjusted
    
    def update_history(self, volatility: float):
        """
        更新波动率历史记录（用于平滑）
        
        Args:
            volatility: 当前波动率
        """
        self._volatility_history.append(volatility)
        if len(self._volatility_history) > self._max_history:
            self._volatility_history.pop(0)
    
    def get_smoothed_volatility(self) -> Optional[float]:
        """
        获取平滑后的波动率（历史均值）
        
        Returns:
            平滑波动率或None（数据不足）
        """
        if len(self._volatility_history) < 5:
            return None
        
        return sum(self._volatility_history) / len(self._volatility_history)
