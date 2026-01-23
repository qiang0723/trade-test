"""
L1 Advisory Engine - 频率控制模块

职责：
1. 决策频率控制（最小间隔、翻转冷却）
2. 与DecisionMemory协作
"""

from typing import Tuple, List, Dict
from datetime import datetime
from models.enums import Decision
from models.reason_tags import ReasonTag
import logging

logger = logging.getLogger(__name__)


class FrequencyController:
    """频率控制器"""
    
    def __init__(self, config: Dict):
        """
        初始化频率控制器
        
        Args:
            config: 完整配置字典
        """
        self.config = config
    
    def apply_decision_control(
        self, 
        symbol: str, 
        decision: Decision, 
        reason_tags: List[ReasonTag],
        timestamp: datetime,
        decision_memory
    ) -> Tuple[Decision, List[ReasonTag]]:
        """
        决策频率控制
        
        规则：
        1. 最小决策间隔：防止短时间内重复输出
        2. 翻转冷却：防止方向频繁切换
        
        Args:
            symbol: 币种符号
            decision: 当前决策（原始信号，不会被改写）
            reason_tags: 现有标签列表
            timestamp: 当前时间
            decision_memory: 决策记忆管理器
        
        Returns:
            (decision保持不变, 新增的控制标签列表)
        """
        control_tags = []
        
        # 如果当前决策已经是NO_TRADE，无需检查
        if decision == Decision.NO_TRADE:
            return decision, control_tags
        
        # 获取配置
        config = self.config.get('decision_control', {})
        enable_min_interval = config.get('enable_min_interval', True)
        enable_flip_cooldown = config.get('enable_flip_cooldown', True)
        min_interval = config.get('min_decision_interval_seconds', 300)
        flip_cooldown = config.get('flip_cooldown_seconds', 600)
        
        # 获取上次决策记忆
        last = decision_memory.get_last_decision(symbol)
        
        if last is None:
            # 首次决策，不阻断
            logger.debug(f"[{symbol}] First decision, no control applied")
            return decision, control_tags
        
        last_time = last['time']
        last_side = last['side']
        elapsed = (timestamp - last_time).total_seconds()
        
        # 检查1: 最小决策间隔
        if enable_min_interval and elapsed < min_interval:
            logger.info(
                f"[{symbol}] MIN_INTERVAL_BLOCK: signal={decision.value}, elapsed={elapsed:.0f}s < {min_interval}s "
                f"(保留信号，通过DENY阻断执行)"
            )
            control_tags.append(ReasonTag.MIN_INTERVAL_BLOCK)
        
        # 检查2: 翻转冷却
        if enable_flip_cooldown:
            is_flip = (decision == Decision.LONG and last_side == Decision.SHORT) or \
                     (decision == Decision.SHORT and last_side == Decision.LONG)
            
            if is_flip and elapsed < flip_cooldown:
                logger.info(
                    f"[{symbol}] FLIP_COOLDOWN_BLOCK: signal={last_side.value}→{decision.value}, "
                    f"elapsed={elapsed:.0f}s < {flip_cooldown}s "
                    f"(保留信号，通过DENY阻断执行)"
                )
                control_tags.append(ReasonTag.FLIP_COOLDOWN_BLOCK)
        
        # 始终返回原始decision（不改写）
        if control_tags:
            logger.debug(f"[{symbol}] Decision control: signal preserved, will be blocked by execution_permission")
        
        return decision, control_tags
