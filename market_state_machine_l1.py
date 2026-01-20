"""
L1 Advisory Layer - 核心决策引擎

这是L1决策层的核心实现，负责：
1. 固化8步决策管道
2. 风险准入评估（第一道闸门）
3. 交易质量评估（第二道闸门）
4. 方向判断（资金费率降级）
5. 置信度计算（工程化）
6. 输出标准化AdvisoryResult

不包含：
- 执行逻辑
- 仓位管理
- 止损止盈
- 订单下达
"""

import yaml
import os
from typing import Dict, Tuple, List, Optional
from datetime import datetime, timedelta
from models.enums import Decision, Confidence, TradeQuality, MarketRegime, SystemState
from models.advisory_result import AdvisoryResult
from models.reason_tags import ReasonTag
from metrics_normalizer import normalize_metrics
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class L1AdvisoryEngine:
    """
    L1 决策层核心引擎
    
    职责:
    - 单币种方向决策 (LONG/SHORT/NO_TRADE)
    - 固化8步决策管道
    - 输出标准化 AdvisoryResult
    
    不做:
    - 不涉及执行逻辑
    - 不输出仓位/入场点/止损止盈
    - 不管理订单
    """
    
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
        self.thresholds = self._flatten_thresholds(self.config)
        
        # 状态机状态
        self.current_state = SystemState.INIT
        self.state_enter_time = datetime.now()
        
        # 历史数据（用于计算指标如资金费率波动）
        self.history_data = {}
        
        # 管道执行记录（用于可视化）
        self.last_pipeline_steps = []
        
        logger.info(f"L1AdvisoryEngine initialized with {len(self.thresholds)} thresholds")
    
    def on_new_tick(self, symbol: str, data: Dict) -> AdvisoryResult:
        """
        L1决策核心入口 - 固定8步管道
        
        Args:
            symbol: 交易对符号（如 "BTC"）
            data: 市场数据字典，包含：
                - price: 当前价格
                - price_change_1h: 1小时价格变化率(%)
                - price_change_6h: 6小时价格变化率(%)
                - volume_1h: 1小时成交量
                - volume_24h: 24小时成交量
                - buy_sell_imbalance: 买卖失衡度 (-1到1)
                - funding_rate: 资金费率（小数，如0.0001表示0.01%）
                - oi_change_1h: 1小时持仓量变化率(%)
                - oi_change_6h: 6小时持仓量变化率(%)
        
        Returns:
            AdvisoryResult: 标准化决策结果
        """
        reason_tags = []
        
        # 清空上次管道记录
        self.last_pipeline_steps = []
        
        logger.info(f"[{symbol}] Starting L1 decision pipeline")
        
        # ===== Step 1: 数据验证 + 指标规范化 + 新鲜度检查 =====
        is_valid, normalized_data, fail_tag = self._validate_data(data)
        if not is_valid:
            fail_reason = fail_tag.value if fail_tag else 'unknown'
            logger.warning(f"[{symbol}] Data validation failed: {fail_reason}")
            self.last_pipeline_steps.append({
                'step': 1, 'name': 'validate_data', 'status': 'failed',
                'message': f'数据验证失败：{fail_reason}', 'result': None
            })
            return self._build_no_trade_result(
                reason_tags=[fail_tag] if fail_tag else [ReasonTag.INVALID_DATA],
                regime=MarketRegime.RANGE,
                risk_allowed=False,
                quality=TradeQuality.POOR
            )
        
        # 使用规范化后的数据（后续所有步骤都用这个）
        data = normalized_data
        
        self.last_pipeline_steps.append({
            'step': 1, 'name': 'validate_data', 'status': 'success',
            'message': '数据验证通过（含规范化+新鲜度检查）', 'result': 'Valid'
        })
        
        # ===== Step 2: 市场环境识别 =====
        regime = self._detect_market_regime(data)
        logger.info(f"[{symbol}] Market regime: {regime.value}")
        
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
                quality=TradeQuality.POOR
            )
        
        # ===== Step 4: 交易质量评估（第二道闸门）=====
        quality, quality_tags = self._eval_trade_quality(data, regime)
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
                quality=TradeQuality.POOR
            )
        
        # ===== Step 5: 方向评估（SHORT优先）=====
        allow_short = self._eval_short_direction(data, regime)
        allow_long = self._eval_long_direction(data, regime)
        
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
        
        # ===== Step 7: 状态机约束检查 =====
        original_decision = decision
        decision, state_tags = self._check_state_transition(decision)
        reason_tags.extend(state_tags)
        
        self.last_pipeline_steps.append({
            'step': 7, 'name': 'check_transition',
            'status': 'success' if decision == original_decision else 'failed',
            'message': '状态转换检查通过' if decision == original_decision else '状态转换被拒绝',
            'result': 'Allowed' if decision == original_decision else 'Denied'
        })
        
        # ===== Step 8: 构造结果 =====
        confidence = self._compute_confidence(decision, regime, quality, reason_tags)
        
        self.last_pipeline_steps.append({
            'step': 8, 'name': 'compute_confidence',
            'status': 'success',
            'message': f"置信度: {confidence.value.upper()}",
            'result': confidence.value
        })
        
        # 更新状态机
        self._update_state(decision)
        
        # 添加辅助标签（资金费率、持仓量变化）
        self._add_auxiliary_tags(data, reason_tags)
        
        result = AdvisoryResult(
            decision=decision,
            confidence=confidence,
            market_regime=regime,
            system_state=self.current_state,
            risk_exposure_allowed=True,
            trade_quality=quality,
            reason_tags=reason_tags,
            timestamp=datetime.now(),
            executable=False  # 先初始化为False
        )
        
        # 计算executable标志位（P2）
        result.executable = result.compute_executable()
        
        logger.info(f"[{symbol}] Decision: {result}")
        
        return result
    
    # ========================================
    # Step 1: 数据验证
    # ========================================
    
    def _validate_data(self, data: Dict) -> Tuple[bool, Dict, Optional[ReasonTag]]:
        """
        验证输入数据的完整性和有效性
        
        包含：
        1. 必需字段检查
        2. 指标口径规范化（百分比统一为小数格式）
        3. 异常尺度检测（防止混用）
        4. 数据新鲜度检查（PR-002）
        
        Args:
            data: 市场数据字典
        
        Returns:
            (是否有效, 规范化后的数据, 失败原因tag)
        """
        required_fields = [
            'price', 'price_change_1h', 'volume_1h', 'volume_24h',
            'buy_sell_imbalance', 'funding_rate', 'oi_change_1h'
        ]
        
        # 检查必需字段
        for field in required_fields:
            if field not in data or data[field] is None:
                logger.error(f"Missing required field: {field}")
                return False, data, ReasonTag.INVALID_DATA
        
        # 数据新鲜度检查（PR-002）
        if 'timestamp' in data or 'source_timestamp' in data:
            data_time = data.get('source_timestamp') or data.get('timestamp')
            if data_time is not None:
                # 计算数据年龄
                if isinstance(data_time, str):
                    data_time = datetime.fromisoformat(data_time)
                
                staleness_seconds = (datetime.now() - data_time).total_seconds()
                max_staleness = self.thresholds.get('data_max_staleness_seconds', 120)
                
                if staleness_seconds > max_staleness:
                    logger.warning(
                        f"Data is stale: {staleness_seconds:.1f}s old "
                        f"(max: {max_staleness}s)"
                    )
                    return False, data, ReasonTag.DATA_STALE
        
        # 指标口径规范化（PR-001）
        normalized_data, is_valid, error_msg = normalize_metrics(data)
        if not is_valid:
            logger.error(f"Metrics normalization failed: {error_msg}")
            return False, data, ReasonTag.INVALID_DATA
        
        # 基础异常值检查
        if normalized_data['buy_sell_imbalance'] < -1 or normalized_data['buy_sell_imbalance'] > 1:
            logger.error(f"Invalid buy_sell_imbalance: {normalized_data['buy_sell_imbalance']}")
            return False, normalized_data, ReasonTag.INVALID_DATA
        
        if normalized_data['price'] <= 0:
            logger.error(f"Invalid price: {normalized_data['price']}")
            return False, normalized_data, ReasonTag.INVALID_DATA
        
        return True, normalized_data, None
    
    # ========================================
    # Step 2: 市场环境识别
    # ========================================
    
    def _detect_market_regime(self, data: Dict) -> MarketRegime:
        """
        识别市场环境：TREND（趋势）/ RANGE（震荡）/ EXTREME（极端）
        
        Args:
            data: 市场数据
        
        Returns:
            MarketRegime: 市场环境类型
        """
        price_change_1h = abs(data.get('price_change_1h', 0))
        price_change_6h = abs(data.get('price_change_6h', 0))
        
        # EXTREME: 极端波动
        if price_change_1h > self.thresholds['extreme_price_change_1h']:
            return MarketRegime.EXTREME
        
        # TREND: 趋势市（持续单边）
        if price_change_6h > self.thresholds['trend_price_change_6h']:
            return MarketRegime.TREND
        
        # RANGE: 震荡市（默认）
        return MarketRegime.RANGE
    
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
        
        # 2. 清算阶段
        price_change_1h = data.get('price_change_1h', 0)
        oi_change_1h = data.get('oi_change_1h', 0)
        
        if (abs(price_change_1h) > self.thresholds['liquidation_price_change'] and 
            oi_change_1h < self.thresholds['liquidation_oi_drop']):
            tags.append(ReasonTag.LIQUIDATION_PHASE)
            return False, tags
        
        # 3. 拥挤风险
        funding_rate = abs(data.get('funding_rate', 0))
        oi_change_6h = data.get('oi_change_6h', 0)
        
        if (funding_rate > self.thresholds['crowding_funding_abs'] and 
            oi_change_6h > self.thresholds['crowding_oi_growth']):
            tags.append(ReasonTag.CROWDING_RISK)
            return False, tags
        
        # 4. 极端成交量
        volume_1h = data.get('volume_1h', 0)
        volume_avg = data.get('volume_24h', 0) / 24
        
        if volume_avg > 0 and volume_1h > volume_avg * self.thresholds['extreme_volume_multiplier']:
            tags.append(ReasonTag.EXTREME_VOLUME)
            return False, tags
        
        # 通过所有风险检查
        return True, []
    
    # ========================================
    # Step 4: 交易质量评估（第二道闸门）
    # ========================================
    
    def _eval_trade_quality(
        self, 
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
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (交易质量, 原因标签列表)
        """
        tags = []
        
        # 1. 吸纳风险
        imbalance = abs(data.get('buy_sell_imbalance', 0))
        volume_1h = data.get('volume_1h', 0)
        volume_avg = data.get('volume_24h', 0) / 24
        
        if (volume_avg > 0 and 
            imbalance > self.thresholds['absorption_imbalance'] and 
            volume_1h < volume_avg * self.thresholds['absorption_volume_ratio']):
            tags.append(ReasonTag.ABSORPTION_RISK)
            return TradeQuality.POOR, tags
        
        # 2. 噪音市（需要历史数据）- PR-004: 返回UNCERTAIN而非POOR
        funding_rate = data.get('funding_rate', 0)
        funding_rate_prev = self.history_data.get('funding_rate_prev', funding_rate)
        funding_volatility = abs(funding_rate - funding_rate_prev)
        
        if (funding_volatility > self.thresholds['noisy_funding_volatility'] and 
            abs(funding_rate) < self.thresholds['noisy_funding_abs']):
            tags.append(ReasonTag.NOISY_MARKET)
            # PR-004: 噪声市场 → UNCERTAIN（不确定性），而非POOR（明确风险）
            return TradeQuality.UNCERTAIN, tags
        
        # 保存当前数据供下次使用
        self.history_data['funding_rate_prev'] = funding_rate
        
        # 3. 轮动风险
        price_change_1h = data.get('price_change_1h', 0)
        oi_change_1h = data.get('oi_change_1h', 0)
        
        if ((price_change_1h > self.thresholds['rotation_price_threshold'] and 
             oi_change_1h < -self.thresholds['rotation_oi_threshold']) or
            (price_change_1h < -self.thresholds['rotation_price_threshold'] and 
             oi_change_1h > self.thresholds['rotation_oi_threshold'])):
            tags.append(ReasonTag.ROTATION_RISK)
            return TradeQuality.POOR, tags
        
        # 4. 震荡市弱信号
        if regime == MarketRegime.RANGE:
            if (imbalance < self.thresholds['range_weak_imbalance'] and 
                abs(oi_change_1h) < self.thresholds['range_weak_oi']):
                tags.append(ReasonTag.WEAK_SIGNAL_IN_RANGE)
                return TradeQuality.POOR, tags
        
        # 通过所有质量检查
        return TradeQuality.GOOD, []
    
    # ========================================
    # Step 5: 方向评估
    # ========================================
    
    def _eval_long_direction(self, data: Dict, regime: MarketRegime) -> bool:
        """
        做多方向评估（资金费率不再作为主要触发条件）
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            bool: 是否允许做多
        """
        imbalance = data.get('buy_sell_imbalance', 0)
        oi_change = data.get('oi_change_1h', 0)
        price_change = data.get('price_change_1h', 0)
        
        if regime == MarketRegime.TREND:
            # 趋势市：多方强势
            if (imbalance > self.thresholds['long_imbalance_trend'] and 
                oi_change > self.thresholds['long_oi_change_trend'] and 
                price_change > self.thresholds['long_price_change_trend']):
                return True
        
        elif regime == MarketRegime.RANGE:
            # 震荡市：需要更强信号
            if (imbalance > self.thresholds['long_imbalance_range'] and 
                oi_change > self.thresholds['long_oi_change_range']):
                return True
        
        return False
    
    def _eval_short_direction(self, data: Dict, regime: MarketRegime) -> bool:
        """
        做空方向评估（资金费率不再作为主要触发条件）
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            bool: 是否允许做空
        """
        imbalance = data.get('buy_sell_imbalance', 0)
        oi_change = data.get('oi_change_1h', 0)
        price_change = data.get('price_change_1h', 0)
        
        if regime == MarketRegime.TREND:
            # 趋势市：空方强势
            if (imbalance < -self.thresholds['short_imbalance_trend'] and 
                oi_change > self.thresholds['short_oi_change_trend'] and 
                price_change < -self.thresholds['short_price_change_trend']):
                return True
        
        elif regime == MarketRegime.RANGE:
            # 震荡市：需要更强信号
            if (imbalance < -self.thresholds['short_imbalance_range'] and 
                oi_change > self.thresholds['short_oi_change_range']):
                return True
        
        return False
    
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
        if allow_short:
            tags.append(ReasonTag.STRONG_SELL_PRESSURE)
            return Decision.SHORT, tags
        
        # LONG
        if allow_long:
            tags.append(ReasonTag.STRONG_BUY_PRESSURE)
            return Decision.LONG, tags
        
        return Decision.NO_TRADE, tags
    
    # ========================================
    # Step 7: 状态机约束
    # ========================================
    
    def _check_state_transition(
        self, 
        decision: Decision
    ) -> Tuple[Decision, List[ReasonTag]]:
        """
        状态机约束检查
        
        规则：
        - COOL_DOWN期间不允许新信号
        
        Args:
            decision: 待检查的决策
        
        Returns:
            (最终决策, 原因标签列表)
        """
        tags = []
        
        # COOL_DOWN期间不允许新信号
        if self.current_state == SystemState.COOL_DOWN:
            if decision in [Decision.LONG, Decision.SHORT]:
                cool_down_minutes = self.config.get('state_machine', {}).get('cool_down_minutes', 60)
                elapsed = (datetime.now() - self.state_enter_time).total_seconds() / 60
                
                if elapsed < cool_down_minutes:
                    tags.append(ReasonTag.COOL_DOWN_ACTIVE)
                    return Decision.NO_TRADE, tags
        
        return decision, tags
    
    # ========================================
    # Step 8: 置信度计算
    # ========================================
    
    def _compute_confidence(
        self, 
        decision: Decision, 
        regime: MarketRegime, 
        quality: TradeQuality, 
        reason_tags: List[ReasonTag]
    ) -> Confidence:
        """
        置信度计算（PR-005: 升级为4层）
        
        逻辑树规则：
        - ULTRA: TREND + GOOD + 强信号
        - HIGH: TREND + GOOD（无强信号），或 RANGE + GOOD + 强信号
        - MEDIUM: TREND + POOR，或 RANGE + GOOD（无强信号）
        - LOW: 其他情况（RANGE + POOR，EXTREME，NO_TRADE）
        
        评分维度（保留评分体系，但映射到4层）：
        1. 市场环境 (0-3分)
        2. 交易质量 (0-2分)
        3. 系统状态 (0-1分)
        4. 信号强度 (0-2分)
        
        总分8分，映射到ULTRA/HIGH/MEDIUM/LOW
        
        Args:
            decision: 决策
            regime: 市场环境
            quality: 交易质量
            reason_tags: 原因标签列表
        
        Returns:
            Confidence: 置信度
        """
        if decision == Decision.NO_TRADE:
            return Confidence.LOW
        
        score = 0
        
        # 1. 市场环境 (0-3分)
        if regime == MarketRegime.TREND:
            score += 3
        elif regime == MarketRegime.RANGE:
            score += 2
        # EXTREME: 0分（不应该出现在这里）
        
        # 2. 交易质量 (0-2分)
        if quality == TradeQuality.GOOD:
            score += 2
        
        # 3. 系统状态 (0-1分)
        if self.current_state in [SystemState.LONG_ACTIVE, SystemState.SHORT_ACTIVE]:
            score += 1
        
        # 4. 信号强度 (0-2分)
        strong_signals = [ReasonTag.STRONG_BUY_PRESSURE, ReasonTag.STRONG_SELL_PRESSURE]
        has_strong_signal = any(tag in reason_tags for tag in strong_signals)
        if has_strong_signal:
            score += 2
        
        # PR-005: 映射到4层置信度（8分满分）
        if score >= 7:
            # 7-8分：TREND(3) + GOOD(2) + 强信号(2) = 7+
            return Confidence.ULTRA
        elif score >= 5:
            # 5-6分：TREND(3) + GOOD(2) = 5，或 RANGE(2) + GOOD(2) + 强信号(2) = 6
            return Confidence.HIGH
        elif score >= 3:
            # 3-4分：TREND(3) + POOR(0) = 3，或 RANGE(2) + GOOD(2) = 4
            return Confidence.MEDIUM
        else:
            # <3分：其他情况
            return Confidence.LOW
    
    # ========================================
    # 状态机更新
    # ========================================
    
    def _update_state(self, decision: Decision):
        """
        更新状态机
        
        简化版状态转换（完整版需要考虑更多规则）
        
        Args:
            decision: 当前决策
        """
        if decision == Decision.LONG:
            self.current_state = SystemState.LONG_ACTIVE
            self.state_enter_time = datetime.now()
        elif decision == Decision.SHORT:
            self.current_state = SystemState.SHORT_ACTIVE
            self.state_enter_time = datetime.now()
        elif decision == Decision.NO_TRADE:
            if self.current_state in [SystemState.LONG_ACTIVE, SystemState.SHORT_ACTIVE]:
                # 从激活状态转为等待
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
        if abs(funding_rate) > 0.0005:
            if funding_rate > 0:
                reason_tags.append(ReasonTag.HIGH_FUNDING_RATE)
            else:
                reason_tags.append(ReasonTag.LOW_FUNDING_RATE)
        
        # 持仓量变化标签
        oi_change_1h = data.get('oi_change_1h', 0)
        if oi_change_1h > 5.0:
            reason_tags.append(ReasonTag.OI_GROWING)
        elif oi_change_1h < -5.0:
            reason_tags.append(ReasonTag.OI_DECLINING)
    
    def _build_no_trade_result(
        self,
        reason_tags: List[ReasonTag],
        regime: MarketRegime,
        risk_allowed: bool,
        quality: TradeQuality
    ) -> AdvisoryResult:
        """
        构造 NO_TRADE 结果
        
        Args:
            reason_tags: 原因标签列表
            regime: 市场环境
            risk_allowed: 风险是否允许
            quality: 交易质量
        
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
            executable=False
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
        flat['extreme_price_change_1h'] = mr.get('extreme_price_change_1h', 5.0)
        flat['trend_price_change_6h'] = mr.get('trend_price_change_6h', 3.0)
        
        # 风险准入
        re = config.get('risk_exposure', {})
        flat['liquidation_price_change'] = re.get('liquidation', {}).get('price_change', 5.0)
        flat['liquidation_oi_drop'] = re.get('liquidation', {}).get('oi_drop', -15.0)
        flat['crowding_funding_abs'] = re.get('crowding', {}).get('funding_abs', 0.001)
        flat['crowding_oi_growth'] = re.get('crowding', {}).get('oi_growth', 30.0)
        flat['extreme_volume_multiplier'] = re.get('extreme_volume', {}).get('multiplier', 10.0)
        
        # 交易质量
        tq = config.get('trade_quality', {})
        flat['absorption_imbalance'] = tq.get('absorption', {}).get('imbalance', 0.7)
        flat['absorption_volume_ratio'] = tq.get('absorption', {}).get('volume_ratio', 0.5)
        flat['noisy_funding_volatility'] = tq.get('noise', {}).get('funding_volatility', 0.0005)
        flat['noisy_funding_abs'] = tq.get('noise', {}).get('funding_abs', 0.0001)
        flat['rotation_price_threshold'] = tq.get('rotation', {}).get('price_threshold', 2.0)
        flat['rotation_oi_threshold'] = tq.get('rotation', {}).get('oi_threshold', 5.0)
        flat['range_weak_imbalance'] = tq.get('range_weak', {}).get('imbalance', 0.6)
        flat['range_weak_oi'] = tq.get('range_weak', {}).get('oi', 10.0)
        
        # 方向评估
        d = config.get('direction', {})
        flat['long_imbalance_trend'] = d.get('trend', {}).get('long', {}).get('imbalance', 0.6)
        flat['long_oi_change_trend'] = d.get('trend', {}).get('long', {}).get('oi_change', 5.0)
        flat['long_price_change_trend'] = d.get('trend', {}).get('long', {}).get('price_change', 1.0)
        flat['short_imbalance_trend'] = d.get('trend', {}).get('short', {}).get('imbalance', 0.6)
        flat['short_oi_change_trend'] = d.get('trend', {}).get('short', {}).get('oi_change', 5.0)
        flat['short_price_change_trend'] = d.get('trend', {}).get('short', {}).get('price_change', 1.0)
        flat['long_imbalance_range'] = d.get('range', {}).get('long', {}).get('imbalance', 0.7)
        flat['long_oi_change_range'] = d.get('range', {}).get('long', {}).get('oi_change', 10.0)
        flat['short_imbalance_range'] = d.get('range', {}).get('short', {}).get('imbalance', 0.7)
        flat['short_oi_change_range'] = d.get('range', {}).get('short', {}).get('oi_change', 10.0)
        
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
                'extreme_price_change_1h': 5.0,
                'trend_price_change_6h': 3.0
            },
            'risk_exposure': {
                'liquidation': {'price_change': 5.0, 'oi_drop': -15.0},
                'crowding': {'funding_abs': 0.001, 'oi_growth': 30.0},
                'extreme_volume': {'multiplier': 10.0}
            },
            'trade_quality': {
                'absorption': {'imbalance': 0.7, 'volume_ratio': 0.5},
                'noise': {'funding_volatility': 0.0005, 'funding_abs': 0.0001},
                'rotation': {'price_threshold': 2.0, 'oi_threshold': 5.0},
                'range_weak': {'imbalance': 0.6, 'oi': 10.0}
            },
            'direction': {
                'trend': {
                    'long': {'imbalance': 0.6, 'oi_change': 5.0, 'price_change': 1.0},
                    'short': {'imbalance': 0.6, 'oi_change': 5.0, 'price_change': 1.0}
                },
                'range': {
                    'long': {'imbalance': 0.7, 'oi_change': 10.0},
                    'short': {'imbalance': 0.7, 'oi_change': 10.0}
                }
            },
            'state_machine': {
                'cool_down_minutes': 60,
                'signal_timeout_minutes': 30
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
