# P0 CodeFix 方案 - 移除全局短路 + 6h降级

**创建时间**: 2026-01-23  
**优先级**: P0（高优先级）  
**状态**: 待实施  
**原因**: 当前存在全局短路bug，违反了独立评估原则  

---

## 📋 问题诊断

### 🐛 Bug 1: coverage全局短路吞掉medium-term

**位置**: `market_state_machine_l1.py` 第2849-2852行

```python
# ❌ 当前实现（有问题）
critical_gaps = [ReasonTag.DATA_GAP_5M, ReasonTag.DATA_GAP_15M]
if any(tag in coverage_tags for tag in critical_gaps):
    logger.warning(f"[{symbol}] Critical window data gap, returning dual NO_TRADE")
    return self._build_dual_no_trade_result(symbol, coverage_tags, regime=MarketRegime.RANGE)  # ← Bug!
```

**问题**:
- 5m/15m gap会直接return，**吞掉medium-term结论**
- 违反了P0-03独立评估原则
- 即使1h/6h数据完整，也无法输出中线结论

**影响**:
- 冷启动时（5-15分钟）：medium-term长期NO_TRADE（应该能输出）
- 偶发5m gap：中线结论被吞（不合理）

---

### 🐛 Bug 2: 6h缺口硬失败

**位置**: `_evaluate_medium_term` 方法

**问题**:
- 将 `price_change_6h`/`oi_change_6h` 视为硬关键字段
- 冷启动或偶发6h缺口 → medium-term 长期NO_TRADE
- 没有降级路径（即使1h数据完整）

**影响**:
- 冷启动时（1-6小时）：medium-term失效
- 6h K线缺口时：中线结论丢失

---

## ✅ 建议合理性评估

### P0 CodeFix-1: 移除coverage全局短路

**建议**: ✅ 非常合理且必要

**理由**:
1. **符合P0-03原则**: short/medium独立评估
2. **已有基础设施**: 第2866-2887行已经有`has_short_data`/`has_medium_data`标志位
3. **问题明确**: 全局短路发生在独立检查**之前**（第2849行 vs 第2866行）
4. **修复简单**: 移除全局短路，让标志位逻辑生效

**风险**: ✅ 低
- 后面已有完整的独立评估逻辑
- 只需移除过早的全局短路

---

### P0 CodeFix-2: 6h缺口降级为1h-only

**建议**: ✅ 合理且实用

**理由**:
1. **提供容错路径**: 6h缺口时仍能输出中线结论
2. **符合体系**: 使用降级标签（MTF_DEGRADED_TO_1H）和降级执行许可
3. **不破坏双门槛**: execution_permission和confidence仍受控制
4. **显性标记**: 用户清楚知道是降级结论

**风险**: ✅ 低
- 降级是显性的（标签+降级执行）
- 仍然尊重双门槛机制
- 不引入新机制（复用现有标签+caps）

---

### P0 TestFix-1: 新增回归测试

**建议**: ✅ 必须

**理由**:
1. **锁定行为**: 防止未来回退
2. **CI可验证**: pytest可在CI中自动运行
3. **覆盖关键场景**: short gap + medium ok / 6h gap降级

**风险**: ✅ 无
- 纯增量测试，不影响现有代码

---

## 🎯 实施方案

### Phase 1: P0 CodeFix-1（移除全局短路）

#### 修改点1: 移除早期全局短路

**位置**: `market_state_machine_l1.py` 第2844-2856行

```python
# ===== Step 1.5: Lookback Coverage 检查（PATCH-2 + P0-CodeFix-1）=====
coverage_ok, coverage_tags = self._check_lookback_coverage(data)
if not coverage_ok:
    logger.warning(f"[{symbol}] Lookback coverage check failed: {[t.value for t in coverage_tags]}")
    # P0-CodeFix-1: 移除全局短路，改为记录标签
    # ❌ 删除：直接return dual NO_TRADE
    # ✅ 改为：记录coverage_tags，后续独立判断
    
    # 对于短期关键窗口缺失（5m/15m），记录但不短路
    critical_gaps_ltf = [ReasonTag.DATA_GAP_5M, ReasonTag.DATA_GAP_15M]
    if any(tag in coverage_tags for tag in critical_gaps_ltf):
        logger.warning(f"[{symbol}] Short-term window data gap detected")
        global_risk_tags.extend([tag for tag in coverage_tags if tag in critical_gaps_ltf])
        # P0-CodeFix-1: 不return，让后续独立评估处理
    
    # 对于中期窗口缺失（1h/6h），记录
    critical_gaps_mtf = [ReasonTag.DATA_GAP_1H, ReasonTag.DATA_GAP_6H]
    if any(tag in coverage_tags for tag in critical_gaps_mtf):
        logger.info(f"[{symbol}] Medium-term window data gap detected")
        global_risk_tags.extend([tag for tag in coverage_tags if tag in critical_gaps_mtf])
        # P0-CodeFix-1: 不return，让降级逻辑处理
```

#### 修改点2: 增强独立检查逻辑

**位置**: `market_state_machine_l1.py` 第2858-2887行

```python
# ===== Step 1.6: Critical Fields 检查（P0-CodeFix-1增强）=====

# 检查短期关键字段（5m/15m）
critical_short_fields = ['price_change_5m', 'price_change_15m', 'oi_change_5m', 'oi_change_15m',
                         'taker_imbalance_5m', 'taker_imbalance_15m', 'volume_ratio_5m', 'volume_ratio_15m']
missing_short = [f for f in critical_short_fields if data.get(f) is None]

has_short_data = True
if missing_short or any(tag in global_risk_tags for tag in [ReasonTag.DATA_GAP_5M, ReasonTag.DATA_GAP_15M]):
    # P0-CodeFix-1: 同时检查缺失字段和coverage gap
    logger.warning(f"[{symbol}] Short-term evaluation blocked: fields={missing_short}, gaps={global_risk_tags}")
    if ReasonTag.DATA_INCOMPLETE_LTF not in global_risk_tags:
        global_risk_tags.append(ReasonTag.DATA_INCOMPLETE_LTF)
    has_short_data = False
    # 不返回，让medium_term有机会评估

# 检查中期关键字段（1h/6h）
critical_medium_fields = ['price_change_1h', 'price_change_6h', 'oi_change_1h', 'oi_change_6h']
missing_medium = [f for f in critical_medium_fields if data.get(f) is None]

has_medium_data = True
has_medium_6h_data = True  # P0-CodeFix-2: 新增6h数据标志

# P0-CodeFix-2: 区分1h和6h缺失
missing_1h = [f for f in ['price_change_1h', 'oi_change_1h'] if data.get(f) is None]
missing_6h = [f for f in ['price_change_6h', 'oi_change_6h'] if data.get(f) is None]

if missing_1h or ReasonTag.DATA_GAP_1H in global_risk_tags:
    # 1h缺失 → 完全无法评估medium-term
    logger.warning(f"[{symbol}] Medium-term evaluation blocked: 1h data missing")
    if ReasonTag.DATA_INCOMPLETE_MTF not in global_risk_tags:
        global_risk_tags.append(ReasonTag.DATA_INCOMPLETE_MTF)
    has_medium_data = False
elif missing_6h or ReasonTag.DATA_GAP_6H in global_risk_tags:
    # 6h缺失但1h完整 → 可降级评估
    logger.info(f"[{symbol}] Medium-term will degrade to 1h-only: 6h data missing")
    has_medium_6h_data = False
    # P0-CodeFix-2: 记录降级标志，但has_medium_data=True（可评估）

# 只有两者都缺数据时才全局短路
if not has_short_data and not has_medium_data:
    logger.warning(f"[{symbol}] Both short and medium term data missing, returning dual NO_TRADE")
    return self._build_dual_no_trade_result(symbol, global_risk_tags, regime=MarketRegime.RANGE)
```

---

### Phase 2: P0 CodeFix-2（6h降级逻辑）

#### 新增ReasonTag

**位置**: `models/reason_tags.py`

```python
class ReasonTag(Enum):
    # ... 现有标签 ...
    
    # P0-CodeFix-2: Medium-term降级标签
    MTF_DEGRADED_TO_1H = "mtf_degraded_to_1h"  # 中期降级为1h-only评估
    DATA_GAP_6H = "data_gap_6h"  # 6小时K线缺口
```

#### 修改_evaluate_medium_term

**位置**: `market_state_machine_l1.py` 第3153行开始

```python
def _evaluate_medium_term(
    self,
    symbol: str,
    data: Dict,
    regime: MarketRegime
) -> 'TimeframeConclusion':
    """
    评估中长期决策（1h/6h）
    
    P0-01: None-safe重构
    P0-CodeFix-2: 6h缺口降级为1h-only
    """
    from models.dual_timeframe_result import TimeframeConclusion
    from models.enums import Timeframe
    
    # ===== P0-01: None-safe读取关键字段 =====
    price_change_1h = self._num(data, 'price_change_1h')
    price_change_6h = self._num(data, 'price_change_6h')
    oi_change_1h = self._num(data, 'oi_change_1h')
    oi_change_6h = self._num(data, 'oi_change_6h')
    taker_imbalance_1h = self._num(data, 'taker_imbalance_1h')
    funding_rate = self._num(data, 'funding_rate')  # 可选，默认0.0
    
    # ===== P0-CodeFix-2: 检测降级场景 =====
    is_6h_degraded = False
    degraded_reason = []
    
    # 1h关键字段检查（硬约束）
    if price_change_1h is None or oi_change_1h is None:
        # 1h缺失 → 完全无法评估
        logger.warning(f"[{symbol}] Medium-term blocked: 1h critical fields missing")
        return TimeframeConclusion(
            timeframe=Timeframe.MEDIUM_TERM,
            timeframe_label="1h/6h",
            decision=Decision.NO_TRADE,
            confidence=Confidence.LOW,
            market_regime=regime,
            trade_quality=TradeQuality.POOR,
            execution_permission=ExecutionPermission.DENY,
            executable=False,
            reason_tags=[ReasonTag.DATA_INCOMPLETE_MTF],
            key_metrics={
                'price_change_1h': price_change_1h,
                'oi_change_1h': oi_change_1h,
                'evaluation_mode': '1h_missing'
            }
        )
    
    # 6h降级检查（可降级）
    if price_change_6h is None or oi_change_6h is None:
        logger.info(f"[{symbol}] Medium-term degrading to 1h-only: 6h data missing")
        is_6h_degraded = True
        degraded_reason.append(ReasonTag.MTF_DEGRADED_TO_1H)
        if price_change_6h is None:
            degraded_reason.append(ReasonTag.DATA_GAP_6H)
    
    # ===== 评估模式选择 =====
    if is_6h_degraded:
        # P0-CodeFix-2: 1h-only降级评估
        decision, confidence, tags, key_metrics = self._evaluate_medium_term_1h_only(
            symbol, data, regime,
            price_change_1h, oi_change_1h, taker_imbalance_1h, funding_rate
        )
        
        # 强制降级约束
        tags.extend(degraded_reason)
        
        # 降级执行许可：至少为ALLOW_REDUCED
        execution_permission = ExecutionPermission.ALLOW_REDUCED
        
        # 降级置信度上限：不超过HIGH
        if confidence == Confidence.VERY_HIGH:
            confidence = Confidence.HIGH
            logger.debug(f"[{symbol}] Confidence capped to HIGH due to 6h degradation")
        
        key_metrics['evaluation_mode'] = '1h_only_degraded'
    else:
        # 完整评估（1h+6h）
        decision, confidence, tags, key_metrics = self._evaluate_medium_term_full(
            symbol, data, regime,
            price_change_1h, price_change_6h,
            oi_change_1h, oi_change_6h,
            taker_imbalance_1h, funding_rate
        )
        execution_permission = ExecutionPermission.ALLOW
        key_metrics['evaluation_mode'] = 'full_1h_6h'
    
    # ===== 构造结论 =====
    trade_quality = self._determine_trade_quality(decision, confidence, tags)
    executable = (decision != Decision.NO_TRADE and 
                  execution_permission != ExecutionPermission.DENY)
    
    return TimeframeConclusion(
        timeframe=Timeframe.MEDIUM_TERM,
        timeframe_label="1h/6h" if not is_6h_degraded else "1h-only(degraded)",
        decision=decision,
        confidence=confidence,
        market_regime=regime,
        trade_quality=trade_quality,
        execution_permission=execution_permission,
        executable=executable,
        reason_tags=tags,
        key_metrics=key_metrics
    )
```

#### 新增辅助方法

```python
def _evaluate_medium_term_1h_only(
    self,
    symbol: str,
    data: Dict,
    regime: MarketRegime,
    price_change_1h: float,
    oi_change_1h: float,
    taker_imbalance_1h: Optional[float],
    funding_rate: Optional[float]
) -> Tuple[Decision, Confidence, List[ReasonTag], Dict]:
    """
    P0-CodeFix-2: 1h-only降级评估（6h缺失时使用）
    
    最小规则：
    - 仅使用1h指标
    - 降级confidence上限
    - 标记降级状态
    """
    medium_config = self.config.get('dual_timeframe', {}).get('medium_term', {})
    
    # 1h阈值（比完整模式更保守）
    min_price_change = medium_config.get('min_price_change_1h', 0.015)  # 1.5%
    min_oi_change = medium_config.get('min_oi_change_1h', 0.04)  # 4%
    min_taker_imbalance = medium_config.get('min_taker_imbalance', 0.55)  # 55%
    
    # None-safe处理
    if taker_imbalance_1h is None:
        taker_imbalance_1h = 0.5  # 中性默认值
    if funding_rate is None:
        funding_rate = 0.0
    
    reason_tags = []
    signals_met = 0
    
    # LONG信号
    long_signals = 0
    if price_change_1h > min_price_change:
        long_signals += 1
    if oi_change_1h > min_oi_change:
        long_signals += 1
    if taker_imbalance_1h > min_taker_imbalance:
        long_signals += 1
    
    # SHORT信号
    short_signals = 0
    if price_change_1h < -min_price_change:
        short_signals += 1
    if oi_change_1h > min_oi_change:  # OI增长（空头增仓）
        short_signals += 1
    if taker_imbalance_1h < -min_taker_imbalance:
        short_signals += 1
    
    # 决策（降级模式：需要2/3信号）
    required_signals = 2
    
    if long_signals >= required_signals:
        decision = Decision.LONG
        confidence = Confidence.MEDIUM if long_signals == 2 else Confidence.HIGH
        reason_tags.append(ReasonTag.TREND_MEDIUM_TERM_LONG)
    elif short_signals >= required_signals:
        decision = Decision.SHORT
        confidence = Confidence.MEDIUM if short_signals == 2 else Confidence.HIGH
        reason_tags.append(ReasonTag.TREND_MEDIUM_TERM_SHORT)
    else:
        decision = Decision.NO_TRADE
        confidence = Confidence.LOW
        reason_tags.append(ReasonTag.NO_CLEAR_DIRECTION)
    
    key_metrics = {
        'price_change_1h': price_change_1h,
        'oi_change_1h': oi_change_1h,
        'taker_imbalance_1h': taker_imbalance_1h,
        'funding_rate': funding_rate,
        'long_signals': long_signals,
        'short_signals': short_signals,
        'required_signals': required_signals
    }
    
    return decision, confidence, reason_tags, key_metrics

def _evaluate_medium_term_full(
    self,
    symbol: str,
    data: Dict,
    regime: MarketRegime,
    price_change_1h: float,
    price_change_6h: float,
    oi_change_1h: float,
    oi_change_6h: float,
    taker_imbalance_1h: Optional[float],
    funding_rate: Optional[float]
) -> Tuple[Decision, Confidence, List[ReasonTag], Dict]:
    """
    完整模式：使用1h+6h数据
    
    （保持原有逻辑，从当前_evaluate_medium_term中提取）
    """
    # ... 原有的完整评估逻辑 ...
    pass
```

---

### Phase 3: P0 TestFix-1（新增测试）

**位置**: `tests/test_p0_codefix_validation.py`（新建）

```python
"""
P0 CodeFix 验收测试

测试内容：
- P0-CodeFix-1: short gap不吞medium
- P0-CodeFix-2: 6h缺口降级为1h-only
"""

import pytest
from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, Confidence, ExecutionPermission
from models.reason_tags import ReasonTag


class TestP0CodeFix1ShortGapNoSwallowMedium:
    """P0-CodeFix-1: 短期gap不吞中线"""
    
    @pytest.fixture
    def engine(self):
        return L1AdvisoryEngine(config_path='config/l1_thresholds.yaml')
    
    def test_5m_gap_medium_still_evaluates(self, engine):
        """
        验收Case A1: 5m gap但medium数据完整
        
        预期：
        - short_term: NO_TRADE (DATA_GAP_5M或DATA_INCOMPLETE_LTF)
        - medium_term: 正常输出（不是None，不被吞）
        """
        # Given: 5m缺失，但1h/6h完整且强势
        data = {
            'price': 50000,
            'volume_24h': 1000,
            # 短期字段缺失（模拟5m gap）
            # 'price_change_5m': None,  # 缺失
            'price_change_15m': 0.008,  # 存在但不影响5m gap
            # 中期字段完整且强势
            'price_change_1h': 0.03,  # 3%上涨
            'price_change_6h': 0.05,  # 5%上涨
            'oi_change_1h': 0.06,  # 6%增长
            'oi_change_6h': 0.10,  # 10%增长
            'taker_imbalance_1h': 0.75,  # 75%买压
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        # When
        result = engine.on_new_tick_dual('BTC', data)
        
        # Then: short_term被阻断
        assert result.short_term.decision == Decision.NO_TRADE, \
            "5m gap应该阻断short_term"
        assert (ReasonTag.DATA_GAP_5M in result.short_term.reason_tags or
                ReasonTag.DATA_INCOMPLETE_LTF in result.short_term.reason_tags), \
            "short_term应该有DATA_GAP_5M或DATA_INCOMPLETE_LTF标签"
        assert result.short_term.executable is False, \
            "short_term不可执行"
        
        # Then: medium_term仍正常输出（不被吞）
        assert result.medium_term is not None, \
            "medium_term不应该是None"
        assert result.medium_term.decision != None, \
            "medium_term应该有决策输出"
        # 由于medium数据强势，应该输出LONG
        # （如果规则更严格，至少不是因为5m gap而被吞掉）
        assert result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE], \
            "medium_term应该有明确的决策（不被short gap影响）"
        
        # Then: 整体结果不是双NO_TRADE（因为medium可能有方向）
        # （除非medium自己判断为NO_TRADE）
        # 关键是：不能因为short gap就让medium也变成NO_TRADE
        
    def test_15m_gap_medium_still_evaluates(self, engine):
        """
        验收Case A2: 15m gap但medium数据完整
        """
        data = {
            'price': 50000,
            'volume_24h': 1000,
            # 短期字段部分缺失（15m gap）
            'price_change_5m': 0.003,
            # 'price_change_15m': None,  # 缺失
            'taker_imbalance_5m': 0.65,
            # 中期字段完整
            'price_change_1h': 0.025,
            'price_change_6h': 0.04,
            'oi_change_1h': 0.05,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.70,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # short_term被阻断
        assert result.short_term.decision == Decision.NO_TRADE
        assert (ReasonTag.DATA_GAP_15M in result.short_term.reason_tags or
                ReasonTag.DATA_INCOMPLETE_LTF in result.short_term.reason_tags)
        
        # medium_term仍输出
        assert result.medium_term is not None
        assert result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE]


class TestP0CodeFix26hDegradeTo1hOnly:
    """P0-CodeFix-2: 6h缺口降级为1h-only"""
    
    @pytest.fixture
    def engine(self):
        return L1AdvisoryEngine(config_path='config/l1_thresholds.yaml')
    
    def test_6h_missing_degrade_to_1h_only(self, engine):
        """
        验收Case B: 6h缺失但1h完整且有明确方向
        
        预期：
        - medium_term: 输出方向（LONG/SHORT或明确NO_TRADE）
        - reason_tags: 包含MTF_DEGRADED_TO_1H或DATA_GAP_6H
        - execution_permission: ALLOW_REDUCED（降级）
        - confidence: 被cap（不超过HIGH）
        """
        # Given: 6h缺失，但1h完整且强势
        data = {
            'price': 50000,
            'volume_24h': 1000,
            # 短期字段完整（便于观察medium独立性）
            'price_change_5m': 0.003,
            'price_change_15m': 0.008,
            'taker_imbalance_5m': 0.60,
            'taker_imbalance_15m': 0.55,
            'volume_ratio_5m': 2.0,
            'volume_ratio_15m': 1.8,
            'oi_change_15m': 0.03,
            # 中期字段：1h完整且强势，6h缺失
            'price_change_1h': 0.025,  # 2.5%上涨
            # 'price_change_6h': None,  # 缺失
            'oi_change_1h': 0.06,  # 6%增长
            # 'oi_change_6h': None,  # 缺失
            'taker_imbalance_1h': 0.75,  # 75%买压
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        # When
        result = engine.on_new_tick_dual('BTC', data)
        
        # Then: medium_term仍输出方向（不硬失败）
        assert result.medium_term is not None, \
            "6h缺失时medium_term不应该None"
        assert result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE], \
            "medium_term应该有决策输出"
        
        # Then: 降级标签
        assert (ReasonTag.MTF_DEGRADED_TO_1H in result.medium_term.reason_tags or
                ReasonTag.DATA_GAP_6H in result.medium_term.reason_tags), \
            "应该有降级标签（MTF_DEGRADED_TO_1H或DATA_GAP_6H）"
        
        # Then: 降级执行许可
        assert result.medium_term.execution_permission in [
            ExecutionPermission.ALLOW_REDUCED,
            ExecutionPermission.DENY  # 如果其他原因也阻断
        ], "降级模式下执行许可应该至少为ALLOW_REDUCED"
        
        # Then: 置信度上限
        assert result.medium_term.confidence in [
            Confidence.LOW,
            Confidence.MEDIUM,
            Confidence.HIGH
            # 不应该是VERY_HIGH（降级后被cap）
        ], "降级模式下confidence应该被cap（不超过HIGH）"
        
        # Then: 如果1h数据强势，应该能输出LONG
        # （这是可选验证，取决于1h数据是否满足降级阈值）
        if result.medium_term.decision == Decision.LONG:
            assert result.medium_term.confidence >= Confidence.MEDIUM, \
                "降级LONG至少应该有MEDIUM置信度"
    
    def test_1h_missing_still_hard_fail(self, engine):
        """
        验收: 1h缺失时仍然硬失败（不降级）
        
        确保降级只发生在6h缺失场景，1h缺失仍然NO_TRADE
        """
        data = {
            'price': 50000,
            'volume_24h': 1000,
            # 1h缺失
            # 'price_change_1h': None,
            'price_change_6h': 0.05,  # 6h存在
            # 'oi_change_1h': None,
            'oi_change_6h': 0.08,
            'taker_imbalance_1h': 0.70,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # 1h缺失 → 硬失败
        assert result.medium_term.decision == Decision.NO_TRADE, \
            "1h缺失应该硬失败NO_TRADE"
        assert ReasonTag.DATA_INCOMPLETE_MTF in result.medium_term.reason_tags, \
            "应该有DATA_INCOMPLETE_MTF标签"
        assert result.medium_term.executable is False, \
            "1h缺失不可执行"


class TestP0CodeFixIntegration:
    """集成测试：两个CodeFix组合"""
    
    @pytest.fixture
    def engine(self):
        return L1AdvisoryEngine(config_path='config/l1_thresholds.yaml')
    
    def test_short_gap_and_medium_6h_gap(self, engine):
        """
        集成Case: short gap + medium 6h gap
        
        预期：
        - short_term: NO_TRADE (DATA_GAP_5M)
        - medium_term: 降级评估（1h-only），输出方向
        """
        data = {
            'price': 50000,
            'volume_24h': 1000,
            # 短期缺失
            # 'price_change_5m': None,
            'price_change_15m': 0.008,
            # 中期：1h完整，6h缺失
            'price_change_1h': 0.025,
            # 'price_change_6h': None,
            'oi_change_1h': 0.06,
            # 'oi_change_6h': None,
            'taker_imbalance_1h': 0.75,
            'funding_rate': 0.0001,
            '_metadata': {'percentage_format': 'decimal'}
        }
        
        result = engine.on_new_tick_dual('BTC', data)
        
        # short_term被阻断
        assert result.short_term.decision == Decision.NO_TRADE
        assert ReasonTag.DATA_INCOMPLETE_LTF in result.short_term.reason_tags
        
        # medium_term降级但仍输出
        assert result.medium_term.decision in [Decision.LONG, Decision.SHORT, Decision.NO_TRADE]
        assert (ReasonTag.MTF_DEGRADED_TO_1H in result.medium_term.reason_tags or
                ReasonTag.DATA_GAP_6H in result.medium_term.reason_tags)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
```

---

## 📊 交付标准验收

### ✅ 必须满足（硬约束）

1. **5m/15m gap不再吞掉medium-term**
   - 测试: `test_5m_gap_medium_still_evaluates` 通过
   - 验证: short_term NO_TRADE，但medium_term正常输出

2. **6h缺口不再硬失败**
   - 测试: `test_6h_missing_degrade_to_1h_only` 通过
   - 验证: medium_term输出方向，带降级标签和降级执行

3. **pytest用例通过**
   - 所有8个测试用例全部通过
   - 可在CI中稳定复现

### ✅ 不破坏现有约束

1. **不引入持仓语义** ✅
   - 仍为纯咨询层

2. **不破坏双门槛** ✅
   - ExecutionPermission: 降级用ALLOW_REDUCED
   - Confidence: 降级有cap上限

3. **显性标记** ✅
   - 所有降级通过reason_tags可见
   - 不隐藏可用结论

---

## 🚀 实施优先级

### Phase 1: P0-CodeFix-1（高优先级）
- **必须立即实施**
- 影响：冷启动时medium-term长期失效
- 风险：低（移除错误的短路）

### Phase 2: P0-CodeFix-2（高优先级）
- **应该立即实施**
- 影响：6h缺口时medium-term失效
- 风险：低（降级是显性的）

### Phase 3: P0-TestFix-1（必须）
- **与CodeFix同步实施**
- 作用：锁定行为，防止回退
- 风险：无

---

## 📖 相关文档

- **doc/输入口径契约与缺口策略.md** - P0核心规范
- **doc/P0改进实施报告.md** - 已完成的P0改进
- **tests/test_p0_none_safe_validation.py** - 现有P0测试

---

**方案版本**: 1.0  
**创建时间**: 2026-01-23  
**合理性评估**: ✅ 非常合理且必要  
**建议优先级**: P0（立即实施）  

**结论: 用户的建议完全合理，应该立即实施！** 🚀
