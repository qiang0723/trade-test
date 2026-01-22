# PR-DUAL: 双周期独立结论架构

**版本**: 1.0  
**日期**: 2026-01-21  
**状态**: ✅ 已实现

---

## 📋 设计原则

根据L1设计原则重申：

> 在不自动下单的前提下，用一致口径的数据与成熟的合约交易逻辑，快速、稳定、可解释地输出"现在是否存在可操作的市场机会"，并给出明确结论：做多 / 做空 / 不操作（以及是否可执行的分级）。

**核心要求**：

1. **双周期独立评估**：短期（5m/15m）与中长期（1h/6h）各自独立的交易结论
2. **一致性分析**：明确说明两者是否一致、是否可执行
3. **冲突处理规则**：当两者冲突时，提供明确的处理策略
4. **向后兼容**：保留单一决策输出，供现有系统使用

---

## 🏗️ 架构设计

### 数据结构

```
┌─────────────────────────────────────────────────────────────────┐
│                      DualTimeframeResult                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │ TimeframeConclusion │    │ TimeframeConclusion │             │
│  │   (SHORT_TERM)      │    │   (MEDIUM_TERM)     │             │
│  ├─────────────────────┤    ├─────────────────────┤             │
│  │ timeframe: 5m/15m   │    │ timeframe: 1h/6h    │             │
│  │ decision: LONG      │    │ decision: LONG      │             │
│  │ confidence: HIGH    │    │ confidence: MEDIUM  │             │
│  │ executable: true    │    │ executable: false   │             │
│  │ reason_tags: [...]  │    │ reason_tags: [...]  │             │
│  │ key_metrics: {...}  │    │ key_metrics: {...}  │             │
│  └─────────────────────┘    └─────────────────────┘             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              AlignmentAnalysis                        │       │
│  ├──────────────────────────────────────────────────────┤       │
│  │ is_aligned: true                                      │       │
│  │ alignment_type: BOTH_LONG                             │       │
│  │ has_conflict: false                                   │       │
│  │ recommended_action: LONG                              │       │
│  │ recommended_confidence: HIGH                          │       │
│  │ recommendation_notes: "✅ 双周期一致看多"              │       │
│  └──────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

### 核心类

#### 1. `TimeframeConclusion`

单个时间周期的交易结论。

```python
@dataclass
class TimeframeConclusion:
    timeframe: Timeframe              # SHORT_TERM | MEDIUM_TERM
    timeframe_label: str              # "5m/15m" | "1h/6h"
    decision: Decision                # LONG | SHORT | NO_TRADE
    confidence: Confidence            # ULTRA | HIGH | MEDIUM | LOW
    market_regime: MarketRegime       # TREND | RANGE | EXTREME
    trade_quality: TradeQuality       # GOOD | UNCERTAIN | POOR
    execution_permission: ExecutionPermission
    executable: bool
    reason_tags: List[ReasonTag]
    key_metrics: Dict                 # 该周期使用的关键指标
```

#### 2. `AlignmentAnalysis`

双周期一致性分析。

```python
@dataclass
class AlignmentAnalysis:
    is_aligned: bool                  # 两者方向是否一致
    alignment_type: AlignmentType     # 一致性类型
    has_conflict: bool                # 是否存在方向冲突
    conflict_resolution: Optional[ConflictResolution]
    resolution_reason: str
    recommended_action: Decision      # 综合建议
    recommended_confidence: Confidence
    recommendation_notes: str
```

#### 3. `DualTimeframeResult`

最终输出结果。

```python
@dataclass
class DualTimeframeResult:
    short_term: TimeframeConclusion   # 短期结论
    medium_term: TimeframeConclusion  # 中长期结论
    alignment: AlignmentAnalysis      # 一致性分析
    symbol: str
    timestamp: datetime
    risk_exposure_allowed: bool       # 全局风险准入
    global_risk_tags: List[ReasonTag]
```

---

## 🎯 枚举定义

### AlignmentType（一致性类型）

```python
class AlignmentType(Enum):
    BOTH_LONG = "both_long"                    # 一致看多
    BOTH_SHORT = "both_short"                  # 一致看空
    BOTH_NO_TRADE = "both_no_trade"            # 一致不交易
    CONFLICT_LONG_SHORT = "conflict_long_short"  # 冲突：短期多/中长期空
    CONFLICT_SHORT_LONG = "conflict_short_long"  # 冲突：短期空/中长期多
    PARTIAL_LONG = "partial_long"              # 部分看多
    PARTIAL_SHORT = "partial_short"            # 部分看空
```

### ConflictResolution（冲突处理策略）

```python
class ConflictResolution(Enum):
    FOLLOW_MEDIUM_TERM = "follow_medium_term"      # 跟随中长期（更稳健）
    FOLLOW_SHORT_TERM = "follow_short_term"        # 跟随短期（更激进）
    NO_TRADE = "no_trade"                          # 冲突时不交易（最保守）
    FOLLOW_HIGHER_CONFIDENCE = "follow_higher_confidence"  # 跟随置信度更高的一方
```

---

## ⚙️ 配置项

### `config/l1_thresholds.yaml`

```yaml
dual_timeframe:
  enabled: true
  
  # 短期评估（5m/15m）阈值
  short_term:
    min_price_change_15m: 0.003    # 0.3%
    min_taker_imbalance: 0.40      # 40%
    min_volume_ratio: 1.2          # 1.2倍
    required_signals: 3            # 4选3触发
  
  # 冲突处理策略
  conflict_resolution:
    default_strategy: "no_trade"   # no_trade | follow_medium_term | follow_short_term | follow_higher_confidence
  
  # 一致性加成
  alignment_bonus:
    confidence_boost: 1            # 提升1档
    relax_executable_threshold: false
```

---

## 🔄 决策流程

### 1. 全局风险评估

```
数据验证 → 市场环境识别 → 全局风险检查
                                ↓
                          EXTREME / 风险拒绝？
                                ↓ YES
                    返回双NO_TRADE结果
                                ↓ NO
                        继续双周期评估
```

### 2. 短期评估（5m/15m）

**数据源**：
- `price_change_5m`, `price_change_15m`
- `taker_imbalance_5m`, `taker_imbalance_15m`
- `volume_ratio_5m`, `volume_ratio_15m`

**信号判断**（4选N）：
- ✅ 15m价格变化 > 0.3%
- ✅ 15m taker失衡 > 40%
- ✅ 15m放量比率 > 1.2x
- ✅ 5m确认（价格 + 失衡同向）

**决策**：
- LONG: `long_signals >= 3` 且 `long_signals > short_signals`
- SHORT: `short_signals >= 3` 且 `short_signals > long_signals`
- NO_TRADE: 信号不足

### 3. 中长期评估（1h/6h）

**数据源**：
- `price_change_1h`, `price_change_6h`
- `oi_change_1h`, `oi_change_6h`
- `buy_sell_imbalance`, `funding_rate`

**方向判断**：
- 复用现有的 `_eval_long_direction()` 和 `_eval_short_direction()`
- 包含资金费率降级、OI辅助判断等成熟逻辑

### 4. 一致性分析

| 短期 | 中长期 | 一致性类型 | 处理策略 |
|------|--------|-----------|---------|
| LONG | LONG | BOTH_LONG | ✅ 一致，可执行 |
| SHORT | SHORT | BOTH_SHORT | ✅ 一致，可执行 |
| LONG | SHORT | CONFLICT_LONG_SHORT | ⚠️ 冲突，按配置处理 |
| SHORT | LONG | CONFLICT_SHORT_LONG | ⚠️ 冲突，按配置处理 |
| LONG | NO_TRADE | PARTIAL_LONG | ⚠️ 部分确认，降级 |
| NO_TRADE | LONG | PARTIAL_LONG | 中长期信号，等待短期确认 |

---

## 📡 API接口

### 新增端点

```
GET /api/l1/advisory-dual/{symbol}
```

**Response**:

```json
{
  "success": true,
  "data": {
    "short_term": {
      "timeframe": "short_term",
      "timeframe_label": "5m/15m",
      "decision": "long",
      "confidence": "high",
      "executable": true,
      "market_regime": "trend",
      "trade_quality": "good",
      "execution_permission": "allow",
      "reason_tags": ["strong_buy_pressure", "short_term_price_surge"],
      "key_metrics": {
        "price_change_5m": 0.005,
        "price_change_15m": 0.008,
        "taker_imbalance_15m": 0.60
      }
    },
    "medium_term": {
      "timeframe": "medium_term",
      "timeframe_label": "1h/6h",
      "decision": "long",
      "confidence": "medium",
      "executable": false,
      "market_regime": "trend",
      "trade_quality": "uncertain",
      "execution_permission": "allow_reduced",
      "reason_tags": ["trend_long", "oi_growing"],
      "key_metrics": {
        "price_change_1h": 0.02,
        "price_change_6h": 0.05,
        "oi_change_1h": 0.015
      }
    },
    "alignment": {
      "is_aligned": true,
      "alignment_type": "both_long",
      "has_conflict": false,
      "conflict_resolution": null,
      "resolution_reason": "",
      "recommended_action": "long",
      "recommended_confidence": "high",
      "recommendation_notes": "✅ 双周期一致看多，信号强度高"
    },
    "symbol": "BTC",
    "timestamp": "2026-01-21T15:30:45.123456",
    "risk_exposure_allowed": true,
    "global_risk_tags": [],
    
    // 向后兼容字段
    "decision": "long",
    "confidence": "high",
    "executable": true,
    "reason_tags": ["strong_buy_pressure", "trend_long", "oi_growing"],
    "market_regime": "trend"
  }
}
```

---

## 🖥️ Web界面

### 新增页面

```
http://localhost:8001/dual
```

**功能**：
- 左右分栏展示短期和中长期结论
- 底部展示一致性分析和综合建议
- 实时刷新（30秒）
- 支持多币种切换

---

## 🧪 测试覆盖

### 测试文件

`tests/test_pr_dual_timeframe.py`

**测试用例**：

1. ✅ `test_dual_both_long()` - 双周期一致看多
2. ✅ `test_dual_both_short()` - 双周期一致看空
3. ✅ `test_dual_conflict_long_short()` - 短期多/中长期空冲突
4. ✅ `test_dual_partial_long()` - 仅短期看多
5. ✅ `test_dual_global_risk_denial()` - 全局风险拒绝
6. ✅ `test_dual_backward_compatibility()` - 向后兼容性

**运行测试**：

```bash
# 本地
python tests/test_pr_dual_timeframe.py

# Docker
docker exec l1-advisory-layer python tests/test_pr_dual_timeframe.py
```

---

## 🚀 使用示例

### Python代码

```python
from market_state_machine_l1 import L1AdvisoryEngine

engine = L1AdvisoryEngine()

# 准备市场数据（需包含多周期数据）
data = {
    'price': 50000,
    'timestamp': 1234567890,
    # 短期数据
    'price_change_5m': 0.005,
    'price_change_15m': 0.008,
    'taker_imbalance_5m': 0.50,
    'taker_imbalance_15m': 0.60,
    'volume_ratio_5m': 1.5,
    'volume_ratio_15m': 1.8,
    # 中长期数据
    'price_change_1h': 0.02,
    'price_change_6h': 0.05,
    'oi_change_1h': 0.015,
    'oi_change_6h': 0.03,
    'buy_sell_imbalance': 0.40,
    'funding_rate': 0.0001,
    'volume_1h': 1000000,
    'volume_24h': 20000000,
}

# 调用双周期决策
result = engine.on_new_tick_dual('BTC', data)

# 查看结果
print(result.get_summary())
# 输出: 短期(5m/15m): LONG | 中长期(1h/6h): LONG | ✅ 一致 (both_long) | 可执行

# 访问各部分
print(f"短期决策: {result.short_term.decision.value}")
print(f"中长期决策: {result.medium_term.decision.value}")
print(f"综合建议: {result.alignment.recommended_action.value}")
print(f"一致性: {result.alignment.is_aligned}")
```

### API调用

```bash
# 获取BTC的双周期决策
curl http://localhost:8001/api/l1/advisory-dual/BTC | python3 -m json.tool
```

---

## 📊 冲突处理策略对比

| 策略 | 适用场景 | 风险等级 | 说明 |
|------|---------|---------|------|
| `no_trade` | 保守型交易者 | 🟢 低 | 冲突时不交易，等待一致（默认） |
| `follow_medium_term` | 趋势交易者 | 🟡 中 | 跟随中长期趋势，忽略短期波动 |
| `follow_short_term` | 日内交易者 | 🔴 高 | 捕捉短期机会，可能逆趋势 |
| `follow_higher_confidence` | 灵活型交易者 | 🟡 中 | 跟随置信度更高的一方 |

**配置修改**：

```yaml
# config/l1_thresholds.yaml
dual_timeframe:
  conflict_resolution:
    default_strategy: "follow_medium_term"  # 修改为跟随中长期
```

---

## 🔄 向后兼容

### 现有API不受影响

- ✅ `/api/l1/advisory/{symbol}` 继续使用单一决策流程
- ✅ 现有前端页面 `/` 不受影响
- ✅ 数据库结构不变（双周期结果不持久化）

### 迁移路径

1. **阶段1**（当前）：双周期API和UI独立运行，现有系统不变
2. **阶段2**（未来）：根据回测结果，决定是否替换单一决策
3. **阶段3**（可选）：统一为双周期输出，旧API返回兼容格式

---

## 📝 待办事项

### 已完成 ✅

- [x] 数据结构设计（TimeframeConclusion, AlignmentAnalysis, DualTimeframeResult）
- [x] 枚举定义（AlignmentType, ConflictResolution）
- [x] 核心引擎方法（`on_new_tick_dual()`）
- [x] 短期评估逻辑（`_evaluate_short_term()`）
- [x] 中长期评估逻辑（`_evaluate_medium_term()`）
- [x] 一致性分析（`_analyze_alignment()`）
- [x] API端点（`/api/l1/advisory-dual/{symbol}`）
- [x] 配置项（`dual_timeframe` section）
- [x] 测试用例（`test_pr_dual_timeframe.py`）
- [x] Web UI（`index_l1_dual.html`）
- [x] 文档（本文档）

### 待验证 🔄

- [ ] 生产环境测试（AWS部署）
- [ ] 多币种验证（BTC, ETH, SOL等）
- [ ] 不同冲突策略的回测对比
- [ ] 性能测试（双周期计算耗时）

### 未来优化 💡

- [ ] 数据库持久化双周期结果（可选）
- [ ] 历史一致性分析统计
- [ ] 冲突频率监控
- [ ] 自适应冲突策略（根据历史表现动态调整）

---

## 🎯 总结

PR-DUAL实现了L1设计原则中的核心要求：

1. ✅ **双周期独立评估**：短期和中长期各自独立计算
2. ✅ **一致性分析**：明确说明是否一致、是否冲突
3. ✅ **冲突处理规则**：4种策略可配置
4. ✅ **向后兼容**：现有系统不受影响
5. ✅ **可追溯性**：每个周期都有reason_tags和key_metrics
6. ✅ **工程化**：完整的测试、文档、UI

**设计亮点**：

- 🎯 **清晰的职责分离**：短期捕捉快速机会，中长期跟随趋势
- 🛡️ **安全优先**：全局风险拒绝优先于双周期评估
- ⚙️ **高度可配置**：阈值、策略都可外部化配置
- 📊 **可视化友好**：专用UI直观展示双周期结论
- 🧪 **测试完备**：覆盖一致、冲突、部分确认等场景

---

**版本历史**：

- **v1.0** (2026-01-21): 初始实现，完成核心功能和测试
