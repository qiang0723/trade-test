"""
止损止盈计算服务

L1信号提示层 - 基于波动率的动态止损止盈建议

设计原则：
1. 止损基于波动率（ATR近似）：避免被正常波动扫出
2. 止盈基于盈亏比：确保合理的风险回报
3. 根据市场环境调整：TREND环境止盈更宽，RANGE环境止盈更窄

计算逻辑：
- 止损 = 入场价 × (1 ± 波动率 × 止损倍数)
- 止盈 = 入场价 × (1 ± 波动率 × 止盈倍数)
- 默认盈亏比 = 2:1 (TREND) 或 1.5:1 (RANGE)
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from models.enums import Decision, MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class StopLossTarget:
    """止损止盈建议"""
    
    # 止损
    stop_loss_price: float          # 止损价格
    stop_loss_pct: float            # 止损百分比（相对入场价）
    
    # 止盈
    take_profit_price: float        # 止盈价格
    take_profit_pct: float          # 止盈百分比（相对入场价）
    
    # 盈亏比
    risk_reward_ratio: float        # 盈亏比
    
    # 计算依据
    volatility_used: float          # 使用的波动率
    calculation_method: str         # 计算方法说明
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'stop_loss_price': round(self.stop_loss_price, 4),
            'stop_loss_pct': round(self.stop_loss_pct * 100, 2),  # 转为百分比显示
            'take_profit_price': round(self.take_profit_price, 4),
            'take_profit_pct': round(self.take_profit_pct * 100, 2),  # 转为百分比显示
            'risk_reward_ratio': round(self.risk_reward_ratio, 2),
            'volatility_used': round(self.volatility_used * 100, 2),  # 转为百分比显示
            'calculation_method': self.calculation_method
        }


class StopLossService:
    """止损止盈计算服务"""
    
    # 默认配置（基于2026-01-30回测优化 v3 - P0优化后）
    # 全局最优参数：止损0.8%，止盈1.6%（盈亏比2.0:1），预期收益+0.364%/笔
    # TREND环境最优：止损1.5%，盈亏比1.5:1，预期收益+0.484%/笔
    CONFIG = {
        # 止损倍数（相对于波动率）
        'stop_loss_multiplier': 1.0,
        
        # 止盈倍数配置（根据市场环境）- 基于回测优化
        'take_profit_multiplier': {
            'trend': 2.0,      # TREND环境：盈亏比2.0:1（全局最优）
            'range': 2.0,      # RANGE环境：盈亏比2.0:1（全局最优）
            'extreme': 1.5,    # EXTREME环境：盈亏比1.5:1（保守）
        },
        
        # 最小/最大止损限制 - 回测优化
        'min_stop_loss_pct': 0.008,   # 最小止损 0.8%（全局最优）
        'max_stop_loss_pct': 0.012,   # 最大止损 1.2%（优化后）
        
        # 默认波动率（当无法计算时使用）
        'default_volatility': 0.008,  # 0.8%（全局最优止损）
    }
    
    def __init__(self, config: Dict = None):
        """
        初始化止损止盈服务
        
        Args:
            config: 可选的配置覆盖
        """
        self.config = {**self.CONFIG, **(config or {})}
    
    def calculate(
        self,
        entry_price: float,
        direction: Decision,
        regime: MarketRegime,
        price_change_1h: Optional[float] = None,
        price_change_15m: Optional[float] = None,
        price_change_5m: Optional[float] = None
    ) -> Optional[StopLossTarget]:
        """
        计算止损止盈建议
        
        Args:
            entry_price: 入场价格
            direction: 交易方向（LONG/SHORT）
            regime: 市场环境
            price_change_1h: 1小时价格变化（用于估算波动率）
            price_change_15m: 15分钟价格变化
            price_change_5m: 5分钟价格变化
        
        Returns:
            StopLossTarget 止损止盈建议，或 None（NO_TRADE时）
        """
        # NO_TRADE 不计算止损止盈
        if direction == Decision.NO_TRADE:
            return None
        
        if entry_price is None or entry_price <= 0:
            logger.warning("Invalid entry price for stop loss calculation")
            return None
        
        # Step 1: 估算波动率（基于价格变化）
        volatility = self._estimate_volatility(
            price_change_1h, price_change_15m, price_change_5m
        )
        
        # Step 2: 计算止损距离
        stop_loss_pct = volatility * self.config['stop_loss_multiplier']
        
        # 应用止损限制
        stop_loss_pct = max(stop_loss_pct, self.config['min_stop_loss_pct'])
        stop_loss_pct = min(stop_loss_pct, self.config['max_stop_loss_pct'])
        
        # Step 3: 计算止盈距离（根据市场环境）
        regime_key = regime.value.lower() if regime else 'range'
        tp_multiplier = self.config['take_profit_multiplier'].get(
            regime_key, 
            self.config['take_profit_multiplier']['range']
        )
        take_profit_pct = stop_loss_pct * tp_multiplier / self.config['stop_loss_multiplier']
        
        # Step 4: 计算具体价格
        if direction == Decision.LONG:
            # LONG: 止损在下方，止盈在上方
            stop_loss_price = entry_price * (1 - stop_loss_pct)
            take_profit_price = entry_price * (1 + take_profit_pct)
        else:
            # SHORT: 止损在上方，止盈在下方
            stop_loss_price = entry_price * (1 + stop_loss_pct)
            take_profit_price = entry_price * (1 - take_profit_pct)
        
        # Step 5: 计算盈亏比
        risk_reward_ratio = take_profit_pct / stop_loss_pct if stop_loss_pct > 0 else 0
        
        # 构建计算方法说明
        method_parts = []
        if price_change_1h is not None:
            method_parts.append("1h波动")
        if price_change_15m is not None:
            method_parts.append("15m波动")
        if price_change_5m is not None:
            method_parts.append("5m波动")
        
        calculation_method = f"基于{'+'.join(method_parts) if method_parts else '默认'}波动率"
        
        return StopLossTarget(
            stop_loss_price=stop_loss_price,
            stop_loss_pct=stop_loss_pct,
            take_profit_price=take_profit_price,
            take_profit_pct=take_profit_pct,
            risk_reward_ratio=risk_reward_ratio,
            volatility_used=volatility,
            calculation_method=calculation_method
        )
    
    def _estimate_volatility(
        self,
        price_change_1h: Optional[float],
        price_change_15m: Optional[float],
        price_change_5m: Optional[float]
    ) -> float:
        """
        估算波动率
        
        使用多周期价格变化的加权平均来估算当前波动率
        
        Args:
            price_change_1h: 1小时价格变化
            price_change_15m: 15分钟价格变化
            price_change_5m: 5分钟价格变化
        
        Returns:
            估算的波动率（小数格式）
        """
        volatilities = []
        weights = []
        
        # 1小时波动率（权重最高，更稳定）
        if price_change_1h is not None:
            volatilities.append(abs(price_change_1h))
            weights.append(0.5)
        
        # 15分钟波动率（年化后与1h对比）
        if price_change_15m is not None:
            # 15m波动率 × 2 近似1h波动率
            volatilities.append(abs(price_change_15m) * 2)
            weights.append(0.3)
        
        # 5分钟波动率（年化后与1h对比）
        if price_change_5m is not None:
            # 5m波动率 × sqrt(12) ≈ 3.46 近似1h波动率
            volatilities.append(abs(price_change_5m) * 3.5)
            weights.append(0.2)
        
        if not volatilities:
            # 无数据时使用默认值
            return self.config['default_volatility']
        
        # 加权平均
        total_weight = sum(weights)
        weighted_volatility = sum(v * w for v, w in zip(volatilities, weights)) / total_weight
        
        # 确保最小波动率
        return max(weighted_volatility, self.config['default_volatility'] * 0.5)
    
    @staticmethod
    def format_for_display(sl_target: StopLossTarget, symbol: str) -> str:
        """
        格式化止损止盈信息用于显示
        
        Args:
            sl_target: 止损止盈建议
            symbol: 交易对符号
        
        Returns:
            格式化的字符串
        """
        if sl_target is None:
            return "无止损止盈建议"
        
        return (
            f"止损: {sl_target.stop_loss_price:.4f} (-{sl_target.stop_loss_pct*100:.2f}%) | "
            f"止盈: {sl_target.take_profit_price:.4f} (+{sl_target.take_profit_pct*100:.2f}%) | "
            f"盈亏比: {sl_target.risk_reward_ratio:.1f}:1"
        )
