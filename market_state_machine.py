"""
市场分析状态机模块

核心设计约束：
- 系统是状态机，不是一次性判断器
- 所有信号必须经过 System_State
- 所有阈值解释必须服从 Market_Regime
- 任一异常，默认 NO_TRADE

这是一个"有记忆、有耐心、会拒绝交易"的状态机，不是信号扫描器。
"""

from enum import Enum
from datetime import datetime
import sqlite3
import json


# ==================== 枚举定义（强制） ====================

class MarketRegime(Enum):
    """市场环境状态"""
    TREND = "TREND"      # 趋势市场
    RANGE = "RANGE"      # 震荡市场
    EXTREME = "EXTREME"  # 极端市场


class SystemState(Enum):
    """系统状态"""
    INIT = "INIT"                # 初始化
    WAIT = "WAIT"                # 等待（可以开方向）
    LONG_ACTIVE = "LONG_ACTIVE"  # 做多状态激活
    SHORT_ACTIVE = "SHORT_ACTIVE" # 做空状态激活
    COOL_DOWN = "COOL_DOWN"      # 冷却期（强制休眠）


class Decision(Enum):
    """交易决策"""
    LONG = "LONG"
    SHORT = "SHORT"
    NO_TRADE = "NO_TRADE"


# ==================== 配置参数 ====================

class StateMachineConfig:
    """状态机配置参数"""
    
    # Market Regime 判定阈值
    VOLATILITY_EXTREME_THRESHOLD = 0.08  # 8% 波动率认为极端
    VOLUME_EXTREME_MULTIPLIER = 5.0      # 成交量超过平均5倍认为极端
    VOLATILITY_NORMAL_RANGE = (0.01, 0.05)  # 正常波动率范围
    
    # OI 相关阈值
    OI_EXTREME_RATE = 0.30  # OI 6h变化超过30%认为极端
    OI_COLLAPSE_RATE = -0.20  # OI 6h变化小于-20%认为崩溃
    
    # 资金费率阈值
    FUNDING_RATE_HEALTHY_RANGE = (-0.0005, 0.001)  # 健康范围
    FUNDING_RATE_OVERHEATED = 0.002  # 过热阈值
    FUNDING_RATE_EXTREME = 0.005     # 极端阈值
    FUNDING_RATE_NEGATIVE = -0.001   # 负资金费率阈值
    
    # 买卖力量阈值
    AGGRESSIVE_BUY_STRONG = 0.60     # 买单强势阈值
    AGGRESSIVE_BUY_WEAK = 0.45       # 买单弱势阈值
    AGGRESSIVE_SELL_STRONG = 0.60    # 卖单强势阈值
    
    # 成交量阈值
    VOLUME_BREAKOUT_MULTIPLIER = 1.5  # 突破放量倍数
    VOLUME_STALL_MULTIPLIER = 0.7     # 滞涨缩量倍数
    
    # 冷却期配置
    COOLDOWN_LENGTH = 3  # 冷却期长度（分析周期数）
    
    # RANGE 市场下的严格阈值倍数
    RANGE_STRICTER_MULTIPLIER = 1.5


# ==================== 状态持久化 ====================

class StateStorage:
    """状态存储管理"""
    
    def __init__(self, db_path='market_state.db'):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化状态数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建状态表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                symbol VARCHAR(10) PRIMARY KEY,
                system_state VARCHAR(20) NOT NULL,
                market_regime VARCHAR(20) NOT NULL,
                cooldown_counter INTEGER DEFAULT 0,
                last_decision VARCHAR(20),
                state_entry_time DATETIME,
                last_update_time DATETIME,
                state_history TEXT,
                extra_data TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_state(self, symbol):
        """获取币种的状态"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM system_state WHERE symbol = ?
        """, (symbol,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        else:
            # 首次查询，返回初始状态
            return {
                'symbol': symbol,
                'system_state': SystemState.INIT.value,
                'market_regime': MarketRegime.RANGE.value,
                'cooldown_counter': 0,
                'last_decision': Decision.NO_TRADE.value,
                'state_entry_time': None,
                'last_update_time': None,
                'state_history': '[]',
                'extra_data': '{}'
            }
    
    def save_state(self, symbol, system_state, market_regime, cooldown_counter, 
                   last_decision, state_history=None, extra_data=None):
        """保存状态"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        state_history_json = json.dumps(state_history or [], ensure_ascii=False)
        extra_data_json = json.dumps(extra_data or {}, ensure_ascii=False)
        
        # 判断是否是状态切换
        old_state = self.get_state(symbol)
        state_entry_time = now if old_state['system_state'] != system_state else old_state.get('state_entry_time', now)
        
        cursor.execute("""
            INSERT OR REPLACE INTO system_state 
            (symbol, system_state, market_regime, cooldown_counter, last_decision,
             state_entry_time, last_update_time, state_history, extra_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, system_state, market_regime, cooldown_counter, last_decision,
              state_entry_time, now, state_history_json, extra_data_json))
        
        conn.commit()
        conn.close()


# ==================== 状态机核心 ====================

class MarketStateMachine:
    """市场分析状态机"""
    
    def __init__(self, config=None, storage=None):
        self.config = config or StateMachineConfig()
        self.storage = storage or StateStorage()
    
    # ==================== Market Regime 判定 ====================
    
    def detect_market_regime(self, data):
        """判定市场环境
        
        Args:
            data: 市场数据字典
            
        Returns:
            MarketRegime: 市场环境状态
        """
        volatility = data.get('volatility', 0)
        volume = data.get('volume', 0)
        volume_avg = data.get('volume_avg', 1)
        price_structure_continuous = data.get('price_structure_continuous', True)
        
        # 极端市场判定
        if volatility > self.config.VOLATILITY_EXTREME_THRESHOLD:
            return MarketRegime.EXTREME
        
        if volume > volume_avg * self.config.VOLUME_EXTREME_MULTIPLIER:
            return MarketRegime.EXTREME
        
        # 趋势市场判定
        if (price_structure_continuous and 
            self.config.VOLATILITY_NORMAL_RANGE[0] <= volatility <= self.config.VOLATILITY_NORMAL_RANGE[1]):
            return MarketRegime.TREND
        
        # 默认震荡市场
        return MarketRegime.RANGE
    
    # ==================== 结构性失败检测 ====================
    
    def detect_structural_failure(self, data):
        """检测结构性失败（核心保护机制）
        
        Args:
            data: 市场数据字典
            
        Returns:
            bool: 是否存在结构性失败
        """
        # OI 极端波动
        oi_delta_rate = abs(data.get('oi_delta_rate', 0))
        if oi_delta_rate > self.config.OI_EXTREME_RATE:
            return True
        
        # 资金费率极端
        funding_rate = abs(data.get('funding_rate', 0))
        if funding_rate > self.config.FUNDING_RATE_EXTREME:
            return True
        
        # 多个核心指标背离
        price_trend_6h = data.get('price_trend_6h', 0)
        oi_change_6h = data.get('oi_change_6h', 0)
        volume_change_6h = data.get('volume_change_6h', 0)
        
        # 价格上涨但OI和成交量都下跌（背离）
        if price_trend_6h > 0.02 and oi_change_6h < -0.1 and volume_change_6h < -0.1:
            return True
        
        # 价格下跌但OI和成交量都上涨（背离）
        if price_trend_6h < -0.02 and oi_change_6h > 0.1 and volume_change_6h > 0.1:
            return True
        
        return False
    
    # ==================== 方向判断函数 ====================
    
    def allow_long(self, data, market_regime):
        """做多判断（含 Regime 影响）
        
        Args:
            data: 市场数据字典
            market_regime: 市场环境
            
        Returns:
            bool: 是否允许做多
        """
        # EXTREME 市场禁止开仓
        if market_regime == MarketRegime.EXTREME:
            return False
        
        # 基础阈值
        volume_threshold = self.config.VOLUME_BREAKOUT_MULTIPLIER
        buy_ratio_threshold = self.config.AGGRESSIVE_BUY_STRONG
        
        # RANGE 市场使用更严格阈值
        if market_regime == MarketRegime.RANGE:
            volume_threshold *= self.config.RANGE_STRICTER_MULTIPLIER
            buy_ratio_threshold = min(0.65, buy_ratio_threshold * 1.1)
        
        # 判断条件
        volume = data.get('volume', 0)
        volume_avg = data.get('volume_avg', 1)
        oi_delta = data.get('oi_delta', 0)
        oi_delta_rate = data.get('oi_delta_rate', 0)
        funding_rate = data.get('funding_rate', 0)
        aggressive_buy_ratio = data.get('aggressive_buy_ratio', 0)
        
        # 核心条件
        volume_condition = volume > volume_avg * volume_threshold
        oi_growth = oi_delta > 0 and oi_delta_rate < self.config.OI_EXTREME_RATE
        funding_healthy = (self.config.FUNDING_RATE_HEALTHY_RANGE[0] <= 
                          funding_rate <= self.config.FUNDING_RATE_HEALTHY_RANGE[1])
        buy_drives = aggressive_buy_ratio >= buy_ratio_threshold
        
        return volume_condition and oi_growth and funding_healthy and buy_drives
    
    def allow_short(self, data, market_regime):
        """做空判断（含 Regime 影响）
        
        Args:
            data: 市场数据字典
            market_regime: 市场环境
            
        Returns:
            bool: 是否允许做空
        """
        # EXTREME 市场禁止开仓
        if market_regime == MarketRegime.EXTREME:
            return False
        
        # 基础阈值
        volume_threshold = self.config.VOLUME_STALL_MULTIPLIER
        sell_ratio_threshold = self.config.AGGRESSIVE_SELL_STRONG
        
        # RANGE 市场使用更严格阈值
        if market_regime == MarketRegime.RANGE:
            sell_ratio_threshold = min(0.65, sell_ratio_threshold * 1.1)
        
        # 判断条件
        volume = data.get('volume', 0)
        volume_avg = data.get('volume_avg', 1)
        price_trend_6h = data.get('price_trend_6h', 0)
        oi_delta = data.get('oi_delta', 0)
        funding_rate = data.get('funding_rate', 0)
        aggressive_buy_ratio = data.get('aggressive_buy_ratio', 0)
        
        # 核心条件
        price_stalls = (price_trend_6h > 0 and volume < volume_avg * volume_threshold)
        oi_accumulation = oi_delta > 0
        funding_overheated = funding_rate > self.config.FUNDING_RATE_OVERHEATED
        buy_weakens = aggressive_buy_ratio < self.config.AGGRESSIVE_BUY_WEAK
        
        return price_stalls and oi_accumulation and funding_overheated and buy_weakens
    
    # ==================== 方向失效判断 ====================
    
    def long_invalidation(self, data):
        """做多失效判断（退出条件）
        
        Args:
            data: 市场数据字典
            
        Returns:
            bool: 做多是否失效
        """
        price_trend_6h = data.get('price_trend_6h', 0)
        funding_rate = data.get('funding_rate', 0)
        oi_change_6h = data.get('oi_change_6h', 0)
        
        # 价格跌破结构（6h下跌超过3%）
        price_breaks = price_trend_6h < -0.03
        
        # 资金费率转为极端
        funding_extreme = abs(funding_rate) > self.config.FUNDING_RATE_EXTREME
        
        # OI 崩溃
        oi_collapses = oi_change_6h < self.config.OI_COLLAPSE_RATE
        
        return price_breaks or funding_extreme or oi_collapses
    
    def short_invalidation(self, data):
        """做空失效判断（退出条件）
        
        Args:
            data: 市场数据字典
            
        Returns:
            bool: 做空是否失效
        """
        aggressive_sell_ratio = data.get('aggressive_sell_ratio', 0)
        funding_rate = data.get('funding_rate', 0)
        oi_change_6h = data.get('oi_change_6h', 0)
        
        # 卖压耗尽（卖单占比低于40%）
        selling_exhausted = aggressive_sell_ratio < 0.40
        
        # 资金费率转负
        funding_negative = funding_rate < self.config.FUNDING_RATE_NEGATIVE
        
        # OI 崩溃
        oi_collapses = oi_change_6h < self.config.OI_COLLAPSE_RATE
        
        return selling_exhausted or funding_negative or oi_collapses
    
    # ==================== 状态机主循环 ====================
    
    def on_new_tick(self, symbol, data):
        """状态机主循环（每个新周期调用）
        
        Args:
            symbol: 币种符号
            data: 市场数据字典
            
        Returns:
            dict: 决策结果
        """
        # 获取当前状态
        state_data = self.storage.get_state(symbol)
        current_state = SystemState(state_data['system_state'])
        cooldown_counter = state_data['cooldown_counter']
        
        # 判定市场环境
        market_regime = self.detect_market_regime(data)
        
        # Step 1：系统级强制保护
        if market_regime == MarketRegime.EXTREME:
            new_state = SystemState.COOL_DOWN
            cooldown_counter = self.config.COOLDOWN_LENGTH
            decision = Decision.NO_TRADE
            reason = f"市场环境极端（{market_regime.value}），强制进入冷却期"
            
            self.storage.save_state(
                symbol, new_state.value, market_regime.value,
                cooldown_counter, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, new_state, market_regime, reason, data)
        
        # Step 2：状态机迁移逻辑
        if current_state == SystemState.INIT:
            return self._handle_init(symbol, data, market_regime)
        
        elif current_state == SystemState.WAIT:
            return self._handle_wait(symbol, data, market_regime)
        
        elif current_state == SystemState.LONG_ACTIVE:
            return self._handle_long_active(symbol, data, market_regime)
        
        elif current_state == SystemState.SHORT_ACTIVE:
            return self._handle_short_active(symbol, data, market_regime)
        
        elif current_state == SystemState.COOL_DOWN:
            return self._handle_cool_down(symbol, data, market_regime, cooldown_counter)
        
        else:
            # 异常状态，重置为 WAIT
            return self._handle_init(symbol, data, market_regime)
    
    # ==================== 状态处理函数 ====================
    
    def _handle_init(self, symbol, data, market_regime):
        """处理 INIT 状态"""
        new_state = SystemState.WAIT
        decision = Decision.NO_TRADE
        reason = "系统初始化，进入等待状态"
        
        self.storage.save_state(
            symbol, new_state.value, market_regime.value,
            0, decision.value,
            extra_data={'reason': reason}
        )
        
        return self._format_result(symbol, decision, new_state, market_regime, reason, data)
    
    def _handle_wait(self, symbol, data, market_regime):
        """处理 WAIT 状态（唯一允许开方向）"""
        # 检查结构性失败
        if self.detect_structural_failure(data):
            decision = Decision.NO_TRADE
            reason = "检测到结构性失败，保持等待"
            
            self.storage.save_state(
                symbol, SystemState.WAIT.value, market_regime.value,
                0, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, SystemState.WAIT, market_regime, reason, data)
        
        # 优先检查做空条件（SHORT 优先级高于 LONG）
        if self.allow_short(data, market_regime):
            new_state = SystemState.SHORT_ACTIVE
            decision = Decision.SHORT
            reason = f"满足做空条件，市场环境：{market_regime.value}"
            
            self.storage.save_state(
                symbol, new_state.value, market_regime.value,
                0, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, new_state, market_regime, reason, data)
        
        # 检查做多条件
        if self.allow_long(data, market_regime):
            new_state = SystemState.LONG_ACTIVE
            decision = Decision.LONG
            reason = f"满足做多条件，市场环境：{market_regime.value}"
            
            self.storage.save_state(
                symbol, new_state.value, market_regime.value,
                0, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, new_state, market_regime, reason, data)
        
        # 没有满足任何条件，继续等待
        decision = Decision.NO_TRADE
        reason = f"无明确信号，继续等待（市场环境：{market_regime.value}）"
        
        self.storage.save_state(
            symbol, SystemState.WAIT.value, market_regime.value,
            0, decision.value,
            extra_data={'reason': reason}
        )
        
        return self._format_result(symbol, decision, SystemState.WAIT, market_regime, reason, data)
    
    def _handle_long_active(self, symbol, data, market_regime):
        """处理 LONG_ACTIVE 状态（方向保持）"""
        # 检查结构性失败
        if self.detect_structural_failure(data):
            new_state = SystemState.COOL_DOWN
            cooldown_counter = self.config.COOLDOWN_LENGTH
            decision = Decision.NO_TRADE
            reason = "做多状态中检测到结构性失败，进入冷却期"
            
            self.storage.save_state(
                symbol, new_state.value, market_regime.value,
                cooldown_counter, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, new_state, market_regime, reason, data)
        
        # 检查做多失效
        if self.long_invalidation(data):
            new_state = SystemState.WAIT
            decision = Decision.NO_TRADE
            reason = "做多条件失效，返回等待状态"
            
            self.storage.save_state(
                symbol, new_state.value, market_regime.value,
                0, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, new_state, market_regime, reason, data)
        
        # 保持做多状态
        decision = Decision.LONG
        reason = f"做多状态保持，市场环境：{market_regime.value}"
        
        self.storage.save_state(
            symbol, SystemState.LONG_ACTIVE.value, market_regime.value,
            0, decision.value,
            extra_data={'reason': reason}
        )
        
        return self._format_result(symbol, decision, SystemState.LONG_ACTIVE, market_regime, reason, data)
    
    def _handle_short_active(self, symbol, data, market_regime):
        """处理 SHORT_ACTIVE 状态（方向保持）"""
        # 检查结构性失败
        if self.detect_structural_failure(data):
            new_state = SystemState.COOL_DOWN
            cooldown_counter = self.config.COOLDOWN_LENGTH
            decision = Decision.NO_TRADE
            reason = "做空状态中检测到结构性失败，进入冷却期"
            
            self.storage.save_state(
                symbol, new_state.value, market_regime.value,
                cooldown_counter, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, new_state, market_regime, reason, data)
        
        # 检查做空失效
        if self.short_invalidation(data):
            new_state = SystemState.WAIT
            decision = Decision.NO_TRADE
            reason = "做空条件失效，返回等待状态"
            
            self.storage.save_state(
                symbol, new_state.value, market_regime.value,
                0, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, new_state, market_regime, reason, data)
        
        # 保持做空状态
        decision = Decision.SHORT
        reason = f"做空状态保持，市场环境：{market_regime.value}"
        
        self.storage.save_state(
            symbol, SystemState.SHORT_ACTIVE.value, market_regime.value,
            0, decision.value,
            extra_data={'reason': reason}
        )
        
        return self._format_result(symbol, decision, SystemState.SHORT_ACTIVE, market_regime, reason, data)
    
    def _handle_cool_down(self, symbol, data, market_regime, cooldown_counter):
        """处理 COOL_DOWN 状态（强制休眠）"""
        cooldown_counter -= 1
        
        if cooldown_counter <= 0:
            new_state = SystemState.WAIT
            decision = Decision.NO_TRADE
            reason = "冷却期结束，返回等待状态"
            
            self.storage.save_state(
                symbol, new_state.value, market_regime.value,
                0, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, new_state, market_regime, reason, data)
        else:
            decision = Decision.NO_TRADE
            reason = f"冷却期中，剩余 {cooldown_counter} 个周期"
            
            self.storage.save_state(
                symbol, SystemState.COOL_DOWN.value, market_regime.value,
                cooldown_counter, decision.value,
                extra_data={'reason': reason}
            )
            
            return self._format_result(symbol, decision, SystemState.COOL_DOWN, market_regime, reason, data)
    
    # ==================== 辅助函数 ====================
    
    def _format_result(self, symbol, decision, system_state, market_regime, reason, data):
        """格式化返回结果"""
        # 构建详细分析过程
        detailed_analysis = self._build_detailed_analysis(
            symbol, decision, system_state, market_regime, reason, data
        )
        
        return {
            'success': True,
            'symbol': symbol,
            'analysis': {
                'trade_action': decision.value,
                'system_state': system_state.value,
                'market_regime': market_regime.value,
                'state_reason': reason,
                'data_summary': {
                    'price': data.get('price', 0),
                    'price_change_24h': data.get('price_change_24h', 0),
                    'price_trend_6h': data.get('price_trend_6h', 0),
                    'volume_change_6h': data.get('volume_change_6h', 0),
                    'oi_change_6h': data.get('oi_change_6h', 0),
                    'funding_rate': data.get('funding_rate', 0),
                    'buy_ratio_1h': data.get('aggressive_buy_ratio', 0) * 100,
                    'sell_ratio_1h': (1 - data.get('aggressive_buy_ratio', 0.5)) * 100,
                    'total_amount_1h': data.get('total_amount_1h', 0)
                },
                'detailed_analysis': detailed_analysis
            }
        }
    
    def _build_detailed_analysis(self, symbol, decision, system_state, market_regime, reason, data):
        """构建详细分析过程
        
        Args:
            symbol: 币种符号
            decision: 交易决策
            system_state: 系统状态
            market_regime: 市场环境
            reason: 决策原因
            data: 市场数据
            
        Returns:
            list: 详细分析内容列表
        """
        analysis = []
        
        # ========== 第一部分：状态概览 ==========
        analysis.extend([
            "=" * 60,
            f"🤖 系统状态：{system_state.value}",
            f"🌍 市场环境：{market_regime.value}",
            f"📊 交易决策：{decision.value}",
            f"💡 决策原因：{reason}",
            "=" * 60,
            ""
        ])
        
        # ========== 第二部分：市场环境分析 ==========
        analysis.append("📍 【市场环境判定】")
        analysis.append("─" * 60)
        
        volatility = data.get('volatility', 0)
        volume = data.get('volume', 0)
        volume_avg = data.get('volume_avg', 1)
        volume_ratio = volume / volume_avg if volume_avg > 0 else 0
        price_structure = data.get('price_structure_continuous', False)
        
        # 极端市场判定
        if market_regime == MarketRegime.EXTREME:
            analysis.append(f"⚠️ 市场环境：EXTREME（极端市场）")
            if volatility > self.config.VOLATILITY_EXTREME_THRESHOLD:
                analysis.append(f"  • 波动率：{volatility*100:.2f}% > {self.config.VOLATILITY_EXTREME_THRESHOLD*100:.0f}%（极端波动）")
            if volume_ratio > self.config.VOLUME_EXTREME_MULTIPLIER:
                analysis.append(f"  • 成交量：{volume_ratio:.2f}x > {self.config.VOLUME_EXTREME_MULTIPLIER:.0f}x（异常放量）")
            analysis.append("  ⇒ 系统强制保护，禁止开仓")
        
        # 趋势市场判定
        elif market_regime == MarketRegime.TREND:
            analysis.append(f"✅ 市场环境：TREND（趋势市场）")
            analysis.append(f"  • 波动率：{volatility*100:.2f}%（正常范围 {self.config.VOLATILITY_NORMAL_RANGE[0]*100:.0f}%-{self.config.VOLATILITY_NORMAL_RANGE[1]*100:.0f}%）")
            analysis.append(f"  • 价格结构：{'连续' if price_structure else '不连续'}")
            analysis.append(f"  • 成交量比：{volume_ratio:.2f}x")
            analysis.append("  ⇒ 使用标准阈值")
        
        # 震荡市场判定
        else:
            analysis.append(f"⚡ 市场环境：RANGE（震荡市场）")
            analysis.append(f"  • 波动率：{volatility*100:.2f}%")
            analysis.append(f"  • 价格结构：不明确")
            analysis.append(f"  • 成交量比：{volume_ratio:.2f}x")
            analysis.append(f"  ⇒ 使用严格阈值（{self.config.RANGE_STRICTER_MULTIPLIER:.1f}倍）")
        
        analysis.append("")
        
        # ========== 第三部分：核心指标检查 ==========
        analysis.append("📊 【核心指标检查】")
        analysis.append("─" * 60)
        
        # 价格趋势
        price_trend_6h = data.get('price_trend_6h', 0)
        price_change_24h = data.get('price_change_24h', 0)
        analysis.append(f"💹 价格趋势：")
        analysis.append(f"  • 6h趋势：{price_trend_6h*100:+.2f}%")
        analysis.append(f"  • 24h涨跌：{price_change_24h*100:+.2f}%")
        
        # 成交量分析
        volume_change_6h = data.get('volume_change_6h', 0)
        analysis.append(f"📊 成交量分析：")
        analysis.append(f"  • 6h变化：{volume_change_6h*100:+.2f}%")
        analysis.append(f"  • 当前/平均：{volume_ratio:.2f}x")
        if volume_ratio > self.config.VOLUME_BREAKOUT_MULTIPLIER:
            analysis.append(f"  ✓ 突破放量（> {self.config.VOLUME_BREAKOUT_MULTIPLIER:.1f}x）")
        elif volume_ratio < self.config.VOLUME_STALL_MULTIPLIER:
            analysis.append(f"  ✓ 滞涨缩量（< {self.config.VOLUME_STALL_MULTIPLIER:.1f}x）")
        else:
            analysis.append(f"  • 成交量正常")
        
        # OI分析
        oi_delta = data.get('oi_delta', 0)
        oi_delta_rate = data.get('oi_delta_rate', 0)
        oi_change_6h = data.get('oi_change_6h', 0)
        analysis.append(f"📈 持仓量（OI）分析：")
        analysis.append(f"  • 6h变化：{oi_change_6h*100:+.2f}%")
        analysis.append(f"  • 变化速率：{oi_delta_rate*100:.2f}%")
        if oi_delta > 0:
            if oi_delta_rate > self.config.OI_EXTREME_RATE:
                analysis.append(f"  ⚠️ OI极端增长（> {self.config.OI_EXTREME_RATE*100:.0f}%）")
            else:
                analysis.append(f"  ✓ OI健康增长")
        elif oi_change_6h < self.config.OI_COLLAPSE_RATE:
            analysis.append(f"  ⚠️ OI崩溃（< {self.config.OI_COLLAPSE_RATE*100:.0f}%）")
        else:
            analysis.append(f"  • OI {'增长' if oi_delta > 0 else '下降'}")
        
        # 资金费率分析
        funding_rate = data.get('funding_rate', 0)
        analysis.append(f"💰 资金费率分析：")
        analysis.append(f"  • 当前费率：{funding_rate*100:+.4f}%")
        if abs(funding_rate) > self.config.FUNDING_RATE_EXTREME:
            analysis.append(f"  ⚠️ 极端费率（绝对值 > {self.config.FUNDING_RATE_EXTREME*100:.2f}%）")
        elif funding_rate > self.config.FUNDING_RATE_OVERHEATED:
            analysis.append(f"  ⚠️ 费率过热（> {self.config.FUNDING_RATE_OVERHEATED*100:.2f}%）")
        elif self.config.FUNDING_RATE_HEALTHY_RANGE[0] <= funding_rate <= self.config.FUNDING_RATE_HEALTHY_RANGE[1]:
            analysis.append(f"  ✓ 费率健康（{self.config.FUNDING_RATE_HEALTHY_RANGE[0]*100:.2f}% ~ {self.config.FUNDING_RATE_HEALTHY_RANGE[1]*100:.2f}%）")
        elif funding_rate < self.config.FUNDING_RATE_NEGATIVE:
            analysis.append(f"  ⚠️ 费率转负（< {self.config.FUNDING_RATE_NEGATIVE*100:.2f}%）")
        else:
            analysis.append(f"  • 费率略高但可接受")
        
        # 买卖力量分析
        buy_ratio = data.get('aggressive_buy_ratio', 0.5)
        sell_ratio = 1 - buy_ratio
        analysis.append(f"🔄 买卖力量分析（1h）：")
        analysis.append(f"  • 主动买单：{buy_ratio*100:.1f}%")
        analysis.append(f"  • 主动卖单：{sell_ratio*100:.1f}%")
        if buy_ratio >= self.config.AGGRESSIVE_BUY_STRONG:
            analysis.append(f"  ✓ 买单主导（≥ {self.config.AGGRESSIVE_BUY_STRONG*100:.0f}%）")
        elif buy_ratio < self.config.AGGRESSIVE_BUY_WEAK:
            analysis.append(f"  ✓ 买单弱势（< {self.config.AGGRESSIVE_BUY_WEAK*100:.0f}%）")
        elif sell_ratio >= self.config.AGGRESSIVE_SELL_STRONG:
            analysis.append(f"  ✓ 卖单主导（≥ {self.config.AGGRESSIVE_SELL_STRONG*100:.0f}%）")
        else:
            analysis.append(f"  • 买卖均衡")
        
        analysis.append("")
        
        # ========== 第四部分：条件判断过程 ==========
        if system_state == SystemState.WAIT:
            analysis.extend(self._build_wait_analysis(data, market_regime, decision))
        elif system_state == SystemState.LONG_ACTIVE:
            analysis.extend(self._build_long_active_analysis(data, decision))
        elif system_state == SystemState.SHORT_ACTIVE:
            analysis.extend(self._build_short_active_analysis(data, decision))
        elif system_state == SystemState.COOL_DOWN:
            state_data = self.storage.get_state(symbol)
            cooldown_counter = state_data.get('cooldown_counter', 0)
            analysis.extend(self._build_cooldown_analysis(cooldown_counter))
        
        # ========== 第五部分：数据摘要 ==========
        analysis.extend([
            "",
            "=" * 60,
            "📋 【数据摘要】",
            "─" * 60,
            f"💹 价格：${data.get('price', 0):.4f}",
            f"📊 24h涨跌：{data.get('price_change_24h', 0)*100:+.2f}%",
            f"📈 6h趋势：{data.get('price_trend_6h', 0)*100:+.2f}%",
            f"📊 成交量6h：{data.get('volume_change_6h', 0)*100:+.2f}%",
            f"📈 持仓量6h：{data.get('oi_change_6h', 0)*100:+.2f}%",
            f"💰 资金费率：{data.get('funding_rate', 0)*100:+.4f}%",
            f"🔄 1h买卖：买{buy_ratio*100:.1f}% vs 卖{sell_ratio*100:.1f}%",
            f"💵 1h成交额：${data.get('total_amount_1h', 0)/1000000:.2f}M",
            "=" * 60
        ])
        
        return analysis
    
    def _build_wait_analysis(self, data, market_regime, decision):
        """构建WAIT状态的分析过程"""
        analysis = [
            "🔍 【等待状态 - 条件检查】",
            "─" * 60
        ]
        
        # 检查结构性失败
        if self.detect_structural_failure(data):
            analysis.append("⚠️ 检测到结构性失败：")
            oi_delta_rate = abs(data.get('oi_delta_rate', 0))
            funding_rate = abs(data.get('funding_rate', 0))
            if oi_delta_rate > self.config.OI_EXTREME_RATE:
                analysis.append(f"  • OI极端波动：{oi_delta_rate*100:.2f}% > {self.config.OI_EXTREME_RATE*100:.0f}%")
            if funding_rate > self.config.FUNDING_RATE_EXTREME:
                analysis.append(f"  • 资金费率极端：{funding_rate*100:.4f}% > {self.config.FUNDING_RATE_EXTREME*100:.2f}%")
            analysis.append("  ⇒ 保持等待，不开仓")
            return analysis
        
        # 检查做空条件（优先级高）
        analysis.append("📉 检查做空条件（优先）：")
        short_allowed = self.allow_short(data, market_regime)
        if market_regime == MarketRegime.EXTREME:
            analysis.append("  ✗ 市场环境极端，禁止开空")
        else:
            price_trend_6h = data.get('price_trend_6h', 0)
            volume = data.get('volume', 0)
            volume_avg = data.get('volume_avg', 1)
            oi_delta = data.get('oi_delta', 0)
            funding_rate = data.get('funding_rate', 0)
            buy_ratio = data.get('aggressive_buy_ratio', 0.5)
            
            price_stalls = price_trend_6h > 0 and volume < volume_avg * self.config.VOLUME_STALL_MULTIPLIER
            oi_accumulation = oi_delta > 0
            funding_overheated = funding_rate > self.config.FUNDING_RATE_OVERHEATED
            buy_weakens = buy_ratio < self.config.AGGRESSIVE_BUY_WEAK
            
            analysis.append(f"  • 滞涨缩量：{'✓' if price_stalls else '✗'} (6h涨{price_trend_6h*100:+.2f}%, 量{volume/volume_avg:.2f}x)")
            analysis.append(f"  • OI堆积：{'✓' if oi_accumulation else '✗'} (OI变化{oi_delta*100:+.2f}%)")
            analysis.append(f"  • 费率过热：{'✓' if funding_overheated else '✗'} (费率{funding_rate*100:.4f}%)")
            analysis.append(f"  • 买单弱势：{'✓' if buy_weakens else '✗'} (买单{buy_ratio*100:.1f}%)")
            
            if short_allowed:
                analysis.append("  ⇒ ✅ 满足做空条件，进入SHORT_ACTIVE")
            else:
                analysis.append("  ⇒ 条件不足，检查做多条件")
        
        # 检查做多条件
        if not short_allowed:
            analysis.append("")
            analysis.append("📈 检查做多条件：")
            long_allowed = self.allow_long(data, market_regime)
            if market_regime == MarketRegime.EXTREME:
                analysis.append("  ✗ 市场环境极端，禁止开多")
            else:
                volume = data.get('volume', 0)
                volume_avg = data.get('volume_avg', 1)
                oi_delta = data.get('oi_delta', 0)
                oi_delta_rate = data.get('oi_delta_rate', 0)
                funding_rate = data.get('funding_rate', 0)
                buy_ratio = data.get('aggressive_buy_ratio', 0.5)
                
                volume_threshold = self.config.VOLUME_BREAKOUT_MULTIPLIER
                if market_regime == MarketRegime.RANGE:
                    volume_threshold *= self.config.RANGE_STRICTER_MULTIPLIER
                
                volume_condition = volume > volume_avg * volume_threshold
                oi_growth = oi_delta > 0 and oi_delta_rate < self.config.OI_EXTREME_RATE
                funding_healthy = (self.config.FUNDING_RATE_HEALTHY_RANGE[0] <= 
                                  funding_rate <= self.config.FUNDING_RATE_HEALTHY_RANGE[1])
                buy_drives = buy_ratio >= self.config.AGGRESSIVE_BUY_STRONG
                
                analysis.append(f"  • 突破放量：{'✓' if volume_condition else '✗'} (量{volume/volume_avg:.2f}x > {volume_threshold:.2f}x)")
                analysis.append(f"  • OI健康增长：{'✓' if oi_growth else '✗'} (OI+{oi_delta*100:.2f}%, 速率{oi_delta_rate*100:.2f}%)")
                analysis.append(f"  • 费率健康：{'✓' if funding_healthy else '✗'} (费率{funding_rate*100:.4f}%)")
                analysis.append(f"  • 买单主导：{'✓' if buy_drives else '✗'} (买单{buy_ratio*100:.1f}%)")
                
                if long_allowed:
                    analysis.append("  ⇒ ✅ 满足做多条件，进入LONG_ACTIVE")
                else:
                    analysis.append("  ⇒ 条件不足，继续等待")
        
        return analysis
    
    def _build_long_active_analysis(self, data, decision):
        """构建LONG_ACTIVE状态的分析过程"""
        analysis = [
            "📈 【做多状态 - 持续检查】",
            "─" * 60
        ]
        
        # 检查结构性失败
        if self.detect_structural_failure(data):
            analysis.append("⚠️ 检测到结构性失败，退出做多状态")
            return analysis
        
        # 检查做多失效条件
        price_trend_6h = data.get('price_trend_6h', 0)
        funding_rate = data.get('funding_rate', 0)
        oi_change_6h = data.get('oi_change_6h', 0)
        
        price_breaks = price_trend_6h < -0.03
        funding_extreme = abs(funding_rate) > self.config.FUNDING_RATE_EXTREME
        oi_collapses = oi_change_6h < self.config.OI_COLLAPSE_RATE
        
        analysis.append("🔍 做多失效检查：")
        analysis.append(f"  • 价格跌破：{'✗ 失效' if price_breaks else '✓ 正常'} (6h{price_trend_6h*100:+.2f}%)")
        analysis.append(f"  • 费率极端：{'✗ 失效' if funding_extreme else '✓ 正常'} (费率{funding_rate*100:.4f}%)")
        analysis.append(f"  • OI崩溃：{'✗ 失效' if oi_collapses else '✓ 正常'} (OI{oi_change_6h*100:+.2f}%)")
        
        if decision == Decision.NO_TRADE:
            analysis.append("  ⇒ ❌ 做多条件失效，返回WAIT")
        else:
            analysis.append("  ⇒ ✅ 做多状态保持")
        
        return analysis
    
    def _build_short_active_analysis(self, data, decision):
        """构建SHORT_ACTIVE状态的分析过程"""
        analysis = [
            "📉 【做空状态 - 持续检查】",
            "─" * 60
        ]
        
        # 检查结构性失败
        if self.detect_structural_failure(data):
            analysis.append("⚠️ 检测到结构性失败，退出做空状态")
            return analysis
        
        # 检查做空失效条件
        sell_ratio = 1 - data.get('aggressive_buy_ratio', 0.5)
        funding_rate = data.get('funding_rate', 0)
        oi_change_6h = data.get('oi_change_6h', 0)
        
        selling_exhausted = sell_ratio < 0.40
        funding_negative = funding_rate < self.config.FUNDING_RATE_NEGATIVE
        oi_collapses = oi_change_6h < self.config.OI_COLLAPSE_RATE
        
        analysis.append("🔍 做空失效检查：")
        analysis.append(f"  • 卖压耗尽：{'✗ 失效' if selling_exhausted else '✓ 正常'} (卖单{sell_ratio*100:.1f}%)")
        analysis.append(f"  • 费率转负：{'✗ 失效' if funding_negative else '✓ 正常'} (费率{funding_rate*100:.4f}%)")
        analysis.append(f"  • OI崩溃：{'✗ 失效' if oi_collapses else '✓ 正常'} (OI{oi_change_6h*100:+.2f}%)")
        
        if decision == Decision.NO_TRADE:
            analysis.append("  ⇒ ❌ 做空条件失效，返回WAIT")
        else:
            analysis.append("  ⇒ ✅ 做空状态保持")
        
        return analysis
    
    def _build_cooldown_analysis(self, cooldown_counter):
        """构建COOL_DOWN状态的分析过程"""
        analysis = [
            "❄️ 【冷却状态 - 强制休眠】",
            "─" * 60,
            f"⏰ 剩余冷却周期：{cooldown_counter}",
            "🚫 冷却期间禁止所有交易操作",
            ""
        ]
        
        if cooldown_counter > 0:
            analysis.append(f"  ⇒ 继续冷却，还需等待 {cooldown_counter} 个周期")
        else:
            analysis.append("  ⇒ 冷却结束，返回WAIT状态")
        
        return analysis


# ==================== 全局实例 ====================

_state_machine_instance = None

def get_state_machine():
    """获取全局状态机实例"""
    global _state_machine_instance
    if _state_machine_instance is None:
        import os
        # 数据库存储在 /app/db 目录（Docker挂载点）
        db_dir = os.getenv('DB_DIR', '/app/db')
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, 'market_state.db')
        storage = StateStorage(db_path=db_path)
        _state_machine_instance = MarketStateMachine(storage=storage)
    return _state_machine_instance
