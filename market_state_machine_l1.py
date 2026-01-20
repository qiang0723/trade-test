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
        
        # ⚠️ 启动时校验：防止口径回归
        self._validate_decimal_calibration(self.config)
        
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
        
        # ===== Step 7: 决策频率控制（PR-C）=====
        original_decision_for_control = decision
        decision, control_tags = self._apply_decision_control(
            symbol=symbol,
            decision=decision,
            reason_tags=reason_tags,
            timestamp=datetime.now()
        )
        reason_tags.extend(control_tags)
        
        control_blocked = (decision != original_decision_for_control)
        self.last_pipeline_steps.append({
            'step': 7, 'name': 'decision_control',
            'status': 'success' if not control_blocked else 'failed',
            'message': '频率控制通过' if not control_blocked else f'频率控制阻断：{control_tags[0].value if control_tags else ""}',
            'result': 'Allowed' if not control_blocked else 'Blocked'
        })
        
        # ===== Step 8: 计算执行许可级别（方案D）=====
        from models.enums import ExecutionPermission
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
        self._add_auxiliary_tags(data, reason_tags)
        
        result_timestamp = datetime.now()
        
        # ===== Step 10: 构造结果 =====
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
            executable=False  # 先初始化为False
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
        self.decision_memory.update_decision(symbol, decision, result_timestamp)
        
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
        
        # 强信号加分
        strong_signals = [ReasonTag.STRONG_BUY_PRESSURE, ReasonTag.STRONG_SELL_PRESSURE]
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
        
        # 3. reduce_tags上限
        reduce_tags = tag_rules.get('reduce_tags', [])
        tag_caps = caps_config.get('tag_caps', {})
        
        for tag in reason_tags:
            tag_value = tag.value
            if tag_value in reduce_tags or tag_value in tag_caps:
                max_level_str = tag_caps.get(tag_value, 'MEDIUM')
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
        """字符串转Confidence枚举"""
        mapping = {
            'LOW': Confidence.LOW,
            'MEDIUM': Confidence.MEDIUM,
            'HIGH': Confidence.HIGH,
            'ULTRA': Confidence.ULTRA
        }
        return mapping.get(s.upper(), Confidence.MEDIUM)
    
    # ========================================
    # 方案D：执行许可计算
    # ========================================
    
    def _compute_execution_permission(self, reason_tags: List[ReasonTag]) -> 'ExecutionPermission':
        """
        计算执行许可级别（方案D：三级执行许可）
        
        映射规则：
        1. 任何 BLOCK 级别标签 → DENY（拒绝执行）
        2. 任何 DEGRADE 级别标签 → ALLOW_REDUCED（降级执行，使用更严格门槛）
        3. 仅 ALLOW 级别标签 → ALLOW（正常执行）
        
        ExecutabilityLevel → ExecutionPermission 映射：
        - BLOCK (EXTREME_VOLUME, ABSORPTION_RISK, ...) → DENY
        - DEGRADE (NOISY_MARKET, WEAK_SIGNAL_IN_RANGE) → ALLOW_REDUCED
        - ALLOW (STRONG_BUY_PRESSURE, OI_GROWING, ...) → ALLOW
        
        Args:
            reason_tags: 原因标签列表
        
        Returns:
            ExecutionPermission: 执行许可级别
        """
        from models.reason_tags import REASON_TAG_EXECUTABILITY, ExecutabilityLevel
        from models.enums import ExecutionPermission
        
        # 优先级1: 检查是否有 BLOCK 级别标签（最高优先级）
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
    
    def _apply_decision_control(
        self, 
        symbol: str, 
        decision: Decision, 
        reason_tags: List[ReasonTag],
        timestamp: datetime
    ) -> Tuple[Decision, List[ReasonTag]]:
        """
        Step 7: 决策频率控制（PR-C）
        
        规则：
        1. 最小决策间隔：防止短时间内重复输出
        2. 翻转冷却：防止方向频繁切换
        
        Args:
            symbol: 币种符号
            decision: 当前决策
            reason_tags: 现有标签列表
            timestamp: 当前时间
        
        Returns:
            (可能被修改的decision, 新增的控制标签列表)
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
                f"[{symbol}] MIN_INTERVAL_BLOCK: elapsed={elapsed:.0f}s < {min_interval}s"
            )
            control_tags.append(ReasonTag.MIN_INTERVAL_BLOCK)
            return Decision.NO_TRADE, control_tags
        
        # 检查2: 翻转冷却
        if enable_flip_cooldown:
            is_flip = (decision == Decision.LONG and last_side == Decision.SHORT) or \
                     (decision == Decision.SHORT and last_side == Decision.LONG)
            
            if is_flip and elapsed < flip_cooldown:
                logger.info(
                    f"[{symbol}] FLIP_COOLDOWN_BLOCK: {last_side.value}→{decision.value}, "
                    f"elapsed={elapsed:.0f}s < {flip_cooldown}s"
                )
                control_tags.append(ReasonTag.FLIP_COOLDOWN_BLOCK)
                return Decision.NO_TRADE, control_tags
        
        # 通过所有检查
        logger.debug(f"[{symbol}] Decision control passed")
        return decision, control_tags
    
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
        from models.enums import ExecutionPermission
        
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
            'state_machine': {
                'cool_down_minutes': 60,
                'signal_timeout_minutes': 30
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
