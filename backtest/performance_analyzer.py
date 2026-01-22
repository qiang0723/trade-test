"""
回测框架 - 绩效分析模块

功能：
1. 详细的绩效指标计算
2. 交易分析（胜率、盈亏比等）
3. 时间序列分析
4. 对比分析（单一 vs 双周期）
"""

from typing import Dict, List
from datetime import datetime
import json


class PerformanceAnalyzer:
    """
    绩效分析器
    
    提供详细的回测结果分析
    """
    
    @staticmethod
    def analyze_trades(trades: List) -> Dict:
        """
        分析交易记录
        
        Args:
            trades: 交易列表
        
        Returns:
            Dict: 详细分析结果
        """
        if not trades:
            return {
                'total_trades': 0,
                'message': 'No trades executed'
            }
        
        # 基础统计
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]
        
        long_trades = [t for t in trades if t.direction.value == 'long']
        short_trades = [t for t in trades if t.direction.value == 'short']
        
        # 胜率分析
        win_rate = len(winning_trades) / total_trades
        long_win_rate = len([t for t in long_trades if t.pnl > 0]) / len(long_trades) if long_trades else 0
        short_win_rate = len([t for t in short_trades if t.pnl > 0]) / len(short_trades) if short_trades else 0
        
        # 盈亏分析
        total_profit = sum(t.pnl_amount for t in winning_trades)
        total_loss = sum(t.pnl_amount for t in losing_trades)
        net_profit = total_profit + total_loss
        
        avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        max_win = max((t.pnl for t in winning_trades), default=0)
        max_loss = min((t.pnl for t in losing_trades), default=0)
        
        # 持仓时间分析
        hold_times = [(t.exit_time - t.entry_time) / 60000 for t in trades]  # 转换为分钟
        avg_hold_time = sum(hold_times) / len(hold_times)
        
        # 平仓原因统计
        exit_reasons = {}
        for t in trades:
            exit_reasons[t.reason] = exit_reasons.get(t.reason, 0) + 1
        
        # 连续盈亏分析
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0
        
        for t in trades:
            if t.pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)
        
        return {
            'total_trades': total_trades,
            'long_trades': len(long_trades),
            'short_trades': len(short_trades),
            
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'long_win_rate': long_win_rate,
            'short_win_rate': short_win_rate,
            
            'total_profit': total_profit,
            'total_loss': total_loss,
            'net_profit': net_profit,
            
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_win': max_win,
            'max_loss': max_loss,
            'profit_factor': abs(total_profit / total_loss) if total_loss != 0 else 0,
            
            'avg_hold_time_minutes': avg_hold_time,
            'exit_reasons': exit_reasons,
            
            'max_consecutive_wins': max_consecutive_wins,
            'max_consecutive_losses': max_consecutive_losses
        }
    
    @staticmethod
    def calculate_risk_metrics(trades: List, initial_capital: float) -> Dict:
        """
        计算风险指标
        
        Args:
            trades: 交易列表
            initial_capital: 初始资金
        
        Returns:
            Dict: 风险指标
        """
        if not trades:
            return {}
        
        # 构建资金曲线
        capital_curve = [initial_capital]
        current_capital = initial_capital
        
        for trade in trades:
            current_capital += trade.pnl_amount
            capital_curve.append(current_capital)
        
        # 最大回撤
        max_drawdown = 0.0
        max_drawdown_duration = 0
        peak = capital_curve[0]
        peak_idx = 0
        current_drawdown_duration = 0
        
        for i, value in enumerate(capital_curve):
            if value > peak:
                peak = value
                peak_idx = i
                current_drawdown_duration = 0
            else:
                drawdown = (peak - value) / peak
                current_drawdown_duration = i - peak_idx
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_duration = current_drawdown_duration
        
        # 收益回撤比
        total_return = (capital_curve[-1] - initial_capital) / initial_capital
        calmar_ratio = total_return / max_drawdown if max_drawdown > 0 else 0
        
        # 波动率
        returns = [t.pnl for t in trades]
        avg_return = sum(returns) / len(returns)
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5
        
        # 夏普比率（年化）
        sharpe_ratio = (avg_return / volatility) * (252 ** 0.5) if volatility > 0 else 0
        
        # 索提诺比率（只考虑下行波动）
        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            downside_variance = sum(r ** 2 for r in downside_returns) / len(downside_returns)
            downside_deviation = downside_variance ** 0.5
            sortino_ratio = (avg_return / downside_deviation) * (252 ** 0.5) if downside_deviation > 0 else 0
        else:
            sortino_ratio = 0
        
        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_duration_trades': max_drawdown_duration,
            'calmar_ratio': calmar_ratio,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'total_return': total_return
        }
    
    @staticmethod
    def compare_strategies(result1: Dict, result2: Dict) -> Dict:
        """
        对比两个策略的结果
        
        Args:
            result1: 策略1回测结果
            result2: 策略2回测结果
        
        Returns:
            Dict: 对比分析
        """
        perf1 = result1['performance']
        perf2 = result2['performance']
        
        comparison = {
            'strategy1': result1['mode'],
            'strategy2': result2['mode'],
            
            'total_return_diff': perf1['total_return'] - perf2['total_return'],
            'win_rate_diff': perf1['win_rate'] - perf2['win_rate'],
            'sharpe_ratio_diff': perf1['sharpe_ratio'] - perf2['sharpe_ratio'],
            'max_drawdown_diff': perf1['max_drawdown'] - perf2['max_drawdown'],
            
            'trades_diff': perf1['total_trades'] - perf2['total_trades'],
            
            'better_return': result1['mode'] if perf1['total_return'] > perf2['total_return'] else result2['mode'],
            'better_sharpe': result1['mode'] if perf1['sharpe_ratio'] > perf2['sharpe_ratio'] else result2['mode'],
            'lower_drawdown': result1['mode'] if perf1['max_drawdown'] < perf2['max_drawdown'] else result2['mode'],
            
            'strategy1_metrics': {
                'total_return': perf1['total_return'],
                'win_rate': perf1['win_rate'],
                'sharpe_ratio': perf1['sharpe_ratio'],
                'max_drawdown': perf1['max_drawdown'],
                'total_trades': perf1['total_trades']
            },
            'strategy2_metrics': {
                'total_return': perf2['total_return'],
                'win_rate': perf2['win_rate'],
                'sharpe_ratio': perf2['sharpe_ratio'],
                'max_drawdown': perf2['max_drawdown'],
                'total_trades': perf2['total_trades']
            }
        }
        
        return comparison
    
    @staticmethod
    def generate_summary(result: Dict) -> str:
        """
        生成回测摘要文本
        
        Args:
            result: 回测结果
        
        Returns:
            str: 格式化的摘要文本
        """
        perf = result['performance']
        
        summary = f"""
========================================
回测摘要报告
========================================

基本信息:
  交易对: {result['symbol']}
  模式: {result['mode']}
  平仓策略: {result['exit_strategy']}
  初始资金: ${result['initial_capital']:,.2f}
  最终资金: ${result['final_capital']:,.2f}

绩效指标:
  总收益率: {perf['total_return']*100:.2f}%
  Buy & Hold收益: {perf['buy_hold_return']*100:.2f}%
  超额收益: {perf['excess_return']*100:.2f}%
  
  总交易次数: {perf['total_trades']}
  盈利交易: {perf['winning_trades']}
  亏损交易: {perf['losing_trades']}
  胜率: {perf['win_rate']*100:.2f}%
  
  平均盈利: {perf['avg_win']*100:.2f}%
  平均亏损: {perf['avg_loss']*100:.2f}%
  盈亏比: {perf['profit_factor']:.2f}
  
风险指标:
  最大回撤: {perf['max_drawdown']*100:.2f}%
  夏普比率: {perf['sharpe_ratio']:.2f}

========================================
"""
        return summary
