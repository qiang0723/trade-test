"""
回测框架 - 核心回测引擎

功能：
1. 遍历历史数据生成L1决策
2. 模拟仓位管理和交易执行
3. 计算P&L和绩效指标
4. 支持单一决策和双周期决策对比
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import logging

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """持仓信息"""
    direction: Decision  # LONG | SHORT
    entry_price: float
    entry_time: int
    size: float = 1.0  # 仓位大小（默认1个单位）
    
    # P3-2: 环境/置信度信息
    confidence: str = ""
    market_regime: str = ""
    alignment: str = ""
    reason_tags: List[str] = field(default_factory=list)
    
    def calculate_pnl(self, exit_price: float) -> float:
        """
        计算P&L（百分比）
        
        Args:
            exit_price: 平仓价格
        
        Returns:
            float: P&L百分比
        """
        if self.direction == Decision.LONG:
            return (exit_price - self.entry_price) / self.entry_price
        elif self.direction == Decision.SHORT:
            return (self.entry_price - exit_price) / self.entry_price
        return 0.0


@dataclass
class Trade:
    """交易记录"""
    symbol: str
    direction: Decision
    entry_time: int
    entry_price: float
    exit_time: int
    exit_price: float
    pnl: float  # P&L百分比
    pnl_amount: float  # P&L金额
    reason: str  # 平仓原因
    
    # 决策信息
    entry_confidence: str = ""
    entry_executable: bool = False
    entry_reason_tags: List[str] = field(default_factory=list)
    
    # P3-2增强：环境/置信度分类
    market_regime: str = ""           # 市场环境：trend/range/extreme
    timeframe_alignment: str = ""      # 周期对齐：aligned/conflict


class BacktestEngine:
    """
    回测引擎
    
    支持：
    - 单一决策回测
    - 双周期决策回测
    - 多种平仓策略
    """
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        position_size: float = 1.0,
        commission_rate: float = 0.001,
        slippage: float = 0.0005
    ):
        """
        初始化回测引擎
        
        Args:
            initial_capital: 初始资金
            position_size: 每次开仓大小（占资金比例）
            commission_rate: 手续费率
            slippage: 滑点
        """
        self.initial_capital = initial_capital
        self.position_size = position_size
        self.commission_rate = commission_rate
        self.slippage = slippage
        
        # 回测状态
        self.capital = initial_capital
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        
        # L1引擎
        self.engine = L1AdvisoryEngine()
        
        # ==================
        # 回测模式特殊配置
        # ==================
        
        # 1. 禁用数据时效性检查（历史数据必然"过期"）
        self.engine.thresholds['data_max_staleness_seconds'] = 315360000  # 10年
        
        # 2. 禁用决策频率控制（回测中每个tick都应独立评估）
        # 修改引擎配置
        self.engine.config['decision_control'] = {
            'min_decision_interval_seconds': 0,  # 禁用最小间隔
            'flip_cooldown_seconds': 0,           # 禁用翻转冷却
            'enable_min_interval': False,
            'enable_flip_cooldown': False
        }
        
        # 3. 禁用双周期频率控制
        self.engine.config['dual_decision_control'] = {
            'short_term_interval_seconds': 0,
            'short_term_flip_cooldown_seconds': 0,
            'medium_term_interval_seconds': 0,
            'medium_term_flip_cooldown_seconds': 0,
            'alignment_flip_cooldown_seconds': 0
        }
        
        # 4. 更新双周期决策记忆的参数
        self.engine.dual_decision_memory.short_term_interval = 0
        self.engine.dual_decision_memory.short_term_flip_cooldown = 0
        self.engine.dual_decision_memory.medium_term_interval = 0
        self.engine.dual_decision_memory.medium_term_flip_cooldown = 0
        self.engine.dual_decision_memory.alignment_flip_cooldown = 0
        
        logger.info(f"BacktestEngine initialized: capital={initial_capital}, "
                   f"position_size={position_size}, commission={commission_rate}")
        logger.info("Backtest mode: data staleness check disabled")
        logger.info("Backtest mode: decision frequency control disabled")
    
    def run_backtest(
        self,
        symbol: str,
        market_data_list: List[Dict],
        mode: str = "single",
        exit_strategy: str = "signal_reverse"
    ) -> Dict:
        """
        运行回测
        
        Args:
            symbol: 交易对
            market_data_list: 市场数据列表（按时间排序）
            mode: 回测模式 "single" | "dual"
            exit_strategy: 平仓策略
                - "signal_reverse": 信号反转时平仓
                - "stop_loss": 止损平仓（固定百分比）
                - "time_based": 固定持仓时间
        
        Returns:
            Dict: 回测结果
        """
        logger.info(f"Starting backtest: symbol={symbol}, mode={mode}, "
                   f"data_points={len(market_data_list)}")
        
        # 重置状态
        self.capital = self.initial_capital
        self.position = None
        self.trades = []
        
        # 遍历数据
        for i, market_data in enumerate(market_data_list):
            if mode == "single":
                result = self.engine.on_new_tick(symbol, market_data)
                decision = result.decision
                executable = result.executable
                confidence = result.confidence.value
                reason_tags = [tag.value for tag in result.reason_tags]
                market_regime = result.market_regime.value if hasattr(result, 'market_regime') else ""
                alignment = ""
            elif mode == "dual":
                result = self.engine.on_new_tick_dual(symbol, market_data)
                decision = result.alignment.recommended_action
                executable = result._compute_combined_executable()
                confidence = result.alignment.recommended_confidence.value
                reason_tags = result._get_combined_reason_tags()
                # P3-2: 记录市场环境和周期对齐
                market_regime = result.medium_term.market_regime.value
                alignment = "aligned" if result.alignment.is_aligned else "conflict"
            else:
                raise ValueError(f"Unknown mode: {mode}")
            
            current_price = market_data['price']
            current_time = market_data['timestamp']
            
            # 处理持仓
            if self.position is not None:
                # 检查是否需要平仓
                should_exit, exit_reason = self._should_exit(
                    decision, executable, exit_strategy, current_price, current_time
                )
                
                if should_exit:
                    self._close_position(
                        symbol, current_price, current_time, exit_reason,
                        confidence, reason_tags
                    )
            
            # 检查是否需要开仓
            if self.position is None and executable:
                if decision in [Decision.LONG, Decision.SHORT]:
                    self._open_position(
                        symbol, decision, current_price, current_time,
                        confidence, executable, reason_tags,
                        market_regime, alignment
                    )
            
            # 进度日志
            if (i + 1) % 1000 == 0:
                logger.info(f"Processed {i + 1}/{len(market_data_list)} data points")
        
        # 强制平仓最后的持仓
        if self.position is not None and len(market_data_list) > 0:
            last_data = market_data_list[-1]
            self._close_position(
                symbol, last_data['price'], last_data['timestamp'],
                "backtest_end", "", []
            )
        
        # 计算绩效
        performance = self._calculate_performance(market_data_list)
        
        logger.info(f"Backtest completed: trades={len(self.trades)}, "
                   f"final_capital={self.capital:.2f}")
        
        return {
            'symbol': symbol,
            'mode': mode,
            'exit_strategy': exit_strategy,
            'initial_capital': self.initial_capital,
            'final_capital': self.capital,
            'trades': self.trades,
            'performance': performance
        }
    
    def _open_position(
        self,
        symbol: str,
        direction: Decision,
        price: float,
        timestamp: int,
        confidence: str,
        executable: bool,
        reason_tags: List[str],
        market_regime: str = "",
        alignment: str = ""
    ):
        """开仓"""
        # 考虑滑点
        entry_price = price * (1 + self.slippage) if direction == Decision.LONG else price * (1 - self.slippage)
        
        # 计算仓位大小
        position_value = self.capital * self.position_size
        size = position_value / entry_price
        
        # 扣除手续费
        commission = position_value * self.commission_rate
        self.capital -= commission
        
        self.position = Position(
            direction=direction,
            entry_price=entry_price,
            entry_time=timestamp,
            size=size,
            confidence=confidence,
            market_regime=market_regime,
            alignment=alignment,
            reason_tags=reason_tags
        )
        
        logger.debug(f"Open {direction.value} at {entry_price:.2f}, size={size:.4f}, "
                    f"confidence={confidence}, regime={market_regime}")
    
    def _close_position(
        self,
        symbol: str,
        price: float,
        timestamp: int,
        reason: str,
        confidence: str,
        reason_tags: List[str]
    ):
        """平仓"""
        if self.position is None:
            return
        
        # 考虑滑点
        exit_price = price * (1 - self.slippage) if self.position.direction == Decision.LONG else price * (1 + self.slippage)
        
        # 计算P&L
        pnl_pct = self.position.calculate_pnl(exit_price)
        position_value = self.capital * self.position_size
        pnl_amount = position_value * pnl_pct
        
        # 扣除手续费
        commission = position_value * self.commission_rate
        self.capital += pnl_amount - commission
        
        # 记录交易（P3-2: 包含环境/置信度信息）
        trade = Trade(
            symbol=symbol,
            direction=self.position.direction,
            entry_time=self.position.entry_time,
            entry_price=self.position.entry_price,
            exit_time=timestamp,
            exit_price=exit_price,
            pnl=pnl_pct,
            pnl_amount=pnl_amount - commission,
            reason=reason,
            entry_confidence=self.position.confidence,
            entry_executable=True,
            entry_reason_tags=self.position.reason_tags,
            market_regime=self.position.market_regime,
            timeframe_alignment=self.position.alignment
        )
        self.trades.append(trade)
        
        logger.debug(f"Close {self.position.direction.value} at {exit_price:.2f}, "
                    f"pnl={pnl_pct*100:.2f}%, reason={reason}")
        
        self.position = None
    
    def _should_exit(
        self,
        current_decision: Decision,
        executable: bool,
        strategy: str,
        current_price: float,
        current_time: int
    ) -> tuple:
        """
        判断是否需要平仓
        
        Returns:
            (should_exit, reason)
        """
        if self.position is None:
            return (False, "")
        
        # 策略1: 信号反转
        if strategy == "signal_reverse":
            # 持多时，出现做空信号或不交易信号
            if self.position.direction == Decision.LONG:
                if current_decision in [Decision.SHORT, Decision.NO_TRADE]:
                    return (True, "signal_reverse")
            # 持空时，出现做多信号或不交易信号
            elif self.position.direction == Decision.SHORT:
                if current_decision in [Decision.LONG, Decision.NO_TRADE]:
                    return (True, "signal_reverse")
        
        # 策略2: 止损（5%）
        elif strategy == "stop_loss":
            pnl = self.position.calculate_pnl(current_price)
            if pnl < -0.05:  # 亏损超过5%
                return (True, "stop_loss")
            # 同时检查信号反转
            if self.position.direction == Decision.LONG and current_decision == Decision.SHORT:
                return (True, "signal_reverse")
            elif self.position.direction == Decision.SHORT and current_decision == Decision.LONG:
                return (True, "signal_reverse")
        
        # 策略3: 固定持仓时间（1小时 = 60分钟 = 60000ms）
        elif strategy == "time_based":
            hold_time = current_time - self.position.entry_time
            if hold_time >= 3600000:  # 1小时
                return (True, "time_based")
        
        return (False, "")
    
    def _calculate_performance(self, market_data_list: List[Dict]) -> Dict:
        """
        计算绩效指标
        
        Returns:
            Dict: 绩效指标
        """
        if not self.trades:
            # Buy & Hold 基准（即使没有交易也要计算）
            if market_data_list:
                start_price = market_data_list[0]['price']
                end_price = market_data_list[-1]['price']
                buy_hold_return = (end_price - start_price) / start_price
            else:
                buy_hold_return = 0.0
                
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'total_return': 0.0,
                'buy_hold_return': buy_hold_return,
                'excess_return': 0.0 - buy_hold_return,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'final_capital': self.capital
            }
        
        # 基础统计
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]
        
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
        
        # 收益统计
        total_return = (self.capital - self.initial_capital) / self.initial_capital
        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0.0
        avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0.0
        
        # 计算最大回撤
        capital_curve = [self.initial_capital]
        current_capital = self.initial_capital
        
        for trade in self.trades:
            current_capital += trade.pnl_amount
            capital_curve.append(current_capital)
        
        max_drawdown = 0.0
        peak = capital_curve[0]
        for value in capital_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 计算夏普比率（简化版）
        if len(self.trades) > 1:
            returns = [t.pnl for t in self.trades]
            avg_return = sum(returns) / len(returns)
            std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
            sharpe_ratio = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0.0
        else:
            sharpe_ratio = 0.0
        
        # Buy & Hold 基准
        if market_data_list:
            start_price = market_data_list[0]['price']
            end_price = market_data_list[-1]['price']
            buy_hold_return = (end_price - start_price) / start_price
        else:
            buy_hold_return = 0.0
        
        # P3-2: 分类绩效分析
        categorized = self._calculate_categorized_performance()
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else 0.0,
            'total_return': total_return,
            'buy_hold_return': buy_hold_return,
            'excess_return': total_return - buy_hold_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'final_capital': self.capital,
            # P3-2: 分类绩效
            'by_confidence': categorized['by_confidence'],
            'by_regime': categorized['by_regime'],
            'by_alignment': categorized['by_alignment'],
            'by_direction': categorized['by_direction']
        }
    
    def _calculate_categorized_performance(self) -> Dict:
        """
        P3-2: 按环境/置信度/对齐分类计算绩效
        
        Returns:
            分类绩效字典
        """
        from collections import defaultdict
        
        def calc_stats(trades_list: List[Trade]) -> Dict:
            """计算一组交易的统计"""
            if not trades_list:
                return {'count': 0, 'win_rate': 0.0, 'avg_pnl': 0.0, 'total_pnl': 0.0}
            
            wins = [t for t in trades_list if t.pnl > 0]
            return {
                'count': len(trades_list),
                'win_rate': len(wins) / len(trades_list),
                'avg_pnl': sum(t.pnl for t in trades_list) / len(trades_list),
                'total_pnl': sum(t.pnl for t in trades_list)
            }
        
        # 按置信度分组
        by_confidence = defaultdict(list)
        for t in self.trades:
            conf = t.entry_confidence.lower() if t.entry_confidence else 'unknown'
            by_confidence[conf].append(t)
        
        # 按市场环境分组
        by_regime = defaultdict(list)
        for t in self.trades:
            regime = t.market_regime.lower() if t.market_regime else 'unknown'
            by_regime[regime].append(t)
        
        # 按周期对齐分组
        by_alignment = defaultdict(list)
        for t in self.trades:
            align = t.timeframe_alignment.lower() if t.timeframe_alignment else 'unknown'
            by_alignment[align].append(t)
        
        # 按方向分组
        by_direction = defaultdict(list)
        for t in self.trades:
            direction = t.direction.value if t.direction else 'unknown'
            by_direction[direction].append(t)
        
        return {
            'by_confidence': {k: calc_stats(v) for k, v in by_confidence.items()},
            'by_regime': {k: calc_stats(v) for k, v in by_regime.items()},
            'by_alignment': {k: calc_stats(v) for k, v in by_alignment.items()},
            'by_direction': {k: calc_stats(v) for k, v in by_direction.items()}
        }
