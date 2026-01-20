"""
L1 Advisory Layer - 决策结果数据类

AdvisoryResult是L1决策层的标准化输出
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from .enums import Decision, Confidence, TradeQuality, MarketRegime, SystemState, ExecutionPermission
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
    trade_quality: TradeQuality     # 交易质量：GOOD/UNCERTAIN/POOR（三态）
    
    # ===== 可追溯性 =====
    reason_tags: List[ReasonTag]    # 决策原因标签列表
    timestamp: datetime             # 决策时间戳
    
    # ===== (方案D) L3执行许可 - 三级执行许可 + 双门槛 =====
    execution_permission: ExecutionPermission = ExecutionPermission.ALLOW  # 执行许可级别
    executable: bool = False        # 是否可执行（基于execution_permission和置信度的双门槛判断）
    
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
            'execution_permission': self.execution_permission.value,  # 方案D新增
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
        
        注意：为了向后兼容，execution_permission 字段可能不存在（旧数据），默认为 ALLOW
        """
        # 向后兼容：旧数据没有 execution_permission 字段
        execution_permission_value = data.get('execution_permission', 'allow')
        
        return cls(
            decision=Decision(data['decision']),
            confidence=Confidence(data['confidence']),
            market_regime=MarketRegime(data['market_regime']),
            system_state=SystemState(data['system_state']),
            risk_exposure_allowed=data['risk_exposure_allowed'],
            trade_quality=TradeQuality(data['trade_quality']),
            reason_tags=[ReasonTag(tag) for tag in data['reason_tags']],
            timestamp=datetime.fromisoformat(data['timestamp']),
            execution_permission=ExecutionPermission(execution_permission_value),
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
    
    def compute_executable(
        self,
        min_confidence_normal: Confidence = Confidence.HIGH,
        min_confidence_reduced: Confidence = Confidence.MEDIUM
    ) -> bool:
        """
        计算是否可执行 - 方案D：双门槛机制
        
        三级执行许可：
        - ALLOW: 正常执行（无降级标签）→ 使用 min_confidence_normal (默认 HIGH)
        - ALLOW_REDUCED: 降级执行（有DEGRADE标签，如NOISY_MARKET）→ 使用 min_confidence_reduced (默认 MEDIUM)
        - DENY: 拒绝执行（有BLOCK标签，如EXTREME_VOLUME）→ 永远 False
        
        前置条件（所有许可级别共用）：
        1. 决策必须是LONG或SHORT
        2. 风险必须通过（risk_exposure_allowed=True）
        
        双门槛逻辑：
        - ALLOW: confidence >= min_confidence_normal (HIGH/ULTRA)
        - ALLOW_REDUCED: confidence >= min_confidence_reduced (MEDIUM/HIGH/ULTRA)
        - DENY: 永远 False
        
        Args:
            min_confidence_normal: ALLOW 的最低置信度要求（默认 HIGH）
            min_confidence_reduced: ALLOW_REDUCED 的最低置信度要求（默认 MEDIUM）
        
        Returns:
            bool: 是否允许L3执行
        """
        # 前置条件1: 决策必须是LONG或SHORT
        if self.decision == Decision.NO_TRADE:
            return False
        
        # 前置条件2: 风险必须通过
        if not self.risk_exposure_allowed:
            return False
        
        # 根据执行许可级别应用不同门槛
        if self.execution_permission == ExecutionPermission.DENY:
            # DENY: 永远不可执行
            return False
        
        elif self.execution_permission == ExecutionPermission.ALLOW:
            # ALLOW: 正常门槛（HIGH/ULTRA）
            return self._confidence_meets_threshold(self.confidence, min_confidence_normal)
        
        elif self.execution_permission == ExecutionPermission.ALLOW_REDUCED:
            # ALLOW_REDUCED: 降级门槛（MEDIUM及以上）
            return self._confidence_meets_threshold(self.confidence, min_confidence_reduced)
        
        # 理论上不会到这里
        return False
    
    def _confidence_meets_threshold(self, confidence: Confidence, threshold: Confidence) -> bool:
        """
        检查置信度是否达到阈值
        
        置信度顺序：LOW < MEDIUM < HIGH < ULTRA
        
        Args:
            confidence: 当前置信度
            threshold: 最低要求
        
        Returns:
            bool: 是否达标
        """
        confidence_order = {
            Confidence.LOW: 0,
            Confidence.MEDIUM: 1,
            Confidence.HIGH: 2,
            Confidence.ULTRA: 3
        }
        
        return confidence_order.get(confidence, 0) >= confidence_order.get(threshold, 0)
    
    def __str__(self) -> str:
        """字符串表示（用于日志）"""
        return (f"AdvisoryResult(decision={self.decision.value}, "
                f"confidence={self.confidence.value}, "
                f"regime={self.market_regime.value}, "
                f"risk_ok={self.risk_exposure_allowed}, "
                f"quality={self.trade_quality.value}, "
                f"exec_perm={self.execution_permission.value}, "
                f"executable={self.executable})")
