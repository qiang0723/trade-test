"""
L1 Backtest Framework

回测框架模块，用于验证L1决策的有效性

主要组件:
- HistoricalDataLoader: 历史数据加载器
- BacktestEngine: 核心回测引擎
- PerformanceAnalyzer: 绩效分析模块
- ReportGenerator: 报告生成器
"""

from .data_loader import HistoricalDataLoader
from .backtest_engine import BacktestEngine, Position, Trade
from .performance_analyzer import PerformanceAnalyzer
from .report_generator import ReportGenerator

__version__ = "1.0.0"
__all__ = [
    'HistoricalDataLoader',
    'BacktestEngine',
    'Position',
    'Trade',
    'PerformanceAnalyzer',
    'ReportGenerator'
]
