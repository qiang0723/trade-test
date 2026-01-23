# PR-ARCH-02 详细实施计划

**状态**: ⚠️  33%完成  
**已完成**: M1-M2（基础设施）  
**待完成**: M3-M6（核心实现）  
**预估剩余时间**: 5天  

---

## 📋 整体进度概览

| Milestone | 状态 | 预估时间 | 交付物 |
|-----------|------|----------|--------|
| **M1: DTO设计** | ✅ 100% | - | models/decision_core_dto.py (300行) |
| **M2: StateStore接口** | ✅ 100% | - | l1_engine/state_store.py (300行) |
| **M3: DecisionCore纯函数** | ⚠️  10% | 2天 | l1_engine/decision_core.py (800行) |
| **M4: DecisionGate频控** | ⚠️  0% | 1天 | l1_engine/decision_gate.py (400行) |
| **M5: L1引擎集成** | ⚠️  0% | 1天 | market_state_machine_l1.py改动 |
| **M6: 确定性单测** | ⚠️  0% | 1天 | tests/test_decision_core.py (400行) |
| **总计** | **33%** | **5天** | **~2100行新增代码** |

---

## 🎯 M3: DecisionCore纯函数实现（预估2天）

### 目标

将`market_state_machine_l1.py`中的决策逻辑提取为纯函数。

### 当前状态

- ✅ 骨架文件已创建：`l1_engine/decision_core.py`
- ✅ 主入口框架完成：`evaluate_single()`, `evaluate_dual()`
- ⚠️  TODO：实现9个核心方法

### 实施步骤

#### Step 1: 提取市场环境识别（预估2小时）

**源方法**: `market_state_machine_l1.py::_detect_market_regime()`  
**目标方法**: `DecisionCore._detect_market_regime()`

**改造要点**:
```python
# 旧实现（依赖self）
def _detect_market_regime(self, data: Dict) -> Tuple[MarketRegime, List[ReasonTag]]:
    price_change_1h = self._num(data, 'price_change_1h')  # helper方法
    regime_thresholds = self.thresholds_typed.market_regime  # 实例变量
    # ...

# 新实现（纯函数）
@staticmethod
def _detect_market_regime(
    features: FeatureSnapshot, 
    thresholds: Thresholds
) -> Tuple[MarketRegime, List[ReasonTag]]:
    price_change_1h = features.features.price.price_change_1h  # FeatureSnapshot
    regime_thresholds = thresholds.market_regime  # 参数传入
    # ...
```

**转换清单**:
- [x] 移除`self`依赖
- [ ] 将`data: Dict`改为`features: FeatureSnapshot`
- [ ] 将`self.thresholds_typed`改为参数`thresholds`
- [ ] 将`self._num()`改为直接访问`features.features.price.price_change_1h`
- [ ] 保持None-safe逻辑
- [ ] 保持退化逻辑（6h缺失时使用15m）

**代码位置**: `market_state_machine_l1.py:1008-1074`

---

#### Step 2: 提取风险准入评估（预估2小时）

**源方法**: `market_state_machine_l1.py::_eval_risk_exposure_allowed()`  
**目标方法**: `DecisionCore._eval_risk_exposure()`

**改造要点**:
```python
# 旧实现
def _eval_risk_exposure_allowed(self, data: Dict, regime: MarketRegime):
    risk_thresholds = self.thresholds_typed.risk_exposure
    price_change_1h = self._num(data, 'price_change_1h')
    # ...

# 新实现（纯函数）
@staticmethod
def _eval_risk_exposure(
    features: FeatureSnapshot, 
    regime: MarketRegime,
    thresholds: Thresholds
):
    risk_thresholds = thresholds.risk_exposure
    price_change_1h = features.features.price.price_change_1h
    # ...
```

**转换清单**:
- [ ] 移除`self`依赖
- [ ] 适配`FeatureSnapshot`
- [ ] 4个检查项：EXTREME/清算/拥挤/极端成交量
- [ ] 保持None-safe逻辑（缺失时跳过规则）

**代码位置**: `market_state_machine_l1.py:1080-1161`

---

#### Step 3: 提取交易质量评估（预估3小时）⚠️  复杂

**源方法**: `market_state_machine_l1.py::_eval_trade_quality()`  
**目标方法**: `DecisionCore._eval_trade_quality()`

**改造要点**:
```python
# 旧实现（依赖历史数据）
def _eval_trade_quality(self, symbol: str, data: Dict, regime: MarketRegime):
    # 噪音市检测需要funding_rate_prev
    funding_rate_prev = self.history_data.get(f'{symbol}_funding_rate_prev', funding_rate)
    funding_volatility = abs(funding_rate - funding_rate_prev)
    self.history_data[f'{symbol}_funding_rate_prev'] = funding_rate  # 副作用！
    # ...

# 新实现（纯函数，需要特殊处理）
@staticmethod
def _eval_trade_quality(
    features: FeatureSnapshot,  # 包含funding_rate_prev吗？
    regime: MarketRegime,
    thresholds: Thresholds,
    symbol: str
):
    # 方案1: FeatureSnapshot包含funding_rate_prev（推荐）
    funding_rate = features.features.funding.funding_rate
    funding_rate_prev = features.features.funding.funding_rate_prev  # ✅
    if funding_rate is not None and funding_rate_prev is not None:
        funding_volatility = abs(funding_rate - funding_rate_prev)
    # ...
```

**⚠️  关键挑战**:
- 噪音市检测需要`funding_rate_prev`
- 当前`FeatureSnapshot`已包含`funding_rate_prev`字段 ✅
- 纯函数不能保存状态，状态管理需要在外部（FeatureBuilder）

**转换清单**:
- [ ] 移除`self`依赖
- [ ] 适配`FeatureSnapshot`
- [ ] 4个检查项：吸纳/噪音/轮动/震荡弱信号
- [ ] ⚠️  确认`FeatureSnapshot.features.funding.funding_rate_prev`可用
- [ ] 移除`self.history_data`副作用
- [ ] 保持None-safe逻辑

**代码位置**: `market_state_machine_l1.py:1167-1273`

---

#### Step 4: 提取方向评估（预估3小时）

**源方法**: 
- `market_state_machine_l1.py::_eval_long_direction()` (1279-1349)
- `market_state_machine_l1.py::_eval_short_direction()` (1351-1421)

**目标方法**: 
- `DecisionCore._eval_long_direction()`
- `DecisionCore._eval_short_direction()`

**改造要点**:
```python
# 旧实现（依赖self.thresholds和self.config）
def _eval_long_direction(self, data: Dict, regime: MarketRegime):
    imbalance = self._num(data, 'taker_imbalance_1h')
    if regime == MarketRegime.TREND:
        if imbalance > self.thresholds['long_imbalance_trend']:  # ⚠️  dict访问
            return True, direction_tags
    elif regime == MarketRegime.RANGE:
        # 短期机会识别
        short_term_config = self.config.get('direction', {}).get('range', {})...  # ⚠️  dict嵌套
        # ...

# 新实现（纯函数，使用强类型配置）
@staticmethod
def _eval_long_direction(
    features: FeatureSnapshot,
    regime: MarketRegime,
    thresholds: Thresholds
):
    imbalance = features.features.taker_imbalance.taker_imbalance_1h
    if regime == MarketRegime.TREND:
        if imbalance > thresholds.direction.long_imbalance_trend:  # ✅ 强类型
            return True, direction_tags
    elif regime == MarketRegime.RANGE:
        # 短期机会识别
        short_term_config = thresholds.direction.range.short_term_opportunity.long  # ✅ 强类型
        # ...
```

**⚠️  关键挑战**:
- 当前`thresholds.direction`尚未完全实现（在`models/thresholds.py`中）
- 需要添加`DirectionThresholds` DTO

**转换清单**:
- [ ] 移除`self`依赖
- [ ] 适配`FeatureSnapshot`
- [ ] ⚠️  扩展`models/thresholds.py`添加`DirectionThresholds`
- [ ] 转换dict访问为强类型访问
- [ ] 保持None-safe逻辑
- [ ] 保持短期机会识别逻辑

---

#### Step 5: 提取决策优先级（预估1小时）✅ 简单

**源方法**: `market_state_machine_l1.py::_decide_priority()` (1427-1469)  
**目标方法**: `DecisionCore._decide_priority()`

**改造要点**:
- ✅ 已经是纯函数（无self依赖）
- ✅ 只需复制粘贴即可

**转换清单**:
- [ ] 直接复制逻辑

---

#### Step 6: 提取资金费率降级（预估2小时）

**源方法**: 分散在多处，需要查找  
**目标方法**: `DecisionCore._apply_funding_rate_downgrade()`

**查找位置**:
```bash
grep -n "funding_rate.*downgrade\|funding.*降级" market_state_machine_l1.py
```

**转换清单**:
- [ ] 查找资金费率降级逻辑
- [ ] 提取为纯函数
- [ ] 适配`FeatureSnapshot`

---

#### Step 7: 提取执行权限判断（预估2小时）

**源方法**: 分散在多处，需要查找  
**目标方法**: `DecisionCore._determine_execution_permission()`

**查找位置**:
```bash
grep -n "ExecutionPermission\|execution_permission" market_state_machine_l1.py
```

**转换清单**:
- [ ] 查找执行权限判断逻辑
- [ ] 提取为纯函数（基于regime/quality/decision）
- [ ] 适配强类型配置

---

#### Step 8: 提取置信度计算（预估3小时）

**源方法**: `market_state_machine_l1.py::_compute_confidence()` (~1476-1600)  
**目标方法**: `DecisionCore._compute_confidence()`

**改造要点**:
```python
# 旧实现（依赖self.config）
def _compute_confidence(self, decision, regime, quality, reason_tags):
    caps = self.config.get('confidence_scoring', {}).get('caps', {})  # dict访问
    # ...

# 新实现（纯函数，使用强类型配置）
@staticmethod
def _compute_confidence(decision, regime, quality, reason_tags, thresholds):
    caps = thresholds.confidence_scoring.caps  # ✅ 强类型
    # ...
```

**转换清单**:
- [ ] 移除`self`依赖
- [ ] 转换dict访问为强类型访问
- [ ] 保持PR-D混合模式逻辑

---

### M3完成验收标准

- [ ] 所有9个核心方法已实现
- [ ] 无`self`依赖（纯静态方法）
- [ ] 输入：`FeatureSnapshot` + `Thresholds`
- [ ] 输出：`DecisionDraft`
- [ ] 保持None-safe逻辑
- [ ] 代码行数：~800行

---

## 🎯 M4: DecisionGate频控实现（预估1天）

### 目标

实现频率控制逻辑（冷却期、最小间隔、阻断）。

### 实施步骤

#### Step 1: 创建DecisionGate类（预估2小时）

**文件**: `l1_engine/decision_gate.py`

**核心结构**:
```python
class DecisionGate:
    """决策门控（频率控制）"""
    
    def __init__(self, state_store: StateStore):
        self.state_store = state_store
    
    def apply(
        self,
        draft: TimeframeDecisionDraft,
        symbol: str,
        now: datetime,
        thresholds: Thresholds,
        timeframe: Timeframe
    ) -> TimeframeDecisionFinal:
        """应用频率控制"""
        # Step 1: 获取历史状态
        last_time = self.state_store.get_last_decision_time(symbol)
        last_direction = self.state_store.get_last_signal_direction(symbol)
        
        # Step 2: 频率控制判断
        freq_control = self._evaluate_frequency_control(...)
        
        # Step 3: 计算最终executable
        executable = self._compute_executable(draft, freq_control)
        
        # Step 4: 保存状态（如果可执行）
        if executable and draft.decision in [Decision.LONG, Decision.SHORT]:
            self.state_store.save_decision_state(symbol, now, draft.decision)
        
        # Step 5: 构建Final
        return TimeframeDecisionFinal.from_draft(...)
```

---

#### Step 2: 实现频率控制判断（预估4小时）

**方法**: `_evaluate_frequency_control()`

**逻辑提取源**: `market_state_machine_l1.py::DualDecisionMemory`

**检查项**:
1. **冷却期**: 相同方向重复信号
   ```python
   if last_direction == draft.decision:
       if (now - last_time) < cooling_period:
           is_cooling = True
   ```

2. **最小间隔**: 两次决策时间间隔
   ```python
   if (now - last_time) < min_interval:
       min_interval_violated = True
   ```

3. **方向翻转**: LONG ↔ SHORT
   ```python
   if last_direction in [Decision.LONG, Decision.SHORT]:
       if draft.decision != last_direction:
           # 允许翻转，但记录
           added_tags.append(ReasonTag.DIRECTION_FLIP)
   ```

**返回**: `FrequencyControlResult`

---

#### Step 3: 实现executable计算（预估2小时）

**方法**: `_compute_executable()`

**规则**:
```python
def _compute_executable(
    draft: TimeframeDecisionDraft,
    freq_control: FrequencyControlResult
) -> bool:
    # Rule 1: NO_TRADE总是允许
    if draft.decision == Decision.NO_TRADE:
        return True
    
    # Rule 2: ExecutionPermission=DENY → 不可执行
    if draft.execution_permission == ExecutionPermission.DENY:
        return False
    
    # Rule 3: 频控阻断
    if freq_control.is_blocked:
        return False
    
    # Rule 4: 冷却期阻断
    if freq_control.is_cooling:
        return False
    
    # Rule 5: 最小间隔未到
    if freq_control.min_interval_violated:
        return False
    
    return True
```

---

#### Step 4: 实现双周期支持（预估2小时）

**方法**: `apply_dual()`

```python
def apply_dual(
    self,
    draft: DualTimeframeDecisionDraft,
    symbol: str,
    now: datetime,
    thresholds: Thresholds
) -> DualTimeframeDecisionFinal:
    """双周期频控"""
    # 分别处理短期和中期
    short_final = self.apply(
        draft.short_term, symbol, now, thresholds, Timeframe.SHORT_TERM
    )
    medium_final = self.apply(
        draft.medium_term, symbol, now, thresholds, Timeframe.MEDIUM_TERM
    )
    
    return DualTimeframeDecisionFinal(
        short_term=short_final,
        medium_term=medium_final,
        global_risk_tags=draft.global_risk_tags
    )
```

---

### M4完成验收标准

- [ ] `DecisionGate`类实现
- [ ] 频率控制逻辑完整（冷却/最小间隔/翻转）
- [ ] `apply()`和`apply_dual()`方法
- [ ] 状态保存逻辑
- [ ] 代码行数：~400行

---

## 🎯 M5: L1引擎集成（预估1天）

### 目标

在`market_state_machine_l1.py`中使用`DecisionCore`和`DecisionGate`。

### 实施步骤

#### Step 1: 初始化新组件（预估1小时）

**修改**: `L1AdvisoryEngine.__init__()`

```python
def __init__(self, config_path: str, thresholds_config_path: str):
    # 现有初始化...
    
    # PR-ARCH-02: 初始化DecisionCore和DecisionGate
    from l1_engine.decision_core import DecisionCore
    from l1_engine.decision_gate import DecisionGate
    from l1_engine.state_store import create_state_store
    
    self.decision_core = DecisionCore()  # 纯静态方法，实例化只是为了命名空间
    self.decision_gate = DecisionGate(
        state_store=create_state_store("dual")  # 双周期状态存储
    )
    
    logger.info("PR-ARCH-02: DecisionCore and DecisionGate initialized")
```

---

#### Step 2: 改造on_new_tick_dual（预估4小时）

**修改**: `L1AdvisoryEngine.on_new_tick_dual()`

**旧流程**:
```python
def on_new_tick_dual(self, symbol: str, data: Dict):
    # Step 1: 数据验证
    # Step 2: 市场环境识别
    regime = self._detect_market_regime(data)
    # Step 3: 风险准入评估
    risk_ok = self._eval_risk_exposure_allowed(data, regime)
    # Step 4: 交易质量评估
    quality = self._eval_trade_quality(symbol, data, regime)
    # Step 5-10: 方向/决策/置信度...
    # ...
    # Step N: 频率控制
    self.dual_decision_memory.check_frequency(...)
    # ...
```

**新流程**（PR-ARCH-02）:
```python
def on_new_tick_dual(self, symbol: str, data: Dict):
    # PR-ARCH-01: 特征生成
    feature_snapshot = self.feature_builder.build(symbol, data, data_cache)
    
    # PR-ARCH-02: DecisionCore评估（纯函数）
    draft = self.decision_core.evaluate_dual(
        feature_snapshot, 
        self.thresholds_typed,
        symbol
    )
    
    # PR-ARCH-02: DecisionGate应用（频控）
    final = self.decision_gate.apply_dual(
        draft, 
        symbol, 
        datetime.now(), 
        self.thresholds_typed
    )
    
    # 转换为DualTimeframeResult（向后兼容）
    return self._convert_final_to_result(final, symbol, feature_snapshot)
```

**关键改动**:
- ✅ 移除旧的决策方法调用（`_detect_market_regime`, `_eval_risk_exposure_allowed`等）
- ✅ 使用`DecisionCore.evaluate_dual()`
- ✅ 使用`DecisionGate.apply_dual()`
- ✅ 添加`_convert_final_to_result()`转换方法

---

#### Step 3: 添加转换方法（预估2小时）

**新增方法**: `L1AdvisoryEngine._convert_final_to_result()`

```python
def _convert_final_to_result(
    self,
    final: DualTimeframeDecisionFinal,
    symbol: str,
    features: FeatureSnapshot
) -> DualTimeframeResult:
    """
    将DecisionFinal转换为DualTimeframeResult（向后兼容）
    
    Args:
        final: DecisionGate输出
        symbol: 交易对符号
        features: 特征快照
    
    Returns:
        DualTimeframeResult
    """
    # 构建TimeframeConclusion
    short_conclusion = TimeframeConclusion(
        decision=final.short_term.decision,
        confidence=final.short_term.confidence,
        executable=final.short_term.executable,
        execution_permission=final.short_term.execution_permission,
        trade_quality=final.short_term.trade_quality,
        market_regime=final.short_term.market_regime,
        reason_tags=final.short_term.reason_tags,
        key_metrics=final.short_term.key_metrics
    )
    
    medium_conclusion = TimeframeConclusion(...)  # 同上
    
    # 构建AlignmentAnalysis（可选）
    alignment = self._analyze_alignment(final.short_term, final.medium_term)
    
    # 构建DualTimeframeResult
    return DualTimeframeResult(
        symbol=symbol,
        timestamp=datetime.now(),
        short_term=short_conclusion,
        medium_term=medium_conclusion,
        alignment=alignment,
        system_state=SystemState.NORMAL  # TODO: 系统状态判断
    )
```

---

#### Step 4: 保留旧方法（向后兼容）（预估1小时）

**策略**: 旧方法标记为`@deprecated`，但保留实现

```python
@deprecated("Use DecisionCore.evaluate_single() instead")
def _detect_market_regime(self, data: Dict) -> Tuple[MarketRegime, List[ReasonTag]]:
    """旧方法，保留向后兼容"""
    # 调用新方法
    feature_snapshot = self.feature_builder.build_from_dict(data)
    regime, tags = DecisionCore._detect_market_regime(
        feature_snapshot, 
        self.thresholds_typed
    )
    return regime, tags
```

---

### M5完成验收标准

- [ ] `DecisionCore`和`DecisionGate`已初始化
- [ ] `on_new_tick_dual()`已改造
- [ ] 转换方法`_convert_final_to_result()`已实现
- [ ] 旧方法标记为`@deprecated`
- [ ] Docker测试通过
- [ ] 代码行数：~150行改动

---

## 🎯 M6: 确定性单测（预估1天）

### 目标

验证`DecisionCore`的确定性和`DecisionGate`的频控逻辑。

### 实施步骤

#### Step 1: DecisionCore确定性测试（预估4小时）

**文件**: `tests/test_decision_core.py`

**测试用例**:
```python
import pytest
from l1_engine.decision_core import DecisionCore
from models.feature_snapshot import FeatureSnapshot
from models.thresholds import Thresholds
from models.enums import Decision, MarketRegime, TradeQuality

def test_decision_core_deterministic():
    """测试DecisionCore的确定性"""
    # 构造固定输入
    features = FeatureSnapshot(...)  # 固定特征
    thresholds = Thresholds(...)  # 固定阈值
    
    # 多次调用
    draft1 = DecisionCore.evaluate_single(features, thresholds)
    draft2 = DecisionCore.evaluate_single(features, thresholds)
    draft3 = DecisionCore.evaluate_single(features, thresholds)
    
    # 断言：相同输入→相同输出
    assert draft1.decision == draft2.decision == draft3.decision
    assert draft1.confidence == draft2.confidence == draft3.confidence
    assert draft1.market_regime == draft2.market_regime == draft3.market_regime
    assert draft1.trade_quality == draft2.trade_quality == draft3.trade_quality
    assert draft1.execution_permission == draft2.execution_permission == draft3.execution_permission
    assert draft1.reason_tags == draft2.reason_tags == draft3.reason_tags

def test_market_regime_detection():
    """测试市场环境识别"""
    # EXTREME情况
    features_extreme = FeatureSnapshot(...)  # price_change_1h = 0.06
    regime, tags = DecisionCore._detect_market_regime(features_extreme, thresholds)
    assert regime == MarketRegime.EXTREME
    
    # TREND情况
    features_trend = FeatureSnapshot(...)  # price_change_6h = 0.04
    regime, tags = DecisionCore._detect_market_regime(features_trend, thresholds)
    assert regime == MarketRegime.TREND
    
    # RANGE情况
    features_range = FeatureSnapshot(...)  # price_change_1h = 0.01
    regime, tags = DecisionCore._detect_market_regime(features_range, thresholds)
    assert regime == MarketRegime.RANGE

def test_risk_exposure_evaluation():
    """测试风险准入评估"""
    # EXTREME regime应该DENY
    features = FeatureSnapshot(...)
    risk_ok, tags = DecisionCore._eval_risk_exposure(
        features, MarketRegime.EXTREME, thresholds
    )
    assert risk_ok == False
    assert ReasonTag.EXTREME_REGIME in tags
    
    # 清算阶段应该DENY
    features_liquidation = FeatureSnapshot(...)  # price_change_1h=-0.06, oi_change_1h=-0.35
    risk_ok, tags = DecisionCore._eval_risk_exposure(
        features_liquidation, MarketRegime.RANGE, thresholds
    )
    assert risk_ok == False
    assert ReasonTag.LIQUIDATION_PHASE in tags

def test_trade_quality_evaluation():
    """测试交易质量评估"""
    # 吸纳风险应该POOR
    features_absorption = FeatureSnapshot(...)  # imbalance=0.8, volume_1h=low
    quality, tags = DecisionCore._eval_trade_quality(
        features_absorption, MarketRegime.RANGE, thresholds, "BTC"
    )
    assert quality == TradeQuality.POOR
    assert ReasonTag.ABSORPTION_RISK in tags

def test_direction_evaluation():
    """测试方向评估"""
    # LONG条件
    features_long = FeatureSnapshot(...)  # imbalance=0.7, oi_change=0.2, price_change=0.02
    allow_long, tags = DecisionCore._eval_long_direction(
        features_long, MarketRegime.TREND, thresholds
    )
    assert allow_long == True
    
    # SHORT条件
    features_short = FeatureSnapshot(...)  # imbalance=-0.7, oi_change=0.2, price_change=-0.02
    allow_short, tags = DecisionCore._eval_short_direction(
        features_short, MarketRegime.TREND, thresholds
    )
    assert allow_short == True
```

---

#### Step 2: DecisionGate频控测试（预估4小时）

**文件**: `tests/test_decision_gate.py`

**测试用例**:
```python
import pytest
from datetime import datetime, timedelta
from l1_engine.decision_gate import DecisionGate
from l1_engine.state_store import InMemoryStateStore
from models.decision_core_dto import TimeframeDecisionDraft
from models.enums import Decision, Confidence, Timeframe

def test_first_decision_allowed():
    """测试第一次决策总是允许"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    
    draft = TimeframeDecisionDraft(decision=Decision.LONG, ...)
    now = datetime.now()
    
    final = gate.apply(draft, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    
    assert final.executable == True
    assert final.frequency_control.is_blocked == False

def test_cooling_period_blocking():
    """测试冷却期阻断"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    
    # 第一次决策：LONG
    draft1 = TimeframeDecisionDraft(decision=Decision.LONG, ...)
    now1 = datetime.now()
    final1 = gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    assert final1.executable == True
    
    # 第二次决策：LONG（冷却期内）
    draft2 = TimeframeDecisionDraft(decision=Decision.LONG, ...)
    now2 = now1 + timedelta(seconds=60)  # 假设冷却期=600秒
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == False
    assert final2.frequency_control.is_cooling == True
    assert ReasonTag.FREQUENCY_COOLING in final2.reason_tags

def test_direction_flip_allowed():
    """测试方向翻转允许"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    
    # 第一次决策：LONG
    draft1 = TimeframeDecisionDraft(decision=Decision.LONG, ...)
    now1 = datetime.now()
    final1 = gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    
    # 第二次决策：SHORT（方向翻转）
    draft2 = TimeframeDecisionDraft(decision=Decision.SHORT, ...)
    now2 = now1 + timedelta(seconds=120)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == True  # 翻转允许
    assert ReasonTag.DIRECTION_FLIP in final2.reason_tags

def test_no_trade_always_executable():
    """测试NO_TRADE总是可执行"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    
    # 第一次决策：LONG
    draft1 = TimeframeDecisionDraft(decision=Decision.LONG, ...)
    now1 = datetime.now()
    gate.apply(draft1, "BTC", now1, thresholds, Timeframe.SHORT_TERM)
    
    # 第二次决策：NO_TRADE（冷却期内）
    draft2 = TimeframeDecisionDraft(decision=Decision.NO_TRADE, ...)
    now2 = now1 + timedelta(seconds=60)
    final2 = gate.apply(draft2, "BTC", now2, thresholds, Timeframe.SHORT_TERM)
    
    assert final2.executable == True  # NO_TRADE总是允许
```

---

### M6完成验收标准

- [ ] `test_decision_core.py`实现（~200行）
- [ ] `test_decision_gate.py`实现（~200行）
- [ ] 所有测试通过
- [ ] 覆盖率 > 80%

---

## 📋 完整交付清单

### 新增文件（6个）

- [x] `models/decision_core_dto.py` (300行) ✅
- [x] `l1_engine/state_store.py` (300行) ✅
- [x] `l1_engine/decision_core.py` (10% / 800行) ⚠️  骨架完成
- [ ] `l1_engine/decision_gate.py` (400行)
- [ ] `tests/test_decision_core.py` (200行)
- [ ] `tests/test_decision_gate.py` (200行)

### 修改文件（2个）

- [ ] `market_state_machine_l1.py` (~150行改动)
- [ ] `models/thresholds.py` (~100行扩展，添加DirectionThresholds）

---

## 🎯 验收标准（总）

### 功能验收

- [ ] **DecisionCore纯函数化**
  - [ ] 所有决策方法无`self`依赖
  - [ ] 输入：`FeatureSnapshot` + `Thresholds`
  - [ ] 输出：`DecisionDraft`
  - [ ] 确定性：相同输入→相同输出

- [ ] **DecisionGate频控**
  - [ ] 冷却期阻断
  - [ ] 最小间隔检查
  - [ ] 方向翻转允许
  - [ ] NO_TRADE总是可执行

- [ ] **L1引擎集成**
  - [ ] `on_new_tick_dual()`使用新架构
  - [ ] 向后兼容（旧方法标记为`@deprecated`）
  - [ ] Docker测试通过

- [ ] **单测覆盖**
  - [ ] DecisionCore确定性测试
  - [ ] DecisionGate频控测试
  - [ ] 覆盖率 > 80%

### 性能验收

- [ ] 决策延迟 < 50ms（纯函数优化）
- [ ] 内存占用无明显增长

### 文档验收

- [ ] DecisionCore API文档
- [ ] DecisionGate API文档
- [ ] 完成报告（PR-ARCH-02-完成报告.md）

---

## 💡 实施建议

### 优先级建议

1. **先完成M3（DecisionCore）** - 核心逻辑提取（2天）
2. **再完成M4（DecisionGate）** - 频控逻辑（1天）
3. **然后M5（集成）** - L1引擎改造（1天）
4. **最后M6（单测）** - 确定性验证（1天）

### 风险提示

⚠️  **高风险点**:
1. **交易质量评估**：噪音市检测依赖`funding_rate_prev`
   - 缓解：确认`FeatureSnapshot`包含此字段
   
2. **方向评估**：依赖`DirectionThresholds`（尚未实现）
   - 缓解：先扩展`models/thresholds.py`
   
3. **L1引擎集成**：改动较大，可能影响稳定性
   - 缓解：保留旧方法，渐进式迁移

### 测试策略

1. **单元测试**（M6）：DecisionCore和DecisionGate独立测试
2. **集成测试**（M5）：Docker环境端到端测试
3. **对比测试**：新旧架构输出对比（相同输入）

---

## 📅 时间规划

| 日期 | 工作内容 | 预期产出 |
|------|----------|----------|
| Day 1 | M3-Step1~3：市场环境/风险/质量 | ~400行代码 |
| Day 2 | M3-Step4~8：方向/优先级/费率/权限/置信度 | ~400行代码 |
| Day 3 | M4：DecisionGate实现 | ~400行代码 |
| Day 4 | M5：L1引擎集成 + Docker测试 | ~150行改动 |
| Day 5 | M6：确定性单测 + 完成报告 | ~400行测试代码 |

---

## 🎉 完成后成果

### 架构演进

**旧架构**:
```
on_new_tick_dual() {
  _detect_market_regime()  // 混在一起
  _eval_risk_exposure()
  _eval_trade_quality()
  _eval_direction()
  _compute_confidence()
  _check_frequency()  // 混在一起
}
```

**新架构**（PR-ARCH-02）:
```
on_new_tick_dual() {
  // PR-ARCH-01: 特征生成
  features = FeatureBuilder.build()
  
  // PR-ARCH-02: 决策核心（纯函数）
  draft = DecisionCore.evaluate_dual(features, thresholds)
  
  // PR-ARCH-02: 决策门控（频控）
  final = DecisionGate.apply_dual(draft, state, now, thresholds)
}
```

### 可测性提升

- ✅ DecisionCore：**100%确定性**（纯函数）
- ✅ DecisionGate：**独立可测**（频控逻辑）
- ✅ 单测覆盖率：**> 80%**

### 可演进性提升

- ✅ 决策逻辑集中（`DecisionCore`）
- ✅ 频控逻辑独立（`DecisionGate`）
- ✅ 易于添加新策略（继承`DecisionCore`）
- ✅ 易于替换频控实现（实现`StateStore`接口）

---

**报告生成时间**: 2026-01-23  
**预估完成时间**: 2026-01-28（5天后）  
**当前状态**: ⚠️  33%完成，M3-M6待实施  

🚀 **准备好继续了吗？从M3开始！**
