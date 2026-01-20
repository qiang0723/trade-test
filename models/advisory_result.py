"""
L1 Advisory Layer - 决策结果数据类

AdvisoryResult是L1决策层的标准化输出
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List
from .enums import Decision, Confidence, TradeQuality, MarketRegime, SystemState
from .reason_tags import ReasonTag


@dataclass
class AdvisoryResult:
    """
    L1决策层标准化输出
    
    这是L1 Advisory Layer的唯一输出格式，包含：
    - 核心决策（LONG/SHORT/NO_TRADE）
    - 置信度（HIGH/MEDIUM/LOW）
    - 市场环境和系统状态
    - 安全闸门状态（风险准入、交易质量）
    - 决策追溯信息（reason_tags）
    
    注意：
    - L1仅提供决策建议，不包含执行信息（仓位、入场点、止损止盈等）
    - executable字段在P2阶段添加，用于L3执行层判断
    """
    
    # ===== 核心决策 =====
    decision: Decision              # LONG | SHORT | NO_TRADE
    confidence: Confidence          # HIGH | MEDIUM | LOW
    
    # ===== 市场环境 =====
    market_regime: MarketRegime     # TREND | RANGE | EXTREME
    system_state: SystemState       # 状态机当前状态
    
    # ===== 闸门状态 =====
    risk_exposure_allowed: bool     # 风险准入：True/False
    trade_quality: TradeQuality     # 交易质量：GOOD/POOR
    
    # ===== 可追溯性 =====
    reason_tags: List[ReasonTag]    # 决策原因标签列表
    timestamp: datetime             # 决策时间戳
    
    # ===== (P2) L3执行许可 =====
    executable: bool = False        # 是否可执行（为L3执行层提供明确许可）
    
    def to_dict(self) -> dict:
        """
        转换为字典，用于JSON序列化
        
        Returns:
            dict: 可JSON序列化的字典
        """
        return {
            'decision': self.decision.value,
            'confidence': self.confidence.value,
            'market_regime': self.market_regime.value,
            'system_state': self.system_state.value,
            'risk_exposure_allowed': self.risk_exposure_allowed,
            'trade_quality': self.trade_quality.value,
            'reason_tags': [tag.value for tag in self.reason_tags],
            'timestamp': self.timestamp.isoformat(),
            'executable': self.executable,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AdvisoryResult':
        """
        从字典构造AdvisoryResult（用于数据库读取）
        
        Args:
            data: 包含所有字段的字典
        
        Returns:
            AdvisoryResult: 重构的对象
        """
        return cls(
            decision=Decision(data['decision']),
            confidence=Confidence(data['confidence']),
            market_regime=MarketRegime(data['market_regime']),
            system_state=SystemState(data['system_state']),
            risk_exposure_allowed=data['risk_exposure_allowed'],
            trade_quality=TradeQuality(data['trade_quality']),
            reason_tags=[ReasonTag(tag) for tag in data['reason_tags']],
            timestamp=datetime.fromisoformat(data['timestamp']),
            executable=data.get('executable', False),
        )
    
    def is_no_trade(self) -> bool:
        """判断是否为NO_TRADE决策"""
        return self.decision == Decision.NO_TRADE
    
    def is_high_confidence(self) -> bool:
        """判断是否为高置信度"""
        return self.confidence == Confidence.HIGH
    
    def has_risk_denial(self) -> bool:
        """判断是否存在风险否决"""
        return not self.risk_exposure_allowed
    
    def has_quality_issue(self) -> bool:
        """判断是否存在质量问题（PR-004: 包含UNCERTAIN和POOR）"""
        return self.trade_quality in [TradeQuality.UNCERTAIN, TradeQuality.POOR]
    
    def compute_executable(self) -> bool:
        """
        计算是否可执行 - 为L3提供明确的执行许可（PR-B综合判定）
        
        规则（PR-B修订）：
        1. 风险必须通过：risk_exposure_allowed=True
        2. 无阻断性标签：has_blocking_tags(reason_tags)=False
        3. 置信度达标：ULTRA或HIGH
        4. 决策方向明确：LONG或SHORT
        
        注意：
        - POOR质量对应的标签（ABSORPTION_RISK/ROTATION_RISK）会被阻断
        - UNCERTAIN质量对应的标签（NOISY_MARKET）为降级，不阻断
        
        Returns:
            bool: 是否允许L3执行
        """
        from .reason_tags import has_blocking_tags
        
        # 1. 决策必须是LONG或SHORT
        if self.decision == Decision.NO_TRADE:
            return False
        
        # 2. 风险必须通过
        if not self.risk_exposure_allowed:
            return False
        
        # 3. PR-B: 检查阻断性标签（包括POOR对应的标签）
        if has_blocking_tags(self.reason_tags):
            return False
        
        # 4. 置信度必须达标（ULTRA或HIGH）
        if self.confidence not in [Confidence.ULTRA, Confidence.HIGH]:
            return False
        
        # 5. 质量不能是POOR（理论上POOR已在阻断标签中排除，这里是双重保险）
        if self.trade_quality == TradeQuality.POOR:
            return False
        
        # 通过所有检查
        return True
    
    def __str__(self) -> str:
        """字符串表示（用于日志）"""
        return (f"AdvisoryResult(decision={self.decision.value}, "
                f"confidence={self.confidence.value}, "
                f"regime={self.market_regime.value}, "
                f"risk_ok={self.risk_exposure_allowed}, "
                f"quality={self.trade_quality.value}, "
                f"executable={self.executable})")
