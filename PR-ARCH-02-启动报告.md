# PR-ARCH-02 启动报告（33%完成）⚠️

**实施时间**: 2026-01-23  
**PR名称**: DecisionCore纯函数化  
**状态**: ⚠️ **33%完成** (M1-M2完成，M3-M6待开始)  

---

## 📊 实施总结

### ⚠️  完成进度: 33% (2/6 Milestones)

| Milestone | 状态 | 交付物 | 预估天数 |
|-----------|------|--------|----------|
| M1: 设计DecisionDraft/DecisionFinal DTO | ✅ | models/decision_core_dto.py | 0.5天 |
| M2: 实现StateStore接口 | ✅ | l1_engine/state_store.py | 0.5天 |
| M3: 实现DecisionCore纯函数 | ⚠️ | l1_engine/decision_core.py | 2天 |
| M4: 实现DecisionGate（频控/阻断） | ⚠️ | l1_engine/decision_gate.py | 1天 |
| M5: 集成到L1引擎 | ⚠️ | 修改market_state_machine_l1.py | 1天 |
| M6: 确定性单测 | ⚠️ | tests/test_decision_core.py | 1天 |
| **总计** | **33%** | **2个新文件** | **6天** |

---

## 🎯 已完成成果

### 1. DecisionDraft/DecisionFinal DTO（M1）✅

**文件**: `models/decision_core_dto.py`

**核心DTO**:
```python
@dataclass
class TimeframeDecisionDraft:
    """决策草稿（纯函数输出）"""
    decision: Decision
    confidence: Confidence
    market_regime: MarketRegime
    trade_quality: TradeQuality
    execution_permission: ExecutionPermission
    reason_tags: List[ReasonTag]
    key_metrics: Dict[str, float]

@dataclass
class TimeframeDecisionFinal:
    """最终决策（添加频控信息）"""
    # 继承自Draft的所有字段
    ...
    # DecisionGate添加
    executable: bool
    frequency_control: FrequencyControlResult
    timeframe: Timeframe

@dataclass
class FrequencyControlState:
    """频率控制状态（最小接口）"""
    last_decision_time: Optional[datetime]
    last_signal_direction: Optional[Decision]

@dataclass
class FrequencyControlResult:
    """频率控制结果"""
    is_blocked: bool
    block_reason: Optional[str]
    is_cooling: bool
    min_interval_violated: bool
    added_tags: List[ReasonTag]
```

**设计亮点**:
- ✅ Draft vs Final明确分离
- ✅ Draft是纯逻辑输出（无时间/状态）
- ✅ Final添加频控信息
- ✅ 阻断不改写signal_decision
- ✅ 双周期支持（DualTimeframeDecisionDraft/Final）

**便捷函数**:
- `create_no_trade_draft()`: 创建NO_TRADE草稿
- `create_dual_no_trade_draft()`: 创建双周期NO_TRADE草稿
- `TimeframeDecisionFinal.from_draft()`: 从Draft构建Final

---

### 2. StateStore接口（M2）✅

**文件**: `l1_engine/state_store.py`

**抽象接口**:
```python
class StateStore(ABC):
    """状态存储接口（最小接口）"""
    
    @abstractmethod
    def save_decision_state(
        self, symbol: str, decision_time: datetime, signal_direction: Decision
    ) -> None:
        pass
    
    @abstractmethod
    def get_last_decision_time(self, symbol: str) -> Optional[datetime]:
        pass
    
    @abstractmethod
    def get_last_signal_direction(self, symbol: str) -> Optional[Decision]:
        pass
    
    @abstractmethod
    def clear(self, symbol: Optional[str] = None) -> None:
        pass
```

**实现类**:
1. **InMemoryStateStore**（默认）:
   - 使用dict存储
   - 不持久化
   - 适合快速迭代

2. **DualTimeframeStateStore**（双周期）:
   - 分别保存短期/中期状态
   - 支持独立频控
   - 扩展方法：save_short/save_medium

**设计亮点**:
- ✅ 最小接口：只保存last_decision_time和last_signal_direction
- ✅ 不引入持仓语义：只记录决策，不记录持仓
- ✅ 可替换实现：内存/Redis/数据库
- ✅ 多symbol支持

**工厂函数**:
```python
def create_state_store(store_type: str = "memory") -> StateStore:
    if store_type == "memory":
        return InMemoryStateStore()
    elif store_type == "dual":
        return DualTimeframeStateStore()
```

---

## 📈 架构设计（已完成部分）

### 设计1: Draft vs Final分离 ✅

**旧方式**（决策和频控混在一起）:
```python
def on_new_tick(symbol, data):
    # 决策逻辑
    decision = _evaluate(...) 
    
    # 频控逻辑（混在一起）
    if is_cooling(...):
        decision = Decision.NO_TRADE
    
    # 最小间隔（混在一起）
    if time_since_last < min_interval:
        executable = False
    
    return AdvisoryResult(...)
```

**新方式**（分离为两层）:
```python
def on_new_tick(symbol, data):
    # Layer 1: DecisionCore（纯函数）
    draft = DecisionCore.evaluate(features, thresholds)
    
    # Layer 2: DecisionGate（频控）
    final = DecisionGate.apply(draft, state, now, thresholds)
    
    return AdvisoryResult.from_final(final)
```

**收益**:
- ✅ DecisionCore可确定性单测（相同输入→相同输出）
- ✅ DecisionGate独立测试（频控逻辑单独验证）
- ✅ 职责清晰（策略 vs 频控）

### 设计2: 最小StateStore接口 ✅

**旧方式**（状态散落各处）:
```python
class L1AdvisoryEngine:
    def __init__(self):
        self.decision_memory = DecisionMemory()  # 复杂状态
        self.dual_decision_memory = DualDecisionMemory()  # 更复杂
        # 状态耦合在引擎内部
```

**新方式**（最小接口）:
```python
class StateStore(ABC):
    @abstractmethod
    def save_decision_state(symbol, time, direction): pass
    
    @abstractmethod
    def get_last_decision_time(symbol): pass
    
    @abstractmethod
    def get_last_signal_direction(symbol): pass
```

**收益**:
- ✅ 接口最小化（只保存必需信息）
- ✅ 不引入持仓语义
- ✅ 可替换实现（内存/Redis/数据库）

---

## ⚠️  待完成工作（67%）

### M3: 实现DecisionCore纯函数（预估2天）⚠️

**目标**:
```python
class DecisionCore:
    """决策核心（纯函数，无时间/状态/IO）"""
    
    @staticmethod
    def evaluate_single(
        features: FeatureSnapshot,
        thresholds: Thresholds
    ) -> TimeframeDecisionDraft:
        """单周期决策评估（纯函数）"""
        # Step 1: 市场环境识别
        regime = _detect_market_regime(features, thresholds)
        
        # Step 2: 风险准入评估
        risk_ok, risk_tags = _eval_risk_exposure(features, regime, thresholds)
        if not risk_ok:
            return create_no_trade_draft(risk_tags, regime)
        
        # Step 3: 交易质量评估
        quality, quality_tags = _eval_trade_quality(features, regime, thresholds)
        
        # Step 4: 方向评估
        direction, direction_tags = _eval_direction(features, regime, quality, thresholds)
        
        # Step 5: 置信度评分
        confidence = _score_confidence(features, regime, quality, direction, thresholds)
        
        # Step 6: 执行权限（策略层）
        execution_permission = _determine_execution_permission(
            regime, quality, confidence, thresholds
        )
        
        return TimeframeDecisionDraft(
            decision=direction,
            confidence=confidence,
            market_regime=regime,
            trade_quality=quality,
            execution_permission=execution_permission,
            reason_tags=risk_tags + quality_tags + direction_tags,
            key_metrics={}
        )
```

**关键原则**:
- ✅ 纯函数：相同输入→相同输出
- ✅ 无时间：不依赖`datetime.now()`
- ✅ 无状态：不依赖历史决策
- ✅ 无IO：不读取数据库/Redis

### M4: 实现DecisionGate（预估1天）⚠️

**目标**:
```python
class DecisionGate:
    """决策门控（频控/冷却/阻断）"""
    
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
        """应用频率控制（添加时间/状态依赖）"""
        # Step 1: 获取历史状态
        last_time = self.state_store.get_last_decision_time(symbol)
        last_direction = self.state_store.get_last_signal_direction(symbol)
        
        # Step 2: 频率控制判断
        freq_control = self._evaluate_frequency_control(
            draft, last_time, last_direction, now, thresholds, timeframe
        )
        
        # Step 3: 计算最终executable
        executable = self._compute_executable(draft, freq_control)
        
        # Step 4: 保存状态（如果可执行）
        if executable and draft.decision in [Decision.LONG, Decision.SHORT]:
            self.state_store.save_decision_state(symbol, now, draft.decision)
        
        # Step 5: 构建Final
        return TimeframeDecisionFinal.from_draft(
            draft, executable, freq_control, timeframe
        )
```

**关键规则**:
- ✅ 阻断时不改写signal_decision
- ✅ 只通过executable/execution_permission表达
- ✅ 冷却期：相同方向重复信号
- ✅ 最小间隔：两次决策时间间隔

### M5: 集成到L1引擎（预估1天）⚠️

**目标**:
```python
class L1AdvisoryEngine:
    def __init__(self):
        # PR-ARCH-02: 初始化新组件
        self.decision_core = DecisionCore()
        self.decision_gate = DecisionGate(
            state_store=create_state_store("dual")
        )
    
    def on_new_tick_dual(self, symbol: str, data: Dict):
        # PR-ARCH-01: 特征生成
        feature_snapshot = self.feature_builder.build(symbol, data, data_cache)
        
        # PR-ARCH-02: DecisionCore评估
        draft = self.decision_core.evaluate_dual(
            feature_snapshot, self.thresholds_typed
        )
        
        # PR-ARCH-02: DecisionGate应用
        final = self.decision_gate.apply_dual(
            draft, symbol, datetime.now(), self.thresholds_typed
        )
        
        return DualTimeframeResult.from_final(final)
```

### M6: 确定性单测（预估1天）⚠️

**目标**:
```python
def test_decision_core_deterministic():
    """测试DecisionCore的确定性"""
    # 构造固定输入
    features = FeatureSnapshot(...)
    thresholds = Thresholds(...)
    
    # 多次调用
    draft1 = DecisionCore.evaluate_single(features, thresholds)
    draft2 = DecisionCore.evaluate_single(features, thresholds)
    
    # 断言：相同输入→相同输出
    assert draft1.decision == draft2.decision
    assert draft1.confidence == draft2.confidence
    assert draft1.reason_tags == draft2.reason_tags

def test_decision_gate_frequency_control():
    """测试DecisionGate的频率控制"""
    state_store = InMemoryStateStore()
    gate = DecisionGate(state_store)
    
    # 第一次决策：LONG
    draft1 = TimeframeDecisionDraft(decision=Decision.LONG, ...)
    final1 = gate.apply(draft1, "BTC", now, thresholds, Timeframe.SHORT_TERM)
    
    # 第二次决策：LONG（冷却期内）
    draft2 = TimeframeDecisionDraft(decision=Decision.LONG, ...)
    final2 = gate.apply(draft2, "BTC", now + timedelta(seconds=60), thresholds, Timeframe.SHORT_TERM)
    
    # 断言：冷却期内被阻断
    assert final1.executable == True
    assert final2.executable == False
    assert final2.frequency_control.is_cooling == True
```

---

## 📊 统计数据

### 已完成代码量
- 新增代码: ~600行
- models/decision_core_dto.py: ~300行
- l1_engine/state_store.py: ~300行

### 待完成代码量（预估）
- l1_engine/decision_core.py: ~800行
- l1_engine/decision_gate.py: ~400行
- market_state_machine_l1.py改动: ~150行
- tests/test_decision_core.py: ~400行
- **总计**: ~1750行

---

## 💡 后续建议

### 短期（继续M3-M6）

**选项A: 完成M3（DecisionCore）**（推荐）
- 提取现有决策逻辑为纯函数
- 预估: 2天
- 收益: 决策逻辑可确定性单测

**选项B: 暂停，先合并PR-ARCH-01+03**
- 提交当前两个完整PR
- 等待反馈后继续
- 收益: 渐进式合并，降低风险

### 中期（完成PR-ARCH-02）

完成M3-M6后：
- ✅ 决策核心纯函数化
- ✅ 频控逻辑独立
- ✅ 确定性单测覆盖
- ✅ 线上/回测/测试共用DecisionCore

---

## ✅ 阶段性完成声明

**PR-ARCH-02（DecisionCore纯函数化）已完成33%！**

### 交付清单（M1-M2）✅
- ✅ DecisionDraft/DecisionFinal DTO（300+行）
- ✅ StateStore接口（300+行）
- ✅ 抽象接口设计
- ✅ 内存/双周期实现

### 待完成清单（M3-M6）⚠️
- ⚠️ DecisionCore纯函数实现
- ⚠️ DecisionGate频控实现
- ⚠️ L1引擎集成
- ⚠️ 确定性单测

---

**报告完成时间**: 2026-01-23 16:00  
**PR状态**: ⚠️ **33%完成** (M1-M2✅, M3-M6⚠️)  
**下一步**: 继续M3或暂停合并已完成PR  

⚠️  PR-ARCH-02基础设施就绪，等待继续或暂停指令！
