"""
PR-ARCH-02: StateStore接口

最小状态存储接口，用于DecisionGate频率控制。

目标：
1. 最小接口：只保存last_decision_time和last_signal_direction
2. 不引入持仓语义：只记录决策，不记录持仓
3. 可替换实现：内存/Redis/数据库

设计原则：
- StateStore是接口，可有多种实现
- DecisionGate只依赖接口，不依赖具体实现
- 支持多symbol独立状态
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict
from datetime import datetime
from models.enums import Decision
import logging

logger = logging.getLogger(__name__)


class StateStore(ABC):
    """
    状态存储接口（抽象基类）
    
    职责：
    - 保存/读取决策时间
    - 保存/读取信号方向
    - 支持多symbol
    
    不负责：
    - 持仓管理（避免引入持仓语义）
    - 业务逻辑（只做存储）
    """
    
    @abstractmethod
    def save_decision_state(
        self,
        symbol: str,
        decision_time: datetime,
        signal_direction: Decision
    ) -> None:
        """
        保存决策状态
        
        Args:
            symbol: 交易对符号
            decision_time: 决策时间
            signal_direction: 信号方向（LONG/SHORT/NO_TRADE）
        """
        pass
    
    @abstractmethod
    def get_last_decision_time(self, symbol: str) -> Optional[datetime]:
        """
        获取上次决策时间
        
        Args:
            symbol: 交易对符号
        
        Returns:
            datetime或None
        """
        pass
    
    @abstractmethod
    def get_last_signal_direction(self, symbol: str) -> Optional[Decision]:
        """
        获取上次信号方向
        
        Args:
            symbol: 交易对符号
        
        Returns:
            Decision或None
        """
        pass
    
    @abstractmethod
    def clear(self, symbol: Optional[str] = None) -> None:
        """
        清空状态（用于测试）
        
        Args:
            symbol: 交易对符号，None表示清空所有
        """
        pass


class InMemoryStateStore(StateStore):
    """
    内存状态存储（默认实现）
    
    特性：
    - 使用dict存储（快速）
    - 不持久化（重启丢失）
    - 适合线上快速迭代
    """
    
    def __init__(self):
        """初始化内存存储"""
        self._last_decision_time: Dict[str, datetime] = {}
        self._last_signal_direction: Dict[str, Decision] = {}
        logger.info("InMemoryStateStore initialized")
    
    def save_decision_state(
        self,
        symbol: str,
        decision_time: datetime,
        signal_direction: Decision
    ) -> None:
        """保存决策状态"""
        self._last_decision_time[symbol] = decision_time
        self._last_signal_direction[symbol] = signal_direction
        logger.debug(f"[{symbol}] State saved: time={decision_time.isoformat()}, direction={signal_direction.value}")
    
    def get_last_decision_time(self, symbol: str) -> Optional[datetime]:
        """获取上次决策时间"""
        return self._last_decision_time.get(symbol)
    
    def get_last_signal_direction(self, symbol: str) -> Optional[Decision]:
        """获取上次信号方向"""
        return self._last_signal_direction.get(symbol)
    
    def clear(self, symbol: Optional[str] = None) -> None:
        """清空状态"""
        if symbol is None:
            self._last_decision_time.clear()
            self._last_signal_direction.clear()
            logger.info("All state cleared")
        else:
            self._last_decision_time.pop(symbol, None)
            self._last_signal_direction.pop(symbol, None)
            logger.debug(f"[{symbol}] State cleared")
    
    def get_state_summary(self) -> Dict:
        """
        获取状态摘要（用于调试）
        
        Returns:
            状态摘要字典
        """
        return {
            'symbols_count': len(self._last_decision_time),
            'symbols': list(self._last_decision_time.keys()),
            'state': {
                symbol: {
                    'last_decision_time': self._last_decision_time.get(symbol).isoformat() if self._last_decision_time.get(symbol) else None,
                    'last_signal_direction': self._last_signal_direction.get(symbol).value if self._last_signal_direction.get(symbol) else None
                }
                for symbol in self._last_decision_time.keys()
            }
        }


class DualTimeframeStateStore(StateStore):
    """
    双周期状态存储（扩展版）
    
    特性：
    - 分别保存短期/中期状态
    - 支持独立频控
    """
    
    def __init__(self):
        """初始化双周期存储"""
        # 短期状态
        self._short_last_decision_time: Dict[str, datetime] = {}
        self._short_last_signal_direction: Dict[str, Decision] = {}
        
        # 中期状态
        self._medium_last_decision_time: Dict[str, datetime] = {}
        self._medium_last_signal_direction: Dict[str, Decision] = {}
        
        logger.info("DualTimeframeStateStore initialized")
    
    def save_decision_state(
        self,
        symbol: str,
        decision_time: datetime,
        signal_direction: Decision
    ) -> None:
        """
        保存决策状态（默认保存到短期）
        
        注意：双周期模式应使用save_short/save_medium
        """
        self.save_short_decision_state(symbol, decision_time, signal_direction)
    
    def save_short_decision_state(
        self,
        symbol: str,
        decision_time: datetime,
        signal_direction: Decision
    ) -> None:
        """保存短期决策状态"""
        self._short_last_decision_time[symbol] = decision_time
        self._short_last_signal_direction[symbol] = signal_direction
        logger.debug(f"[{symbol}] Short-term state saved")
    
    def save_medium_decision_state(
        self,
        symbol: str,
        decision_time: datetime,
        signal_direction: Decision
    ) -> None:
        """保存中期决策状态"""
        self._medium_last_decision_time[symbol] = decision_time
        self._medium_last_signal_direction[symbol] = signal_direction
        logger.debug(f"[{symbol}] Medium-term state saved")
    
    def get_last_decision_time(self, symbol: str) -> Optional[datetime]:
        """获取上次决策时间（短期）"""
        return self._short_last_decision_time.get(symbol)
    
    def get_short_last_decision_time(self, symbol: str) -> Optional[datetime]:
        """获取短期上次决策时间"""
        return self._short_last_decision_time.get(symbol)
    
    def get_medium_last_decision_time(self, symbol: str) -> Optional[datetime]:
        """获取中期上次决策时间"""
        return self._medium_last_decision_time.get(symbol)
    
    def get_last_signal_direction(self, symbol: str) -> Optional[Decision]:
        """获取上次信号方向（短期）"""
        return self._short_last_signal_direction.get(symbol)
    
    def get_short_last_signal_direction(self, symbol: str) -> Optional[Decision]:
        """获取短期上次信号方向"""
        return self._short_last_signal_direction.get(symbol)
    
    def get_medium_last_signal_direction(self, symbol: str) -> Optional[Decision]:
        """获取中期上次信号方向"""
        return self._medium_last_signal_direction.get(symbol)
    
    def clear(self, symbol: Optional[str] = None) -> None:
        """清空状态"""
        if symbol is None:
            self._short_last_decision_time.clear()
            self._short_last_signal_direction.clear()
            self._medium_last_decision_time.clear()
            self._medium_last_signal_direction.clear()
            logger.info("All dual-timeframe state cleared")
        else:
            self._short_last_decision_time.pop(symbol, None)
            self._short_last_signal_direction.pop(symbol, None)
            self._medium_last_decision_time.pop(symbol, None)
            self._medium_last_signal_direction.pop(symbol, None)
            logger.debug(f"[{symbol}] Dual-timeframe state cleared")


# ============================================
# 工厂函数
# ============================================

def create_state_store(store_type: str = "memory") -> StateStore:
    """
    创建StateStore实例（工厂函数）
    
    Args:
        store_type: 存储类型 "memory" | "dual" | "redis" (future)
    
    Returns:
        StateStore实例
    """
    if store_type == "memory":
        return InMemoryStateStore()
    elif store_type == "dual":
        return DualTimeframeStateStore()
    else:
        raise ValueError(f"Unknown store_type: {store_type}")
