"""
信号准确率分析器

评估信号发出后一定时间内的价格方向是否正确
适用于信号提醒系统的效果评估

评估维度：
1. 15分钟准确率：信号发出后15分钟价格方向是否正确
2. 1小时准确率：信号发出后1小时价格方向是否正确
3. 按置信度分组：HIGH/MEDIUM/LOW信号的准确率
4. 按市场环境分组：TREND/RANGE环境的准确率
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import logging

from models.enums import Decision

logger = logging.getLogger(__name__)


@dataclass
class SignalRecord:
    """信号记录"""
    timestamp: int              # 信号时间戳
    decision: Decision          # LONG/SHORT
    confidence: str             # HIGH/MEDIUM/LOW/ULTRA
    regime: str                 # TREND/RANGE/EXTREME
    price_at_signal: float      # 信号时价格
    
    # 后续价格（用于计算准确率）
    price_after_15m: Optional[float] = None
    price_after_1h: Optional[float] = None
    price_after_4h: Optional[float] = None
    
    # 准确性判断
    correct_15m: Optional[bool] = None
    correct_1h: Optional[bool] = None
    correct_4h: Optional[bool] = None
    
    # 价格变化幅度
    change_15m: Optional[float] = None
    change_1h: Optional[float] = None
    change_4h: Optional[float] = None


@dataclass
class AccuracyMetrics:
    """准确率指标"""
    total_signals: int = 0
    correct_signals: int = 0
    accuracy: float = 0.0
    
    # 按方向分组
    long_total: int = 0
    long_correct: int = 0
    long_accuracy: float = 0.0
    
    short_total: int = 0
    short_correct: int = 0
    short_accuracy: float = 0.0
    
    # 平均价格变化
    avg_correct_change: float = 0.0
    avg_wrong_change: float = 0.0


class SignalAccuracyAnalyzer:
    """
    信号准确率分析器
    
    用法：
    1. 遍历历史数据，记录每个信号
    2. 对每个信号，查找后续价格
    3. 计算准确率统计
    """
    
    def __init__(self):
        self.signals: List[SignalRecord] = []
        self.price_history: Dict[int, float] = {}  # timestamp -> price
    
    def record_price(self, timestamp: int, price: float):
        """记录价格历史"""
        self.price_history[timestamp] = price
    
    def record_signal(
        self,
        timestamp: int,
        decision: Decision,
        confidence: str,
        regime: str,
        price: float
    ):
        """记录信号"""
        if decision not in [Decision.LONG, Decision.SHORT]:
            return  # 只记录LONG/SHORT信号
        
        signal = SignalRecord(
            timestamp=timestamp,
            decision=decision,
            confidence=confidence,
            regime=regime,
            price_at_signal=price
        )
        self.signals.append(signal)
    
    def fill_future_prices(self):
        """填充信号后的价格数据"""
        # 将价格历史按时间排序
        sorted_timestamps = sorted(self.price_history.keys())
        
        for signal in self.signals:
            signal_ts = signal.timestamp
            signal_price = signal.price_at_signal
            
            # 查找15分钟后的价格（15 * 60 * 1000 = 900000ms）
            target_15m = signal_ts + 900000
            price_15m = self._find_closest_price(target_15m, sorted_timestamps)
            if price_15m:
                signal.price_after_15m = price_15m
                signal.change_15m = (price_15m - signal_price) / signal_price
                signal.correct_15m = self._is_correct(signal.decision, signal.change_15m)
            
            # 查找1小时后的价格（60 * 60 * 1000 = 3600000ms）
            target_1h = signal_ts + 3600000
            price_1h = self._find_closest_price(target_1h, sorted_timestamps)
            if price_1h:
                signal.price_after_1h = price_1h
                signal.change_1h = (price_1h - signal_price) / signal_price
                signal.correct_1h = self._is_correct(signal.decision, signal.change_1h)
            
            # 查找4小时后的价格（4 * 60 * 60 * 1000 = 14400000ms）
            target_4h = signal_ts + 14400000
            price_4h = self._find_closest_price(target_4h, sorted_timestamps)
            if price_4h:
                signal.price_after_4h = price_4h
                signal.change_4h = (price_4h - signal_price) / signal_price
                signal.correct_4h = self._is_correct(signal.decision, signal.change_4h)
    
    def _find_closest_price(
        self, 
        target_ts: int, 
        sorted_timestamps: List[int],
        tolerance_ms: int = 120000  # 2分钟容差
    ) -> Optional[float]:
        """查找最接近目标时间的价格"""
        if not sorted_timestamps:
            return None
        
        # 二分查找
        left, right = 0, len(sorted_timestamps) - 1
        
        while left < right:
            mid = (left + right) // 2
            if sorted_timestamps[mid] < target_ts:
                left = mid + 1
            else:
                right = mid
        
        # 检查最接近的时间戳
        closest_ts = sorted_timestamps[left]
        if abs(closest_ts - target_ts) <= tolerance_ms:
            return self.price_history[closest_ts]
        
        # 也检查前一个
        if left > 0:
            prev_ts = sorted_timestamps[left - 1]
            if abs(prev_ts - target_ts) <= tolerance_ms:
                return self.price_history[prev_ts]
        
        return None
    
    def _is_correct(self, decision: Decision, price_change: float) -> bool:
        """判断信号是否正确"""
        if decision == Decision.LONG:
            return price_change > 0
        elif decision == Decision.SHORT:
            return price_change < 0
        return False
    
    def calculate_accuracy(self, timeframe: str = "15m") -> AccuracyMetrics:
        """
        计算指定时间窗口的准确率
        
        Args:
            timeframe: "15m" / "1h" / "4h"
        
        Returns:
            AccuracyMetrics: 准确率指标
        """
        metrics = AccuracyMetrics()
        
        # 选择正确性字段
        if timeframe == "15m":
            correct_field = "correct_15m"
            change_field = "change_15m"
        elif timeframe == "1h":
            correct_field = "correct_1h"
            change_field = "change_1h"
        elif timeframe == "4h":
            correct_field = "correct_4h"
            change_field = "change_4h"
        else:
            raise ValueError(f"Unknown timeframe: {timeframe}")
        
        correct_changes = []
        wrong_changes = []
        
        for signal in self.signals:
            correct = getattr(signal, correct_field)
            change = getattr(signal, change_field)
            
            if correct is None:
                continue  # 跳过没有后续价格的信号
            
            metrics.total_signals += 1
            if correct:
                metrics.correct_signals += 1
                if change:
                    correct_changes.append(abs(change))
            else:
                if change:
                    wrong_changes.append(abs(change))
            
            # 按方向统计
            if signal.decision == Decision.LONG:
                metrics.long_total += 1
                if correct:
                    metrics.long_correct += 1
            elif signal.decision == Decision.SHORT:
                metrics.short_total += 1
                if correct:
                    metrics.short_correct += 1
        
        # 计算准确率
        if metrics.total_signals > 0:
            metrics.accuracy = metrics.correct_signals / metrics.total_signals
        if metrics.long_total > 0:
            metrics.long_accuracy = metrics.long_correct / metrics.long_total
        if metrics.short_total > 0:
            metrics.short_accuracy = metrics.short_correct / metrics.short_total
        
        # 计算平均价格变化
        if correct_changes:
            metrics.avg_correct_change = sum(correct_changes) / len(correct_changes)
        if wrong_changes:
            metrics.avg_wrong_change = sum(wrong_changes) / len(wrong_changes)
        
        return metrics
    
    def calculate_accuracy_by_confidence(
        self, 
        timeframe: str = "15m"
    ) -> Dict[str, AccuracyMetrics]:
        """按置信度分组计算准确率"""
        # 按置信度分组信号
        grouped = defaultdict(list)
        for signal in self.signals:
            grouped[signal.confidence].append(signal)
        
        results = {}
        for confidence, signals in grouped.items():
            # 临时替换信号列表
            original_signals = self.signals
            self.signals = signals
            results[confidence] = self.calculate_accuracy(timeframe)
            self.signals = original_signals
        
        return results
    
    def calculate_accuracy_by_regime(
        self, 
        timeframe: str = "15m"
    ) -> Dict[str, AccuracyMetrics]:
        """按市场环境分组计算准确率"""
        grouped = defaultdict(list)
        for signal in self.signals:
            grouped[signal.regime].append(signal)
        
        results = {}
        for regime, signals in grouped.items():
            original_signals = self.signals
            self.signals = signals
            results[regime] = self.calculate_accuracy(timeframe)
            self.signals = original_signals
        
        return results
    
    def generate_report(self) -> str:
        """生成完整的准确率报告"""
        self.fill_future_prices()
        
        report = []
        report.append("=" * 60)
        report.append("📊 信号准确率分析报告")
        report.append("=" * 60)
        report.append(f"\n总信号数: {len(self.signals)}")
        
        # 总体准确率
        for tf in ["15m", "1h", "4h"]:
            metrics = self.calculate_accuracy(tf)
            report.append(f"\n--- {tf} 准确率 ---")
            report.append(f"总体准确率: {metrics.accuracy*100:.1f}% ({metrics.correct_signals}/{metrics.total_signals})")
            report.append(f"LONG准确率: {metrics.long_accuracy*100:.1f}% ({metrics.long_correct}/{metrics.long_total})")
            report.append(f"SHORT准确率: {metrics.short_accuracy*100:.1f}% ({metrics.short_correct}/{metrics.short_total})")
            report.append(f"正确信号平均涨跌幅: {metrics.avg_correct_change*100:.2f}%")
            report.append(f"错误信号平均涨跌幅: {metrics.avg_wrong_change*100:.2f}%")
        
        # 按置信度分组
        report.append(f"\n--- 按置信度分组（15m）---")
        by_conf = self.calculate_accuracy_by_confidence("15m")
        for conf in ["ultra", "high", "medium", "low"]:
            if conf in by_conf:
                m = by_conf[conf]
                report.append(f"{conf.upper()}: {m.accuracy*100:.1f}% ({m.correct_signals}/{m.total_signals})")
        
        # 按市场环境分组
        report.append(f"\n--- 按市场环境分组（15m）---")
        by_regime = self.calculate_accuracy_by_regime("15m")
        for regime in ["trend", "range", "extreme"]:
            if regime in by_regime:
                m = by_regime[regime]
                report.append(f"{regime.upper()}: {m.accuracy*100:.1f}% ({m.correct_signals}/{m.total_signals})")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)
    
    def get_summary_dict(self) -> Dict:
        """获取摘要字典（用于JSON导出）"""
        self.fill_future_prices()
        
        summary = {
            "total_signals": len(self.signals),
            "accuracy_15m": {},
            "accuracy_1h": {},
            "accuracy_4h": {},
            "by_confidence_15m": {},
            "by_regime_15m": {}
        }
        
        for tf in ["15m", "1h", "4h"]:
            metrics = self.calculate_accuracy(tf)
            summary[f"accuracy_{tf}"] = {
                "total": metrics.total_signals,
                "correct": metrics.correct_signals,
                "accuracy": round(metrics.accuracy, 4),
                "long_accuracy": round(metrics.long_accuracy, 4),
                "short_accuracy": round(metrics.short_accuracy, 4),
                "avg_correct_change": round(metrics.avg_correct_change, 6),
                "avg_wrong_change": round(metrics.avg_wrong_change, 6)
            }
        
        by_conf = self.calculate_accuracy_by_confidence("15m")
        for conf, m in by_conf.items():
            summary["by_confidence_15m"][conf] = {
                "total": m.total_signals,
                "correct": m.correct_signals,
                "accuracy": round(m.accuracy, 4)
            }
        
        by_regime = self.calculate_accuracy_by_regime("15m")
        for regime, m in by_regime.items():
            summary["by_regime_15m"][regime] = {
                "total": m.total_signals,
                "correct": m.correct_signals,
                "accuracy": round(m.accuracy, 4)
            }
        
        return summary
