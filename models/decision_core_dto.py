"""
PR-ARCH-02: DecisionCore DTO

定义DecisionCore纯函数的输入输出DTO。

目标：
1. DecisionDraft：决策草稿（纯函数输出，不包含频控信息）
2. DecisionFinal：最终决策（包含频控/阻断信息）
3. 强类型、可序列化、可测试

设计原则：
- DecisionCore输出DecisionDraft（纯逻辑，无时间/状态）
- DecisionGate输入DecisionDraft，输出DecisionFinal（添加频控/阻断）
- 阻断不可执行时，不改写signal_decision，只通过executable/execution_permission表达
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from models.enums import (
    Decision, Confidence, TradeQuality, MarketRegime, 
    ExecutionPermission, Timeframe
)
from models.reason_tags import ReasonTag


@dataclass
class TimeframeDecisionDraft:
    """
    单周期决策草稿（DecisionCore输出）
    
    特性：
    - 纯逻辑输出：不包含频控/冷却信息
    - 确定性：相同输入必得相同输出
    - 无时间：不依赖当前时间
    - 无状态：不依赖历史决策
    """
    # 核心决策
    decision: Decision                          # LONG/SHORT/NO_TRADE
    confidence: Confidence                      # HIGH/MEDIUM/LOW
    
    # 市场判断
    market_regime: MarketRegime                 # TREND/RANGE/EXTREME
    trade_quality: TradeQuality                 # GOOD/UNCERTAIN/POOR
    
    # 执行权限（策略层判断，不含频控）
    execution_permission: ExecutionPermission   # ALLOW/ALLOW_REDUCED/DENY
    
    # 原因标签（完整的决策依据）
    reason_tags: List[ReasonTag] = field(default_factory=list)
    
    # 关键指标（用于可视化/调试）
    key_metrics: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'decision': self.decision.value if isinstance(self.decision, Decision) else self.decision,
            'confidence': self.confidence.value if isinstance(self.confidence, Confidence) else self.confidence,
            'market_regime': self.market_regime.value if isinstance(self.market_regime, MarketRegime) else self.market_regime,
            'trade_quality': self.trade_quality.value if isinstance(self.trade_quality, TradeQuality) else self.trade_quality,
            'execution_permission': self.execution_permission.value if isinstance(self.execution_permission, ExecutionPermission) else self.execution_permission,
            'reason_tags': [tag.value if isinstance(tag, ReasonTag) else tag for tag in self.reason_tags],
            'key_metrics': self.key_metrics
        }


@dataclass
class DualTimeframeDecisionDraft:
    """
    双周期决策草稿（DecisionCore输出）
    
    包含短期和中期的独立结论
    """
    # 短期决策（5m/15m）
    short_term: TimeframeDecisionDraft
    
    # 中期决策（1h/6h）
    medium_term: TimeframeDecisionDraft
    
    # 全局风险标签
    global_risk_tags: List[ReasonTag] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'short_term': self.short_term.to_dict(),
            'medium_term': self.medium_term.to_dict(),
            'global_risk_tags': [tag.value if isinstance(tag, ReasonTag) else tag for tag in self.global_risk_tags]
        }


@dataclass
class FrequencyControlState:
    """
    频率控制状态（DecisionGate使用）
    
    最小状态接口：
    - last_decision_time: 上次决策时间
    - last_signal_direction: 上次信号方向（LONG/SHORT/NO_TRADE）
    
    不包含持仓信息（避免引入持仓语义）
    """
    last_decision_time: Optional[datetime] = None
    last_signal_direction: Optional[Decision] = None
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'last_decision_time': self.last_decision_time.isoformat() if self.last_decision_time else None,
            'last_signal_direction': self.last_signal_direction.value if self.last_signal_direction else None
        }


@dataclass
class FrequencyControlResult:
    """
    频率控制结果（DecisionGate输出）
    
    记录频控/冷却/阻断的判断结果
    """
    # 是否被频控阻断
    is_blocked: bool = False
    
    # 阻断原因
    block_reason: Optional[str] = None
    
    # 冷却中（相同方向重复信号）
    is_cooling: bool = False
    
    # 最小间隔未到
    min_interval_violated: bool = False
    
    # 添加的reason_tags（频控相关）
    added_tags: List[ReasonTag] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'is_blocked': self.is_blocked,
            'block_reason': self.block_reason,
            'is_cooling': self.is_cooling,
            'min_interval_violated': self.min_interval_violated,
            'added_tags': [tag.value if isinstance(tag, ReasonTag) else tag for tag in self.added_tags]
        }


@dataclass
class TimeframeDecisionFinal:
    """
    单周期最终决策（DecisionGate输出）
    
    在DecisionDraft基础上添加频控信息
    """
    # 继承自Draft
    decision: Decision
    confidence: Confidence
    market_regime: MarketRegime
    trade_quality: TradeQuality
    execution_permission: ExecutionPermission
    reason_tags: List[ReasonTag]
    key_metrics: Dict[str, float]
    
    # DecisionGate添加的信息
    executable: bool                                    # 最终是否可执行
    frequency_control: FrequencyControlResult           # 频控结果
    timeframe: Timeframe                                # 周期标识
    
    @classmethod
    def from_draft(
        cls,
        draft: TimeframeDecisionDraft,
        executable: bool,
        frequency_control: FrequencyControlResult,
        timeframe: Timeframe
    ) -> 'TimeframeDecisionFinal':
        """从Draft构建Final"""
        # 合并reason_tags
        all_tags = draft.reason_tags + frequency_control.added_tags
        
        return cls(
            decision=draft.decision,
            confidence=draft.confidence,
            market_regime=draft.market_regime,
            trade_quality=draft.trade_quality,
            execution_permission=draft.execution_permission,
            reason_tags=all_tags,
            key_metrics=draft.key_metrics,
            executable=executable,
            frequency_control=frequency_control,
            timeframe=timeframe
        )
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'decision': self.decision.value if isinstance(self.decision, Decision) else self.decision,
            'confidence': self.confidence.value if isinstance(self.confidence, Confidence) else self.confidence,
            'market_regime': self.market_regime.value if isinstance(self.market_regime, MarketRegime) else self.market_regime,
            'trade_quality': self.trade_quality.value if isinstance(self.trade_quality, TradeQuality) else self.trade_quality,
            'execution_permission': self.execution_permission.value if isinstance(self.execution_permission, ExecutionPermission) else self.execution_permission,
            'reason_tags': [tag.value if isinstance(tag, ReasonTag) else tag for tag in self.reason_tags],
            'key_metrics': self.key_metrics,
            'executable': self.executable,
            'frequency_control': self.frequency_control.to_dict(),
            'timeframe': self.timeframe.value if isinstance(self.timeframe, Timeframe) else self.timeframe
        }


@dataclass
class DualTimeframeDecisionFinal:
    """
    双周期最终决策（DecisionGate输出）
    
    包含短期和中期的最终结论
    """
    # 短期最终决策
    short_term: TimeframeDecisionFinal
    
    # 中期最终决策
    medium_term: TimeframeDecisionFinal
    
    # 全局风险标签
    global_risk_tags: List[ReasonTag]
    
    # 对齐分析（可选，保留兼容）
    alignment: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        result = {
            'short_term': self.short_term.to_dict(),
            'medium_term': self.medium_term.to_dict(),
            'global_risk_tags': [tag.value if isinstance(tag, ReasonTag) else tag for tag in self.global_risk_tags]
        }
        
        if self.alignment:
            result['alignment'] = self.alignment
        
        return result


# ============================================
# 便捷构造函数
# ============================================

def create_no_trade_draft(
    reason_tags: List[ReasonTag],
    market_regime: MarketRegime = MarketRegime.RANGE
) -> TimeframeDecisionDraft:
    """
    创建NO_TRADE决策草稿（便捷函数）
    
    Args:
        reason_tags: 原因标签列表
        market_regime: 市场环境
    
    Returns:
        TimeframeDecisionDraft
    """
    return TimeframeDecisionDraft(
        decision=Decision.NO_TRADE,
        confidence=Confidence.LOW,
        market_regime=market_regime,
        trade_quality=TradeQuality.POOR,
        execution_permission=ExecutionPermission.DENY,
        reason_tags=reason_tags,
        key_metrics={}
    )


def create_dual_no_trade_draft(
    global_risk_tags: List[ReasonTag]
) -> DualTimeframeDecisionDraft:
    """
    创建双周期NO_TRADE决策草稿（便捷函数）
    
    Args:
        global_risk_tags: 全局风险标签
    
    Returns:
        DualTimeframeDecisionDraft
    """
    short_draft = create_no_trade_draft(global_risk_tags)
    medium_draft = create_no_trade_draft(global_risk_tags)
    
    return DualTimeframeDecisionDraft(
        short_term=short_draft,
        medium_term=medium_draft,
        global_risk_tags=global_risk_tags
    )
