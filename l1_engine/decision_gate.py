"""
PR-ARCH-02: DecisionGate决策门控

频率控制逻辑（冷却期、最小间隔、阻断）。

目标：
1. 频控与策略分离：DecisionCore负责策略，DecisionGate负责频控
2. 阻断不改写signal_decision：只通过executable/execution_permission表达
3. 最小状态接口：只依赖StateStore（last_decision_time + last_signal_direction）
4. 双周期支持：短期和中期独立频控

设计原则：
- DecisionGate只处理时间相关的频控逻辑
- 不修改DecisionDraft的decision字段
- 通过FrequencyControlResult记录阻断原因
"""

import logging
from typing import Optional
from datetime import datetime, timedelta
from models.decision_core_dto import (
    TimeframeDecisionDraft, TimeframeDecisionFinal,
    DualTimeframeDecisionDraft, DualTimeframeDecisionFinal,
    FrequencyControlResult
)
from models.thresholds import Thresholds
from models.enums import Decision, Timeframe
from models.reason_tags import ReasonTag
from l1_engine.state_store import StateStore

logger = logging.getLogger(__name__)


class DecisionGate:
    """
    决策门控（频率控制）
    
    职责：
    - 冷却期检查：相同方向重复信号
    - 最小间隔检查：两次决策时间间隔
    - 方向翻转：允许但记录
    - 状态保存：可执行信号更新StateStore
    
    不负责：
    - 策略逻辑（由DecisionCore负责）
    - 信号生成（由DecisionCore负责）
    """
    
    def __init__(self, state_store: StateStore):
        """
        初始化DecisionGate
        
        Args:
            state_store: 状态存储接口（InMemoryStateStore或DualTimeframeStateStore）
        """
        self.state_store = state_store
        logger.info("DecisionGate initialized (PR-ARCH-02 M4)")
    
    # ========================================
    # 主入口：单周期频控
    # ========================================
    
    def apply(
        self,
        draft: TimeframeDecisionDraft,
        symbol: str,
        now: datetime,
        thresholds: Thresholds,
        timeframe: Timeframe
    ) -> TimeframeDecisionFinal:
        """
        应用频率控制（单周期）
        
        流程：
        1. 获取历史状态
        2. 评估频率控制
        3. 计算最终executable
        4. 保存状态（如果可执行）
        5. 构建DecisionFinal
        
        Args:
            draft: 决策草稿（DecisionCore输出）
            symbol: 交易对符号
            now: 当前时间
            thresholds: 阈值配置
            timeframe: 周期标识（SHORT_TERM或MEDIUM_TERM）
        
        Returns:
            TimeframeDecisionFinal: 最终决策（添加频控信息）
        """
        # Step 1: 获取历史状态
        last_decision_time = self.state_store.get_last_decision_time(symbol)
        last_signal_direction = self.state_store.get_last_signal_direction(symbol)
        
        # Step 2: 评估频率控制
        freq_control = self._evaluate_frequency_control(
            draft, last_decision_time, last_signal_direction, now, thresholds, timeframe
        )
        
        # Step 3: 计算最终executable
        executable = self._compute_executable(draft, freq_control)
        
        # Step 4: 保存状态（如果可执行且是LONG/SHORT）
        if executable and draft.decision in [Decision.LONG, Decision.SHORT]:
            self.state_store.save_decision_state(symbol, now, draft.decision)
            logger.debug(f"[{symbol}] State saved: {draft.decision.value} at {now.isoformat()}")
        
        # Step 5: 构建DecisionFinal
        final = TimeframeDecisionFinal.from_draft(
            draft, executable, freq_control, timeframe
        )
        
        logger.debug(
            f"[{symbol}] {timeframe.value}: decision={draft.decision.value}, "
            f"executable={executable}, freq_blocked={freq_control.is_blocked}"
        )
        
        return final
    
    # ========================================
    # 主入口：双周期频控
    # ========================================
    
    def apply_dual(
        self,
        draft: DualTimeframeDecisionDraft,
        symbol: str,
        now: datetime,
        thresholds: Thresholds
    ) -> DualTimeframeDecisionFinal:
        """
        应用频率控制（双周期）
        
        短期和中期使用独立的StateStore，分别频控。
        
        Args:
            draft: 双周期决策草稿
            symbol: 交易对符号
            now: 当前时间
            thresholds: 阈值配置
        
        Returns:
            DualTimeframeDecisionFinal: 双周期最终决策
        """
        # 检查是否使用DualTimeframeStateStore
        from l1_engine.state_store import DualTimeframeStateStore
        
        if isinstance(self.state_store, DualTimeframeStateStore):
            # 使用双周期状态存储（独立频控）
            short_final = self._apply_with_dual_store(
                draft.short_term, symbol, now, thresholds, Timeframe.SHORT_TERM
            )
            medium_final = self._apply_with_dual_store(
                draft.medium_term, symbol, now, thresholds, Timeframe.MEDIUM_TERM
            )
        else:
            # 使用单一状态存储（共享频控）
            short_final = self.apply(
                draft.short_term, symbol, now, thresholds, Timeframe.SHORT_TERM
            )
            medium_final = self.apply(
                draft.medium_term, symbol, now, thresholds, Timeframe.MEDIUM_TERM
            )
        
        # 构建双周期最终决策
        return DualTimeframeDecisionFinal(
            short_term=short_final,
            medium_term=medium_final,
            global_risk_tags=draft.global_risk_tags,
            alignment=None  # TODO: 添加对齐分析
        )
    
    def _apply_with_dual_store(
        self,
        draft: TimeframeDecisionDraft,
        symbol: str,
        now: datetime,
        thresholds: Thresholds,
        timeframe: Timeframe
    ) -> TimeframeDecisionFinal:
        """
        使用双周期状态存储应用频控（内部方法）
        
        Args:
            draft: 决策草稿
            symbol: 交易对符号
            now: 当前时间
            thresholds: 阈值配置
            timeframe: 周期标识
        
        Returns:
            TimeframeDecisionFinal
        """
        from l1_engine.state_store import DualTimeframeStateStore
        dual_store = self.state_store  # type: DualTimeframeStateStore
        
        # 根据timeframe获取对应的历史状态
        if timeframe == Timeframe.SHORT_TERM:
            last_decision_time = dual_store.get_short_last_decision_time(symbol)
            last_signal_direction = dual_store.get_short_last_signal_direction(symbol)
        else:
            last_decision_time = dual_store.get_medium_last_decision_time(symbol)
            last_signal_direction = dual_store.get_medium_last_signal_direction(symbol)
        
        # 评估频率控制
        freq_control = self._evaluate_frequency_control(
            draft, last_decision_time, last_signal_direction, now, thresholds, timeframe
        )
        
        # 计算最终executable
        executable = self._compute_executable(draft, freq_control)
        
        # 保存状态
        if executable and draft.decision in [Decision.LONG, Decision.SHORT]:
            if timeframe == Timeframe.SHORT_TERM:
                dual_store.save_short_decision_state(symbol, now, draft.decision)
            else:
                dual_store.save_medium_decision_state(symbol, now, draft.decision)
            logger.debug(f"[{symbol}] {timeframe.value} state saved")
        
        # 构建Final
        return TimeframeDecisionFinal.from_draft(
            draft, executable, freq_control, timeframe
        )
    
    # ========================================
    # Step 2: 频率控制判断
    # ========================================
    
    def _evaluate_frequency_control(
        self,
        draft: TimeframeDecisionDraft,
        last_decision_time: Optional[datetime],
        last_signal_direction: Optional[Decision],
        now: datetime,
        thresholds: Thresholds,
        timeframe: Timeframe
    ) -> FrequencyControlResult:
        """
        评估频率控制
        
        检查项：
        1. 首次决策：总是允许
        2. 冷却期：相同方向重复信号（阻断）
        3. 最小间隔：两次决策时间过短（阻断）
        4. 方向翻转：允许但记录
        
        Args:
            draft: 决策草稿
            last_decision_time: 上次决策时间
            last_signal_direction: 上次信号方向
            now: 当前时间
            thresholds: 阈值配置
            timeframe: 周期标识
        
        Returns:
            FrequencyControlResult: 频控结果
        """
        result = FrequencyControlResult()
        
        # Rule 1: NO_TRADE总是允许（不受频控限制）
        if draft.decision == Decision.NO_TRADE:
            return result
        
        # Rule 2: 首次决策，总是允许
        if last_decision_time is None or last_signal_direction is None:
            logger.debug("First decision, no frequency control applied")
            return result
        
        # 计算时间间隔
        time_since_last = (now - last_decision_time).total_seconds()
        
        # 获取频控配置（TODO: 从thresholds读取，临时硬编码）
        if timeframe == Timeframe.SHORT_TERM:
            cooling_period = 1800  # 30分钟 TODO: thresholds.dual_timeframe.short_term_cooling_seconds
            min_interval = 600      # 10分钟 TODO: thresholds.dual_timeframe.short_term_min_interval_seconds
        else:
            cooling_period = 7200   # 2小时 TODO: thresholds.dual_timeframe.medium_term_cooling_seconds
            min_interval = 1800     # 30分钟 TODO: thresholds.dual_timeframe.medium_term_min_interval_seconds
        
        # Rule 3: 冷却期检查（相同方向重复信号）
        if draft.decision == last_signal_direction:
            if time_since_last < cooling_period:
                result.is_cooling = True
                result.is_blocked = True
                result.block_reason = f"Cooling period: {int(time_since_last)}s < {cooling_period}s"
                result.added_tags.append(ReasonTag.FREQUENCY_COOLING)
                logger.debug(f"Cooling period: same direction within {time_since_last}s")
                return result
        
        # Rule 4: 最小间隔检查（任意决策）
        if time_since_last < min_interval:
            result.min_interval_violated = True
            result.is_blocked = True
            result.block_reason = f"Min interval: {int(time_since_last)}s < {min_interval}s"
            result.added_tags.append(ReasonTag.MIN_INTERVAL_VIOLATED)
            logger.debug(f"Min interval violated: {time_since_last}s < {min_interval}s")
            return result
        
        # Rule 5: 方向翻转（允许但记录）
        if draft.decision != last_signal_direction and last_signal_direction != Decision.NO_TRADE:
            result.added_tags.append(ReasonTag.DIRECTION_FLIP)
            logger.debug(f"Direction flip: {last_signal_direction.value} -> {draft.decision.value}")
        
        return result
    
    # ========================================
    # Step 3: Executable计算
    # ========================================
    
    def _compute_executable(
        self,
        draft: TimeframeDecisionDraft,
        freq_control: FrequencyControlResult
    ) -> bool:
        """
        计算最终executable
        
        规则：
        1. NO_TRADE总是executable=True（允许随时输出）
        2. ExecutionPermission=DENY → False
        3. 频控阻断 → False
        4. 其他 → True
        
        Args:
            draft: 决策草稿
            freq_control: 频控结果
        
        Returns:
            bool: 是否可执行
        """
        # Rule 1: NO_TRADE总是允许
        if draft.decision == Decision.NO_TRADE:
            return True
        
        # Rule 2: ExecutionPermission=DENY
        from models.enums import ExecutionPermission
        if draft.execution_permission == ExecutionPermission.DENY:
            return False
        
        # Rule 3: 频控阻断
        if freq_control.is_blocked:
            return False
        
        # Rule 4: 其他情况允许
        return True


# ============================================
# 便捷函数
# ============================================

def apply_single_gate(
    draft: TimeframeDecisionDraft,
    symbol: str,
    now: datetime,
    thresholds: Thresholds,
    state_store: StateStore,
    timeframe: Timeframe = Timeframe.SHORT_TERM
) -> TimeframeDecisionFinal:
    """
    便捷函数：应用单周期频控
    
    Args:
        draft: 决策草稿
        symbol: 交易对符号
        now: 当前时间
        thresholds: 阈值配置
        state_store: 状态存储
        timeframe: 周期标识
    
    Returns:
        TimeframeDecisionFinal
    """
    gate = DecisionGate(state_store)
    return gate.apply(draft, symbol, now, thresholds, timeframe)


def apply_dual_gate(
    draft: DualTimeframeDecisionDraft,
    symbol: str,
    now: datetime,
    thresholds: Thresholds,
    state_store: StateStore
) -> DualTimeframeDecisionFinal:
    """
    便捷函数：应用双周期频控
    
    Args:
        draft: 双周期决策草稿
        symbol: 交易对符号
        now: 当前时间
        thresholds: 阈值配置
        state_store: 状态存储
    
    Returns:
        DualTimeframeDecisionFinal
    """
    gate = DecisionGate(state_store)
    return gate.apply_dual(draft, symbol, now, thresholds)
