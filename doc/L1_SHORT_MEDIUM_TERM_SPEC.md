# L1 Advisory Layer - 短线/中线评估规范（唯一真相）

> 版本: v2.0 (P0优化后)  
> 更新日期: 2026-01-29  
> 维护者: L1 Advisory Layer Team

## 1. 概述

本文档定义 L1 Advisory Layer 中**短线(SHORT_TERM)**和**中线(MEDIUM_TERM)**评估的唯一口径。所有决策逻辑、测试用例、回测脚本必须以本文档为准。

### 1.1 核心原则

1. **数据缺失显性化**：缺失字段使用 `None`，禁止用 `0` 伪装
2. **短线使用MultiTF**：`context_1h → confirm_15m → trigger_5m` 三层触发
3. **中线使用传统逻辑**：`1h/6h` 数据驱动
4. **Permission由ReasonTagRules驱动**：`deny_tags → DENY`，`reduce_tags → ALLOW_REDUCED`
5. **Confidence由scoring+caps计算**：`tag_caps` 只限制上限，不强制降级

---

## 2. 时间框架定义

| Timeframe | 主驱动数据 | 评估逻辑 | 适用场景 |
|-----------|-----------|---------|---------|
| SHORT_TERM | 15m/5m | MultiTF三层触发 | 日内交易、短期机会 |
| MEDIUM_TERM | 1h/6h | 传统方向判定 | 波段交易、趋势跟踪 |

### 2.1 SHORT_TERM (短线)

**数据优先级**：`5m > 15m > 1h`（短周期优先）

**触发逻辑（P0-03 MultiTF）**：

```
Layer 1: Context (1h)
├── price_change_1h > 0.7% (LONG) / < -0.7% (SHORT)
├── taker_imbalance_1h > 30% (LONG) / < -30% (SHORT)
├── oi_change_1h > 3.5%
└── 要求: 3选2

Layer 2: Confirm (15m)
├── price_change_15m > 0.3% (LONG) / < -0.3% (SHORT)
├── taker_imbalance_15m > 40% (LONG) / < -40% (SHORT)
├── volume_ratio_15m > 1.2x
├── oi_change_15m > 2%
└── 要求: 4选2

Layer 3: Trigger (5m)
├── price_change_5m > 0.15% (LONG) / < -0.15% (SHORT)
├── taker_imbalance_5m > 50% (LONG) / < -50% (SHORT)
├── volume_ratio_5m > 1.5x
└── 要求: 3选2
```

**触发结果**：
- 三层全部满足 → `LTF_CONFIRMED` 标签，正常输出信号
- Context + Confirm满足，Trigger不足 → `LTF_PARTIAL_CONFIRM`，降级输出
- Confirm不足 → `LTF_FAILED_CONFIRM`，不输出信号
- Context不满足 → `LTF_CONTEXT_DENIED`，不输出信号

### 2.2 MEDIUM_TERM (中线)

**数据优先级**：`6h > 1h`（长周期优先）

**触发逻辑（传统方向判定）**：

```
TREND环境:
├── LONG: imbalance > 6% AND price_change > 0.5%
├── SHORT: imbalance < -10% AND (price_change < -1.2% OR oi_change > 0.5%)
└── 条件: LONG需2/2，SHORT需2/3

RANGE环境:
├── LONG: imbalance > 6% AND oi_change > 0.2%
├── SHORT: imbalance < -10% AND oi_change > 0.5%
└── 条件: 严格模式2/2
```

---

## 3. 数据字段规范

### 3.1 核心字段（必须）

| 字段 | 类型 | 缺失处理 | 说明 |
|------|-----|---------|------|
| price | float | 阻断(`DATA_MISSING_PRICE`) | 当前价格 |
| volume_24h | float | 降级(`DATA_MISSING_VOLUME`) | 24h成交量 |
| funding_rate | float | 降级(`DATA_MISSING_FUNDING_RATE`) | 资金费率 |

### 3.2 辅助字段（重要）

| 字段 | 类型 | 缺失处理 | 说明 |
|------|-----|---------|------|
| open_interest | float | 降级 | 持仓量 |
| taker_imbalance_1h | float | 降级 | 1h taker买卖失衡 |
| taker_imbalance_15m | float | 跳过15m层 | 15m taker买卖失衡 |
| taker_imbalance_5m | float | 跳过5m层 | 5m taker买卖失衡 |

### 3.3 百分比格式

**统一使用decimal格式**：`0.05 = 5%`

| 来源 | 输出格式 | 转换 |
|-----|---------|-----|
| data_cache | percent_point (5.0) | ÷100 → 0.05 |
| FeatureSnapshot | decimal (0.05) | 无需转换 |
| 配置文件(yaml) | decimal (0.05) | 无需转换 |

---

## 4. ExecutionPermission 规范

### 4.1 规则（P0-04）

**完全由ReasonTagRules驱动**：

```python
# 伪代码
for tag in reason_tags:
    level = REASON_TAG_EXECUTABILITY[tag]
    if level == BLOCK:
        return DENY        # 立即终止
    elif level == DEGRADE:
        has_degrade = True

if has_degrade:
    return ALLOW_REDUCED   # 有DEGRADE标签
return ALLOW               # 全是ALLOW标签
```

### 4.2 标签等级映射

| Level | 标签示例 | Permission |
|-------|---------|-----------|
| BLOCK | `INVALID_DATA`, `LIQUIDATION_PHASE`, `DATA_MISSING_PRICE` | DENY |
| DEGRADE | `NOISY_MARKET`, `DATA_MISSING_VOLUME`, `LTF_PARTIAL_CONFIRM` | ALLOW_REDUCED |
| ALLOW | `STRONG_BUY_PRESSURE`, `OI_GROWING` | ALLOW |

---

## 5. Confidence 规范

### 5.1 评分制（P0-05）

| 维度 | ULTRA | HIGH | MEDIUM | LOW |
|------|-------|------|--------|-----|
| 决策分 | 30 | 30 | 30 | 0 |
| 环境分(TREND) | 35 | 35 | 35 | 0 |
| 环境分(RANGE) | 0 | 0 | 0 | 0 |
| 质量分(GOOD) | 30 | 30 | 30 | 0 |
| 质量分(UNCERTAIN) | 15 | 15 | 15 | 0 |
| 强信号加分 | 15 | 15 | - | - |

**档位阈值**：
- ULTRA: ≥85分
- HIGH: ≥75分
- MEDIUM: ≥50分
- LOW: <50分

### 5.2 tag_caps

| 标签 | cap | 说明 |
|-----|-----|-----|
| `noisy_market` | MEDIUM | 噪音市场cap到MEDIUM |
| `weak_signal_in_range` | MEDIUM | RANGE弱信号cap到MEDIUM |
| `reduce_default_max` | MEDIUM | 所有reduce_tags的默认cap |
| `uncertain_quality_max` | MEDIUM | UNCERTAIN质量的默认cap |

**规则**：
- caps只限制上限，不强制降级
- UNCERTAIN质量不再总是LOW，参与正常评分后被cap

---

## 6. 决策管道流程

```
┌─────────────────────────────────────────────────────────────┐
│                     DecisionCore.evaluate_single            │
├─────────────────────────────────────────────────────────────┤
│ Step 1: 数据验证 (coverage.short_evaluable/medium_evaluable)│
│ Step 2: 市场环境识别 (TREND/RANGE/EXTREME)                  │
│ Step 3: 风险准入评估 (第一道闸门)                            │
│ Step 4: 交易质量评估 (第二道闸门)                            │
│ Step 5: 方向评估                                            │
│         ├── SHORT_TERM: MultiTF三层触发                     │
│         └── MEDIUM_TERM: 传统方向判定                       │
│ Step 6: 决策优先级 (SHORT > LONG > NO_TRADE)                │
│ Step 7: 资金费率降级 (TODO)                                  │
│ Step 8: 执行权限 (P0-04: ReasonTagRules驱动)                 │
│ Step 9: 置信度计算 (P0-05: scoring + caps)                   │
│ Step 10: 输出标准化 (TimeframeDecisionDraft)                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 测试验证

### 7.1 回归测试覆盖

| 场景 | 测试文件 | 验证点 |
|-----|---------|-------|
| 强短线触发 | `test_p0_signal_frequency_regression.py` | MultiTF三层全部满足 |
| 部分确认 | 同上 | Confirm弱时的降级行为 |
| 噪音市场 | 同上 | NOISY标签的cap行为 |
| 数据缺失 | 同上 | None不被0伪装 |
| 信号频率 | 同上 | 非NO_TRADE比例在10%-40% |

### 7.2 运行测试

```bash
cd /path/to/trade-info
python3 tests/test_p0_signal_frequency_regression.py
```

---

## 8. 版本历史

| 版本 | 日期 | 变更 |
|-----|------|-----|
| v1.0 | 2025-xx-xx | 初始版本 |
| v2.0 | 2026-01-29 | P0优化：DataFix, MultiTF, Permission, Caps |

---

## 9. 联系方式

如有疑问，请联系 L1 Advisory Layer Team。
