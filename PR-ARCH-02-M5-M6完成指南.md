# PR-ARCH-02 M5-M6完成指南

**当前状态**: PR-ARCH-02 70%完成（M1-M4✅ + M5 20%）  
**剩余工作**: M5剩余80% + M6全部  
**预估时间**: 1天（14小时）  

---

## 📋 当前进度

| Milestone | 完成度 | 状态 |
|-----------|--------|------|
| M1: DTO设计 | 100% | ✅ 已推送 |
| M2: StateStore接口 | 100% | ✅ 已推送 |
| M3: DecisionCore纯函数 | 100% | ✅ 已推送 |
| M4: DecisionGate频控 | 100% | ✅ 已推送 |
| M5: L1引擎集成 | 20% | ⚠️  部分完成 |
| M6: 确定性单测 | 0% | ⚠️  待开始 |

---

## 🎯 M5剩余工作：L1引擎完全切换

### 当前状态

**已完成（20%）**:
- ✅ `__init__`中初始化DecisionCore和DecisionGate
- ✅ `on_new_tick_dual`中添加新架构使用示例（注释形式）

**待完成（80%）**:
- ⚠️  改造`on_new_tick_dual`主流程
- ⚠️  添加`_convert_final_to_result()`转换方法
- ⚠️  Docker测试验证

---

### M5-Step2: 改造on_new_tick_dual主流程（预估4小时）

#### 改造策略（推荐）

**方案A: 完全替换（激进）**
```python
def on_new_tick_dual(self, symbol: str, data: Dict) -> 'DualTimeframeResult':
    """使用新架构"""
    # Step 1: 特征生成（PR-ARCH-01）
    from data_cache import get_cache
    feature_snapshot = self.feature_builder.build(symbol, data, get_cache())
    
    # Step 2: DecisionCore评估（PR-ARCH-02）
    draft = self.decision_core.evaluate_dual(
        feature_snapshot, self.thresholds_typed, symbol
    )
    
    # Step 3: DecisionGate应用（PR-ARCH-02）
    final = self.decision_gate.apply_dual(
        draft, symbol, datetime.now(), self.thresholds_typed
    )
    
    # Step 4: 转换为DualTimeframeResult
    return self._convert_final_to_result(final, symbol, feature_snapshot)
```

**方案B: 并行运行（稳健）**
```python
def on_new_tick_dual(self, symbol: str, data: Dict) -> 'DualTimeframeResult':
    """并行运行新旧架构，对比结果"""
    # 新架构
    try:
        new_result = self._on_new_tick_dual_new_arch(symbol, data)
        logger.info(f"[{symbol}] New arch result: {new_result.get_summary()}")
    except Exception as e:
        logger.error(f"[{symbol}] New arch failed: {e}")
        new_result = None
    
    # 旧架构（保留）
    old_result = self._on_new_tick_dual_legacy(symbol, data)
    
    # TODO: 对比new_result和old_result，记录差异
    
    # 返回旧结果（保守）
    return old_result
```

**方案C: 特性开关（最稳健）**
```python
def on_new_tick_dual(self, symbol: str, data: Dict) -> 'DualTimeframeResult':
    """根据配置选择架构"""
    use_new_arch = os.getenv('USE_NEW_ARCH', 'false').lower() == 'true'
    
    if use_new_arch:
        return self._on_new_tick_dual_new_arch(symbol, data)
    else:
        return self._on_new_tick_dual_legacy(symbol, data)
```

#### 推荐：方案B（并行运行）

**理由**:
1. 可以对比新旧结果，发现问题
2. 不破坏现有逻辑
3. 可以渐进式切换

**实施步骤**:

1. 将现有`on_new_tick_dual`重命名为`_on_new_tick_dual_legacy`
2. 创建新方法`_on_new_tick_dual_new_arch`（使用新架构）
3. 在`on_new_tick_dual`中并行调用两者，返回旧结果
4. 记录差异日志

---

### M5-Step3: 实现_convert_final_to_result（预估2小时）

#### 目标

将`DualTimeframeDecisionFinal`转换为`DualTimeframeResult`（向后兼容）。

#### 实现骨架

```python
def _convert_final_to_result(
    self,
    final: DualTimeframeDecisionFinal,
    symbol: str,
    features: FeatureSnapshot
) -> 'DualTimeframeResult':
    """
    将DecisionFinal转换为DualTimeframeResult（向后兼容）
    
    Args:
        final: DecisionGate输出
        symbol: 交易对符号
        features: 特征快照
    
    Returns:
        DualTimeframeResult
    """
    from models.dual_timeframe_result import (
        DualTimeframeResult, TimeframeConclusion, AlignmentAnalysis
    )
    from models.enums import Timeframe
    
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
        reason_tags=final.short_term.reason_tags,
        key_metrics=final.short_term.key_metrics
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
        reason_tags=final.medium_term.reason_tags,
        key_metrics=final.medium_term.key_metrics
    )
    
    # 构建AlignmentAnalysis（简化版本）
    # TODO: 实现完整的对齐分析逻辑
    alignment = self._analyze_alignment_from_final(short_conclusion, medium_conclusion)
    
    # 构建DualTimeframeResult
    return DualTimeframeResult(
        symbol=symbol,
        timestamp=datetime.now(),
        short_term=short_conclusion,
        medium_term=medium_conclusion,
        alignment=alignment,
        price=features.features.price.current_price,
        risk_exposure_allowed=True,  # TODO: 从final中提取
        global_risk_tags=final.global_risk_tags,
        system_state=SystemState.NORMAL  # TODO: 系统状态判断
    )

def _analyze_alignment_from_final(
    self,
    short: TimeframeConclusion,
    medium: TimeframeConclusion
) -> AlignmentAnalysis:
    """
    分析短期和中期的对齐关系（简化版本）
    
    TODO: 实现完整的对齐分析逻辑
    
    Args:
        short: 短期结论
        medium: 中期结论
    
    Returns:
        AlignmentAnalysis
    """
    from models.dual_timeframe_result import AlignmentAnalysis
    from models.enums import AlignmentType
    
    # 简化逻辑：判断是否方向一致
    if short.decision == medium.decision:
        if short.decision == Decision.NO_TRADE:
            alignment_type = AlignmentType.BOTH_NO_TRADE
        else:
            alignment_type = AlignmentType.ALIGNED_SIGNAL
        
        return AlignmentAnalysis(
            is_aligned=True,
            alignment_type=alignment_type,
            has_conflict=False,
            conflict_resolution=None,
            resolution_reason=None,
            recommended_action=short.decision,
            recommended_confidence=max(short.confidence, medium.confidence),
            recommendation_notes="短期和中期方向一致"
        )
    else:
        # 冲突情况
        return AlignmentAnalysis(
            is_aligned=False,
            alignment_type=AlignmentType.CONFLICTING,
            has_conflict=True,
            conflict_resolution=ConflictResolution.PREFER_MEDIUM_TERM,
            resolution_reason="短期和中期方向冲突，优先中期",
            recommended_action=medium.decision,
            recommended_confidence=Confidence.LOW,
            recommendation_notes="⚠️ 周期冲突"
        )
```

---

## 🎯 M6: 确定性单测（预估8小时）

### M6-Step1: DecisionCore确定性测试（4小时）

#### 文件

`tests/test_decision_core.py`

#### 测试用例清单

**Test 1: 确定性基础测试**
```python
def test_decision_core_deterministic():
    """测试DecisionCore的确定性"""
    # 构造固定输入
    features = FeatureSnapshot(...)
    thresholds = Thresholds(...)
    
    # 多次调用
    results = [
        DecisionCore.evaluate_single(features, thresholds)
        for _ in range(10)
    ]
    
    # 断言：所有结果完全相同
    for i in range(1, len(results)):
        assert results[i].decision == results[0].decision
        assert results[i].confidence == results[0].confidence
        assert results[i].market_regime == results[0].market_regime
        assert results[i].trade_quality == results[0].trade_quality
        assert results[i].execution_permission == results[0].execution_permission
        # reason_tags可能顺序不同，但集合应该相同
        assert set(results[i].reason_tags) == set(results[0].reason_tags)
```

**Test 2: 市场环境识别测试**
```python
def test_market_regime_detection():
    """测试市场环境识别"""
    thresholds = load_test_thresholds()
    
    # EXTREME: price_change_1h = 0.06 (> 0.05)
    features_extreme = create_test_features(price_change_1h=0.06)
    regime, tags = DecisionCore._detect_market_regime(features_extreme, thresholds)
    assert regime == MarketRegime.EXTREME
    
    # TREND: price_change_6h = 0.04 (> 0.03)
    features_trend = create_test_features(price_change_6h=0.04)
    regime, tags = DecisionCore._detect_market_regime(features_trend, thresholds)
    assert regime == MarketRegime.TREND
    
    # RANGE: 默认
    features_range = create_test_features(price_change_1h=0.01)
    regime, tags = DecisionCore._detect_market_regime(features_range, thresholds)
    assert regime == MarketRegime.RANGE
```

**Test 3: 风险准入评估测试**
```python
def test_risk_exposure_evaluation():
    """测试风险准入评估"""
    thresholds = load_test_thresholds()
    
    # EXTREME regime应该DENY
    features = create_test_features()
    risk_ok, tags = DecisionCore._eval_risk_exposure(
        features, MarketRegime.EXTREME, thresholds
    )
    assert risk_ok == False
    assert ReasonTag.EXTREME_REGIME in tags
    
    # 清算阶段应该DENY
    features_liquidation = create_test_features(
        price_change_1h=-0.06,  # 急跌
        oi_change_1h=-0.35       # OI急降
    )
    risk_ok, tags = DecisionCore._eval_risk_exposure(
        features_liquidation, MarketRegime.RANGE, thresholds
    )
    assert risk_ok == False
    assert ReasonTag.LIQUIDATION_PHASE in tags
    
    # 拥挤风险应该DENY
    features_crowding = create_test_features(
        funding_rate=0.0015,     # 极端费率
        oi_change_6h=0.60        # 高OI增长
    )
    risk_ok, tags = DecisionCore._eval_risk_exposure(
        features_crowding, MarketRegime.RANGE, thresholds
    )
    assert risk_ok == False
    assert ReasonTag.CROWDING_RISK in tags
```

**Test 4: 交易质量评估测试**
```python
def test_trade_quality_evaluation():
    """测试交易质量评估"""
    thresholds = load_test_thresholds()
    
    # 吸纳风险应该POOR
    features_absorption = create_test_features(
        taker_imbalance_1h=0.8,  # 高失衡
        volume_1h=1000,          # 低成交量
        volume_24h=50000         # 24h平均高
    )
    quality, tags = DecisionCore._eval_trade_quality(
        features_absorption, MarketRegime.RANGE, thresholds, "BTC"
    )
    assert quality == TradeQuality.POOR
    assert ReasonTag.ABSORPTION_RISK in tags
    
    # 噪音市应该UNCERTAIN
    features_noise = create_test_features(
        funding_rate=0.0002,      # 当前费率低
        funding_rate_prev=0.0008  # 前值高（波动大）
    )
    quality, tags = DecisionCore._eval_trade_quality(
        features_noise, MarketRegime.RANGE, thresholds, "BTC"
    )
    assert quality == TradeQuality.UNCERTAIN
    assert ReasonTag.NOISY_MARKET in tags
```

**Test 5: 方向评估测试**
```python
def test_direction_evaluation():
    """测试方向评估"""
    thresholds = load_test_thresholds()
    
    # LONG条件（TREND）
    features_long_trend = create_test_features(
        taker_imbalance_1h=0.7,  # > 0.6
        oi_change_1h=0.35,       # > 0.3
        price_change_1h=0.025    # > 0.02
    )
    allow_long, tags = DecisionCore._eval_long_direction(
        features_long_trend, MarketRegime.TREND, thresholds
    )
    assert allow_long == True
    
    # SHORT条件（TREND）
    features_short_trend = create_test_features(
        taker_imbalance_1h=-0.7,  # < -0.6
        oi_change_1h=0.35,        # > 0.3
        price_change_1h=-0.025    # < -0.02
    )
    allow_short, tags = DecisionCore._eval_short_direction(
        features_short_trend, MarketRegime.TREND, thresholds
    )
    assert allow_short == True
```

**Test 6: None-safe测试**
```python
def test_none_safe_behavior():
    """测试None-safe行为"""
    thresholds = load_test_thresholds()
    
    # 缺失关键字段时，应该返回NO_TRADE（不崩溃）
    features_missing = create_test_features(
        price_change_1h=None,  # 缺失
        oi_change_1h=None      # 缺失
    )
    
    draft = DecisionCore.evaluate_single(features_missing, thresholds)
    
    # 应该返回NO_TRADE，不应该抛异常
    assert draft.decision == Decision.NO_TRADE
    # 应该有DATA_INCOMPLETE相关标签
    assert any('DATA' in tag.value for tag in draft.reason_tags)
```

#### Helper函数

```python
def create_test_features(**kwargs) -> FeatureSnapshot:
    """
    创建测试用的FeatureSnapshot
    
    Args:
        **kwargs: 覆盖默认值的字段
    
    Returns:
        FeatureSnapshot
    """
    from models.feature_snapshot import (
        FeatureSnapshot, MarketFeatures, PriceFeatures,
        OpenInterestFeatures, TakerImbalanceFeatures,
        VolumeFeatures, FundingFeatures,
        CoverageInfo, FeatureMetadata
    )
    
    # 默认值（正常市场）
    defaults = {
        'price_change_1h': 0.01,
        'price_change_6h': 0.02,
        'oi_change_1h': 0.15,
        'oi_change_6h': 0.25,
        'taker_imbalance_1h': 0.3,
        'volume_1h': 10000,
        'volume_24h': 200000,
        'funding_rate': 0.0001,
        'funding_rate_prev': 0.0001
    }
    
    # 覆盖用户提供的值
    defaults.update(kwargs)
    
    # 构建FeatureSnapshot
    features = FeatureSnapshot(
        features=MarketFeatures(
            price=PriceFeatures(
                price_change_1h=defaults['price_change_1h'],
                price_change_6h=defaults['price_change_6h'],
                current_price=50000.0
            ),
            open_interest=OpenInterestFeatures(
                oi_change_1h=defaults['oi_change_1h'],
                oi_change_6h=defaults['oi_change_6h']
            ),
            taker_imbalance=TakerImbalanceFeatures(
                taker_imbalance_1h=defaults['taker_imbalance_1h']
            ),
            volume=VolumeFeatures(
                volume_1h=defaults['volume_1h'],
                volume_24h=defaults['volume_24h']
            ),
            funding=FundingFeatures(
                funding_rate=defaults['funding_rate'],
                funding_rate_prev=defaults['funding_rate_prev']
            )
        ),
        coverage=CoverageInfo(
            short_evaluable=True,
            medium_evaluable=True
        ),
        metadata=FeatureMetadata(symbol="BTC")
    )
    
    return features

def load_test_thresholds() -> Thresholds:
    """
    加载测试用的Thresholds配置
    
    Returns:
        Thresholds
    """
    from l1_engine.threshold_compiler import ThresholdCompiler
    
    compiler = ThresholdCompiler()
    # 使用实际配置文件
    config_path = 'config/l1_thresholds.yaml'
    return compiler.compile(config_path)
```

---

### M6-Step2: DecisionGate频控测试（4小时）

#### 文件

`tests/test_decision_gate.py`

#### 测试用例清单

**Test 1: 首次决策总是允许**
```python
def test_first_decision_allowed():
    """测试第一次决策总是允许"""
    from l1_engine.decision_gate import DecisionGate
    from l1_engine.state_store import InMemoryStateStore
    from models.decision_core_dto import TimeframeDecisionDraft
    
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    draft = create_test_draft(decision=Decision.LONG)
    now = datetime.now()
    
    final = gate.apply(draft, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    
    assert final.executable == True
    assert final.frequency_control.is_blocked == False
    assert final.frequency_control.is_cooling == False
```

**Test 2: 冷却期阻断测试**
```python
def test_cooling_period_blocking():
    """测试冷却期阻断"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 第一次决策：LONG
    draft1 = create_test_draft(decision=Decision.LONG)
    now1 = datetime.now()
    final1 = gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True
    
    # 第二次决策：LONG（冷却期内，60秒 < 1800秒）
    draft2 = create_test_draft(decision=Decision.LONG)
    now2 = now1 + timedelta(seconds=60)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == False
    assert final2.frequency_control.is_cooling == True
    assert ReasonTag.FREQUENCY_COOLING in final2.reason_tags
```

**Test 3: 最小间隔测试**
```python
def test_min_interval_violation():
    """测试最小间隔"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 第一次决策：LONG
    draft1 = create_test_draft(decision=Decision.LONG)
    now1 = datetime.now()
    gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    
    # 第二次决策：SHORT（方向翻转，但时间过短，60秒 < 600秒）
    draft2 = create_test_draft(decision=Decision.SHORT)
    now2 = now1 + timedelta(seconds=60)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == False
    assert final2.frequency_control.min_interval_violated == True
    assert ReasonTag.MIN_INTERVAL_VIOLATED in final2.reason_tags
```

**Test 4: 方向翻转允许测试**
```python
def test_direction_flip_allowed():
    """测试方向翻转允许（超过最小间隔）"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 第一次决策：LONG
    draft1 = create_test_draft(decision=Decision.LONG)
    now1 = datetime.now()
    gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    
    # 第二次决策：SHORT（方向翻转，时间足够，700秒 > 600秒）
    draft2 = create_test_draft(decision=Decision.SHORT)
    now2 = now1 + timedelta(seconds=700)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == True
    assert ReasonTag.DIRECTION_FLIP in final2.reason_tags
```

**Test 5: NO_TRADE总是允许**
```python
def test_no_trade_always_executable():
    """测试NO_TRADE总是可执行"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 第一次决策：LONG
    draft1 = create_test_draft(decision=Decision.LONG)
    now1 = datetime.now()
    gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    
    # 第二次决策：NO_TRADE（冷却期内，但NO_TRADE总是允许）
    draft2 = create_test_draft(decision=Decision.NO_TRADE)
    now2 = now1 + timedelta(seconds=60)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == True
    assert final2.frequency_control.is_blocked == False
```

**Test 6: 双周期独立频控测试**
```python
def test_dual_timeframe_independent_control():
    """测试双周期独立频控"""
    from l1_engine.state_store import DualTimeframeStateStore
    
    state_store = DualTimeframeStateStore()
    gate = DecisionGate(state_store)
    thresholds = load_test_thresholds()
    
    # 构建双周期draft
    draft = DualTimeframeDecisionDraft(
        short_term=create_test_draft(decision=Decision.LONG),
        medium_term=create_test_draft(decision=Decision.SHORT),
        global_risk_tags=[]
    )
    
    now = datetime.now()
    final = gate.apply_dual(draft, "BTC", now, thresholds)
    
    # 短期和中期都应该可执行（首次决策）
    assert final.short_term.executable == True
    assert final.medium_term.executable == True
    
    # 第二次：短期LONG（冷却期内），中期SHORT（不同方向，允许）
    draft2 = DualTimeframeDecisionDraft(
        short_term=create_test_draft(decision=Decision.LONG),
        medium_term=create_test_draft(decision=Decision.SHORT),
        global_risk_tags=[]
    )
    
    now2 = now + timedelta(seconds=700)
    final2 = gate.apply_dual(draft2, "BTC", now2, thresholds)
    
    # 短期被冷却期阻断，中期允许（独立频控）
    assert final2.short_term.executable == False
    assert final2.medium_term.executable == True
```

#### Helper函数

```python
def create_test_draft(**kwargs) -> TimeframeDecisionDraft:
    """
    创建测试用的DecisionDraft
    
    Args:
        **kwargs: 覆盖默认值的字段
    
    Returns:
        TimeframeDecisionDraft
    """
    from models.decision_core_dto import TimeframeDecisionDraft
    
    defaults = {
        'decision': Decision.NO_TRADE,
        'confidence': Confidence.LOW,
        'market_regime': MarketRegime.RANGE,
        'trade_quality': TradeQuality.GOOD,
        'execution_permission': ExecutionPermission.ALLOW,
        'reason_tags': [],
        'key_metrics': {}
    }
    
    defaults.update(kwargs)
    
    return TimeframeDecisionDraft(**defaults)
```

---

## 📝 验收清单

### M5验收

- [ ] `on_new_tick_dual`使用新架构（或并行运行）
- [ ] `_convert_final_to_result`实现
- [ ] Docker测试通过
- [ ] 日志显示新架构正常工作

### M6验收

- [ ] `test_decision_core.py`至少6个测试用例
- [ ] `test_decision_gate.py`至少6个测试用例
- [ ] 所有测试通过：`pytest tests/test_decision_*.py -v`
- [ ] 覆盖率 > 80%：`pytest --cov=l1_engine --cov-report=html`

### 整体验收

- [ ] **功能验收**：新架构输出与旧架构一致（或差异可解释）
- [ ] **性能验收**：决策延迟 < 50ms
- [ ] **稳定性验收**：Docker运行24小时无崩溃
- [ ] **文档验收**：完成报告（PR-ARCH-02-完成报告.md）

---

## 🚀 快速启动命令

### 运行单测

```bash
# 运行DecisionCore测试
pytest tests/test_decision_core.py -v

# 运行DecisionGate测试
pytest tests/test_decision_gate.py -v

# 运行所有测试
pytest tests/ -v

# 生成覆盖率报告
pytest --cov=l1_engine --cov-report=html tests/
```

### Docker测试

```bash
# 重建Docker（包含新代码）
docker compose -f docker-compose-l1.yml build --no-cache

# 启动服务
docker compose -f docker-compose-l1.yml up

# 查看日志（确认新架构初始化）
docker compose -f docker-compose-l1.yml logs -f
```

---

## 💡 实施建议

### 推荐路径

**Day 1上午（4小时）**:
- M5-Step2: 实现`_on_new_tick_dual_new_arch`（2小时）
- M5-Step3: 实现`_convert_final_to_result`（2小时）

**Day 1下午（4小时）**:
- M6-Step1: 编写DecisionCore测试（4小时）

**Day 1晚上（2小时）**:
- M6-Step2: 编写DecisionGate测试（2小时）
- Docker测试验证（1小时）
- 生成完成报告（1小时）

### 风险提示

⚠️  **高风险点**:
1. `on_new_tick_dual`改造可能影响稳定性
   - 缓解：采用方案B（并行运行），不破坏旧逻辑
   
2. 测试用例可能无法覆盖所有场景
   - 缓解：先覆盖核心场景，后续迭代补充

3. Docker测试可能暴露集成问题
   - 缓解：保留fallback逻辑，新架构失败时使用旧架构

---

## 📋 TODO清单

### M5剩余工作

- [ ] 重命名`on_new_tick_dual` → `_on_new_tick_dual_legacy`
- [ ] 创建`_on_new_tick_dual_new_arch`（使用DecisionCore+Gate）
- [ ] 创建新的`on_new_tick_dual`（并行运行两者）
- [ ] 实现`_convert_final_to_result`
- [ ] 实现`_analyze_alignment_from_final`
- [ ] Docker测试验证

### M6全部工作

- [ ] 创建`tests/test_decision_core.py`
- [ ] 实现6个DecisionCore测试用例
- [ ] 创建`tests/test_decision_gate.py`
- [ ] 实现6个DecisionGate测试用例
- [ ] 运行所有测试：`pytest tests/ -v`
- [ ] 生成覆盖率报告

---

**指南生成时间**: 2026-01-23  
**预估完成时间**: 2026-01-24  
**当前进度**: PR-ARCH-02 70%完成  

🚀 **核心架构已完成，最后冲刺！**
