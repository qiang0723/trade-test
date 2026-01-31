"""
P3-3: 参数敏感性分析与自动优化模块

功能：
1. 参数敏感性分析 - 分析各参数对绩效的影响
2. 网格搜索优化 - 在参数空间中寻找最优组合
3. 敏感度报告 - 生成参数敏感度分析报告
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass, field
from itertools import product
import logging
import copy

logger = logging.getLogger(__name__)


@dataclass
class ParameterRange:
    """参数范围定义"""
    name: str                      # 参数名（支持嵌套，如 "market_regime.extreme_price_change_1h"）
    min_value: float               # 最小值
    max_value: float               # 最大值
    step: float                    # 步长
    description: str = ""          # 参数说明
    
    def get_values(self) -> List[float]:
        """获取参数可能取值列表"""
        values = []
        current = self.min_value
        while current <= self.max_value:
            values.append(round(current, 6))
            current += self.step
        return values


@dataclass
class OptimizationResult:
    """优化结果"""
    best_params: Dict[str, float]           # 最优参数
    best_score: float                        # 最优得分
    best_performance: Dict                   # 最优绩效详情
    all_results: List[Dict] = field(default_factory=list)  # 所有结果
    sensitivity_report: Dict = field(default_factory=dict)  # 敏感性报告


class ParameterOptimizer:
    """
    参数优化器
    
    支持：
    - 网格搜索
    - 敏感性分析
    - 最优参数推荐
    """
    
    # 常用参数范围预设
    PRESET_RANGES = {
        # 市场环境阈值
        'extreme_price_change_1h': ParameterRange(
            name='market_regime.extreme_price_change_1h',
            min_value=0.03, max_value=0.08, step=0.01,
            description='极端行情价格变化阈值'
        ),
        'trend_price_change_6h': ParameterRange(
            name='market_regime.trend_price_change_6h',
            min_value=0.02, max_value=0.05, step=0.005,
            description='趋势市场6h价格变化阈值'
        ),
        
        # 风险控制阈值
        'liquidation_price_change': ParameterRange(
            name='risk_exposure.liquidation.price_change',
            min_value=0.03, max_value=0.08, step=0.01,
            description='清算阶段价格变化阈值'
        ),
        'crowding_funding_abs': ParameterRange(
            name='risk_exposure.crowding.funding_abs',
            min_value=0.0005, max_value=0.002, step=0.0005,
            description='拥挤风险资金费率阈值'
        ),
        
        # 止损止盈
        'stop_loss_pct': ParameterRange(
            name='stop_loss.min_stop_loss_pct',
            min_value=0.005, max_value=0.02, step=0.002,
            description='最小止损百分比'
        ),
        'take_profit_multiplier': ParameterRange(
            name='stop_loss.take_profit_multiplier',
            min_value=1.5, max_value=3.0, step=0.5,
            description='止盈倍数'
        ),
    }
    
    def __init__(
        self,
        backtest_engine,
        base_config: Dict,
        scoring_function: Optional[Callable] = None
    ):
        """
        初始化优化器
        
        Args:
            backtest_engine: 回测引擎实例
            base_config: 基础配置
            scoring_function: 自定义评分函数（接收performance字典，返回分数）
        """
        self.backtest_engine = backtest_engine
        self.base_config = copy.deepcopy(base_config)
        self.scoring_function = scoring_function or self._default_scoring
    
    def _default_scoring(self, performance: Dict) -> float:
        """
        默认评分函数（综合考虑收益、风险、胜率）
        
        评分 = 总收益 * 夏普比率 * 胜率 / (1 + 最大回撤)
        """
        total_return = performance.get('total_return', 0)
        sharpe = performance.get('sharpe_ratio', 0)
        win_rate = performance.get('win_rate', 0)
        max_dd = performance.get('max_drawdown', 0)
        
        # 惩罚负收益
        if total_return < 0:
            return total_return * (1 + max_dd)
        
        return total_return * max(sharpe, 0.1) * max(win_rate, 0.1) / (1 + max_dd)
    
    def _set_nested_value(self, config: Dict, path: str, value: float):
        """设置嵌套配置值"""
        keys = path.split('.')
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
    
    def _get_nested_value(self, config: Dict, path: str, default=None):
        """获取嵌套配置值"""
        keys = path.split('.')
        current = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    def grid_search(
        self,
        symbol: str,
        market_data_list: List[Dict],
        param_ranges: List[ParameterRange],
        mode: str = "dual"
    ) -> OptimizationResult:
        """
        网格搜索优化
        
        Args:
            symbol: 交易对
            market_data_list: 市场数据列表
            param_ranges: 参数范围列表
            mode: 回测模式
            
        Returns:
            OptimizationResult
        """
        logger.info(f"Starting grid search with {len(param_ranges)} parameters")
        
        # 生成参数组合
        param_names = [p.name for p in param_ranges]
        param_values = [p.get_values() for p in param_ranges]
        combinations = list(product(*param_values))
        
        logger.info(f"Total combinations to test: {len(combinations)}")
        
        all_results = []
        best_score = float('-inf')
        best_params = {}
        best_performance = {}
        
        for i, combo in enumerate(combinations):
            # 构建配置
            test_config = copy.deepcopy(self.base_config)
            params = dict(zip(param_names, combo))
            
            for name, value in params.items():
                self._set_nested_value(test_config, name, value)
            
            # 更新引擎配置
            self.backtest_engine.engine.config = test_config
            self.backtest_engine.engine.thresholds = self.backtest_engine.engine._flatten_thresholds(test_config)
            
            # 运行回测
            try:
                result = self.backtest_engine.run_backtest(
                    symbol, market_data_list, mode=mode
                )
                performance = result['performance']
                score = self.scoring_function(performance)
                
                all_results.append({
                    'params': params,
                    'score': score,
                    'performance': performance
                })
                
                if score > best_score:
                    best_score = score
                    best_params = params.copy()
                    best_performance = performance.copy()
                    
            except Exception as e:
                logger.warning(f"Failed to run backtest with params {params}: {e}")
                continue
            
            # 进度日志
            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i + 1}/{len(combinations)}, "
                           f"best_score={best_score:.4f}")
        
        # 生成敏感性报告
        sensitivity = self._analyze_sensitivity(all_results, param_names)
        
        logger.info(f"Grid search completed. Best score: {best_score:.4f}")
        logger.info(f"Best params: {best_params}")
        
        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            best_performance=best_performance,
            all_results=all_results,
            sensitivity_report=sensitivity
        )
    
    def _analyze_sensitivity(
        self,
        results: List[Dict],
        param_names: List[str]
    ) -> Dict:
        """
        分析参数敏感性
        
        计算每个参数对得分的影响程度
        """
        if not results:
            return {}
        
        sensitivity = {}
        
        for param in param_names:
            # 按参数值分组
            by_value = {}
            for r in results:
                value = r['params'].get(param)
                if value not in by_value:
                    by_value[value] = []
                by_value[value].append(r['score'])
            
            # 计算每个值的平均得分
            avg_scores = {v: sum(s)/len(s) for v, s in by_value.items()}
            
            # 计算敏感度指标
            if len(avg_scores) > 1:
                scores_list = list(avg_scores.values())
                score_range = max(scores_list) - min(scores_list)
                score_std = (sum((s - sum(scores_list)/len(scores_list))**2 
                                for s in scores_list) / len(scores_list)) ** 0.5
            else:
                score_range = 0
                score_std = 0
            
            # 找最优值
            best_value = max(avg_scores, key=avg_scores.get)
            
            sensitivity[param] = {
                'avg_scores_by_value': avg_scores,
                'score_range': score_range,
                'score_std': score_std,
                'sensitivity_rank': score_range,  # 用范围作为敏感度排名
                'optimal_value': best_value,
                'optimal_avg_score': avg_scores[best_value]
            }
        
        # 排序敏感度
        sorted_params = sorted(
            sensitivity.items(),
            key=lambda x: x[1]['sensitivity_rank'],
            reverse=True
        )
        
        return {
            'by_param': dict(sorted_params),
            'most_sensitive': sorted_params[0][0] if sorted_params else None,
            'least_sensitive': sorted_params[-1][0] if sorted_params else None
        }
    
    def quick_sensitivity_test(
        self,
        symbol: str,
        market_data_list: List[Dict],
        param_name: str,
        test_values: List[float],
        mode: str = "dual"
    ) -> Dict:
        """
        快速敏感性测试（单参数）
        
        Args:
            symbol: 交易对
            market_data_list: 市场数据
            param_name: 参数名
            test_values: 测试值列表
            mode: 回测模式
            
        Returns:
            敏感性分析结果
        """
        results = []
        
        for value in test_values:
            test_config = copy.deepcopy(self.base_config)
            self._set_nested_value(test_config, param_name, value)
            
            # 更新引擎配置
            self.backtest_engine.engine.config = test_config
            self.backtest_engine.engine.thresholds = self.backtest_engine.engine._flatten_thresholds(test_config)
            
            try:
                result = self.backtest_engine.run_backtest(
                    symbol, market_data_list, mode=mode
                )
                performance = result['performance']
                score = self.scoring_function(performance)
                
                results.append({
                    'value': value,
                    'score': score,
                    'win_rate': performance.get('win_rate', 0),
                    'total_return': performance.get('total_return', 0),
                    'max_drawdown': performance.get('max_drawdown', 0)
                })
            except Exception as e:
                logger.warning(f"Failed for {param_name}={value}: {e}")
        
        # 找最优值
        if results:
            best = max(results, key=lambda x: x['score'])
            return {
                'param_name': param_name,
                'results': results,
                'optimal_value': best['value'],
                'optimal_score': best['score']
            }
        
        return {'param_name': param_name, 'results': [], 'error': 'No valid results'}
    
    def generate_report(self, opt_result: OptimizationResult) -> str:
        """
        生成优化报告
        
        Args:
            opt_result: 优化结果
            
        Returns:
            Markdown格式报告
        """
        report = []
        report.append("# 参数优化报告\n")
        report.append("## 1. 最优参数\n")
        report.append(f"- 最优得分: {opt_result.best_score:.4f}\n")
        
        for param, value in opt_result.best_params.items():
            report.append(f"- {param}: {value}\n")
        
        report.append("\n## 2. 最优绩效\n")
        perf = opt_result.best_performance
        report.append(f"- 总收益: {perf.get('total_return', 0)*100:.2f}%\n")
        report.append(f"- 胜率: {perf.get('win_rate', 0)*100:.2f}%\n")
        report.append(f"- 夏普比率: {perf.get('sharpe_ratio', 0):.2f}\n")
        report.append(f"- 最大回撤: {perf.get('max_drawdown', 0)*100:.2f}%\n")
        
        report.append("\n## 3. 参数敏感性\n")
        if opt_result.sensitivity_report:
            sens = opt_result.sensitivity_report
            report.append(f"- 最敏感参数: {sens.get('most_sensitive', 'N/A')}\n")
            report.append(f"- 最不敏感参数: {sens.get('least_sensitive', 'N/A')}\n")
            
            report.append("\n### 敏感性排名:\n")
            for param, data in sens.get('by_param', {}).items():
                report.append(f"- {param}: 范围={data['score_range']:.4f}, "
                             f"最优值={data['optimal_value']}\n")
        
        report.append(f"\n## 4. 测试组合数: {len(opt_result.all_results)}\n")
        
        return ''.join(report)


# 便捷函数
def run_quick_optimization(
    backtest_engine,
    symbol: str,
    market_data: List[Dict],
    params_to_optimize: List[str] = None
) -> OptimizationResult:
    """
    快速优化（使用预设参数范围）
    
    Args:
        backtest_engine: 回测引擎
        symbol: 交易对
        market_data: 市场数据
        params_to_optimize: 要优化的参数列表（使用预设范围）
        
    Returns:
        OptimizationResult
    """
    optimizer = ParameterOptimizer(
        backtest_engine,
        backtest_engine.engine.config
    )
    
    if params_to_optimize is None:
        params_to_optimize = ['extreme_price_change_1h', 'stop_loss_pct']
    
    ranges = [
        ParameterOptimizer.PRESET_RANGES[p]
        for p in params_to_optimize
        if p in ParameterOptimizer.PRESET_RANGES
    ]
    
    return optimizer.grid_search(symbol, market_data, ranges)
