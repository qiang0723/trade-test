"""
L1 Advisory Layer - 双周期独立结论数据类

PR-DUAL: 实现L1设计原则 - 同时输出短期和中长期两套独立结论

设计原则：
- 在不自动下单的前提下，快速、稳定、可解释地输出市场机会判断
- 短期（5m/15m）与中长期（1h/6h）各自独立评估
- 明确说明两者是否一致、是否可执行、冲突时的处理规则
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict
from .enums import (
    Decision, Confidence, TradeQuality, MarketRegime, 
    ExecutionPermission, Timeframe, AlignmentType, ConflictResolution
)
from .reason_tags import ReasonTag


@dataclass
class TimeframeConclusion:
    """
    单个时间周期的交易结论
    
    包含该周期独立评估的所有信息：决策、置信度、可执行性、原因标签
    """
    
    # ===== 周期标识 =====
    timeframe: Timeframe              # SHORT_TERM 或 MEDIUM_TERM
    timeframe_label: str              # 人类可读标签，如 "5m/15m" 或 "1h/6h"
    
    # ===== 核心决策 =====
    decision: Decision                # LONG | SHORT | NO_TRADE
    confidence: Confidence            # ULTRA | HIGH | MEDIUM | LOW
    
    # ===== 市场环境 =====
    market_regime: MarketRegime       # TREND | RANGE | EXTREME
    trade_quality: TradeQuality       # GOOD | UNCERTAIN | POOR
    
    # ===== 执行许可 =====
    execution_permission: ExecutionPermission = ExecutionPermission.ALLOW
    executable: bool = False
    
    # ===== 可追溯性 =====
    reason_tags: List[ReasonTag] = field(default_factory=list)
    
    # ===== 关键指标快照 =====
    key_metrics: Dict = field(default_factory=dict)  # 该周期使用的关键指标
    
    def to_dict(self) -> dict:
        """转换为字典，用于JSON序列化"""
        return {
            'timeframe': self.timeframe.value,
            'timeframe_label': self.timeframe_label,
            'decision': self.decision.value,
            'confidence': self.confidence.value,
            'market_regime': self.market_regime.value,
            'trade_quality': self.trade_quality.value,
            'execution_permission': self.execution_permission.value,
            'executable': self.executable,
            'reason_tags': [tag.value for tag in self.reason_tags],
            'key_metrics': self.key_metrics
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TimeframeConclusion':
        """从字典构造"""
        return cls(
            timeframe=Timeframe(data['timeframe']),
            timeframe_label=data['timeframe_label'],
            decision=Decision(data['decision']),
            confidence=Confidence(data['confidence']),
            market_regime=MarketRegime(data['market_regime']),
            trade_quality=TradeQuality(data['trade_quality']),
            execution_permission=ExecutionPermission(data.get('execution_permission', 'allow')),
            executable=data.get('executable', False),
            reason_tags=[ReasonTag(tag) for tag in data.get('reason_tags', [])],
            key_metrics=data.get('key_metrics', {})
        )


@dataclass
class AlignmentAnalysis:
    """
    双周期一致性分析
    
    分析短期和中长期结论的关系，提供冲突处理建议
    """
    
    # ===== 一致性判断 =====
    is_aligned: bool                  # 两者方向是否一致
    alignment_type: AlignmentType     # 一致性类型（详细分类）
    
    # ===== 冲突处理 =====
    has_conflict: bool                # 是否存在方向冲突
    conflict_resolution: Optional[ConflictResolution] = None  # 建议的冲突处理策略
    resolution_reason: str = ""       # 处理策略的原因说明
    
    # ===== 综合建议 =====
    recommended_action: Decision = Decision.NO_TRADE  # 综合建议的操作
    recommended_confidence: Confidence = Confidence.LOW
    recommendation_notes: str = ""    # 综合建议说明
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'is_aligned': self.is_aligned,
            'alignment_type': self.alignment_type.value,
            'has_conflict': self.has_conflict,
            'conflict_resolution': self.conflict_resolution.value if self.conflict_resolution else None,
            'resolution_reason': self.resolution_reason,
            'recommended_action': self.recommended_action.value,
            'recommended_confidence': self.recommended_confidence.value,
            'recommendation_notes': self.recommendation_notes
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AlignmentAnalysis':
        """从字典构造"""
        conflict_res = data.get('conflict_resolution')
        return cls(
            is_aligned=data['is_aligned'],
            alignment_type=AlignmentType(data['alignment_type']),
            has_conflict=data['has_conflict'],
            conflict_resolution=ConflictResolution(conflict_res) if conflict_res else None,
            resolution_reason=data.get('resolution_reason', ''),
            recommended_action=Decision(data.get('recommended_action', 'no_trade')),
            recommended_confidence=Confidence(data.get('recommended_confidence', 'low')),
            recommendation_notes=data.get('recommendation_notes', '')
        )


@dataclass
class DualTimeframeResult:
    """
    L1双周期独立结论 - 最终输出
    
    包含：
    1. 短期结论（5m/15m）
    2. 中长期结论（1h/6h）
    3. 一致性分析
    4. 综合建议（向后兼容）
    """
    
    # ===== 双周期独立结论 =====
    short_term: TimeframeConclusion   # 短期结论
    medium_term: TimeframeConclusion  # 中长期结论
    
    # ===== 一致性分析 =====
    alignment: AlignmentAnalysis      # 一致性分析结果
    
    # ===== 元信息 =====
    symbol: str                       # 交易对
    timestamp: datetime               # 决策时间戳
    
    # ===== 系统风险状态（全局，不分周期）=====
    risk_exposure_allowed: bool = True  # 全局风险准入
    global_risk_tags: List[ReasonTag] = field(default_factory=list)  # 全局风险标签
    
    def to_dict(self) -> dict:
        """
        转换为字典，用于JSON序列化
        
        输出格式包含：
        - short_term: 短期结论
        - medium_term: 中长期结论
        - alignment: 一致性分析
        - 向后兼容字段（decision, confidence, executable等）
        """
        return {
            # 新结构：双周期独立结论
            'short_term': self.short_term.to_dict(),
            'medium_term': self.medium_term.to_dict(),
            'alignment': self.alignment.to_dict(),
            
            # 元信息
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'risk_exposure_allowed': self.risk_exposure_allowed,
            'global_risk_tags': [tag.value for tag in self.global_risk_tags],
            
            # 向后兼容字段（使用综合建议）
            'decision': self.alignment.recommended_action.value,
            'confidence': self.alignment.recommended_confidence.value,
            'executable': self._compute_combined_executable(),
            'reason_tags': self._get_combined_reason_tags(),
            'market_regime': self.medium_term.market_regime.value,  # 使用中长期环境
        }
    
    def _compute_combined_executable(self) -> bool:
        """
        计算综合可执行性
        
        规则：
        - 一致时：两者都可执行才返回True
        - 冲突时：根据冲突处理策略决定
        """
        if self.alignment.has_conflict:
            # 冲突时，根据处理策略
            if self.alignment.conflict_resolution == ConflictResolution.NO_TRADE:
                return False
            elif self.alignment.conflict_resolution == ConflictResolution.FOLLOW_SHORT_TERM:
                return self.short_term.executable
            elif self.alignment.conflict_resolution == ConflictResolution.FOLLOW_MEDIUM_TERM:
                return self.medium_term.executable
            elif self.alignment.conflict_resolution == ConflictResolution.FOLLOW_HIGHER_CONFIDENCE:
                # 跟随置信度更高的一方
                if self._confidence_level(self.short_term.confidence) > self._confidence_level(self.medium_term.confidence):
                    return self.short_term.executable
                else:
                    return self.medium_term.executable
            return False
        else:
            # 一致时，两者都可执行才返回True（保守策略）
            return self.short_term.executable and self.medium_term.executable
    
    def _confidence_level(self, conf: Confidence) -> int:
        """置信度数值化"""
        return {Confidence.LOW: 0, Confidence.MEDIUM: 1, Confidence.HIGH: 2, Confidence.ULTRA: 3}.get(conf, 0)
    
    def _get_combined_reason_tags(self) -> List[str]:
        """合并两个周期的reason_tags（去重）"""
        seen = set()
        combined = []
        for tag in self.short_term.reason_tags + self.medium_term.reason_tags + self.global_risk_tags:
            if tag.value not in seen:
                seen.add(tag.value)
                combined.append(tag.value)
        return combined
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DualTimeframeResult':
        """从字典构造"""
        return cls(
            short_term=TimeframeConclusion.from_dict(data['short_term']),
            medium_term=TimeframeConclusion.from_dict(data['medium_term']),
            alignment=AlignmentAnalysis.from_dict(data['alignment']),
            symbol=data['symbol'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            risk_exposure_allowed=data.get('risk_exposure_allowed', True),
            global_risk_tags=[ReasonTag(tag) for tag in data.get('global_risk_tags', [])]
        )
    
    def get_summary(self) -> str:
        """
        获取人类可读的摘要
        
        Returns:
            简明的决策摘要
        """
        short_str = f"短期({self.short_term.timeframe_label}): {self.short_term.decision.value.upper()}"
        medium_str = f"中长期({self.medium_term.timeframe_label}): {self.medium_term.decision.value.upper()}"
        
        if self.alignment.is_aligned:
            align_str = f"✅ 一致 ({self.alignment.alignment_type.value})"
        else:
            align_str = f"⚠️ 冲突 ({self.alignment.alignment_type.value})"
        
        exec_str = "可执行" if self._compute_combined_executable() else "不可执行"
        
        return f"{short_str} | {medium_str} | {align_str} | {exec_str}"
    
    def __str__(self) -> str:
        return self.get_summary()
