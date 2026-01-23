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

# PR-ARCH-03: 强类型配置编译器
from l1_engine.threshold_compiler import ThresholdCompiler, ConfigValidationError
from models.thresholds import Thresholds

# PR-ARCH-01: 特征生成管道
from l1_engine.feature_builder import FeatureBuilder, build_features_from_cache
from models.feature_snapshot import FeatureSnapshot

# PR-DUAL: 类型检查导入（避免循环导入）
if TYPE_CHECKING:
    from models.dual_timeframe_result import (
        DualTimeframeResult, TimeframeConclusion, AlignmentAnalysis
    )

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



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
        初始化L1引擎 (PR-ARCH-03增强：集成ThresholdCompiler)
        
        Args:
            config_path: 配置文件路径，默认为 config/l1_thresholds.yaml
        """
        # 加载配置
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'config', 'l1_thresholds.yaml')
        
        # PR-ARCH-03: 编译配置为强类型对象
        try:
            compiler = ThresholdCompiler()
            self.thresholds_typed = compiler.compile(config_path)
            logger.info(f"✅ Thresholds compiled (version: {self.thresholds_typed.version[:16]}...)")
        except ConfigValidationError as e:
            logger.error(f"❌ Config validation failed: {e}")
            raise
        
        # 向后兼容：保留旧的config字典（渐进式迁移）
        self.config = self._load_config(config_path)
        
        # ⚠️ 启动时校验：防止配置错误（P1-3, PR-H）
        self._validate_decimal_calibration(self.config)        # 1. 口径校验：百分比必须用小数
        self._validate_threshold_consistency(self.config)      # 2. 门槛一致性校验（P1-3）
        self._validate_reason_tag_spelling(self.config)        # 3. ReasonTag拼写校验（P1-3）
        self._validate_confidence_values(self.config)          # 4. Confidence值拼写校验（PR-H）
        
        # 旧阈值字典（向后兼容）
        self.thresholds = self._flatten_thresholds(self.config)
        
        # 状态机状态
        self.current_state = SystemState.INIT
        self.state_enter_time = datetime.now()
        
        # 历史数据（用于计算指标如资金费率波动）
        self.history_data = {}
        
        # 管道执行记录（用于可视化）
        self.last_pipeline_steps = []
        
        # PR-ARCH-01: 特征生成器
        self.feature_builder = FeatureBuilder(enable_trace=False)  # 线上环境关闭trace
        
        # PR-ARCH-02: DecisionCore（纯函数）+ DecisionGate（频控）
        from l1_engine.decision_core import DecisionCore
        from l1_engine.decision_gate import DecisionGate
        from l1_engine.state_store import create_state_store
        
        self.decision_core = DecisionCore  # 纯静态方法类，无需实例化
        self.decision_gate = DecisionGate(
            state_store=create_state_store("dual")  # 双周期独立频控
        )
        logger.info("✅ PR-ARCH-02: DecisionCore and DecisionGate initialized")
        
        logger.info(f"L1AdvisoryEngine initialized with {len(self.thresholds)} thresholds")
    
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
        
        PR-ARCH-03改进：
        - 使用强类型配置 thresholds_typed.market_regime.xxx
        
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
        
        # PR-ARCH-03: 使用强类型配置
        regime_thresholds = self.thresholds_typed.market_regime
        
        # 1. EXTREME: 极端波动（优先级最高）
        if price_change_1h is not None:
            price_change_1h_abs = abs(price_change_1h)
            if price_change_1h_abs > regime_thresholds.extreme_price_change_1h:
                return MarketRegime.EXTREME, regime_tags
        
        # 2. TREND: 趋势市
        # 2.1 中期趋势（6小时）
        if price_change_6h is not None:
            price_change_6h_abs = abs(price_change_6h)
            if price_change_6h_abs > regime_thresholds.trend_price_change_6h:
                return MarketRegime.TREND, regime_tags
        elif price_change_15m is not None:
            # PATCH-P0-02: 缺6h时使用15m退化判定（更保守阈值）
            price_change_15m_abs = abs(price_change_15m)
            fallback_threshold = regime_thresholds.trend_price_change_6h * 0.5  # 15m用更低阈值
            if price_change_15m_abs > fallback_threshold:
                regime_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)  # 标记退化
                logger.debug("Regime detection using 15m fallback (6h missing)")
                return MarketRegime.TREND, regime_tags
        
        # 2.2 短期趋势（1小时）- 方案1: 捕获短期机会
        if price_change_1h is not None:
            price_change_1h_abs = abs(price_change_1h)
            if price_change_1h_abs > regime_thresholds.short_term_trend_1h:
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
        
        PR-ARCH-03改进：
        - 使用强类型配置 thresholds_typed.risk_exposure.xxx
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (是否允许风险敞口, 原因标签列表)
        """
        tags = []
        
        # PR-ARCH-03: 使用强类型配置
        risk_thresholds = self.thresholds_typed.risk_exposure
        
        # 1. 极端行情
        if regime == MarketRegime.EXTREME:
            tags.append(ReasonTag.EXTREME_REGIME)
            return False, tags
        
        # 2. 清算阶段（PATCH-P0-02: None-safe）
        price_change_1h = self._num(data, 'price_change_1h')
        oi_change_1h = self._num(data, 'oi_change_1h')
        
        if price_change_1h is not None and oi_change_1h is not None:
            if (abs(price_change_1h) > risk_thresholds.liquidation.price_change and 
                oi_change_1h < risk_thresholds.liquidation.oi_drop):
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
            if (funding_rate_abs > risk_thresholds.crowding.funding_abs and 
                oi_change_6h > risk_thresholds.crowding.oi_growth):
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
            if volume_1h > volume_avg * risk_thresholds.extreme_volume.multiplier:
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
        
        PR-ARCH-03改进：
        - 使用强类型配置 thresholds_typed.trade_quality.xxx
        
        Args:
            data: 市场数据
            regime: 市场环境
        
        Returns:
            (交易质量, 原因标签列表)
        """
        tags = []
        
        # PR-ARCH-03: 使用强类型配置
        quality_thresholds = self.thresholds_typed.trade_quality
        
        # 1. 吸纳风险（PATCH-P0-02: None-safe）
        imbalance_value = self._num(data, 'taker_imbalance_1h')
        volume_1h = self._num(data, 'volume_1h')
        volume_24h = self._num(data, 'volume_24h')
        
        if imbalance_value is not None and volume_1h is not None and volume_24h is not None and volume_24h > 0:
            imbalance_abs = abs(imbalance_value)
            volume_avg = volume_24h / 24
            if (imbalance_abs > quality_thresholds.absorption.imbalance and 
                volume_1h < volume_avg * quality_thresholds.absorption.volume_ratio):
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
            
            if (funding_volatility > quality_thresholds.noise.funding_volatility and 
                abs(funding_rate) < quality_thresholds.noise.funding_abs):
                tags.append(ReasonTag.NOISY_MARKET)
                return TradeQuality.UNCERTAIN, tags
        else:
            logger.debug(f"[{symbol}] Noise check skipped (funding_rate missing)")
        
        # 3. 轮动风险（PATCH-P0-02: None-safe）
        price_change_1h = self._num(data, 'price_change_1h')
        oi_change_1h = self._num(data, 'oi_change_1h')
        
        if price_change_1h is not None and oi_change_1h is not None:
            if ((price_change_1h > quality_thresholds.rotation.price_threshold and 
                 oi_change_1h < -quality_thresholds.rotation.oi_threshold) or
                (price_change_1h < -quality_thresholds.rotation.price_threshold and 
                 oi_change_1h > quality_thresholds.rotation.oi_threshold)):
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
                if (imbalance_abs < quality_thresholds.range_weak.imbalance and 
                    oi_change_1h_abs < quality_thresholds.range_weak.oi):
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
        
        logger.info(f"[{symbol}] Starting dual-timeframe L1 decision pipeline (NEW ARCH)")
        
        # ===== PR-ARCH-02: 新架构（已稳定运行，老架构已删除）=====
        # 调用新架构主流程
        result = self._on_new_tick_dual_new_arch(symbol, data)
        logger.info(f"[{symbol}] ✅ NEW ARCH result: {result.alignment.recommended_action.value}")
        return result
    
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
    
    # ========================================
    # PR-ARCH-02: 新架构主流程
    # ========================================
    
    def _on_new_tick_dual_new_arch(
        self,
        symbol: str,
        data: Dict
    ) -> 'DualTimeframeResult':
        """
        双周期决策主流程（新架构）
        
        PR-ARCH-02: 使用DecisionCore + DecisionGate的新架构
        
        流程：
        1. FeatureBuilder生成特征（PR-ARCH-01）
        2. DecisionCore评估决策（纯函数）
        3. DecisionGate应用频控（独立频控）
        4. 转换为DualTimeframeResult（向后兼容）
        
        Args:
            symbol: 交易对符号
            data: 市场数据字典
        
        Returns:
            DualTimeframeResult: 双周期决策结果
        """
        from data_cache import get_cache
        
        logger.info(f"[{symbol}] Starting NEW ARCH dual-timeframe pipeline")
        
        # ===== Step 1: 特征生成（PR-ARCH-01）=====
        try:
            data_cache = get_cache()
            feature_snapshot = self.feature_builder.build(symbol, data, data_cache=data_cache)
            logger.debug(f"[{symbol}] FeatureSnapshot built (version: {feature_snapshot.metadata.feature_version.value})")
        except Exception as e:
            logger.error(f"[{symbol}] FeatureBuilder failed: {e}")
            # Fallback：如果特征生成失败，返回NO_TRADE
            from models.reason_tags import ReasonTag
            return self._build_dual_no_trade_result(
                symbol, 
                [ReasonTag.INVALID_DATA],
                price=data.get('price')
            )
        
        # ===== Step 2: DecisionCore评估（纯函数）=====
        try:
            # 使用DecisionCore.evaluate_dual进行双周期评估
            draft = self.decision_core.evaluate_dual(
                feature_snapshot,
                self.thresholds_typed,
                symbol
            )
            logger.debug(
                f"[{symbol}] DecisionCore evaluated: "
                f"short={draft.short_term.decision.value}, "
                f"medium={draft.medium_term.decision.value}"
            )
        except Exception as e:
            logger.error(f"[{symbol}] DecisionCore failed: {e}")
            # Fallback：如果决策评估失败，返回NO_TRADE
            from models.reason_tags import ReasonTag
            return self._build_dual_no_trade_result(
                symbol,
                [ReasonTag.INVALID_DATA],
                price=feature_snapshot.features.price.current_price if feature_snapshot.features.price else None
            )
        
        # ===== Step 3: DecisionGate应用（频控）=====
        try:
            final = self.decision_gate.apply_dual(
                draft,
                symbol,
                datetime.now(),
                self.thresholds_typed
            )
            logger.debug(
                f"[{symbol}] DecisionGate applied: "
                f"short_exec={final.short_term.executable}, "
                f"medium_exec={final.medium_term.executable}"
            )
        except Exception as e:
            logger.error(f"[{symbol}] DecisionGate failed: {e}")
            # Fallback：如果频控失败，返回NO_TRADE
            from models.reason_tags import ReasonTag
            return self._build_dual_no_trade_result(
                symbol,
                [ReasonTag.INVALID_DATA],
                price=feature_snapshot.features.price.current_price if feature_snapshot.features.price else None
            )
        
        # ===== Step 4: 转换为DualTimeframeResult（向后兼容）=====
        try:
            result = self._convert_final_to_result(final, symbol, feature_snapshot)
            logger.info(f"[{symbol}] NEW ARCH result: {result.alignment.recommended_action.value}")
            return result
        except Exception as e:
            logger.error(f"[{symbol}] Result conversion failed: {e}")
            # Fallback：如果转换失败，返回NO_TRADE
            from models.reason_tags import ReasonTag
            return self._build_dual_no_trade_result(
                symbol,
                [ReasonTag.INVALID_DATA],
                price=feature_snapshot.features.price.current_price if feature_snapshot.features.price else None
            )
    
    # ========================================
    # PR-ARCH-02: 新架构转换方法
    # ========================================
    
    def _convert_final_to_result(
        self,
        final: 'DualTimeframeDecisionFinal',
        symbol: str,
        features: 'FeatureSnapshot'
    ) -> 'DualTimeframeResult':
        """
        将DualTimeframeDecisionFinal转换为DualTimeframeResult（向后兼容）
        
        PR-ARCH-02: 新架构核心转换方法
        
        Args:
            final: DecisionGate输出的最终决策
            symbol: 交易对符号
            features: 特征快照（用于提取price等元信息）
        
        Returns:
            DualTimeframeResult: 向后兼容的结果对象
        """
        from models.dual_timeframe_result import (
            DualTimeframeResult, TimeframeConclusion, AlignmentAnalysis
        )
        from models.enums import Timeframe
        
        logger.debug(f"[{symbol}] Converting DualTimeframeDecisionFinal to DualTimeframeResult")
        
        # 构建短期TimeframeConclusion
        short_conclusion = TimeframeConclusion(
            timeframe=Timeframe.SHORT_TERM,
            timeframe_label="5m/15m",
            decision=final.short_term.decision,
            confidence=final.short_term.confidence,
            executable=final.short_term.executable,
            execution_permission=final.short_term.execution_permission,
            trade_quality=final.short_term.trade_quality,
            market_regime=final.short_term.market_regime,
            reason_tags=final.short_term.reason_tags.copy(),
            key_metrics=final.short_term.key_metrics.copy() if final.short_term.key_metrics else {}
        )
        
        # 构建中期TimeframeConclusion
        medium_conclusion = TimeframeConclusion(
            timeframe=Timeframe.MEDIUM_TERM,
            timeframe_label="1h/6h",
            decision=final.medium_term.decision,
            confidence=final.medium_term.confidence,
            executable=final.medium_term.executable,
            execution_permission=final.medium_term.execution_permission,
            trade_quality=final.medium_term.trade_quality,
            market_regime=final.medium_term.market_regime,
            reason_tags=final.medium_term.reason_tags.copy(),
            key_metrics=final.medium_term.key_metrics.copy() if final.medium_term.key_metrics else {}
        )
        
        # 构建AlignmentAnalysis
        alignment = self._analyze_alignment_from_final(short_conclusion, medium_conclusion)
        
        # 提取price（优先使用features中的current_price）
        price = None
        if features and features.features and features.features.price:
            price = features.features.price.current_price
        
        # 构建DualTimeframeResult
        return DualTimeframeResult(
            symbol=symbol,
            timestamp=datetime.now(),
            short_term=short_conclusion,
            medium_term=medium_conclusion,
            alignment=alignment,
            price=price,
            risk_exposure_allowed=True,  # 新架构中风险评估已在DecisionCore中完成
            global_risk_tags=final.global_risk_tags.copy()
        )
    
    def _analyze_alignment_from_final(
        self,
        short: 'TimeframeConclusion',
        medium: 'TimeframeConclusion'
    ) -> 'AlignmentAnalysis':
        """
        从两个TimeframeConclusion分析对齐关系
        
        PR-ARCH-02: 简化版本的对齐分析（基于决策方向）
        
        规则：
        1. 都是NO_TRADE → BOTH_NO_TRADE（一致）
        2. 方向相同（LONG/SHORT） → ALIGNED_SIGNAL（一致）
        3. 一个NO_TRADE，一个有信号 → PARTIALLY_ALIGNED（部分一致）
        4. 方向相反（LONG vs SHORT） → CONFLICTING（冲突）
        
        TODO: 实现完整的对齐分析逻辑（考虑confidence、executable等）
        
        Args:
            short: 短期结论
            medium: 中期结论
        
        Returns:
            AlignmentAnalysis: 对齐分析结果
        """
        from models.dual_timeframe_result import AlignmentAnalysis
        from models.enums import AlignmentType, ConflictResolution
        
        # Rule 1: 都是NO_TRADE
        if short.decision == Decision.NO_TRADE and medium.decision == Decision.NO_TRADE:
            return AlignmentAnalysis(
                is_aligned=True,
                alignment_type=AlignmentType.BOTH_NO_TRADE,
                has_conflict=False,
                conflict_resolution=None,
                resolution_reason="短期和中期均无交易信号",
                recommended_action=Decision.NO_TRADE,
                recommended_confidence=Confidence.LOW,
                recommendation_notes="⏸️ 双周期均无交易机会"
            )
        
        # Rule 2: 方向相同（LONG/SHORT）
        if short.decision == medium.decision and short.decision != Decision.NO_TRADE:
            return AlignmentAnalysis(
                is_aligned=True,
                alignment_type=AlignmentType.ALIGNED_SIGNAL,
                has_conflict=False,
                conflict_resolution=None,
                resolution_reason="短期和中期方向一致",
                recommended_action=short.decision,
                recommended_confidence=max(short.confidence, medium.confidence),
                recommendation_notes=f"✅ 双周期一致：{short.decision.value.upper()}"
            )
        
        # Rule 3: 一个NO_TRADE，一个有信号
        if (short.decision == Decision.NO_TRADE and medium.decision != Decision.NO_TRADE) or \
           (short.decision != Decision.NO_TRADE and medium.decision == Decision.NO_TRADE):
            active_decision = medium.decision if short.decision == Decision.NO_TRADE else short.decision
            active_timeframe = "中期" if short.decision == Decision.NO_TRADE else "短期"
            
            return AlignmentAnalysis(
                is_aligned=False,
                alignment_type=AlignmentType.PARTIALLY_ALIGNED,
                has_conflict=False,
                conflict_resolution=ConflictResolution.PREFER_MEDIUM_TERM if active_decision == medium.decision else ConflictResolution.PREFER_SHORT_TERM,
                resolution_reason=f"只有{active_timeframe}有信号",
                recommended_action=active_decision,
                recommended_confidence=Confidence.LOW,
                recommendation_notes=f"⚠️  仅{active_timeframe}：{active_decision.value.upper()}"
            )
        
        # Rule 4: 方向相反（LONG vs SHORT）
        return AlignmentAnalysis(
            is_aligned=False,
            alignment_type=AlignmentType.CONFLICTING,
            has_conflict=True,
            conflict_resolution=ConflictResolution.PREFER_MEDIUM_TERM,
            resolution_reason="短期和中期方向冲突，优先中期",
            recommended_action=medium.decision,
            recommended_confidence=Confidence.LOW,
            recommendation_notes=f"⚠️  周期冲突：短期{short.decision.value} vs 中期{medium.decision.value}"
        )
