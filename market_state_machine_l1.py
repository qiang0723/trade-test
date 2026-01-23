"""
L1 Advisory Layer - 核心决策引擎

这是L1决策层的核心实现，负责：
1. 固化10步决策管道（v3.0扩展：新增Step 8执行许可、Step 9置信度）
2. 风险准入评估（第一道闸门）
3. 交易质量评估（第二道闸门）
4. 方向判断（资金费率降级）
5. 决策频率控制（PR-C）
6. ExecutionPermission三级执行许可（方案D）
7. 置信度混合模式计算（PR-D）
8. 输出标准化AdvisoryResult（含executable双门槛判定）

不包含：
- 执行逻辑
- 仓位管理
- 止损止盈
- 订单下达
"""

import yaml
import os
from typing import Dict, Tuple, List, Optional, TYPE_CHECKING
from datetime import datetime, timedelta
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, SystemState, ExecutionPermission
from models.advisory_result import AdvisoryResult
from models.reason_tags import ReasonTag
from metrics_normalizer import normalize_metrics, normalize_metrics_with_trace
import logging

# PR-DUAL: 类型检查导入（避免循环导入）
if TYPE_CHECKING:
    from models.dual_timeframe_result import (
        DualTimeframeResult, TimeframeConclusion, AlignmentAnalysis
    )

# 配置日志
logging.basicConfig(level=logging.INFO)
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


class L1AdvisoryEngine:
    """
    L1 决策层核心引擎
    
    职责:
    - 单币种方向决策 (LONG/SHORT/NO_TRADE)
    - 固化10步决策管道（v3.0扩展：含ExecutionPermission三级许可、双门槛机制）
    - 输出标准化 AdvisoryResult
    
    不做:
    - 不涉及执行逻辑
    - 不输出仓位/入场点/止损止盈
    - 不管理订单
    
    PATCH-P0-02增强:
    - None一等公民：全链路None-safe，防止abs(None)/比较None崩溃
    - 提供统一helper函数：_num, _abs, _compare, _fmt
    
    PATCH-P0-01增强:
    - 冷启动/缺口策略：字段分级检查（core vs optional）
    - 禁止6h缺数据长期INVALID_DATA
    """
    
    # ========== PATCH-P0-01: 字段分类定义 ==========
    
    # 核心必需字段（最小不可缺集合）
    CORE_REQUIRED_FIELDS = [
        'price',
        'volume_24h',
        'funding_rate'
    ]
    
    # 短期可选字段（5m/15m）- 缺失影响short_term结论
    SHORT_TERM_OPTIONAL_FIELDS = [
        'price_change_5m',
        'price_change_15m',
        'oi_change_5m',
        'oi_change_15m',
        'taker_imbalance_5m',
        'taker_imbalance_15m',
        'volume_ratio_5m',
        'volume_ratio_15m'
    ]
    
    # 中期可选字段（1h/6h）- 缺失影响medium_term结论
    MEDIUM_TERM_OPTIONAL_FIELDS = [
        'price_change_1h',
        'price_change_6h',
        'oi_change_1h',
        'oi_change_6h',
        'taker_imbalance_1h',
        'volume_1h'
    ]
    
    # ========== End of Field Categories ==========
    
    # ========== PATCH-P0-02: None-safe Helper函数 ==========
    
    def _num(self, data: Dict, key: str, default=None) -> Optional[float]:
        """
        None-safe数值读取
        
        Args:
            data: 数据字典
            key: 键名
            default: 默认值（None）
        
        Returns:
            float值或None
        
        示例:
            imbalance = self._num(data, 'taker_imbalance_1h')
            if imbalance is not None and abs(imbalance) > 0.6:
                # 安全处理
        """
        value = data.get(key, default)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning(f"Invalid numeric value for {key}: {value}")
            return None
    
    def _abs(self, value: Optional[float]) -> Optional[float]:
        """
        None-safe abs
        
        Args:
            value: 数值或None
        
        Returns:
            abs(value)或None
        """
        return abs(value) if value is not None else None
    
    def _compare(self, value: Optional[float], op: str, threshold: float) -> bool:
        """
        None-safe比较（None视为False）
        
        Args:
            value: 数值或None
            op: 操作符（'>', '<', '>=', '<=', '==', '!='）
            threshold: 阈值
        
        Returns:
            比较结果（None返回False）
        
        示例:
            if self._compare(imbalance, '>', 0.6):
                # imbalance > 0.6 且不为None
        """
        if value is None:
            return False
        
        if op == '>':
            return value > threshold
        elif op == '<':
            return value < threshold
        elif op == '>=':
            return value >= threshold
        elif op == '<=':
            return value <= threshold
        elif op == '==':
            return value == threshold
        elif op == '!=':
            return value != threshold
        else:
            logger.warning(f"Unknown operator: {op}")
            return False
    
    def _fmt(self, value: Optional[float], precision: int = 2) -> str:
        """
        None-safe格式化（用于日志）
        
        Args:
            value: 数值或None
            precision: 小数位数
        
        Returns:
            格式化字符串（None返回"NA"）
        
        示例:
            logger.info(f"Imbalance: {self._fmt(imbalance)}")
        """
        if value is None:
            return "NA"
        try:
            return f"{value:.{precision}f}"
        except (TypeError, ValueError):
            return str(value)
    
    # ========== End of None-safe Helpers ==========
    
    def __init__(self, config_path: str = None):
        """
        初始化L1引擎
        
        Args:
            config_path: 配置文件路径，默认为 config/l1_thresholds.yaml
        """
        # 加载配置
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'config', 'l1_thresholds.yaml')
        
        self.config = self._load_config(config_path)
        
        # ⚠️ 启动时校验：防止配置错误（P1-3, PR-H）
        self._validate_decimal_calibration(self.config)        # 1. 口径校验：百分比必须用小数
        self._validate_threshold_consistency(self.config)      # 2. 门槛一致性校验（P1-3）
        self._validate_reason_tag_spelling(self.config)        # 3. ReasonTag拼写校验（P1-3）
        self._validate_confidence_values(self.config)          # 4. Confidence值拼写校验（PR-H）
        
        self.thresholds = self._flatten_thresholds(self.config)
        
        # 状态机状态
        self.current_state = SystemState.INIT
        self.state_enter_time = datetime.now()
        
        # 历史数据（用于计算指标如资金费率波动）
        self.history_data = {}
        
        # 管道执行记录（用于可视化）
        self.last_pipeline_steps = []
        
        # 决策记忆管理（PR-C）
        self.decision_memory = DecisionMemory()
        
        # 双周期决策记忆管理（PR-DUAL）
        self.dual_decision_memory = DualDecisionMemory(self.config)
        
        logger.info(f"L1AdvisoryEngine initialized with {len(self.thresholds)} thresholds")
    
    def on_new_tick(self, symbol: str, data: Dict) -> AdvisoryResult:
        """
        L1决策核心入口 - 固定10步管道（v3.0扩展版）
        
        Args:
            symbol: 交易对符号（如 "BTC"）
            data: 市场数据字典，包含：
                - price: 当前价格
                - price_change_1h: 1小时价格变化率(%)
                - price_change_6h: 6小时价格变化率(%)
                - volume_1h: 1小时成交量
                - volume_24h: 24小时成交量
                - taker_imbalance_1h: Taker买卖失衡度 (-1到1)（PATCH-P0-2：统一使用taker_imbalance）
                - funding_rate: 资金费率（小数，如0.0001表示0.01%）
                - oi_change_1h: 1小时持仓量变化率(%)
                - oi_change_6h: 6小时持仓量变化率(%)
        
        Returns:
            AdvisoryResult: 标准化决策结果（含execution_permission和executable字段）
        """
        reason_tags = []
        
        # 清空上次管道记录
        self.last_pipeline_steps = []
        
        logger.info(f"[{symbol}] Starting L1 decision pipeline")
        
        # ===== Step 1: 数据验证 + 指标规范化 + 新鲜度检查 =====
        is_valid, normalized_data, fail_tag, norm_trace = self._validate_data(data)
        if not is_valid:
            fail_reason = fail_tag.value if fail_tag else 'unknown'
            logger.warning(f"[{symbol}] Data validation failed: {fail_reason}")
            self.last_pipeline_steps.append({
                'step': 1, 'name': 'validate_data', 'status': 'failed',
                'message': f'数据验证失败：{fail_reason}',
                'result': None,
                'normalization_trace': norm_trace  # PATCH-1: 添加 trace
            })
            return self._build_no_trade_result(
                reason_tags=[fail_tag] if fail_tag else [ReasonTag.INVALID_DATA],
                regime=MarketRegime.RANGE,
                risk_allowed=False,
                quality=TradeQuality.POOR,
                price=data.get('price')  # 尝试从原始data获取
            )
        
        # 使用规范化后的数据（后续所有步骤都用这个）
        data = normalized_data
        
        self.last_pipeline_steps.append({
            'step': 1, 'name': 'validate_data', 'status': 'success',
            'message': '数据验证通过（含规范化+新鲜度检查）',
            'result': 'Valid',
            'normalization_trace': norm_trace  # PATCH-1: 添加 trace
        })
        
        # ===== Step 1.5: Lookback Coverage 检查（PATCH-2）=====
        coverage_ok, coverage_tags = self._check_lookback_coverage(data)
        if not coverage_ok:
            logger.warning(f"[{symbol}] Lookback coverage check failed: {[t.value for t in coverage_tags]}")
            self.last_pipeline_steps.append({
                'step': 1.5, 'name': 'check_coverage', 'status': 'failed',
                'message': f'Lookback coverage检查失败：{[t.value for t in coverage_tags]}',
                'result': None
            })
            # 任何关键窗口缺失都返回 NO_TRADE
            return self._build_no_trade_result(
                reason_tags=coverage_tags,
                regime=MarketRegime.RANGE,
                risk_allowed=False,
                quality=TradeQuality.POOR,
                price=data.get('price')
            )
        
        # ===== Step 2: 市场环境识别 =====
        regime, regime_tags = self._detect_market_regime(data)
        reason_tags.extend(regime_tags)  # ✅ 添加市场环境标签（如SHORT_TERM_TREND）
        
        logger.info(f"[{symbol}] Market regime: {regime.value}")
        if regime_tags:
            logger.info(f"[{symbol}] Regime tags: {[tag.value for tag in regime_tags]}")
        
        self.last_pipeline_steps.append({
            'step': 2, 'name': 'detect_regime', 'status': 'success',
            'message': f'市场环境: {regime.value.upper()}', 'result': regime.value
        })
        
        # ===== Step 3: 风险准入评估（第一道闸门）=====
        risk_allowed, risk_tags = self._eval_risk_exposure_allowed(data, regime)
        reason_tags.extend(risk_tags)
        
        self.last_pipeline_steps.append({
            'step': 3, 'name': 'eval_risk', 
            'status': 'success' if risk_allowed else 'failed',
            'message': f"风险准入: {'通过' if risk_allowed else '拒绝'}",
            'result': 'Allowed' if risk_allowed else 'Denied'
        })
        
        if not risk_allowed:
            logger.warning(f"[{symbol}] Risk denied: {[tag.value for tag in risk_tags]}")
            return self._build_no_trade_result(
                reason_tags=reason_tags,
                regime=regime,
                risk_allowed=False,
                quality=TradeQuality.POOR,
                price=data.get('price')
            )
        
        # ===== Step 4: 交易质量评估（第二道闸门）=====
        quality, quality_tags = self._eval_trade_quality(symbol, data, regime)
        reason_tags.extend(quality_tags)
        
        self.last_pipeline_steps.append({
            'step': 4, 'name': 'eval_quality',
            'status': 'success' if quality == TradeQuality.GOOD else 'warning',
            'message': f"交易质量: {quality.value.upper()}",
            'result': quality.value
        })
        
        if quality == TradeQuality.POOR:
            logger.warning(f"[{symbol}] Quality poor: {[tag.value for tag in quality_tags]}")
            return self._build_no_trade_result(
                reason_tags=reason_tags,
                regime=regime,
                risk_allowed=True,
                quality=TradeQuality.POOR,
                price=data.get('price')
            )
        
        # ===== Step 5: 方向评估（SHORT优先）=====
        allow_short, short_tags = self._eval_short_direction(data, regime)
        allow_long, long_tags = self._eval_long_direction(data, regime)
        
        # ✅ 添加方向评估产生的标签（包括短期信号标签）
        if allow_short:
            reason_tags.extend(short_tags)
        if allow_long:
            reason_tags.extend(long_tags)
        
        logger.info(f"[{symbol}] Direction: allow_short={allow_short}, allow_long={allow_long}")
        
        direction_result = []
        if allow_long:
            direction_result.append('LONG')
        if allow_short:
            direction_result.append('SHORT')
        
        self.last_pipeline_steps.append({
            'step': 5, 'name': 'eval_direction',
            'status': 'success' if (allow_long or allow_short) else 'warning',
            'message': f"方向评估: {', '.join(direction_result) if direction_result else '无明确方向'}",
            'result': direction_result if direction_result else None
        })
        
        # ===== Step 6: 决策优先级判断 =====
        decision, direction_tags = self._decide_priority(allow_short, allow_long)
        reason_tags.extend(direction_tags)
        
        self.last_pipeline_steps.append({
            'step': 6, 'name': 'decide_priority',
            'status': 'success' if decision != Decision.NO_TRADE else 'warning',
            'message': f"决策: {decision.value.upper()}",
            'result': decision.value
        })
        
        # ===== Step 6.5: 三层触发判定（PR-005）=====
        # 在方向确定后，频控前，进行多周期确认
        ltf_status, ltf_tags = self._evaluate_multi_tf(data, decision)
        reason_tags.extend(ltf_tags)
        
        # 应用binding_policy（仅当LTF功能启用且有结果时记录）
        if ltf_status != 'not_applicable':
            self.last_pipeline_steps.append({
                'step': 6.5, 'name': 'multi_tf_check',
                'status': 'success' if ltf_status in ['confirmed', 'partial'] else 'warning',
                'message': f"三层触发: {ltf_status.upper()}",
                'result': ltf_status
            })
            
            # PR-005: 根据ltf_status和binding_policy应用策略
            decision = self._apply_binding_policy(
                decision=decision,
                ltf_status=ltf_status,
                reason_tags=reason_tags
            )
            logger.debug(f"[{symbol}] LTF Status: {ltf_status}, decision after binding: {decision.value}")
        
        # ===== Step 7: 决策频率控制（PR-004重构）=====
        # PR-004: 保存原始信号（频控前的方向）
        signal_decision = decision
        
        decision, control_tags = self._apply_decision_control(
            symbol=symbol,
            decision=decision,
            reason_tags=reason_tags,
            timestamp=datetime.now()
        )
        reason_tags.extend(control_tags)
        
        # PR-004: decision不再被改写，检查是否有频控标签
        control_blocked = len(control_tags) > 0
        
        self.last_pipeline_steps.append({
            'step': 7, 'name': 'decision_control',
            'status': 'success' if not control_blocked else 'warning',
            'message': '频率控制通过' if not control_blocked else f'频率控制标记：{control_tags[0].value if control_tags else ""}（信号保留，执行阻断）',
            'result': 'Allowed' if not control_blocked else f'Signal:{signal_decision.value}, Blocked'
        })
        
        # ===== Step 8: 计算执行许可级别（方案D）=====
        execution_permission = self._compute_execution_permission(reason_tags)
        
        self.last_pipeline_steps.append({
            'step': 8, 'name': 'compute_execution_permission',
            'status': 'success',
            'message': f"执行许可: {execution_permission.value.upper()}",
            'result': execution_permission.value
        })
        
        # ===== Step 9: 置信度计算 =====
        confidence = self._compute_confidence(decision, regime, quality, reason_tags)
        
        self.last_pipeline_steps.append({
            'step': 9, 'name': 'compute_confidence',
            'status': 'success',
            'message': f"置信度: {confidence.value.upper()}",
            'result': confidence.value
        })
        
        # 更新状态机
        self._update_state(decision)
        
        # 添加辅助标签（资金费率、持仓量变化）
        # ⚠️ 设计意图：辅助标签在 Step 8 之后添加，是纯信息性标签，不影响 execution_permission
        # 如果需要让辅助标签影响执行许可，应移到 Step 8 之前
        self._add_auxiliary_tags(data, reason_tags)
        
        # 去重 reason_tags（保持顺序）
        seen = set()
        unique_tags = []
        for tag in reason_tags:
            if tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)
        reason_tags = unique_tags
        
        result_timestamp = datetime.now()
        
        # ===== Step 10: 构造结果（PR-004: 包含signal_decision）=====
        result = AdvisoryResult(
            decision=decision,
            confidence=confidence,
            market_regime=regime,
            system_state=self.current_state,
            risk_exposure_allowed=True,
            trade_quality=quality,
            reason_tags=reason_tags,
            timestamp=result_timestamp,
            execution_permission=execution_permission,  # 方案D新增
            executable=False,  # 先初始化为False
            signal_decision=signal_decision,  # PR-004: 原始信号方向（频控前）
            price=data.get('price')  # 添加信号出现时的价格
        )
        
        # 计算executable标志位（方案D双门槛）
        exec_config = self.config.get('executable_control', {})
        min_conf_normal_str = exec_config.get('min_confidence_normal', 'HIGH')
        min_conf_reduced_str = exec_config.get('min_confidence_reduced', 'MEDIUM')
        
        min_conf_normal = self._string_to_confidence(min_conf_normal_str)
        min_conf_reduced = self._string_to_confidence(min_conf_reduced_str)
        
        result.executable = result.compute_executable(
            min_confidence_normal=min_conf_normal,
            min_confidence_reduced=min_conf_reduced
        )
        
        # 🔥 更新决策记忆（PR-C）- 仅LONG/SHORT会更新
        # P1修复：被频控阻断的决策不更新记忆，避免"间隔"被被阻断的决策刷新
        # 这样翻转冷却的计算基准始终是上次"真正可执行"的决策时间
        if not control_blocked:
            self.decision_memory.update_decision(symbol, decision, result_timestamp)
        else:
            logger.debug(f"[{symbol}] Decision memory NOT updated: blocked by frequency control")
        
        logger.info(f"[{symbol}] Decision: {result}")
        
        return result
    
    # ========================================
    # Step 1: 数据验证
    # ========================================
    
    def _validate_data(self, data: Dict) -> Tuple[bool, Dict, Optional[ReasonTag], Optional[dict]]:
        """
        验证输入数据的完整性和有效性
        
        包含：
        1. 必需字段检查
        2. 指标口径规范化（百分比统一为小数格式）- PATCH-1增强
        3. 异常尺度检测（防止混用）
        4. 数据新鲜度检查（PR-002）
        
        Args:
            data: 市场数据字典
        
        Returns:
            (是否有效, 规范化后的数据, 失败原因tag, normalization_trace字典)
        """
        # PATCH-P0-01: 字段分级检查（替代原有required_fields）
        # 1. 检查核心必需字段（最小不可缺集合）
        missing_core = [f for f in self.CORE_REQUIRED_FIELDS if f not in data or data[f] is None]
        if missing_core:
            logger.error(f"Missing core required fields: {missing_core}")
            return False, data, ReasonTag.INVALID_DATA, None
        
        # 2. 检查短期可选字段（缺失标记但不硬失败）
        missing_short_term = [f for f in self.SHORT_TERM_OPTIONAL_FIELDS if f not in data or data[f] is None]
        
        # 3. 检查中期可选字段（缺失标记但不硬失败）
        missing_medium_term = [f for f in self.MEDIUM_TERM_OPTIONAL_FIELDS if f not in data or data[f] is None]
        
        # 4. 记录缺失情况（用于后续决策）
        data['_field_gaps'] = {
            'short_term': missing_short_term,
            'medium_term': missing_medium_term
        }
        
        # 5. 日志输出
        if missing_short_term:
            logger.info(f"Short-term optional fields missing: {missing_short_term}")
        if missing_medium_term:
            logger.info(f"Medium-term optional fields missing: {missing_medium_term}")
        
        # PATCH-P0-01: 即使optional字段缺失，也不返回INVALID_DATA
        # 后续逻辑会根据_field_gaps决定如何处理
        
        # 数据新鲜度检查（PR-002）
        if 'timestamp' in data or 'source_timestamp' in data:
            data_time = data.get('source_timestamp') or data.get('timestamp')
            if data_time is not None:
                # 计算数据年龄，统一转换为datetime对象
                if isinstance(data_time, str):
                    data_time = datetime.fromisoformat(data_time)
                elif isinstance(data_time, int):
                    # 毫秒时间戳转换为datetime
                    data_time = datetime.fromtimestamp(data_time / 1000)
                elif not isinstance(data_time, datetime):
                    # 其他类型尝试转换
                    try:
                        data_time = datetime.fromtimestamp(int(data_time) / 1000)
                    except:
                        pass  # 无法转换，跳过时效性检查
                
                if isinstance(data_time, datetime):
                    staleness_seconds = (datetime.now() - data_time).total_seconds()
                else:
                    staleness_seconds = 0  # 无效时间，不检查时效性
                max_staleness = self.thresholds.get('data_max_staleness_seconds', 120)
                
                if staleness_seconds > max_staleness:
                    logger.warning(
                        f"Data is stale: {staleness_seconds:.1f}s old "
                        f"(max: {max_staleness}s)"
                    )
                    return False, data, ReasonTag.DATA_STALE, None
        
        # PATCH-2: 保存 coverage（normalize 会移除 _metadata）
        lookback_coverage = data.get('_metadata', {}).get('lookback_coverage')
        
        # 指标口径规范化（PATCH-1增强：含 trace）
        normalized_data, is_valid, error_msg, norm_trace = normalize_metrics_with_trace(data)
        if not is_valid:
            logger.error(f"Metrics normalization failed: {error_msg}")
            return False, data, ReasonTag.INVALID_DATA, norm_trace.to_dict()
        
        # PATCH-2: 恢复 coverage（用于后续检查）
        if lookback_coverage:
            normalized_data['_metadata'] = {'lookback_coverage': lookback_coverage}
        
        # 规范化成功，记录 trace
        logger.debug(
            f"Normalization trace: format={norm_trace.input_percentage_format}, "
            f"converted={len(norm_trace.converted_fields)}, "
            f"skipped={len(norm_trace.skipped_fields)}"
        )
        
        # P0-02: 兼容注入层（在normalize之后、使用之前）
        normalized_data = self._inject_compatibility_fields(normalized_data)
        
        # 基础异常值检查（保留，作为双重保护）
        # P0-02: 使用taker_imbalance_1h（可能由buy_sell_imbalance注入）
        taker_imb_1h = self._num(normalized_data, 'taker_imbalance_1h')
        if taker_imb_1h is not None and (taker_imb_1h < -1 or taker_imb_1h > 1):
            logger.error(f"Invalid taker_imbalance_1h: {taker_imb_1h}")
            return False, normalized_data, ReasonTag.INVALID_DATA, norm_trace.to_dict()
        
        if normalized_data['price'] <= 0:
            logger.error(f"Invalid price: {normalized_data['price']}")
            return False, normalized_data, ReasonTag.INVALID_DATA, norm_trace.to_dict()
        
        return True, normalized_data, None, norm_trace.to_dict()
    
    def _inject_compatibility_fields(self, data: Dict) -> Dict:
        """
        P0-02: 兼容注入层 - 字段真相闭环
        
        规则：
        1. 仅在新字段缺失时从旧字段注入
        2. 注入是单向的（legacy → 新字段）
        3. 后续逻辑只读新字段
        
        兼容映射：
        - buy_sell_imbalance → taker_imbalance_1h（主要）
        - 未来可扩展其他兼容
        
        Args:
            data: 已规范化的数据字典
        
        Returns:
            注入后的数据字典
        """
        # taker_imbalance_1h兼容注入
        if data.get('taker_imbalance_1h') is None:
            legacy_value = data.get('buy_sell_imbalance')
            if legacy_value is not None:
                data['taker_imbalance_1h'] = legacy_value
                logger.info(
                    f"[P0-02] Injected taker_imbalance_1h={legacy_value:.4f} "
                    f"from buy_sell_imbalance (compatibility)"
                )
        
        return data
    
    def _check_lookback_coverage(self, data: Dict) -> Tuple[bool, List[ReasonTag]]:
        """
        检查 lookback coverage（PATCH-2）
        
        从 _metadata.lookback_coverage 读取各窗口的 lookback 结果，
        检查关键窗口是否存在数据缺口。
        
        Args:
            data: 市场数据字典（包含 _metadata）
        
        Returns:
            (是否通过检查, 失败原因tags列表)
        """
        metadata = data.get('_metadata', {})
        coverage = metadata.get('lookback_coverage', {})
        
        if not coverage or not coverage.get('has_data'):
            # 没有 coverage 信息（可能是旧版数据源），不检查
            logger.debug("No lookback_coverage in metadata, skipping coverage check")
            return True, []
        
        windows = coverage.get('windows', {})
        failed_tags = []
        
        # 检查各窗口
        window_tag_map = {
            '5m': ReasonTag.DATA_GAP_5M,
            '15m': ReasonTag.DATA_GAP_15M,
            '1h': ReasonTag.DATA_GAP_1H,
            '6h': ReasonTag.DATA_GAP_6H,
        }
        
        for window_key, tag in window_tag_map.items():
            window_info = windows.get(window_key, {})
            if not window_info.get('is_valid', True):  # 默认 True 避免误报
                error_reason = window_info.get('error_reason', 'UNKNOWN')
                gap_seconds = window_info.get('gap_seconds')
                logger.warning(
                    f"Lookback failed for {window_key}: {error_reason} "
                    f"(gap={gap_seconds}s)" if gap_seconds else f"Lookback failed for {window_key}: {error_reason}"
                )
                failed_tags.append(tag)
        
        # 如果有任何窗口失败，返回失败
        if failed_tags:
            return False, failed_tags
        
        return True, []
    
    # ========================================
    # Step 2: 市场环境识别
    # ========================================
    
    def _detect_market_regime(self, data: Dict) -> Tuple[MarketRegime, List[ReasonTag]]:
        """
        识别市场环境：TREND（趋势）/ RANGE（震荡）/ EXTREME（极端）
        
        方案1+4组合：
        - 添加短期TREND判断（1小时 > 2%）
        - 为RANGE短期机会识别奠定基础
        - 返回regime_tags以在前端展示
        
        PATCH-P0-02改进：
        - None-safe：缺6h时使用1h/15m退化判定
        - 使用_num/_abs helper
        
        Args:
            data: 市场数据
        
        Returns:
            (MarketRegime, 标识标签列表)
        """
        regime_tags = []
        
        # PATCH-P0-02: None-safe读取
        price_change_1h = self._num(data, 'price_change_1h')
        price_change_6h = self._num(data, 'price_change_6h')
        price_change_15m = self._num(data, 'price_change_15m')  # fallback
        
        # 1. EXTREME: 极端波动（优先级最高）
        if price_change_1h is not None:
            price_change_1h_abs = abs(price_change_1h)
            if price_change_1h_abs > self.thresholds['extreme_price_change_1h']:
                return MarketRegime.EXTREME, regime_tags
        
        # 2. TREND: 趋势市
        # 2.1 中期趋势（6小时）
        if price_change_6h is not None:
            price_change_6h_abs = abs(price_change_6h)
            if price_change_6h_abs > self.thresholds['trend_price_change_6h']:
                return MarketRegime.TREND, regime_tags
        elif price_change_15m is not None:
            # PATCH-P0-02: 缺6h时使用15m退化判定（更保守阈值）
            price_change_15m_abs = abs(price_change_15m)
            fallback_threshold = self.thresholds['trend_price_change_6h'] * 0.5  # 15m用更低阈值
            if price_change_15m_abs > fallback_threshold:
                regime_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)  # 标记退化
                logger.debug("Regime detection using 15m fallback (6h missing)")
                return MarketRegime.TREND, regime_tags
        
        # 2.2 短期趋势（1小时）- 方案1: 捕获短期机会
        if price_change_1h is not None:
            price_change_1h_abs = abs(price_change_1h)
            if price_change_1h_abs > self.thresholds.get('short_term_trend_1h', 0.02):
                regime_tags.append(ReasonTag.SHORT_TERM_TREND)
                return MarketRegime.TREND, regime_tags
        
        # 3. RANGE: 震荡市（默认）
        # PATCH-P0-02: 如果关键字段全缺失，标记但仍返回RANGE（保守）
        if price_change_1h is None and price_change_6h is None:
            regime_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)
            logger.debug("Regime defaults to RANGE (price_change data missing)")
        
        return MarketRegime.RANGE, regime_tags
    
    # ========================================
    # Step 3: 风险准入评估（第一道闸门）
    # ========================================
    
    def _eval_risk_exposure_allowed(
        self, 
        data: Dict, 
        regime: MarketRegime
    ) -> Tuple[bool, List[ReasonTag]]:
        """
        风险准入评估 - 系统性风险检查
        
        检查项：
        1. 极端行情（最高优先级）
        2. 清算阶段（价格急变 + OI急降）
        3. 拥挤风险（极端费率 + 高OI增长）
        4. 极端成交量
        
        PATCH-P0-02改进：
        - None-safe：关键字段缺失时跳过规则（不误DENY）
        - 使用_num/_abs/_compare helper
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (是否允许风险敞口, 原因标签列表)
        """
        tags = []
        
        # 1. 极端行情
        if regime == MarketRegime.EXTREME:
            tags.append(ReasonTag.EXTREME_REGIME)
            return False, tags
        
        # 2. 清算阶段（PATCH-P0-02: None-safe）
        price_change_1h = self._num(data, 'price_change_1h')
        oi_change_1h = self._num(data, 'oi_change_1h')
        
        if price_change_1h is not None and oi_change_1h is not None:
            if (abs(price_change_1h) > self.thresholds['liquidation_price_change'] and 
                oi_change_1h < self.thresholds['liquidation_oi_drop']):
                tags.append(ReasonTag.LIQUIDATION_PHASE)
                return False, tags
        else:
            # 关键字段缺失，跳过此规则但记录
            if price_change_1h is None or oi_change_1h is None:
                logger.debug("Liquidation check skipped (price_change_1h or oi_change_1h missing)")
        
        # 3. 拥挤风险（PATCH-P0-02: None-safe）
        funding_rate_value = self._num(data, 'funding_rate')
        oi_change_6h = self._num(data, 'oi_change_6h')
        
        if funding_rate_value is not None and oi_change_6h is not None:
            funding_rate_abs = abs(funding_rate_value)
            if (funding_rate_abs > self.thresholds['crowding_funding_abs'] and 
                oi_change_6h > self.thresholds['crowding_oi_growth']):
                tags.append(ReasonTag.CROWDING_RISK)
                return False, tags
        else:
            # 关键字段缺失，跳过此规则
            if funding_rate_value is None or oi_change_6h is None:
                logger.debug("Crowding check skipped (funding_rate or oi_change_6h missing)")
        
        # 4. 极端成交量（PATCH-P0-02: None-safe）
        volume_1h = self._num(data, 'volume_1h')
        volume_24h = self._num(data, 'volume_24h')
        
        if volume_1h is not None and volume_24h is not None and volume_24h > 0:
            volume_avg = volume_24h / 24
            if volume_1h > volume_avg * self.thresholds['extreme_volume_multiplier']:
                tags.append(ReasonTag.EXTREME_VOLUME)
                return False, tags
        else:
            # 成交量数据缺失，跳过此规则
            logger.debug("Extreme volume check skipped (volume data missing)")
        
        # 通过所有风险检查
        return True, []
    
    # ========================================
    # Step 4: 交易质量评估（第二道闸门）
    # ========================================
    
    def _eval_trade_quality(
        self, 
        symbol: str,
        data: Dict, 
        regime: MarketRegime
    ) -> Tuple[TradeQuality, List[ReasonTag]]:
        """
        交易质量评估 - 机会质量检查
        
        检查项：
        1. 吸纳风险（高失衡 + 低成交量）
        2. 噪音市（费率波动大但无方向）
        3. 轮动风险（OI和价格背离）
        4. 震荡市弱信号
        
        PATCH-P0-02改进：
        - None-safe：关键字段缺失时最多降级到UNCERTAIN（不直接POOR）
        - 使用_num/_abs helper
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (交易质量, 原因标签列表)
        """
        tags = []
        
        # 1. 吸纳风险（PATCH-P0-02: None-safe）
        imbalance_value = self._num(data, 'taker_imbalance_1h')
        volume_1h = self._num(data, 'volume_1h')
        volume_24h = self._num(data, 'volume_24h')
        
        if imbalance_value is not None and volume_1h is not None and volume_24h is not None and volume_24h > 0:
            imbalance_abs = abs(imbalance_value)
            volume_avg = volume_24h / 24
            if (imbalance_abs > self.thresholds['absorption_imbalance'] and 
                volume_1h < volume_avg * self.thresholds['absorption_volume_ratio']):
                tags.append(ReasonTag.ABSORPTION_RISK)
                return TradeQuality.POOR, tags
        elif imbalance_value is None or volume_1h is None or volume_24h is None:
            # PATCH-P0-02: 关键字段缺失 → 降级到UNCERTAIN（不直接POOR）
            logger.debug(f"[{symbol}] Absorption check skipped (imbalance/volume missing)")
            tags.append(ReasonTag.DATA_INCOMPLETE_MTF)
            return TradeQuality.UNCERTAIN, tags
        
        # 2. 噪音市（PATCH-P0-02: None-safe）
        funding_rate = self._num(data, 'funding_rate')
        
        if funding_rate is not None:
            history_key = f'{symbol}_funding_rate_prev'
            is_first_call = history_key not in self.history_data
            
            # 首次调用时使用当前值作为历史值（冷启动）
            funding_rate_prev = self.history_data.get(history_key, funding_rate)
            funding_volatility = abs(funding_rate - funding_rate_prev)
            
            # 保存当前数据供下次使用
            self.history_data[history_key] = funding_rate
            
            if is_first_call:
                logger.debug(f"[{symbol}] First call for noise detection, funding_rate history initialized")
            
            if (funding_volatility > self.thresholds['noisy_funding_volatility'] and 
                abs(funding_rate) < self.thresholds['noisy_funding_abs']):
                tags.append(ReasonTag.NOISY_MARKET)
                return TradeQuality.UNCERTAIN, tags
        else:
            logger.debug(f"[{symbol}] Noise check skipped (funding_rate missing)")
        
        # 3. 轮动风险（PATCH-P0-02: None-safe）
        price_change_1h = self._num(data, 'price_change_1h')
        oi_change_1h = self._num(data, 'oi_change_1h')
        
        if price_change_1h is not None and oi_change_1h is not None:
            if ((price_change_1h > self.thresholds['rotation_price_threshold'] and 
                 oi_change_1h < -self.thresholds['rotation_oi_threshold']) or
                (price_change_1h < -self.thresholds['rotation_price_threshold'] and 
                 oi_change_1h > self.thresholds['rotation_oi_threshold'])):
                tags.append(ReasonTag.ROTATION_RISK)
                return TradeQuality.POOR, tags
        else:
            # PATCH-P0-02: 关键字段缺失 → 跳过规则
            logger.debug(f"[{symbol}] Rotation check skipped (price_change_1h or oi_change_1h missing)")
        
        # 4. 震荡市弱信号（PATCH-P0-02: None-safe）
        if regime == MarketRegime.RANGE:
            # 重新读取imbalance_abs（前面已读取imbalance_value）
            imbalance_abs = self._abs(imbalance_value) if imbalance_value is not None else None
            oi_change_1h_abs = self._abs(oi_change_1h) if oi_change_1h is not None else None
            
            if imbalance_abs is not None and oi_change_1h_abs is not None:
                if (imbalance_abs < self.thresholds['range_weak_imbalance'] and 
                    oi_change_1h_abs < self.thresholds['range_weak_oi']):
                    tags.append(ReasonTag.WEAK_SIGNAL_IN_RANGE)
                    return TradeQuality.UNCERTAIN, tags
            else:
                logger.debug(f"[{symbol}] Range weak signal check skipped (imbalance or oi_change missing)")
        
        # 通过所有质量检查
        return TradeQuality.GOOD, []
    
    # ========================================
    # Step 5: 方向评估
    # ========================================
    
    def _eval_long_direction(self, data: Dict, regime: MarketRegime) -> Tuple[bool, List[ReasonTag]]:
        """
        做多方向评估（方案1+4组合：短期机会识别）
        
        PATCH-P0-02改进：
        - None-safe：关键字段缺失时返回False（不误判LONG）
        - 使用_num helper
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (是否允许做多, 标签列表)
        """
        direction_tags = []
        
        # PATCH-P0-02: None-safe读取
        imbalance = self._num(data, 'taker_imbalance_1h')
        oi_change = self._num(data, 'oi_change_1h')
        price_change = self._num(data, 'price_change_1h')
        
        # 关键字段缺失，无法判断方向
        if imbalance is None or oi_change is None or price_change is None:
            logger.debug("Long direction eval skipped (key fields missing)")
            return False, direction_tags
        
        if regime == MarketRegime.TREND:
            # 趋势市：多方强势
            if (imbalance > self.thresholds['long_imbalance_trend'] and 
                oi_change > self.thresholds['long_oi_change_trend'] and 
                price_change > self.thresholds['long_price_change_trend']):
                return True, direction_tags
        
        elif regime == MarketRegime.RANGE:
            # 震荡市：原有强信号逻辑
            if (imbalance > self.thresholds['long_imbalance_range'] and 
                oi_change > self.thresholds['long_oi_change_range']):
                return True, direction_tags
            
            # 方案4：短期机会识别（综合指标，3选2确认）
            short_term_config = self.config.get('direction', {}).get('range', {}).get('short_term_opportunity', {}).get('long', {})
            if short_term_config:
                signals = []
                signal_tags = []
                
                # 信号1: 价格短期上涨
                if price_change > short_term_config.get('min_price_change_1h', 0.015):
                    signals.append('price_surge')
                    signal_tags.append(ReasonTag.SHORT_TERM_PRICE_SURGE)
                
                # 信号2: OI增长
                if oi_change > short_term_config.get('min_oi_change_1h', 0.15):
                    signals.append('oi_growing')
                    # oi_growing标签在辅助信息中已有
                
                # 信号3: 强买压
                # PATCH-P0-05: 优先读取min_taker_imbalance，fallback到min_buy_sell_imbalance
                min_imbalance_threshold = short_term_config.get('min_taker_imbalance') or short_term_config.get('min_buy_sell_imbalance', 0.65)
                if imbalance > min_imbalance_threshold:
                    signals.append('strong_buy_pressure')
                    signal_tags.append(ReasonTag.SHORT_TERM_STRONG_BUY)
                
                # 至少满足required_signals个信号
                required = short_term_config.get('required_signals', 2)
                if len(signals) >= required:
                    direction_tags.append(ReasonTag.RANGE_SHORT_TERM_LONG)  # ✅ 主标签
                    direction_tags.extend(signal_tags)  # ✅ 具体信号
                    return True, direction_tags
        
        return False, direction_tags
    
    def _eval_short_direction(self, data: Dict, regime: MarketRegime) -> Tuple[bool, List[ReasonTag]]:
        """
        做空方向评估（方案1+4组合：短期机会识别）
        
        PATCH-P0-02改进：
        - None-safe：关键字段缺失时返回False（不误判SHORT）
        - 使用_num helper
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (是否允许做空, 标签列表)
        """
        direction_tags = []
        
        # PATCH-P0-02: None-safe读取
        imbalance = self._num(data, 'taker_imbalance_1h')
        oi_change = self._num(data, 'oi_change_1h')
        price_change = self._num(data, 'price_change_1h')
        
        # 关键字段缺失，无法判断方向
        if imbalance is None or oi_change is None or price_change is None:
            logger.debug("Short direction eval skipped (key fields missing)")
            return False, direction_tags
        
        if regime == MarketRegime.TREND:
            # 趋势市：空方强势
            if (imbalance < -self.thresholds['short_imbalance_trend'] and 
                oi_change > self.thresholds['short_oi_change_trend'] and 
                price_change < -self.thresholds['short_price_change_trend']):
                return True, direction_tags
        
        elif regime == MarketRegime.RANGE:
            # 震荡市：原有强信号逻辑
            if (imbalance < -self.thresholds['short_imbalance_range'] and 
                oi_change > self.thresholds['short_oi_change_range']):
                return True, direction_tags
            
            # 方案4：短期机会识别（综合指标，3选2确认）
            short_term_config = self.config.get('direction', {}).get('range', {}).get('short_term_opportunity', {}).get('short', {})
            if short_term_config:
                signals = []
                signal_tags = []
                
                # 信号1: 价格短期下跌
                if price_change < short_term_config.get('max_price_change_1h', -0.015):
                    signals.append('price_drop')
                    signal_tags.append(ReasonTag.SHORT_TERM_PRICE_DROP)  # 使用专门的下跌标签
                
                # 信号2: OI增长
                if oi_change > short_term_config.get('min_oi_change_1h', 0.15):
                    signals.append('oi_growing')
                    # oi_growing标签在辅助信息中已有
                
                # 信号3: 强卖压
                # PATCH-P0-05: 优先读取max_taker_imbalance，fallback到max_buy_sell_imbalance
                max_imbalance_threshold = short_term_config.get('max_taker_imbalance') or short_term_config.get('max_buy_sell_imbalance', -0.65)
                if imbalance < max_imbalance_threshold:
                    signals.append('strong_sell_pressure')
                    signal_tags.append(ReasonTag.SHORT_TERM_STRONG_SELL)
                
                # 至少满足required_signals个信号
                required = short_term_config.get('required_signals', 2)
                if len(signals) >= required:
                    direction_tags.append(ReasonTag.RANGE_SHORT_TERM_SHORT)  # ✅ 主标签
                    direction_tags.extend(signal_tags)  # ✅ 具体信号
                    return True, direction_tags
        
        return False, direction_tags
    
    # ========================================
    # Step 6: 决策优先级
    # ========================================
    
    def _decide_priority(
        self, 
        allow_short: bool, 
        allow_long: bool
    ) -> Tuple[Decision, List[ReasonTag]]:
        """
        决策优先级判断：SHORT > LONG > NO_TRADE
        
        冲突时保守处理：返回NO_TRADE
        
        Args:
            allow_short: 是否允许做空
            allow_long: 是否允许做多
        
        Returns:
            (决策, 原因标签列表)
        """
        tags = []
        
        # 两个方向都不允许
        if not allow_short and not allow_long:
            tags.append(ReasonTag.NO_CLEAR_DIRECTION)
            return Decision.NO_TRADE, tags
        
        # 冲突（保守处理）
        if allow_short and allow_long:
            tags.append(ReasonTag.CONFLICTING_SIGNALS)
            return Decision.NO_TRADE, tags
        
        # SHORT优先
        # 添加决策方向标识标签（与方向评估中的具体信号标签如SHORT_TERM_STRONG_SELL不同）
        # STRONG_SELL_PRESSURE: 通用决策方向标识
        # SHORT_TERM_STRONG_SELL: 具体信号来源标识
        if allow_short:
            tags.append(ReasonTag.STRONG_SELL_PRESSURE)
            return Decision.SHORT, tags
        
        # LONG
        if allow_long:
            tags.append(ReasonTag.STRONG_BUY_PRESSURE)
            return Decision.LONG, tags
        
        return Decision.NO_TRADE, tags
    
    
    # ========================================
    # Step 9: 置信度计算（PR-D混合模式）
    # ========================================
    
    def _compute_confidence(
        self, 
        decision: Decision, 
        regime: MarketRegime, 
        quality: TradeQuality, 
        reason_tags: List[ReasonTag]
    ) -> Confidence:
        """
        置信度计算（PR-D混合模式）
        
        流程：
        1. 基础加分（保持PR-005的加分制）
        2. 硬降级上限（caps）
        3. 强信号突破（+1档，不突破cap）
        
        Args:
            decision: 决策
            regime: 市场环境
            quality: 交易质量
            reason_tags: 原因标签列表
        
        Returns:
            Confidence: 置信度
        """
        # NO_TRADE强制LOW
        if decision == Decision.NO_TRADE:
            return Confidence.LOW
        
        # ===== 第1步：基础加分 =====
        score = 0
        scoring_config = self.config.get('confidence_scoring', {})
        
        # 决策类型分
        if decision in [Decision.LONG, Decision.SHORT]:
            score += scoring_config.get('decision_score', 30)
        
        # 市场环境分
        if regime == MarketRegime.TREND:
            score += scoring_config.get('regime_trend_score', 30)
        elif regime == MarketRegime.RANGE:
            score += scoring_config.get('regime_range_score', 10)
        elif regime == MarketRegime.EXTREME:
            score += scoring_config.get('regime_extreme_score', 0)
        
        # 质量分
        if quality == TradeQuality.GOOD:
            score += scoring_config.get('quality_good_score', 30)
        elif quality == TradeQuality.UNCERTAIN:
            score += scoring_config.get('quality_uncertain_score', 15)
        elif quality == TradeQuality.POOR:
            score += scoring_config.get('quality_poor_score', 0)
        
        # 强信号加分（P1-1修复：从配置读取required_tags，而非硬编码）
        boost_config = scoring_config.get('strong_signal_boost', {})
        required_tag_values = boost_config.get('required_tags', ['strong_buy_pressure', 'strong_sell_pressure'])
        
        # 将配置中的字符串转换为 ReasonTag 枚举
        strong_signals = []
        for tag_value in required_tag_values:
            try:
                strong_signals.append(ReasonTag(tag_value))
            except ValueError:
                logger.warning(f"Invalid required_tag in config: {tag_value}, skipping")
        
        has_strong_signal = any(tag in reason_tags for tag in strong_signals)
        if has_strong_signal:
            score += scoring_config.get('strong_signal_bonus', 10)
        
        # 映射到初始档位
        initial_confidence = self._score_to_confidence(score, scoring_config)
        
        # ===== 第2步：硬降级上限（caps）=====
        capped_confidence, has_cap = self._apply_confidence_caps(
            confidence=initial_confidence,
            quality=quality,
            reason_tags=reason_tags
        )
        
        # ===== 第3步：强信号突破（+1档，不突破cap）=====
        # 如果有cap限制，则不能突破cap；否则可以突破到ULTRA
        cap_limit = capped_confidence if has_cap else Confidence.ULTRA
        final_confidence = self._apply_strong_signal_boost(
            confidence=capped_confidence,
            reason_tags=reason_tags,
            cap_limit=cap_limit,
            has_strong_signal=has_strong_signal
        )
        
        return final_confidence
    
    def _score_to_confidence(self, score: int, scoring_config: dict) -> Confidence:
        """
        将分数映射到置信度档位（PR-D）
        
        Args:
            score: 总分
            scoring_config: 配置字典
        
        Returns:
            Confidence: 置信度档位
        """
        thresholds = scoring_config.get('thresholds', {})
        ultra_threshold = thresholds.get('ultra', 90)
        high_threshold = thresholds.get('high', 65)
        medium_threshold = thresholds.get('medium', 40)
        
        if score >= ultra_threshold:
            return Confidence.ULTRA
        elif score >= high_threshold:
            return Confidence.HIGH
        elif score >= medium_threshold:
            return Confidence.MEDIUM
        else:
            return Confidence.LOW
    
    def _apply_confidence_caps(
        self,
        confidence: Confidence,
        quality: TradeQuality,
        reason_tags: List[ReasonTag]
    ) -> tuple:
        """
        应用硬降级上限（PR-D）
        
        优先级：
        1. deny条件（风险拒绝等） → 强制LOW
        2. UNCERTAIN质量 → cap
        3. reduce_tags → cap
        
        Args:
            confidence: 初始置信度
            quality: 交易质量
            reason_tags: 原因标签列表
        
        Returns:
            (应用cap后的置信度, 是否有cap限制)
        """
        scoring_config = self.config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        tag_rules = self.config.get('reason_tag_rules', {})
        
        has_cap = False
        
        # 1. deny条件：强制LOW（当前不在这里处理，因为risk_denied已经在Step 3短路）
        
        # 2. UNCERTAIN质量上限
        if quality == TradeQuality.UNCERTAIN:
            max_level_str = caps_config.get('uncertain_quality_max', 'MEDIUM')
            max_level = self._string_to_confidence(max_level_str)
            if self._confidence_level(confidence) > self._confidence_level(max_level):
                logger.debug(f"[Cap] UNCERTAIN quality: {confidence.value} → {max_level.value}")
                confidence = max_level
                has_cap = True
        
        # 3. reduce_tags上限（PR-I：使用配置化默认值）
        reduce_tags = tag_rules.get('reduce_tags', [])
        tag_caps = caps_config.get('tag_caps', {})
        
        # PR-I：reduce_tags 的默认cap配置化
        # 如果 reduce_tag 未在 tag_caps 中配置，使用 reduce_default_max 作为默认值
        # 建议默认值等于 uncertain_quality_max，保持逻辑一致性
        reduce_default_max_str = caps_config.get('reduce_default_max', 
                                                  caps_config.get('uncertain_quality_max', 'MEDIUM'))
        
        for tag in reason_tags:
            tag_value = tag.value
            if tag_value in reduce_tags or tag_value in tag_caps:
                # PR-I修复：使用配置化默认值，而非硬编码 'MEDIUM'
                max_level_str = tag_caps.get(tag_value, reduce_default_max_str)
                max_level = self._string_to_confidence(max_level_str)
                if self._confidence_level(confidence) > self._confidence_level(max_level):
                    logger.debug(f"[Cap] Tag {tag_value}: {confidence.value} → {max_level.value}")
                    confidence = max_level
                    has_cap = True
        
        return confidence, has_cap
    
    def _apply_strong_signal_boost(
        self,
        confidence: Confidence,
        reason_tags: List[ReasonTag],
        cap_limit: Confidence,
        has_strong_signal: bool
    ) -> Confidence:
        """
        强信号突破（PR-D）
        
        条件：
        1. 存在强信号标签
        2. 不能突破cap_limit
        
        Args:
            confidence: cap后的置信度
            reason_tags: 原因标签列表
            cap_limit: 上限（不可突破）
            has_strong_signal: 是否有强信号
        
        Returns:
            Confidence: 最终置信度
        """
        boost_config = self.config.get('confidence_scoring', {}).get('strong_signal_boost', {})
        
        if not boost_config.get('enabled', True):
            return confidence
        
        if not has_strong_signal:
            return confidence
        
        # 提升1档
        boost_levels = boost_config.get('boost_levels', 1)
        boosted = self._boost_confidence(confidence, boost_levels)
        
        # 不能突破cap
        if self._confidence_level(boosted) > self._confidence_level(cap_limit):
            logger.debug(f"[Boost] Capped at {cap_limit.value}, cannot boost to {boosted.value}")
            return cap_limit
        
        if boosted != confidence:
            logger.debug(f"[Boost] Strong signal: {confidence.value} → {boosted.value}")
        
        return boosted
    
    def _boost_confidence(self, confidence: Confidence, levels: int) -> Confidence:
        """提升置信度档位"""
        order = [Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH, Confidence.ULTRA]
        try:
            current_idx = order.index(confidence)
            new_idx = min(current_idx + levels, len(order) - 1)
            return order[new_idx]
        except ValueError:
            return confidence
    
    def _confidence_level(self, confidence: Confidence) -> int:
        """置信度档位的数值表示（用于比较）"""
        order = {
            Confidence.LOW: 0,
            Confidence.MEDIUM: 1,
            Confidence.HIGH: 2,
            Confidence.ULTRA: 3
        }
        return order.get(confidence, 0)
    
    def _string_to_confidence(self, s: str) -> Confidence:
        """
        字符串转Confidence枚举（P1-2修复：配置错误时返回LOW而非MEDIUM）
        
        保守原则：
        - 配置错误时默认 LOW（最严格），而非 MEDIUM
        - 避免配置拼写错误导致门槛降低、可执行概率提升
        - 记录 ERROR 日志让问题可见
        
        Args:
            s: 配置字符串（如 "HIGH", "MEDIUM"）
        
        Returns:
            Confidence: 对应的枚举值，配置错误返回 LOW
        """
        mapping = {
            'LOW': Confidence.LOW,
            'MEDIUM': Confidence.MEDIUM,
            'HIGH': Confidence.HIGH,
            'ULTRA': Confidence.ULTRA
        }
        
        result = mapping.get(s.upper())
        if result is None:
            logger.error(
                f"⚠️ 配置错误: 未知的置信度字符串 '{s}'，"
                f"有效值: LOW/MEDIUM/HIGH/ULTRA，"
                f"已回退到 LOW（最保守）以确保安全"
            )
            return Confidence.LOW
        
        return result
    
    # ========================================
    # 方案D：执行许可计算
    # ========================================
    
    def _compute_execution_permission(self, reason_tags: List[ReasonTag]) -> ExecutionPermission:
        """
        计算执行许可级别（PR-004增强：频控标签映射为DENY）
        
        映射规则：
        1. 频控标签（PR-004新增）→ DENY
           - MIN_INTERVAL_BLOCK
           - FLIP_COOLDOWN_BLOCK
        2. 任何 BLOCK 级别标签 → DENY（拒绝执行）
        3. 任何 DEGRADE 级别标签 → ALLOW_REDUCED（降级执行）
        4. 仅 ALLOW 级别标签 → ALLOW（正常执行）
        
        ExecutabilityLevel → ExecutionPermission 映射：
        - BLOCK (EXTREME_VOLUME, ABSORPTION_RISK, ROTATION_RISK, ...) → DENY
        - DEGRADE (NOISY_MARKET, WEAK_SIGNAL_IN_RANGE) → ALLOW_REDUCED
        - ALLOW (STRONG_BUY_PRESSURE, OI_GROWING, ...) → ALLOW
        
        特别说明：
        - ABSORPTION_RISK 和 ROTATION_RISK 被设置为 BLOCK 而非 DEGRADE（更保守）
        - 它们等价于风险否决类的 deny_tags（LIQUIDATION_PHASE、CROWDING_RISK等）
        - 双重保护：POOR硬短路 + BLOCK标签 → 即使强信号也无法绕过
        - 执行顺序保证：Step 8（执行许可）在 Step 9（置信度+强信号boost）之前
        
        PR-004改进：
        - 频控标签在最高优先级检查（优先于BLOCK标签）
        - 确保频控触发时execution_permission=DENY
        - 配合signal_decision实现信号透明化
        
        Args:
            reason_tags: 原因标签列表
        
        Returns:
            ExecutionPermission: 执行许可级别
        """
        from models.reason_tags import REASON_TAG_EXECUTABILITY, ExecutabilityLevel
        
        # PR-004优先级0: 频控标签（最高优先级，确保阻断）
        if ReasonTag.MIN_INTERVAL_BLOCK in reason_tags:
            logger.debug(f"[ExecPerm] DENY: MIN_INTERVAL_BLOCK (PR-004频控)")
            return ExecutionPermission.DENY
        
        if ReasonTag.FLIP_COOLDOWN_BLOCK in reason_tags:
            logger.debug(f"[ExecPerm] DENY: FLIP_COOLDOWN_BLOCK (PR-004频控)")
            return ExecutionPermission.DENY
        
        # PR-007优先级0.5: EXTREME_VOLUME联立否决检查
        # EXTREME_VOLUME单独出现时只是DEGRADE
        # 但与LIQUIDATION_PHASE或EXTREME_REGIME联立时升级为DENY
        if ReasonTag.EXTREME_VOLUME in reason_tags:
            has_liquidation = ReasonTag.LIQUIDATION_PHASE in reason_tags
            has_extreme_regime = ReasonTag.EXTREME_REGIME in reason_tags
            
            if has_liquidation or has_extreme_regime:
                logger.debug(
                    f"[ExecPerm] DENY: EXTREME_VOLUME + "
                    f"{'LIQUIDATION_PHASE' if has_liquidation else 'EXTREME_REGIME'} "
                    f"(PR-007联立否决)"
                )
                return ExecutionPermission.DENY
            # else: EXTREME_VOLUME单独，继续后续检查（会被映射为DEGRADE）
        
        # 优先级1: 检查是否有 BLOCK 级别标签
        for tag in reason_tags:
            exec_level = REASON_TAG_EXECUTABILITY.get(tag, ExecutabilityLevel.ALLOW)
            
            if exec_level == ExecutabilityLevel.BLOCK:
                logger.debug(f"[ExecPerm] DENY: found blocking tag {tag.value}")
                return ExecutionPermission.DENY
        
        # 优先级2: 检查是否有 DEGRADE 级别标签
        for tag in reason_tags:
            exec_level = REASON_TAG_EXECUTABILITY.get(tag, ExecutabilityLevel.ALLOW)
            
            if exec_level == ExecutabilityLevel.DEGRADE:
                logger.debug(f"[ExecPerm] ALLOW_REDUCED: found degrading tag {tag.value}")
                return ExecutionPermission.ALLOW_REDUCED
        
        # 优先级3: 全是 ALLOW 级别（或没有可识别的标签）
        logger.debug(f"[ExecPerm] ALLOW: no blocking or degrading tags")
        return ExecutionPermission.ALLOW
    
    # ========================================
    # 状态维护（简化版：L1咨询层不维护持仓状态）
    # ========================================
    
    def _update_state(self, decision: Decision):
        """
        状态维护（简化版）
        
        L1作为纯咨询层，不维护持仓状态，固定为WAIT状态。
        反抖动功能由DecisionMemory（PR-C）实现。
        
        Args:
            decision: 当前决策（保留参数以兼容现有调用）
        """
        # L1咨询层固定为WAIT状态
        self.current_state = SystemState.WAIT
        self.state_enter_time = datetime.now()
    
    # ========================================
    # 辅助方法
    # ========================================
    
    def _add_auxiliary_tags(self, data: Dict, reason_tags: List[ReasonTag]):
        """
        添加辅助信息标签（非否决性）
        
        Args:
            data: 市场数据
            reason_tags: 标签列表（会被修改）
        """
        # 资金费率标签
        funding_rate = data.get('funding_rate', 0)
        funding_threshold = self.thresholds.get('aux_funding_rate_threshold', 0.0005)
        if abs(funding_rate) > funding_threshold:
            if funding_rate > 0:
                reason_tags.append(ReasonTag.HIGH_FUNDING_RATE)
            else:
                reason_tags.append(ReasonTag.LOW_FUNDING_RATE)
        
        # 持仓量变化标签（P0-3修复：使用DECIMAL格式阈值，与系统口径一致）
        oi_change_1h = data.get('oi_change_1h', 0)
        oi_growing_threshold = self.thresholds.get('aux_oi_growing_threshold', 0.05)
        oi_declining_threshold = self.thresholds.get('aux_oi_declining_threshold', -0.05)
        
        if oi_change_1h > oi_growing_threshold:
            reason_tags.append(ReasonTag.OI_GROWING)
        elif oi_change_1h < oi_declining_threshold:
            reason_tags.append(ReasonTag.OI_DECLINING)
    
    def _apply_decision_control(
        self, 
        symbol: str, 
        decision: Decision, 
        reason_tags: List[ReasonTag],
        timestamp: datetime
    ) -> Tuple[Decision, List[ReasonTag]]:
        """
        Step 7: 决策频率控制（PR-004重构：不改写decision）
        
        PR-004改进：
        - 频控触发时只添加控制标签（MIN_INTERVAL_BLOCK/FLIP_COOLDOWN_BLOCK）
        - 不再改写decision为NO_TRADE
        - 通过reason_tags让execution_permission=DENY，从而设置executable=False
        - 保持信号透明：用户可看到原始方向但被频控阻断
        
        规则：
        1. 最小决策间隔：防止短时间内重复输出
        2. 翻转冷却：防止方向频繁切换
        
        Args:
            symbol: 币种符号
            decision: 当前决策（原始信号，不会被改写）
            reason_tags: 现有标签列表
            timestamp: 当前时间
        
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
        last = self.decision_memory.get_last_decision(symbol)
        
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
                f"(PR-004: 保留信号，通过DENY阻断执行)"
            )
            control_tags.append(ReasonTag.MIN_INTERVAL_BLOCK)
            # PR-004: 不改写decision，只添加标签
        
        # 检查2: 翻转冷却
        if enable_flip_cooldown:
            is_flip = (decision == Decision.LONG and last_side == Decision.SHORT) or \
                     (decision == Decision.SHORT and last_side == Decision.LONG)
            
            if is_flip and elapsed < flip_cooldown:
                logger.info(
                    f"[{symbol}] FLIP_COOLDOWN_BLOCK: signal={last_side.value}→{decision.value}, "
                    f"elapsed={elapsed:.0f}s < {flip_cooldown}s "
                    f"(PR-004: 保留信号，通过DENY阻断执行)"
                )
                control_tags.append(ReasonTag.FLIP_COOLDOWN_BLOCK)
                # PR-004: 不改写decision，只添加标签
        
        # PR-004: 始终返回原始decision（不改写）
        # 频控标签会在Step 8被识别为DENY
        if control_tags:
            logger.debug(f"[{symbol}] Decision control: signal preserved, will be blocked by execution_permission")
        
        return decision, control_tags
    
    def _build_no_trade_result(
        self,
        reason_tags: List[ReasonTag],
        regime: MarketRegime,
        risk_allowed: bool,
        quality: TradeQuality,
        price: Optional[float] = None
    ) -> AdvisoryResult:
        """
        构造 NO_TRADE 结果
        
        Args:
            reason_tags: 原因标签列表
            regime: 市场环境
            risk_allowed: 风险是否允许
            quality: 交易质量
            price: 当前价格（可选）
        
        Returns:
            AdvisoryResult: NO_TRADE决策结果
        """
        result = AdvisoryResult(
            decision=Decision.NO_TRADE,
            confidence=Confidence.LOW,
            market_regime=regime,
            system_state=self.current_state,
            risk_exposure_allowed=risk_allowed,
            trade_quality=quality,
            reason_tags=reason_tags,
            timestamp=datetime.now(),
            execution_permission=ExecutionPermission.DENY,  # NO_TRADE → DENY
            executable=False,
            signal_decision=None,  # PR-004: NO_TRADE场景无原始信号
            price=price  # 添加价格信息
        )
        # NO_TRADE的executable永远是False，无需重新计算
        return result
    
    def _load_config(self, config_path: str) -> dict:
        """
        加载YAML配置文件
        
        Args:
            config_path: 配置文件路径
        
        Returns:
            dict: 配置字典
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded config from {config_path}")
            return config
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}, using defaults")
            return self._get_default_config()
    
    def _validate_decimal_calibration(self, config: dict):
        """
        启动时校验：检查配置口径是否为小数格式（防回归）
        
        目标：所有百分比阈值必须使用小数格式（0.05=5%），不允许百分点格式（5.0）
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 如果发现疑似百分点格式的阈值
        """
        errors = []
        
        # 定义需要检查的百分比阈值路径（值应 < 1.0）
        percentage_thresholds = [
            ('market_regime', 'extreme_price_change_1h', 'EXTREME价格变化阈值'),
            ('market_regime', 'trend_price_change_6h', 'TREND价格变化阈值'),
            ('risk_exposure', 'liquidation', 'price_change', '清算价格变化阈值'),
            ('risk_exposure', 'liquidation', 'oi_drop', '清算OI下降阈值'),
            ('risk_exposure', 'crowding', 'oi_growth', '拥挤OI增长阈值'),
            ('trade_quality', 'rotation', 'price_threshold', '轮动价格阈值'),
            ('trade_quality', 'rotation', 'oi_threshold', '轮动OI阈值'),
            ('trade_quality', 'range_weak', 'oi', '震荡弱信号OI阈值'),
        ]
        
        # 检查基础百分比阈值
        for path_parts in percentage_thresholds:
            *path, last_key, name = path_parts
            value = config
            try:
                for key in path:
                    value = value[key]
                threshold_value = value[last_key]
                
                # 检查：百分比阈值的绝对值应该 < 1.0（允许负数，如-0.15）
                if abs(threshold_value) >= 1.0:
                    config_path = '.'.join(path) + '.' + last_key if path else last_key
                    errors.append(
                        f"❌ {config_path} = {threshold_value} ({name}，疑似百分点格式，应使用小数格式，如 0.05 表示 5%)"
                    )
            except (KeyError, TypeError):
                # 配置项不存在，跳过
                pass
        
        # 检查方向评估阈值（嵌套结构）
        direction_config = config.get('direction', {})
        for regime in ['trend', 'range']:
            for side in ['long', 'short']:
                side_config = direction_config.get(regime, {}).get(side, {})
                
                # oi_change 应 < 1.0
                oi_change = side_config.get('oi_change')
                if oi_change is not None and abs(oi_change) >= 1.0:
                    errors.append(
                        f"❌ direction.{regime}.{side}.oi_change = {oi_change} "
                        f"(疑似百分点格式，应使用小数格式，如 0.05 表示 5%)"
                    )
                
                # price_change 应 < 1.0
                price_change = side_config.get('price_change')
                if price_change is not None and abs(price_change) >= 1.0:
                    errors.append(
                        f"❌ direction.{regime}.{side}.price_change = {price_change} "
                        f"(疑似百分点格式，应使用小数格式，如 0.01 表示 1%)"
                    )
        
        # 如果发现错误，拒绝启动
        if errors:
            error_message = (
                "\n" + "="*80 + "\n"
                "⚠️  配置口径错误检测（Decimal Calibration Validation Failed）\n"
                "="*80 + "\n"
                "发现疑似使用百分点格式的阈值配置，系统拒绝启动！\n\n"
                "错误项：\n" + "\n".join(f"  {err}" for err in errors) + "\n\n"
                "修复方法：\n"
                "  1. 打开配置文件: config/l1_thresholds.yaml\n"
                "  2. 将所有百分比阈值改为小数格式:\n"
                "     - 错误: 5.0 (百分点)\n"
                "     - 正确: 0.05 (小数，表示5%)\n"
                "  3. 参考文档: doc/平台详解3.0.md 第4章（口径规范）\n"
                "="*80
            )
            logger.error(error_message)
            raise ValueError(error_message)
        
        logger.info("✅ 配置口径校验通过：所有百分比阈值使用小数格式")
    
    def _validate_threshold_consistency(self, config: dict):
        """
        启动时校验：门槛一致性检查（P1-3）
        
        目标：防止"允许降级但永远达不到门槛"的逻辑矛盾
        
        检查项：
        1. min_confidence_reduced <= uncertain_quality_max
           - reduced门槛不能高于UNCERTAIN的cap
           - 否则UNCERTAIN质量永远达不到reduced门槛
        
        2. min_confidence_reduced <= tag_caps (for reduce_tags)
           - reduced门槛不能高于降级标签的cap
           - 否则有降级标签时永远达不到reduced门槛
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 如果发现门槛一致性问题
        """
        from models.enums import Confidence
        
        errors = []
        
        # 获取配置
        exec_config = config.get('executable_control', {})
        min_reduced_str = exec_config.get('min_confidence_reduced', 'MEDIUM')
        
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        uncertain_max_str = caps_config.get('uncertain_quality_max', 'MEDIUM')
        tag_caps = caps_config.get('tag_caps', {})
        
        tag_rules = config.get('reason_tag_rules', {})
        reduce_tags = tag_rules.get('reduce_tags', [])
        
        # 置信度顺序映射
        confidence_order = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2, 'ULTRA': 3}
        
        min_reduced_level = confidence_order.get(min_reduced_str.upper(), 1)
        uncertain_max_level = confidence_order.get(uncertain_max_str.upper(), 1)
        
        # 检查1: min_confidence_reduced <= uncertain_quality_max
        if min_reduced_level > uncertain_max_level:
            errors.append(
                f"min_confidence_reduced ({min_reduced_str}) > uncertain_quality_max ({uncertain_max_str})\n"
                f"  → UNCERTAIN质量被cap到 {uncertain_max_str}，但reduced门槛要求 {min_reduced_str}\n"
                f"  → 逻辑矛盾：UNCERTAIN永远达不到reduced门槛，降级执行失效"
            )
        
        # 检查2: min_confidence_reduced <= tag_caps (for reduce_tags)
        for tag_name in reduce_tags:
            if tag_name in tag_caps:
                tag_cap_str = tag_caps[tag_name]
                tag_cap_level = confidence_order.get(tag_cap_str.upper(), 1)
                
                if min_reduced_level > tag_cap_level:
                    errors.append(
                        f"min_confidence_reduced ({min_reduced_str}) > tag_caps['{tag_name}'] ({tag_cap_str})\n"
                        f"  → {tag_name} 被cap到 {tag_cap_str}，但reduced门槛要求 {min_reduced_str}\n"
                        f"  → 逻辑矛盾：有{tag_name}时永远达不到reduced门槛"
                    )
        
        if errors:
            error_message = (
                "\n" + "="*80 + "\n"
                "⚠️  门槛一致性错误检测（Threshold Consistency Validation Failed）\n"
                "="*80 + "\n"
                "发现门槛配置不一致，会导致'允许降级但永远达不到门槛'的逻辑矛盾！\n\n"
                "错误项：\n" + "\n".join(f"  {i+1}. {err}\n" for i, err in enumerate(errors)) + "\n"
                "修复方法：\n"
                "  1. 确保 min_confidence_reduced <= uncertain_quality_max\n"
                "  2. 确保 min_confidence_reduced <= tag_caps (for all reduce_tags)\n"
                "  3. 推荐配置（方案D）:\n"
                "     - min_confidence_reduced: MEDIUM\n"
                "     - uncertain_quality_max: HIGH\n"
                "     - tag_caps: {noisy_market: HIGH, weak_signal_in_range: HIGH}\n"
                "     - 确保 MEDIUM <= HIGH 的一致性\n\n"
                "设计原理：\n"
                "  ALLOW_REDUCED场景需要 cap >= reduced门槛，否则降级执行永远失效\n"
                "="*80 + "\n"
            )
            raise ValueError(error_message)
        
        logger.info("✅ 门槛一致性校验通过：reduced门槛 <= caps，降级执行逻辑正确")
    
    def _validate_reason_tag_spelling(self, config: dict):
        """
        启动时校验：ReasonTag拼写有效性检查（P1-3）
        
        目标：防止配置中的标签名拼写错误，fail-fast
        
        检查范围：
        1. reason_tag_rules.reduce_tags
        2. reason_tag_rules.deny_tags
        3. confidence_scoring.caps.tag_caps (keys)
        4. confidence_scoring.strong_signal_boost.required_tags
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 如果发现无效的ReasonTag名称
        """
        from models.reason_tags import ReasonTag
        
        # 获取所有有效的ReasonTag值
        valid_tags = {tag.value for tag in ReasonTag}
        
        errors = []
        
        # 检查 reduce_tags
        tag_rules = config.get('reason_tag_rules', {})
        reduce_tags = tag_rules.get('reduce_tags', [])
        for tag_name in reduce_tags:
            if tag_name not in valid_tags:
                errors.append(
                    f"reason_tag_rules.reduce_tags: '{tag_name}' 不是有效的ReasonTag\n"
                    f"  → 可能是拼写错误，请检查 models/reason_tags.py 中的定义"
                )
        
        # 检查 deny_tags
        deny_tags = tag_rules.get('deny_tags', [])
        for tag_name in deny_tags:
            if tag_name not in valid_tags:
                errors.append(
                    f"reason_tag_rules.deny_tags: '{tag_name}' 不是有效的ReasonTag\n"
                    f"  → 可能是拼写错误，请检查 models/reason_tags.py 中的定义"
                )
        
        # 检查 tag_caps (keys)
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        tag_caps = caps_config.get('tag_caps', {})
        for tag_name in tag_caps.keys():
            if tag_name not in valid_tags:
                errors.append(
                    f"confidence_scoring.caps.tag_caps: '{tag_name}' 不是有效的ReasonTag\n"
                    f"  → 可能是拼写错误，请检查 models/reason_tags.py 中的定义"
                )
        
        # 检查 required_tags
        boost_config = scoring_config.get('strong_signal_boost', {})
        required_tags = boost_config.get('required_tags', [])
        for tag_name in required_tags:
            if tag_name not in valid_tags:
                errors.append(
                    f"confidence_scoring.strong_signal_boost.required_tags: '{tag_name}' 不是有效的ReasonTag\n"
                    f"  → 可能是拼写错误，请检查 models/reason_tags.py 中的定义"
                )
        
        if errors:
            error_message = (
                "\n" + "="*80 + "\n"
                "⚠️  ReasonTag拼写错误检测（ReasonTag Spelling Validation Failed）\n"
                "="*80 + "\n"
                "发现无效的ReasonTag名称，系统拒绝启动（fail-fast）！\n\n"
                "错误项：\n" + "\n".join(f"  {i+1}. {err}\n" for i, err in enumerate(errors)) + "\n"
                "有效的ReasonTag列表：\n"
                "  " + ", ".join(sorted(valid_tags)) + "\n\n"
                "修复方法：\n"
                "  1. 检查配置文件: config/l1_thresholds.yaml\n"
                "  2. 修正拼写错误的标签名\n"
                "  3. 参考 models/reason_tags.py 中的 ReasonTag 枚举定义\n"
                "  4. 标签名必须使用下划线小写格式（如 strong_buy_pressure）\n\n"
                "设计原理：\n"
                "  配置中的标签拼写错误会导致运行时逻辑失效，fail-fast机制确保启动前发现\n"
                "="*80 + "\n"
            )
            raise ValueError(error_message)
        
        logger.info("✅ ReasonTag拼写校验通过：所有标签名有效")
    
    def _validate_confidence_values(self, config: dict):
        """
        启动时校验：Confidence值拼写有效性检查（PR-H）
        
        目标：所有 Confidence 字符串配置必须是合法枚举；拼写错误直接拒绝启动，
             而不是运行中降级为 LOW
        
        检查范围：
        1. execution.min_confidence_normal
        2. execution.min_confidence_reduced
        3. confidence_scoring.caps.uncertain_quality_max
        4. confidence_scoring.caps.tag_caps.* (所有值)
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 如果发现无效的Confidence值
        """
        # 有效的Confidence值（大小写不敏感）
        valid_confidence_values = {'LOW', 'MEDIUM', 'HIGH', 'ULTRA'}
        
        errors = []
        
        # 检查 executable_control.min_confidence_normal
        # P1修复：与实际使用的配置段名称保持一致（executable_control 而非 execution）
        exec_config = config.get('executable_control', {})
        min_conf_normal = exec_config.get('min_confidence_normal', 'HIGH')
        if min_conf_normal.upper() not in valid_confidence_values:
            errors.append(
                f"executable_control.min_confidence_normal: '{min_conf_normal}' 不是有效的Confidence值\n"
                f"  → 有效值: LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）"
            )
        
        # 检查 executable_control.min_confidence_reduced
        min_conf_reduced = exec_config.get('min_confidence_reduced', 'MEDIUM')
        if min_conf_reduced.upper() not in valid_confidence_values:
            errors.append(
                f"executable_control.min_confidence_reduced: '{min_conf_reduced}' 不是有效的Confidence值\n"
                f"  → 有效值: LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）"
            )
        
        # 检查 confidence_scoring.caps.uncertain_quality_max
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        uncertain_max = caps_config.get('uncertain_quality_max', 'MEDIUM')
        if uncertain_max.upper() not in valid_confidence_values:
            errors.append(
                f"confidence_scoring.caps.uncertain_quality_max: '{uncertain_max}' 不是有效的Confidence值\n"
                f"  → 有效值: LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）"
            )
        
        # 检查 confidence_scoring.caps.tag_caps.* (所有值)
        tag_caps = caps_config.get('tag_caps', {})
        for tag_name, cap_value in tag_caps.items():
            if cap_value.upper() not in valid_confidence_values:
                errors.append(
                    f"confidence_scoring.caps.tag_caps.{tag_name}: '{cap_value}' 不是有效的Confidence值\n"
                    f"  → 有效值: LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）"
                )
        
        if errors:
            error_message = (
                "\n" + "="*80 + "\n"
                "⚠️  Confidence值拼写错误检测（Confidence Value Validation Failed）\n"
                "="*80 + "\n"
                "发现无效的Confidence配置值，系统拒绝启动（fail-fast）！\n\n"
                "错误项：\n" + "\n".join(f"  {i+1}. {err}\n" for i, err in enumerate(errors)) + "\n"
                "有效的Confidence值：\n"
                "  LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）\n\n"
                "修复方法：\n"
                "  1. 检查配置文件: config/l1_thresholds.yaml\n"
                "  2. 修正拼写错误的Confidence值\n"
                "  3. 常见错误: HGIH → HIGH, MEDUIM → MEDIUM\n"
                "  4. 确保所有置信度配置使用正确的枚举值\n\n"
                "设计原理（PR-H）：\n"
                "  - 采用fail-fast原则，配置错误直接拒绝启动\n"
                "  - 避免运行时静默回退到LOW导致意外行为\n"
                "  - 保持与ReasonTag拼写校验的一致性\n"
                "="*80 + "\n"
            )
            raise ValueError(error_message)
        
        logger.info("✅ Confidence值拼写校验通过：所有置信度配置有效")
    
    
    def _flatten_thresholds(self, config: dict) -> dict:
        """
        将嵌套配置扁平化为易于访问的字典
        
        Args:
            config: 嵌套配置字典
        
        Returns:
            dict: 扁平化后的阈值字典
        """
        flat = {}
        
        # 数据质量（PR-002）
        dq = config.get('data_quality', {})
        flat['data_max_staleness_seconds'] = dq.get('max_staleness_seconds', 120)
        
        # 市场环境
        mr = config.get('market_regime', {})
        flat['extreme_price_change_1h'] = mr.get('extreme_price_change_1h', 0.05)
        flat['trend_price_change_6h'] = mr.get('trend_price_change_6h', 0.03)
        
        # 风险准入
        re = config.get('risk_exposure', {})
        flat['liquidation_price_change'] = re.get('liquidation', {}).get('price_change', 0.05)
        flat['liquidation_oi_drop'] = re.get('liquidation', {}).get('oi_drop', -0.15)
        flat['crowding_funding_abs'] = re.get('crowding', {}).get('funding_abs', 0.001)
        flat['crowding_oi_growth'] = re.get('crowding', {}).get('oi_growth', 0.30)
        flat['extreme_volume_multiplier'] = re.get('extreme_volume', {}).get('multiplier', 10.0)
        
        # 交易质量
        tq = config.get('trade_quality', {})
        flat['absorption_imbalance'] = tq.get('absorption', {}).get('imbalance', 0.7)
        flat['absorption_volume_ratio'] = tq.get('absorption', {}).get('volume_ratio', 0.5)
        flat['noisy_funding_volatility'] = tq.get('noise', {}).get('funding_volatility', 0.0005)
        flat['noisy_funding_abs'] = tq.get('noise', {}).get('funding_abs', 0.0001)
        flat['rotation_price_threshold'] = tq.get('rotation', {}).get('price_threshold', 0.02)
        flat['rotation_oi_threshold'] = tq.get('rotation', {}).get('oi_threshold', 0.05)
        flat['range_weak_imbalance'] = tq.get('range_weak', {}).get('imbalance', 0.6)
        flat['range_weak_oi'] = tq.get('range_weak', {}).get('oi', 0.10)
        
        # 方向评估
        d = config.get('direction', {})
        flat['long_imbalance_trend'] = d.get('trend', {}).get('long', {}).get('imbalance', 0.6)
        flat['long_oi_change_trend'] = d.get('trend', {}).get('long', {}).get('oi_change', 0.05)
        flat['long_price_change_trend'] = d.get('trend', {}).get('long', {}).get('price_change', 0.01)
        flat['short_imbalance_trend'] = d.get('trend', {}).get('short', {}).get('imbalance', 0.6)
        flat['short_oi_change_trend'] = d.get('trend', {}).get('short', {}).get('oi_change', 0.05)
        flat['short_price_change_trend'] = d.get('trend', {}).get('short', {}).get('price_change', 0.01)
        flat['long_imbalance_range'] = d.get('range', {}).get('long', {}).get('imbalance', 0.7)
        flat['long_oi_change_range'] = d.get('range', {}).get('long', {}).get('oi_change', 0.10)
        flat['short_imbalance_range'] = d.get('range', {}).get('short', {}).get('imbalance', 0.7)
        flat['short_oi_change_range'] = d.get('range', {}).get('short', {}).get('oi_change', 0.10)
        
        # 辅助标签阈值（P0-3）
        aux = config.get('auxiliary_tags', {})
        flat['aux_oi_growing_threshold'] = aux.get('oi_growing_threshold', 0.05)
        flat['aux_oi_declining_threshold'] = aux.get('oi_declining_threshold', -0.05)
        flat['aux_funding_rate_threshold'] = aux.get('funding_rate_threshold', 0.0005)
        
        return flat
    
    def _get_default_config(self) -> dict:
        """
        获取默认配置（当配置文件不存在时）
        
        Returns:
            dict: 默认配置字典
        """
        return {
            'symbol_universe': {
                'enabled_symbols': ['BTC', 'ETH', 'BNB', 'SOL', 'XRP'],
                'default_symbol': 'BTC'
            },
            'data_quality': {
                'max_staleness_seconds': 120
            },
            'market_regime': {
                'extreme_price_change_1h': 0.05,
                'trend_price_change_6h': 0.03
            },
            'risk_exposure': {
                'liquidation': {'price_change': 0.05, 'oi_drop': -0.15},
                'crowding': {'funding_abs': 0.001, 'oi_growth': 0.30},
                'extreme_volume': {'multiplier': 10.0}
            },
            'trade_quality': {
                'absorption': {'imbalance': 0.7, 'volume_ratio': 0.5},
                'noise': {'funding_volatility': 0.0005, 'funding_abs': 0.0001},
                'rotation': {'price_threshold': 0.02, 'oi_threshold': 0.05},
                'range_weak': {'imbalance': 0.6, 'oi': 0.10}
            },
            'direction': {
                'trend': {
                    'long': {'imbalance': 0.6, 'oi_change': 0.05, 'price_change': 0.01},
                    'short': {'imbalance': 0.6, 'oi_change': 0.05, 'price_change': 0.01}
                },
                'range': {
                    'long': {'imbalance': 0.7, 'oi_change': 0.10},
                    'short': {'imbalance': 0.7, 'oi_change': 0.10}
                }
            },
            'decision_control': {
                'min_decision_interval_seconds': 300,
                'flip_cooldown_seconds': 600,
                'enable_min_interval': True,
                'enable_flip_cooldown': True
            }
        }
    
    def update_thresholds(self, new_thresholds: dict):
        """
        热更新阈值配置
        
        Args:
            new_thresholds: 新的阈值字典
        """
        self.thresholds.update(new_thresholds)
        logger.info(f"Thresholds updated: {len(new_thresholds)} items")

    # ========================================
    # PR-005: 三层触发机制（1h/15m/5m）
    # ========================================
    
    def _evaluate_multi_tf(
        self,
        data: Dict,
        decision: Decision
    ) -> Tuple[str, List[ReasonTag]]:
        """
        PR-005: 三层触发判定（1h Context → 15m Confirm → 5m Trigger）
        
        三层架构：
        1. Context（1h）：确定允许的方向偏置
        2. Confirm（15m）：4选2确认信号强度
        3. Trigger（5m）：3选2最终触发
        
        Args:
            data: 市场数据（必须包含5m/15m/1h多周期字段）
            decision: 当前决策方向（LONG/SHORT）
        
        Returns:
            (ltf_status, ltf_tags列表)
        """
        from models.enums import LTFStatus
        
        # 检查功能开关
        config = self.config.get('multi_tf', {})
        if not config.get('enabled', False):
            return LTFStatus.NOT_APPLICABLE.value, []  # 统一使用枚举
        
        # 如果decision是NO_TRADE，无需LTF判定
        if decision == Decision.NO_TRADE:
            return LTFStatus.NOT_APPLICABLE.value, []
        
        # PR-005: 检查数据完整性
        required_fields = [
            'volume_5m', 'volume_15m', 'volume_1h',
            'volume_ratio_5m', 'volume_ratio_15m',
            'taker_imbalance_5m', 'taker_imbalance_15m', 'taker_imbalance_1h'
        ]
        
        missing_fields = [f for f in required_fields if data.get(f) is None]
        if missing_fields:
            logger.warning(f"LTF data incomplete, missing: {missing_fields}")
            return LTFStatus.MISSING.value, [ReasonTag.DATA_INCOMPLETE]
        
        # Layer 1: Context（1小时方向偏置）
        context_allowed = self._check_context_1h(data, decision, config)
        if not context_allowed:
            logger.debug(f"[LTF] Context denied for {decision.value}")
            return LTFStatus.NOT_APPLICABLE.value, [ReasonTag.LTF_CONTEXT_DENIED]
        
        # Layer 2: Confirm（15分钟，4选2）
        confirm_count = self._check_confirm_15m(data, decision, config)
        
        # Layer 3: Trigger（5分钟，3选2）
        trigger_count = self._check_trigger_5m(data, decision, config)
        
        logger.debug(f"[LTF] {decision.value}: confirm={confirm_count}/4, trigger={trigger_count}/3")
        
        # 综合判定
        confirm_config = config.get('confirm_15m', {}).get(decision.value, {})
        required_confirmed = confirm_config.get('required_confirmed', 2)
        required_partial = confirm_config.get('required_partial', 1)
        
        trigger_config = config.get('trigger_5m', {}).get(decision.value, {})
        required_trigger = trigger_config.get('required_signals', 2)
        
        if confirm_count >= required_confirmed and trigger_count >= required_trigger:
            return LTFStatus.CONFIRMED.value, [ReasonTag.LTF_CONFIRMED]
        elif confirm_count >= required_partial and trigger_count >= required_trigger:
            return LTFStatus.PARTIAL.value, [ReasonTag.LTF_PARTIAL_CONFIRM]
        else:
            return LTFStatus.FAILED.value, [ReasonTag.LTF_FAILED_CONFIRM]
    
    def _check_context_1h(
        self,
        data: Dict,
        decision: Decision,
        config: Dict
    ) -> bool:
        """
        PR-005 Layer 1: Context层（1小时方向偏置）
        
        判定1小时级别是否允许该方向的交易
        3个信号，满足required_signals个（默认2个）
        
        Args:
            data: 市场数据
            decision: 决策方向（LONG/SHORT）
            config: multi_tf配置
        
        Returns:
            bool: 是否允许该方向
        """
        context_config = config.get('context_1h', {}).get(decision.value, {})
        if not context_config:
            return True  # 无配置时默认允许
        
        # P0-01: None-safe读取
        price_change_1h = self._num(data, 'price_change_1h')
        taker_imbalance_1h = self._num(data, 'taker_imbalance_1h')
        oi_change_1h = self._num(data, 'oi_change_1h')
        
        # P0-01: 关键字段缺失，Context层无法判断
        if price_change_1h is None or taker_imbalance_1h is None or oi_change_1h is None:
            logger.debug(f"[Context] Key fields missing, denying context")
            return False
        
        signals_met = 0
        
        if decision == Decision.LONG:
            # LONG Context: 1h上涨趋势
            if price_change_1h > context_config.get('min_price_change', 0.01):
                signals_met += 1
            if taker_imbalance_1h > context_config.get('min_taker_imbalance', 0.40):
                signals_met += 1
            if oi_change_1h > context_config.get('min_oi_change', 0.05):
                signals_met += 1
        
        elif decision == Decision.SHORT:
            # SHORT Context: 1h下跌趋势
            if price_change_1h < context_config.get('max_price_change', -0.01):
                signals_met += 1
            if taker_imbalance_1h < context_config.get('max_taker_imbalance', -0.40):
                signals_met += 1
            if oi_change_1h > context_config.get('min_oi_change', 0.05):
                signals_met += 1
        
        required = context_config.get('required_signals', 2)
        context_ok = signals_met >= required
        
        logger.debug(f"[Context] {decision.value}: {signals_met}/{required} signals met")
        return context_ok
    
    def _check_confirm_15m(
        self,
        data: Dict,
        decision: Decision,
        config: Dict
    ) -> int:
        """
        PR-005 Layer 2: Confirm层（15分钟确认）
        
        4个信号，满足>=2个为CONFIRMED，1个为PARTIAL
        
        Args:
            data: 市场数据
            decision: 决策方向
            config: multi_tf配置
        
        Returns:
            int: 满足的信号数量（0-4）
        """
        confirm_config = config.get('confirm_15m', {}).get(decision.value, {})
        if not confirm_config:
            return 0
        
        # P0-05: None-safe读取（不提供默认值）
        price_change_15m = self._num(data, 'price_change_15m')
        taker_imbalance_15m = self._num(data, 'taker_imbalance_15m')
        volume_ratio_15m = self._num(data, 'volume_ratio_15m')
        oi_change_15m = self._num(data, 'oi_change_15m')
        
        # P0-05: 字段缺失直接返回0（不计入signals_met）
        # 不伪装成"中性"，而是"无法判断"
        if any(v is None for v in [price_change_15m, taker_imbalance_15m, volume_ratio_15m, oi_change_15m]):
            missing = [k for k, v in {
                'price_change_15m': price_change_15m,
                'taker_imbalance_15m': taker_imbalance_15m,
                'volume_ratio_15m': volume_ratio_15m,
                'oi_change_15m': oi_change_15m
            }.items() if v is None]
            logger.debug(f"[Confirm] Fields missing: {missing}, cannot evaluate")
            return 0  # 无法计算信号数
        
        signals_met = 0
        
        if decision == Decision.LONG:
            if price_change_15m > confirm_config.get('min_price_change', 0.005):
                signals_met += 1
            if taker_imbalance_15m > confirm_config.get('min_taker_imbalance', 0.50):
                signals_met += 1
            if volume_ratio_15m > confirm_config.get('min_volume_ratio', 1.5):
                signals_met += 1
            if oi_change_15m > confirm_config.get('min_oi_change', 0.03):
                signals_met += 1
        
        elif decision == Decision.SHORT:
            if price_change_15m < confirm_config.get('max_price_change', -0.005):
                signals_met += 1
            if taker_imbalance_15m < confirm_config.get('max_taker_imbalance', -0.50):
                signals_met += 1
            if volume_ratio_15m > confirm_config.get('min_volume_ratio', 1.5):
                signals_met += 1
            if oi_change_15m > confirm_config.get('min_oi_change', 0.03):
                signals_met += 1
        
        logger.debug(f"[Confirm] {decision.value}: {signals_met}/4 signals met")
        return signals_met
    
    def _check_trigger_5m(
        self,
        data: Dict,
        decision: Decision,
        config: Dict
    ) -> int:
        """
        PR-005 Layer 3: Trigger层（5分钟触发）
        
        3个信号，满足>=2个触发
        
        Args:
            data: 市场数据
            decision: 决策方向
            config: multi_tf配置
        
        Returns:
            int: 满足的信号数量（0-3）
        """
        trigger_config = config.get('trigger_5m', {}).get(decision.value, {})
        if not trigger_config:
            return 0
        
        # P0-05: None-safe读取（不提供默认值）
        price_change_5m = self._num(data, 'price_change_5m')
        taker_imbalance_5m = self._num(data, 'taker_imbalance_5m')
        volume_ratio_5m = self._num(data, 'volume_ratio_5m')
        
        # P0-05: 字段缺失直接返回0（不计入signals_met）
        if any(v is None for v in [price_change_5m, taker_imbalance_5m, volume_ratio_5m]):
            missing = [k for k, v in {
                'price_change_5m': price_change_5m,
                'taker_imbalance_5m': taker_imbalance_5m,
                'volume_ratio_5m': volume_ratio_5m
            }.items() if v is None]
            logger.debug(f"[Trigger] Fields missing: {missing}, cannot evaluate")
            return 0  # 无法计算信号数
        
        signals_met = 0
        
        if decision == Decision.LONG:
            if price_change_5m > trigger_config.get('min_price_change', 0.002):
                signals_met += 1
            if taker_imbalance_5m > trigger_config.get('min_taker_imbalance', 0.60):
                signals_met += 1
            if volume_ratio_5m > trigger_config.get('min_volume_ratio', 2.0):
                signals_met += 1
        
        elif decision == Decision.SHORT:
            if price_change_5m < trigger_config.get('max_price_change', -0.002):
                signals_met += 1
            if taker_imbalance_5m < trigger_config.get('max_taker_imbalance', -0.60):
                signals_met += 1
            if volume_ratio_5m > trigger_config.get('min_volume_ratio', 2.0):
                signals_met += 1
        
        logger.debug(f"[Trigger] {decision.value}: {signals_met}/3 signals met")
        return signals_met
    
    def _apply_binding_policy(
        self,
        decision: Decision,
        ltf_status: str,
        reason_tags: List[ReasonTag]
    ) -> Decision:
        """
        PR-005: 应用binding_policy策略
        
        根据LTF状态和配置中的binding_policy决定如何处理决策：
        - CONFIRMED: 正常通过
        - PARTIAL: 根据 partial_action 处理（degrade/allow/deny）
        - FAILED: 根据是否短期机会决定处理方式
        - MISSING: 数据缺失，降级处理
        
        Args:
            decision: 当前决策
            ltf_status: LTF判定状态
            reason_tags: 原因标签列表（可能被修改）
        
        Returns:
            Decision: 处理后的决策（可能被改为NO_TRADE）
        """
        if decision == Decision.NO_TRADE:
            return decision
        
        # 读取binding_policy配置
        multi_tf_config = self.config.get('multi_tf', {})
        binding_policy = multi_tf_config.get('binding_policy', {})
        
        # 检测是否是短期机会（通过检查特定标签）
        short_term_tags = [
            ReasonTag.RANGE_SHORT_TERM_LONG,
            ReasonTag.RANGE_SHORT_TERM_SHORT,
            ReasonTag.SHORT_TERM_TREND
        ]
        is_short_term_opportunity = any(tag in reason_tags for tag in short_term_tags)
        
        # 根据ltf_status应用策略
        if ltf_status == 'confirmed':
            # CONFIRMED: 三层全部满足，正常通过
            logger.debug(f"[BindingPolicy] CONFIRMED: decision={decision.value} passed")
            return decision
        
        elif ltf_status == 'partial':
            # PARTIAL: 根据配置处理
            partial_action = binding_policy.get('partial_action', 'degrade')
            
            if partial_action == 'deny':
                logger.info(f"[BindingPolicy] PARTIAL + deny: {decision.value} → NO_TRADE")
                return Decision.NO_TRADE
            elif partial_action == 'degrade':
                # degrade: 通过，但标签已经添加了LTF_PARTIAL_CONFIRM（会导致ALLOW_REDUCED）
                logger.debug(f"[BindingPolicy] PARTIAL + degrade: decision={decision.value} degraded")
                return decision
            else:  # allow
                logger.debug(f"[BindingPolicy] PARTIAL + allow: decision={decision.value} allowed")
                return decision
        
        elif ltf_status == 'failed':
            # FAILED: 根据是否短期机会决定
            if is_short_term_opportunity:
                failed_action = binding_policy.get('failed_short_term_action', 'cancel')
                if failed_action == 'cancel':
                    logger.info(
                        f"[BindingPolicy] FAILED + short_term_opportunity: "
                        f"{decision.value} → NO_TRADE (短期机会取消)"
                    )
                    return Decision.NO_TRADE
            else:
                # 长期信号
                failed_action = binding_policy.get('failed_long_term_action', 'degrade')
                if failed_action == 'cancel' or failed_action == 'deny':
                    logger.info(f"[BindingPolicy] FAILED + long_term: {decision.value} → NO_TRADE")
                    return Decision.NO_TRADE
                # degrade: 通过，但标签已经添加了LTF_FAILED_CONFIRM（会导致DENY）
                logger.debug(f"[BindingPolicy] FAILED + long_term + degrade: decision={decision.value}")
            
            return decision
        
        elif ltf_status == 'missing':
            # MISSING: 数据缺失，降级处理（不取消决策，但会被DEGRADE）
            logger.debug(f"[BindingPolicy] MISSING: decision={decision.value} with incomplete data")
            return decision
        
        # 其他状态（context_denied等）: 标签已添加，正常返回
        return decision
    
    # ========================================
    # PR-DUAL: 双周期独立结论
    # ========================================
    
    def on_new_tick_dual(self, symbol: str, data: Dict) -> 'DualTimeframeResult':
        """
        L1决策核心入口 - 双周期独立结论（PR-DUAL）
        
        同时输出短期（5m/15m）和中长期（1h/6h）两套独立结论，
        并分析两者是否一致、是否可执行，以及冲突时的处理规则。
        
        Args:
            symbol: 交易对符号（如 "BTC"）
            data: 市场数据字典（需包含多周期数据）
        
        Returns:
            DualTimeframeResult: 包含双周期独立结论的完整输出
        """
        from models.dual_timeframe_result import (
            DualTimeframeResult, TimeframeConclusion, AlignmentAnalysis
        )
        from models.enums import Timeframe, AlignmentType, ConflictResolution
        
        logger.info(f"[{symbol}] Starting dual-timeframe L1 decision pipeline")
        
        # ===== Step 1: 数据验证（全局）=====
        is_valid, normalized_data, fail_tag, norm_trace = self._validate_data(data)
        global_risk_tags = []
        
        if not is_valid:
            # 数据验证失败，返回双NO_TRADE
            logger.warning(f"[{symbol}] Data validation failed, returning dual NO_TRADE")
            global_risk_tags = [fail_tag] if fail_tag else [ReasonTag.INVALID_DATA]
            # PATCH-1: 记录 trace（虽然是 dual 模式，也要记录）
            logger.debug(f"[{symbol}] Normalization trace (failed): {norm_trace}")
            return self._build_dual_no_trade_result(symbol, global_risk_tags, price=data.get('price'))
        
        data = normalized_data
        
        # ===== Step 1.5: Lookback Coverage 检查（PATCH-2）=====
        coverage_ok, coverage_tags = self._check_lookback_coverage(data)
        if not coverage_ok:
            logger.warning(f"[{symbol}] Lookback coverage check failed: {[t.value for t in coverage_tags]}")
            # 对于短期决策关键的窗口（5m/15m）缺失，直接返回 NO_TRADE
            critical_gaps = [ReasonTag.DATA_GAP_5M, ReasonTag.DATA_GAP_15M]
            if any(tag in coverage_tags for tag in critical_gaps):
                logger.warning(f"[{symbol}] Critical window data gap, returning dual NO_TRADE")
                return self._build_dual_no_trade_result(symbol, coverage_tags, regime=MarketRegime.RANGE)
            else:
                # 非关键窗口缺失（1h/6h），记录但继续（可能降级）
                global_risk_tags.extend(coverage_tags)
                logger.info(f"[{symbol}] Non-critical window gap, continuing with degraded quality")
        
        # ===== Step 1.6: Critical Fields 检查（P0-03重构：独立标记，不过度短路）=====
        # P0-03改进：short和medium独立检查，不相互短路
        
        # 检查短期关键字段（5m/15m）
        critical_short_fields = ['price_change_5m', 'price_change_15m', 'oi_change_5m', 'oi_change_15m',
                                 'taker_imbalance_5m', 'taker_imbalance_15m', 'volume_ratio_5m', 'volume_ratio_15m']
        missing_short = [f for f in critical_short_fields if data.get(f) is None]
        
        has_short_data = True
        if missing_short:
            logger.warning(f"[{symbol}] Short-term critical fields missing: {missing_short}")
            global_risk_tags.append(ReasonTag.DATA_INCOMPLETE_LTF)
            has_short_data = False
            # P0-03: 不立即返回，让medium_term有机会评估
        
        # 检查中期关键字段（1h/6h）
        critical_medium_fields = ['price_change_1h', 'price_change_6h', 'oi_change_1h', 'oi_change_6h']
        missing_medium = [f for f in critical_medium_fields if data.get(f) is None]
        
        has_medium_data = True
        if missing_medium:
            logger.info(f"[{symbol}] Medium-term critical fields missing: {missing_medium}")
            global_risk_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)
            has_medium_data = False
            # P0-03: 不立即返回，让short_term有机会评估（如果有数据）
        
        # P0-03: 只有两者都缺数据时才全局短路
        if not has_short_data and not has_medium_data:
            logger.warning(f"[{symbol}] Both short and medium term data missing, returning dual NO_TRADE")
            return self._build_dual_no_trade_result(symbol, global_risk_tags, regime=MarketRegime.RANGE)
        
        # ===== Step 2: 全局风险评估（极端行情等）=====
        regime, regime_tags = self._detect_market_regime(data)
        
        if regime == MarketRegime.EXTREME:
            logger.warning(f"[{symbol}] EXTREME regime detected, returning dual NO_TRADE")
            global_risk_tags.append(ReasonTag.EXTREME_REGIME)
            return self._build_dual_no_trade_result(symbol, global_risk_tags, regime=regime)
        
        # 检查其他全局风险
        risk_allowed, risk_tags = self._eval_risk_exposure_allowed(data, regime)
        if not risk_allowed:
            logger.warning(f"[{symbol}] Global risk denied: {[t.value for t in risk_tags]}")
            global_risk_tags.extend(risk_tags)
            return self._build_dual_no_trade_result(symbol, global_risk_tags, regime=regime, risk_allowed=False)
        
        # ===== Step 3: 短期评估（5m/15m）- P0-03: 独立评估 =====
        # P0-03: 即使short缺数据，仍尝试评估（内部会返回NO_TRADE+DATA_INCOMPLETE_LTF）
        short_term = self._evaluate_short_term(symbol, data, regime)
        
        # ===== Step 4: 中长期评估（1h/6h）- P0-03: 独立评估 =====
        # P0-03: 即使medium缺数据，仍尝试评估（内部会返回NO_TRADE+DATA_INCOMPLETE_MTF）
        # short缺数据不应掐掉medium的评估
        medium_term = self._evaluate_medium_term(symbol, data, regime)
        
        # ===== Step 5: 一致性分析 =====
        alignment = self._analyze_alignment(short_term, medium_term)
        
        # ===== Step 5.5: 频率控制（PR-DUAL）=====
        current_time = datetime.now()
        
        # 5.5.1 检查短期决策是否被频率控制阻断
        short_blocked, short_block_reason = self.dual_decision_memory.should_block_short_term(
            symbol, short_term.decision, current_time
        )
        
        if short_blocked:
            logger.info(f"[{symbol}] Short-term decision blocked by frequency control: {short_block_reason}")
            # PATCH-3: 频控不改写信号方向，只标记不可执行
            # 保留原始决策（signal_decision），但设置 executable=False
            from models.dual_timeframe_result import TimeframeConclusion
            from models.enums import Timeframe
            
            # 保存原始信号
            original_decision = short_term.decision
            original_tags = short_term.reason_tags.copy()
            
            # 添加频控标签，但保留原始方向
            short_term = TimeframeConclusion(
                timeframe=Timeframe.SHORT_TERM,
                timeframe_label="5m/15m",
                decision=original_decision,  # PATCH-3: 保留原始方向
                confidence=short_term.confidence,  # 保留原始置信度
                market_regime=regime,
                trade_quality=short_term.trade_quality,
                execution_permission=ExecutionPermission.DENY,  # 阻断执行
                executable=False,  # 不可执行
                reason_tags=original_tags + [ReasonTag.MIN_INTERVAL_BLOCK],  # 添加频控标签
                key_metrics=short_term.key_metrics  # 保留原始指标
            )
            logger.debug(f"[{symbol}] Short-term signal preserved: {original_decision.value}, but executable=False")
        
        # 5.5.2 检查中长期决策是否被频率控制阻断
        medium_blocked, medium_block_reason = self.dual_decision_memory.should_block_medium_term(
            symbol, medium_term.decision, current_time
        )
        
        if medium_blocked:
            logger.info(f"[{symbol}] Medium-term decision blocked by frequency control: {medium_block_reason}")
            # PATCH-3: 频控不改写信号方向，只标记不可执行
            from models.dual_timeframe_result import TimeframeConclusion
            from models.enums import Timeframe
            
            # 保存原始信号
            original_decision = medium_term.decision
            original_tags = medium_term.reason_tags.copy()
            
            # 添加频控标签，但保留原始方向
            medium_term = TimeframeConclusion(
                timeframe=Timeframe.MEDIUM_TERM,
                timeframe_label="1h/6h",
                decision=original_decision,  # PATCH-3: 保留原始方向
                confidence=medium_term.confidence,  # 保留原始置信度
                market_regime=regime,
                trade_quality=medium_term.trade_quality,
                execution_permission=ExecutionPermission.DENY,  # 阻断执行
                executable=False,  # 不可执行
                reason_tags=original_tags + [ReasonTag.MIN_INTERVAL_BLOCK],  # 添加频控标签
                key_metrics=medium_term.key_metrics  # 保留原始指标
            )
            logger.debug(f"[{symbol}] Medium-term signal preserved: {original_decision.value}, but executable=False")
        
        # 5.5.3 重新分析一致性（如果有周期被阻断）
        if short_blocked or medium_blocked:
            alignment = self._analyze_alignment(short_term, medium_term)
            logger.debug(f"[{symbol}] Alignment re-analyzed after frequency control: {alignment.alignment_type.value}")
        
        # 5.5.4 检查对齐类型翻转是否被阻断
        alignment_blocked, alignment_block_reason = self.dual_decision_memory.should_block_alignment_flip(
            symbol, alignment.alignment_type, current_time
        )
        
        if alignment_blocked:
            logger.info(f"[{symbol}] Alignment flip blocked: {alignment_block_reason}")
            # 对齐翻转被阻断，保持为BOTH_NO_TRADE（最保守策略）
            from models.dual_timeframe_result import AlignmentAnalysis
            from models.enums import AlignmentType
            alignment = AlignmentAnalysis(
                is_aligned=True,
                alignment_type=AlignmentType.BOTH_NO_TRADE,
                has_conflict=False,
                conflict_resolution=None,
                resolution_reason="对齐类型翻转频率控制",
                recommended_action=Decision.NO_TRADE,
                recommended_confidence=Confidence.LOW,
                recommendation_notes="⏸️ 对齐类型翻转冷却中，暂不输出"
            )
        
        # 5.5.5 更新决策记忆
        if not short_blocked:
            self.dual_decision_memory.update_short_term(symbol, short_term.decision, current_time)
        if not medium_blocked:
            self.dual_decision_memory.update_medium_term(symbol, medium_term.decision, current_time)
        if not alignment_blocked:
            self.dual_decision_memory.update_alignment(symbol, alignment.alignment_type, current_time)
        
        # ===== Step 6: 构造结果 =====
        result = DualTimeframeResult(
            short_term=short_term,
            medium_term=medium_term,
            alignment=alignment,
            symbol=symbol,
            timestamp=current_time,
            price=data.get('price'),
            risk_exposure_allowed=risk_allowed,
            global_risk_tags=global_risk_tags + regime_tags
        )
        
        logger.info(f"[{symbol}] Dual-timeframe result: {result.get_summary()}")
        
        return result
    
    def _evaluate_short_term(
        self, 
        symbol: str, 
        data: Dict, 
        regime: MarketRegime
    ) -> 'TimeframeConclusion':
        """
        短期评估（5m/15m）- P0动态阈值版本
        
        使用5分钟和15分钟的数据进行快速方向判断。
        
        5维信号评估：
        1. 价格变化（15m） - 动态阈值
        2. Taker失衡（15m）
        3. OI变化（15m）
        4. 放量比率（15m）
        5. 5m动量确认
        
        动态阈值规则：
        - TREND: 0.3%（灵敏，捕捉趋势延续）
        - RANGE: 0.8%（保守，减少假信号）
        - EXTREME: 1.5%（Safety First，极端环境更严格）
        """
        from models.dual_timeframe_result import TimeframeConclusion
        from models.enums import Timeframe
        
        reason_tags = []
        
        # P0-05: None-safe读取（不提供默认值，禁止伪中性）
        price_change_5m = self._num(data, 'price_change_5m')
        price_change_15m = self._num(data, 'price_change_15m')
        taker_imbalance_5m = self._num(data, 'taker_imbalance_5m')
        taker_imbalance_15m = self._num(data, 'taker_imbalance_15m')
        volume_ratio_5m = self._num(data, 'volume_ratio_5m')
        volume_ratio_15m = self._num(data, 'volume_ratio_15m')
        oi_change_15m = self._num(data, 'oi_change_15m')
        
        # P0-05: 检查短期关键字段完整性
        critical_short_fields = {
            'price_change_5m': price_change_5m,
            'price_change_15m': price_change_15m,
            'taker_imbalance_5m': taker_imbalance_5m,
            'taker_imbalance_15m': taker_imbalance_15m,
            'volume_ratio_5m': volume_ratio_5m,
            'volume_ratio_15m': volume_ratio_15m,
            'oi_change_15m': oi_change_15m
        }
        
        missing_fields = [k for k, v in critical_short_fields.items() if v is None]
        
        if missing_fields:
            # P0-05: 显性标记短期数据缺失
            logger.warning(f"[{symbol}] Short-term critical fields missing: {missing_fields}")
            reason_tags.append(ReasonTag.DATA_INCOMPLETE_LTF)
            
            # 构造NO_TRADE结论（不进入required_signals计数）
            from models.dual_timeframe_result import TimeframeConclusion
            from models.enums import Timeframe
            
            return TimeframeConclusion(
                timeframe=Timeframe.SHORT_TERM,
                timeframe_label="5m/15m",
                decision=Decision.NO_TRADE,
                confidence=Confidence.LOW,
                market_regime=regime,
                trade_quality=TradeQuality.POOR,
                execution_permission=ExecutionPermission.DENY,
                executable=False,
                reason_tags=reason_tags,
                key_metrics={'missing_fields': missing_fields}
            )
        
        # 短期方向判断（使用配置中的短期阈值）
        short_config = self.config.get('dual_timeframe', {}).get('short_term', {})
        
        # ===== P0: 动态阈值选择 =====
        price_change_config = short_config.get('min_price_change_15m', {})
        
        if isinstance(price_change_config, dict) and price_change_config.get('dynamic', False):
            # 动态阈值模式：根据市场环境选择
            if regime == MarketRegime.TREND:
                min_price_change = price_change_config.get('trend', 0.003)  # 0.3%
                threshold_regime = 'trend'
            elif regime == MarketRegime.RANGE:
                min_price_change = price_change_config.get('range', 0.008)  # 0.8%
                threshold_regime = 'range'
            elif regime == MarketRegime.EXTREME:
                min_price_change = price_change_config.get('extreme', 0.015)  # 1.5%
                threshold_regime = 'extreme'
            else:
                min_price_change = price_change_config.get('default', 0.005)  # 0.5%
                threshold_regime = 'default'
            
            logger.debug(f"[{symbol}] Dynamic threshold: regime={regime.value} -> min_price_change={min_price_change:.4f} ({threshold_regime})")
        else:
            # 兼容模式：使用固定阈值（向后兼容）
            min_price_change = price_change_config if isinstance(price_change_config, (int, float)) else 0.003
            threshold_regime = 'fixed'
        
        # 其他阈值
        min_taker_imbalance = short_config.get('min_taker_imbalance', 0.40)
        min_volume_ratio = short_config.get('min_volume_ratio', 1.5)
        min_oi_change = short_config.get('min_oi_change_15m', 0.02)
        required_signals = short_config.get('required_signals', 4)
        
        # P0-05: 构造key_metrics（使用实际值，已确保非None）
        key_metrics = {
            'price_change_5m': price_change_5m,  # 此时已确保非None
            'price_change_15m': price_change_15m,
            'taker_imbalance_5m': taker_imbalance_5m,
            'taker_imbalance_15m': taker_imbalance_15m,
            'volume_ratio_5m': volume_ratio_5m,
            'volume_ratio_15m': volume_ratio_15m,
            'oi_change_15m': oi_change_15m,
            # 动态阈值元数据（便于前端显示和回测分析）
            'threshold_min_price_change': min_price_change,
            'threshold_regime': threshold_regime
        }
        
        # ===== 5维信号评估（P0-05: 所有比较已确保非None） =====
        
        # LONG 条件：价格上涨 + 买压 + OI增长 + 放量 + 5m确认
        long_signals = 0
        # 维度1: 价格变化（动态阈值）- 已确保非None
        if price_change_15m > min_price_change:
            long_signals += 1
        # 维度2: Taker失衡 - 已确保非None
        if taker_imbalance_15m > min_taker_imbalance:
            long_signals += 1
        # 维度3: OI变化（多头增仓）- 已确保非None
        if oi_change_15m > min_oi_change:
            long_signals += 1
        # 维度4: 放量 - 已确保非None
        if volume_ratio_15m > min_volume_ratio:
            long_signals += 1
        # 维度5: 5m动量确认 - 已确保非None
        if price_change_5m > 0 and taker_imbalance_5m > 0.30:
            long_signals += 1
        
        # SHORT 条件：价格下跌 + 卖压 + OI增长 + 放量 + 5m确认
        short_signals = 0
        # 维度1: 价格变化（动态阈值）- 已确保非None
        if price_change_15m < -min_price_change:
            short_signals += 1
        # 维度2: Taker失衡 - 已确保非None
        if taker_imbalance_15m < -min_taker_imbalance:
            short_signals += 1
        # 维度3: OI变化（空头增仓，OI同样增长）- 已确保非None
        if oi_change_15m > min_oi_change:
            short_signals += 1
        # 维度4: 放量 - 已确保非None
        if volume_ratio_15m > min_volume_ratio:
            short_signals += 1
        # 维度5: 5m动量确认 - 已确保非None
        if price_change_5m < 0 and taker_imbalance_5m < -0.30:
            short_signals += 1
        
        # 记录信号详情到日志
        logger.debug(f"[{symbol}] Short-term signals: LONG={long_signals}/5, SHORT={short_signals}/5, required={required_signals}")
        
        # 决策判断（5选N）
        if long_signals >= required_signals and long_signals > short_signals:
            decision = Decision.LONG
            reason_tags.append(ReasonTag.STRONG_BUY_PRESSURE)
            if price_change_15m > 0.01:
                reason_tags.append(ReasonTag.SHORT_TERM_PRICE_SURGE)
        elif short_signals >= required_signals and short_signals > long_signals:
            decision = Decision.SHORT
            reason_tags.append(ReasonTag.STRONG_SELL_PRESSURE)
            if price_change_15m < -0.01:
                reason_tags.append(ReasonTag.SHORT_TERM_PRICE_DROP)
        else:
            decision = Decision.NO_TRADE
            reason_tags.append(ReasonTag.NO_CLEAR_DIRECTION)
        
        # 置信度计算（基于信号数量）
        max_signals = max(long_signals, short_signals)
        if max_signals >= 5:
            confidence = Confidence.ULTRA  # 5/5 完美信号
        elif max_signals >= 4:
            confidence = Confidence.HIGH   # 4/5 高置信
        elif max_signals >= 3:
            confidence = Confidence.MEDIUM # 3/5 中等
        else:
            confidence = Confidence.LOW    # <3 低置信
        
        # 质量评估
        if abs(taker_imbalance_15m) > 0.6 and volume_ratio_15m > 1.5:
            quality = TradeQuality.GOOD
        elif abs(taker_imbalance_15m) > 0.3:
            quality = TradeQuality.UNCERTAIN
        else:
            quality = TradeQuality.POOR
        
        # 执行许可
        exec_perm = self._compute_execution_permission(reason_tags)
        
        # 构造结论
        conclusion = TimeframeConclusion(
            timeframe=Timeframe.SHORT_TERM,
            timeframe_label="5m/15m",
            decision=decision,
            confidence=confidence,
            market_regime=regime,
            trade_quality=quality,
            execution_permission=exec_perm,
            executable=self._compute_tf_executable(decision, confidence, exec_perm, quality),
            reason_tags=reason_tags,
            key_metrics=key_metrics
        )
        
        logger.debug(f"[{symbol}] Short-term result: {decision.value}, conf={confidence.value}, threshold={threshold_regime}({min_price_change:.4f})")
        
        return conclusion
    
    def _evaluate_medium_term(
        self, 
        symbol: str, 
        data: Dict, 
        regime: MarketRegime
    ) -> 'TimeframeConclusion':
        """
        中长期评估（1h/6h）- P0-01: None-safe重构
        
        使用1小时和6小时的数据进行趋势判断
        
        P0-01改进：
        - 禁止None→0伪中性
        - 关键字段缺失显性标记DATA_INCOMPLETE_MTF
        - 使用None-safe读取
        """
        from models.dual_timeframe_result import TimeframeConclusion
        from models.enums import Timeframe
        
        reason_tags = []
        
        # P0-01: None-safe读取（不提供默认值）
        price_change_1h = self._num(data, 'price_change_1h')
        price_change_6h = self._num(data, 'price_change_6h')
        oi_change_1h = self._num(data, 'oi_change_1h')
        oi_change_6h = self._num(data, 'oi_change_6h')
        taker_imbalance_1h = self._num(data, 'taker_imbalance_1h')  # P0-02: 统一字段
        funding_rate = self._num(data, 'funding_rate')
        
        # P0-01: 检查关键字段完整性
        critical_fields = {
            'price_change_1h': price_change_1h,
            'price_change_6h': price_change_6h,
            'oi_change_1h': oi_change_1h,
            'oi_change_6h': oi_change_6h,
            'taker_imbalance_1h': taker_imbalance_1h
        }
        
        missing_fields = [k for k, v in critical_fields.items() if v is None]
        
        if missing_fields:
            # 显性标记：中期关键字段缺失
            logger.warning(f"[{symbol}] Medium-term critical fields missing: {missing_fields}")
            reason_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)
            
            # 构造NO_TRADE结论（不伪装成"无变化"）
            return TimeframeConclusion(
                timeframe=Timeframe.MEDIUM_TERM,
                timeframe_label="1h/6h",
                decision=Decision.NO_TRADE,
                confidence=Confidence.LOW,
                market_regime=regime,
                trade_quality=TradeQuality.POOR,
                execution_permission=ExecutionPermission.DENY,
                executable=False,
                reason_tags=reason_tags,
                key_metrics={'missing_fields': missing_fields}
            )
        
        # P0-01: key_metrics使用实际值（可能为None，但不伪装成0）
        # funding_rate可以缺失（非关键），使用0.0作为默认
        key_metrics = {
            'price_change_1h': price_change_1h,  # 此时已确保非None
            'price_change_6h': price_change_6h,
            'oi_change_1h': oi_change_1h,
            'oi_change_6h': oi_change_6h,
            'taker_imbalance_1h': taker_imbalance_1h,  # P0-02: 统一字段名
            'funding_rate': funding_rate if funding_rate is not None else 0.0  # 非关键字段可默认
        }
        
        # 中长期方向判断（复用现有的方向评估逻辑）
        allow_long, long_tags = self._eval_long_direction(data, regime)
        allow_short, short_tags = self._eval_short_direction(data, regime)
        
        # 添加方向标签
        if allow_long:
            reason_tags.extend(long_tags)
        if allow_short:
            reason_tags.extend(short_tags)
        
        # 决策判断
        if allow_long and not allow_short:
            decision = Decision.LONG
        elif allow_short and not allow_long:
            decision = Decision.SHORT
        elif allow_long and allow_short:
            # 冲突，保守处理
            decision = Decision.NO_TRADE
            reason_tags.append(ReasonTag.CONFLICTING_SIGNALS)
        else:
            decision = Decision.NO_TRADE
            reason_tags.append(ReasonTag.NO_CLEAR_DIRECTION)
        
        # 质量评估
        quality, quality_tags = self._eval_trade_quality(symbol, data, regime)
        reason_tags.extend(quality_tags)
        
        # 置信度计算（复用现有逻辑）
        confidence = self._compute_confidence(decision, regime, quality, reason_tags)
        
        # 执行许可
        exec_perm = self._compute_execution_permission(reason_tags)
        
        # 构造结论
        conclusion = TimeframeConclusion(
            timeframe=Timeframe.MEDIUM_TERM,
            timeframe_label="1h/6h",
            decision=decision,
            confidence=confidence,
            market_regime=regime,
            trade_quality=quality,
            execution_permission=exec_perm,
            executable=self._compute_tf_executable(decision, confidence, exec_perm, quality),
            reason_tags=reason_tags,
            key_metrics=key_metrics
        )
        
        logger.debug(f"[{symbol}] Medium-term: {decision.value}, conf={confidence.value}, exec={conclusion.executable}")
        
        return conclusion
    
    def _compute_tf_executable(
        self, 
        decision: Decision, 
        confidence: Confidence, 
        exec_perm: ExecutionPermission,
        quality: TradeQuality
    ) -> bool:
        """
        计算单周期的可执行性
        """
        if decision == Decision.NO_TRADE:
            return False
        
        if exec_perm == ExecutionPermission.DENY:
            return False
        
        if quality == TradeQuality.POOR:
            return False
        
        # 读取配置门槛
        exec_config = self.config.get('executable_control', {})
        min_conf_normal = self._string_to_confidence(exec_config.get('min_confidence_normal', 'HIGH'))
        min_conf_reduced = self._string_to_confidence(exec_config.get('min_confidence_reduced', 'MEDIUM'))
        
        if exec_perm == ExecutionPermission.ALLOW:
            return self._confidence_level(confidence) >= self._confidence_level(min_conf_normal)
        elif exec_perm == ExecutionPermission.ALLOW_REDUCED:
            return self._confidence_level(confidence) >= self._confidence_level(min_conf_reduced)
        
        return False
    
    def _analyze_alignment(
        self, 
        short_term: 'TimeframeConclusion', 
        medium_term: 'TimeframeConclusion'
    ) -> 'AlignmentAnalysis':
        """
        分析双周期一致性
        
        判断短期和中长期结论是否一致，并生成处理建议
        """
        from models.dual_timeframe_result import AlignmentAnalysis
        from models.enums import AlignmentType, ConflictResolution
        
        short_dec = short_term.decision
        medium_dec = medium_term.decision
        
        # 判断一致性类型
        if short_dec == Decision.LONG and medium_dec == Decision.LONG:
            alignment_type = AlignmentType.BOTH_LONG
            is_aligned = True
            has_conflict = False
        elif short_dec == Decision.SHORT and medium_dec == Decision.SHORT:
            alignment_type = AlignmentType.BOTH_SHORT
            is_aligned = True
            has_conflict = False
        elif short_dec == Decision.NO_TRADE and medium_dec == Decision.NO_TRADE:
            alignment_type = AlignmentType.BOTH_NO_TRADE
            is_aligned = True
            has_conflict = False
        elif short_dec == Decision.LONG and medium_dec == Decision.SHORT:
            alignment_type = AlignmentType.CONFLICT_LONG_SHORT
            is_aligned = False
            has_conflict = True
        elif short_dec == Decision.SHORT and medium_dec == Decision.LONG:
            alignment_type = AlignmentType.CONFLICT_SHORT_LONG
            is_aligned = False
            has_conflict = True
        elif short_dec in [Decision.LONG, Decision.SHORT] and medium_dec == Decision.NO_TRADE:
            alignment_type = AlignmentType.PARTIAL_LONG if short_dec == Decision.LONG else AlignmentType.PARTIAL_SHORT
            is_aligned = False
            has_conflict = False
        elif medium_dec in [Decision.LONG, Decision.SHORT] and short_dec == Decision.NO_TRADE:
            alignment_type = AlignmentType.PARTIAL_LONG if medium_dec == Decision.LONG else AlignmentType.PARTIAL_SHORT
            is_aligned = False
            has_conflict = False
        else:
            alignment_type = AlignmentType.BOTH_NO_TRADE
            is_aligned = True
            has_conflict = False
        
        # 读取冲突处理配置
        conflict_config = self.config.get('dual_timeframe', {}).get('conflict_resolution', {})
        default_strategy = conflict_config.get('default_strategy', 'no_trade')
        
        # 生成冲突处理建议
        conflict_resolution = None
        resolution_reason = ""
        recommended_action = Decision.NO_TRADE
        recommended_confidence = Confidence.LOW
        recommendation_notes = ""
        
        if has_conflict:
            # 方向冲突
            conflict_resolution = ConflictResolution(default_strategy)
            
            if conflict_resolution == ConflictResolution.NO_TRADE:
                resolution_reason = "短期与中长期方向冲突，保守选择不交易"
                recommended_action = Decision.NO_TRADE
                recommendation_notes = "⚠️ 周期冲突：建议等待方向一致后再操作"
            elif conflict_resolution == ConflictResolution.FOLLOW_MEDIUM_TERM:
                resolution_reason = "跟随中长期趋势，忽略短期波动"
                recommended_action = medium_dec
                recommended_confidence = medium_term.confidence
                recommendation_notes = f"跟随中长期({medium_term.timeframe_label})方向：{medium_dec.value.upper()}"
            elif conflict_resolution == ConflictResolution.FOLLOW_SHORT_TERM:
                resolution_reason = "捕捉短期机会"
                recommended_action = short_dec
                recommended_confidence = short_term.confidence
                recommendation_notes = f"跟随短期({short_term.timeframe_label})方向：{short_dec.value.upper()}"
            elif conflict_resolution == ConflictResolution.FOLLOW_HIGHER_CONFIDENCE:
                if self._confidence_level(short_term.confidence) > self._confidence_level(medium_term.confidence):
                    resolution_reason = "短期置信度更高"
                    recommended_action = short_dec
                    recommended_confidence = short_term.confidence
                else:
                    resolution_reason = "中长期置信度更高"
                    recommended_action = medium_dec
                    recommended_confidence = medium_term.confidence
                recommendation_notes = f"跟随置信度更高的周期"
        
        elif is_aligned:
            # 一致
            if alignment_type == AlignmentType.BOTH_LONG:
                recommended_action = Decision.LONG
                recommended_confidence = max(short_term.confidence, medium_term.confidence, key=lambda c: self._confidence_level(c))
                recommendation_notes = "✅ 双周期一致看多，信号强度高"
            elif alignment_type == AlignmentType.BOTH_SHORT:
                recommended_action = Decision.SHORT
                recommended_confidence = max(short_term.confidence, medium_term.confidence, key=lambda c: self._confidence_level(c))
                recommendation_notes = "✅ 双周期一致看空，信号强度高"
            else:
                recommended_action = Decision.NO_TRADE
                recommendation_notes = "双周期一致无交易机会"
        
        else:
            # 部分一致（一方有信号，一方无）
            if short_dec in [Decision.LONG, Decision.SHORT]:
                recommended_action = short_dec
                recommended_confidence = Confidence.LOW  # 降级置信度
                recommendation_notes = f"⚠️ 仅短期有{short_dec.value.upper()}信号，中长期未确认，谨慎操作"
            elif medium_dec in [Decision.LONG, Decision.SHORT]:
                recommended_action = medium_dec
                recommended_confidence = medium_term.confidence
                recommendation_notes = f"中长期{medium_dec.value.upper()}信号，短期暂无确认"
        
        return AlignmentAnalysis(
            is_aligned=is_aligned,
            alignment_type=alignment_type,
            has_conflict=has_conflict,
            conflict_resolution=conflict_resolution,
            resolution_reason=resolution_reason,
            recommended_action=recommended_action,
            recommended_confidence=recommended_confidence,
            recommendation_notes=recommendation_notes
        )
    
    def _build_dual_no_trade_result(
        self,
        symbol: str,
        global_risk_tags: List[ReasonTag],
        regime: MarketRegime = MarketRegime.RANGE,
        risk_allowed: bool = True,
        price: Optional[float] = None  # PATCH-P0-3: 支持传入price
    ) -> 'DualTimeframeResult':
        """
        构造双周期NO_TRADE结果（用于全局风险拒绝等场景）
        
        即使在NO_TRADE场景，也包含动态阈值元数据，便于前端显示和回测分析。
        """
        from models.dual_timeframe_result import (
            DualTimeframeResult, TimeframeConclusion, AlignmentAnalysis
        )
        from models.enums import Timeframe, AlignmentType
        
        # ===== P0: 计算动态阈值元数据（即使NO_TRADE也需要） =====
        short_config = self.config.get('dual_timeframe', {}).get('short_term', {})
        price_change_config = short_config.get('min_price_change_15m', {})
        
        if isinstance(price_change_config, dict) and price_change_config.get('dynamic', False):
            if regime == MarketRegime.TREND:
                threshold_value = price_change_config.get('trend', 0.003)
                threshold_regime = 'trend'
            elif regime == MarketRegime.RANGE:
                threshold_value = price_change_config.get('range', 0.008)
                threshold_regime = 'range'
            elif regime == MarketRegime.EXTREME:
                threshold_value = price_change_config.get('extreme', 0.015)
                threshold_regime = 'extreme'
            else:
                threshold_value = price_change_config.get('default', 0.005)
                threshold_regime = 'default'
        else:
            threshold_value = price_change_config if isinstance(price_change_config, (int, float)) else 0.003
            threshold_regime = 'fixed'
        
        # 短期NO_TRADE（含动态阈值元数据）
        short_term = TimeframeConclusion(
            timeframe=Timeframe.SHORT_TERM,
            timeframe_label="5m/15m",
            decision=Decision.NO_TRADE,
            confidence=Confidence.LOW,
            market_regime=regime,
            trade_quality=TradeQuality.POOR,
            execution_permission=ExecutionPermission.DENY,
            executable=False,
            reason_tags=global_risk_tags.copy(),
            key_metrics={
                'threshold_min_price_change': threshold_value,
                'threshold_regime': threshold_regime
            }
        )
        
        # 中长期NO_TRADE
        medium_term = TimeframeConclusion(
            timeframe=Timeframe.MEDIUM_TERM,
            timeframe_label="1h/6h",
            decision=Decision.NO_TRADE,
            confidence=Confidence.LOW,
            market_regime=regime,
            trade_quality=TradeQuality.POOR,
            execution_permission=ExecutionPermission.DENY,
            executable=False,
            reason_tags=global_risk_tags.copy(),
            key_metrics={}
        )
        
        # 一致性（都是NO_TRADE）
        alignment = AlignmentAnalysis(
            is_aligned=True,
            alignment_type=AlignmentType.BOTH_NO_TRADE,
            has_conflict=False,
            conflict_resolution=None,
            resolution_reason="全局风险拒绝",
            recommended_action=Decision.NO_TRADE,
            recommended_confidence=Confidence.LOW,
            recommendation_notes="⛔ 全局风险触发，双周期均不可交易"
        )
        
        return DualTimeframeResult(
            short_term=short_term,
            medium_term=medium_term,
            alignment=alignment,
            symbol=symbol,
            timestamp=datetime.now(),
            price=price,  # PATCH-P0-3: 使用传入的price参数
            risk_exposure_allowed=risk_allowed,
            global_risk_tags=global_risk_tags
        )
