"""
L1 决策记忆管理

负责：
- DecisionMemory: 单路径决策记忆
- DualDecisionMemory: 双路径决策记忆（PR-DUAL）
"""

from typing import Dict, Optional, Tuple, TYPE_CHECKING
from datetime import datetime
from models.enums import Decision
import logging

# PR-DUAL: 类型检查导入（避免循环导入）
if TYPE_CHECKING:
    from models.enums import AlignmentType

logger = logging.getLogger(__name__)


class DecisionMemory:
    """
    决策记忆管理（PR-C）
    
    职责：
    - 记录每个币种的上次非NO_TRADE决策
    - 用于决策频率控制（最小间隔、翻转冷却）
    """
    
    def __init__(self):
        self._memory = {}  # {symbol: {"time": datetime, "side": Decision}}
    
    def get_last_decision(self, symbol: str) -> Optional[Dict]:
        """获取指定币种的上次决策记录"""
        return self._memory.get(symbol)
    
    def update_decision(self, symbol: str, decision: Decision, timestamp: datetime):
        """
        更新决策记忆（仅LONG/SHORT）
        
        Args:
            symbol: 币种符号
            decision: 决策方向
            timestamp: 决策时间
        """
        # 只记录LONG和SHORT，NO_TRADE不更新记忆
        if decision in [Decision.LONG, Decision.SHORT]:
            self._memory[symbol] = {
                "time": timestamp,
                "side": decision
            }
            logger.debug(f"[{symbol}] Updated decision memory: {decision.value} at {timestamp}")
    
    def clear(self, symbol: str):
        """清除指定币种的记忆"""
        self._memory.pop(symbol, None)
        logger.debug(f"[{symbol}] Cleared decision memory")


class DualDecisionMemory:
    """
    双周期决策记忆管理（PR-DUAL）
    
    职责：
    - 管理短期（5m/15m）、中长期（1h/6h）、对齐类型三个独立计时器
    - 防止短时间内重复输出相同决策
    - 防止频繁方向翻转（LONG ↔ SHORT）
    
    设计原则：
    - 三独立计时器：短期、中长期、对齐类型各自管理
    - NO_TRADE不受频率控制（允许随时输出）
    - 翻转冷却独立于决策间隔
    """
    
    def __init__(self, config: Dict = None):
        """
        初始化双周期决策记忆
        
        Args:
            config: 配置字典，包含 dual_decision_control 配置段
        """
        # 短期决策记忆 {symbol: {"time": datetime, "decision": Decision}}
        self._short_term_memory = {}
        
        # 中长期决策记忆 {symbol: {"time": datetime, "decision": Decision}}
        self._medium_term_memory = {}
        
        # 对齐类型记忆 {symbol: {"time": datetime, "alignment_type": AlignmentType}}
        self._alignment_memory = {}
        
        # 从配置加载时间参数
        if config:
            dual_config = config.get('dual_decision_control', {})
        else:
            dual_config = {}
        
        # 短期决策控制参数
        self.short_term_interval = dual_config.get('short_term_interval_seconds', 300)  # 5分钟
        self.short_term_flip_cooldown = dual_config.get('short_term_flip_cooldown_seconds', 450)  # 7.5分钟
        
        # 中长期决策控制参数
        self.medium_term_interval = dual_config.get('medium_term_interval_seconds', 1800)  # 30分钟
        self.medium_term_flip_cooldown = dual_config.get('medium_term_flip_cooldown_seconds', 900)  # 15分钟
        
        # 对齐类型翻转冷却
        self.alignment_flip_cooldown = dual_config.get('alignment_flip_cooldown_seconds', 900)  # 15分钟
        
        logger.info(f"DualDecisionMemory initialized: "
                   f"short_term={self.short_term_interval}s/{self.short_term_flip_cooldown}s, "
                   f"medium_term={self.medium_term_interval}s/{self.medium_term_flip_cooldown}s, "
                   f"alignment_flip={self.alignment_flip_cooldown}s")
    
    def should_block_short_term(
        self, 
        symbol: str, 
        new_decision: Decision, 
        current_time: datetime
    ) -> Tuple[bool, str]:
        """
        检查短期决策是否应被频率控制阻断
        
        规则：
        1. NO_TRADE永远不阻断（允许随时输出）
        2. 最小间隔检查：距离上次决策 < short_term_interval
        3. 翻转冷却检查：LONG ↔ SHORT 切换需等待 flip_cooldown
        
        Args:
            symbol: 币种符号
            new_decision: 新决策
            current_time: 当前时间
        
        Returns:
            (should_block, reason): 是否阻断及原因
        """
        # NO_TRADE永不阻断
        if new_decision == Decision.NO_TRADE:
            return False, ""
        
        last_record = self._short_term_memory.get(symbol)
        
        if not last_record:
            # 首次决策，不阻断
            return False, ""
        
        last_time = last_record["time"]
        last_decision = last_record["decision"]
        time_elapsed = (current_time - last_time).total_seconds()
        
        # 检查1：最小间隔
        if time_elapsed < self.short_term_interval:
            reason = f"短期决策间隔不足 ({time_elapsed:.0f}s < {self.short_term_interval}s)"
            logger.debug(f"[{symbol}] Short-term blocked: {reason}")
            return True, reason
        
        # 检查2：翻转冷却（LONG ↔ SHORT）
        if last_decision != Decision.NO_TRADE and new_decision != last_decision:
            if time_elapsed < self.short_term_flip_cooldown:
                reason = f"短期方向翻转冷却中 ({time_elapsed:.0f}s < {self.short_term_flip_cooldown}s)"
                logger.debug(f"[{symbol}] Short-term flip blocked: {last_decision.value} → {new_decision.value}")
                return True, reason
        
        return False, ""
    
    def should_block_medium_term(
        self, 
        symbol: str, 
        new_decision: Decision, 
        current_time: datetime
    ) -> Tuple[bool, str]:
        """
        检查中长期决策是否应被频率控制阻断
        
        规则同 should_block_short_term，但使用中长期时间参数
        """
        # NO_TRADE永不阻断
        if new_decision == Decision.NO_TRADE:
            return False, ""
        
        last_record = self._medium_term_memory.get(symbol)
        
        if not last_record:
            return False, ""
        
        last_time = last_record["time"]
        last_decision = last_record["decision"]
        time_elapsed = (current_time - last_time).total_seconds()
        
        # 检查1：最小间隔
        if time_elapsed < self.medium_term_interval:
            reason = f"中长期决策间隔不足 ({time_elapsed:.0f}s < {self.medium_term_interval}s)"
            logger.debug(f"[{symbol}] Medium-term blocked: {reason}")
            return True, reason
        
        # 检查2：翻转冷却
        if last_decision != Decision.NO_TRADE and new_decision != last_decision:
            if time_elapsed < self.medium_term_flip_cooldown:
                reason = f"中长期方向翻转冷却中 ({time_elapsed:.0f}s < {self.medium_term_flip_cooldown}s)"
                logger.debug(f"[{symbol}] Medium-term flip blocked: {last_decision.value} → {new_decision.value}")
                return True, reason
        
        return False, ""
    
    def should_block_alignment_flip(
        self, 
        symbol: str, 
        new_alignment_type: 'AlignmentType', 
        current_time: datetime
    ) -> Tuple[bool, str]:
        """
        检查对齐类型翻转是否应被阻断
        
        规则：
        - 仅阻断重大翻转：BOTH_LONG ↔ BOTH_SHORT
        - 其他类型变化不阻断（如 BOTH_LONG → PARTIAL_LONG）
        
        Args:
            symbol: 币种符号
            new_alignment_type: 新的对齐类型
            current_time: 当前时间
        
        Returns:
            (should_block, reason): 是否阻断及原因
        """
        from models.enums import AlignmentType
        
        # 定义重大翻转对（双向）
        major_flips = {
            (AlignmentType.BOTH_LONG, AlignmentType.BOTH_SHORT),
            (AlignmentType.BOTH_SHORT, AlignmentType.BOTH_LONG),
        }
        
        last_record = self._alignment_memory.get(symbol)
        
        if not last_record:
            return False, ""
        
        last_time = last_record["time"]
        last_alignment = last_record["alignment_type"]
        time_elapsed = (current_time - last_time).total_seconds()
        
        # 检查是否是重大翻转
        flip_pair = (last_alignment, new_alignment_type)
        if flip_pair in major_flips:
            if time_elapsed < self.alignment_flip_cooldown:
                reason = f"对齐类型重大翻转冷却中 ({time_elapsed:.0f}s < {self.alignment_flip_cooldown}s)"
                logger.debug(f"[{symbol}] Alignment flip blocked: {last_alignment.value} → {new_alignment_type.value}")
                return True, reason
        
        return False, ""
    
    def update_short_term(self, symbol: str, decision: Decision, timestamp: datetime):
        """更新短期决策记忆（仅LONG/SHORT）"""
        if decision in [Decision.LONG, Decision.SHORT]:
            self._short_term_memory[symbol] = {
                "time": timestamp,
                "decision": decision
            }
            logger.debug(f"[{symbol}] Updated short-term memory: {decision.value}")
    
    def update_medium_term(self, symbol: str, decision: Decision, timestamp: datetime):
        """更新中长期决策记忆（仅LONG/SHORT）"""
        if decision in [Decision.LONG, Decision.SHORT]:
            self._medium_term_memory[symbol] = {
                "time": timestamp,
                "decision": decision
            }
            logger.debug(f"[{symbol}] Updated medium-term memory: {decision.value}")
    
    def update_alignment(self, symbol: str, alignment_type: 'AlignmentType', timestamp: datetime):
        """更新对齐类型记忆"""
        self._alignment_memory[symbol] = {
            "time": timestamp,
            "alignment_type": alignment_type
        }
        logger.debug(f"[{symbol}] Updated alignment memory: {alignment_type.value}")
    
    def clear(self, symbol: str):
        """清除指定币种的所有记忆"""
        self._short_term_memory.pop(symbol, None)
        self._medium_term_memory.pop(symbol, None)
        self._alignment_memory.pop(symbol, None)
        logger.debug(f"[{symbol}] Cleared dual decision memory")
