# L1 Advisory Layer - 完整测试套件

## 测试目标
确保L1决策系统的**数据准确性**和**决策可靠性**，所有测试用例必须固定并可回归验证。

---

## 测试分类

### 📊 **分类1: P0级别Bug修复测试**
| 测试文件 | 测试内容 | 状态 |
|---------|---------|------|
| `test_p0_percentage_scale_bugfix.py` | 百分比口径统一（小幅变化不被放大100倍） | ✅ 完成 |
| `test_p0_volume_scale_bugfix.py` | 成交量计算修正（差值而非累加） | ✅ 完成 |
| `test_p0_volume_unit_bugfix.py` | 单位一致性（BTC vs BTC） | ✅ 完成 |
| `test_p0_required_fields_bugfix.py` | 字段完整性（price_change_6h/oi_change_6h必填） | ✅ 完成 |

### 🔧 **分类2: 数据验证测试**
| 测试文件 | 测试内容 | 状态 |
|---------|---------|------|
| `test_data_validation_completeness.py` | 必填字段完整性校验 | ⚠️ 待创建 |
| `test_data_validation_ranges.py` | 数值合理性范围检查 | ⚠️ 待创建 |
| `test_data_normalization.py` | 指标口径规范化 | ⚠️ 待创建 |
| `test_data_type_safety.py` | 数据类型安全检查 | ⚠️ 待创建 |

### 🎯 **分类3: 决策逻辑测试**
| 测试文件 | 测试内容 | 状态 |
|---------|---------|------|
| `test_market_regime_detection.py` | 市场环境识别（TREND/RANGE/EXTREME） | ⚠️ 待创建 |
| `test_risk_gates.py` | 风险闸门（清算、拥挤、极端成交量） | ⚠️ 待创建 |
| `test_trade_quality_evaluation.py` | 交易质量评估（GOOD/UNCERTAIN/POOR） | ⚠️ 待创建 |
| `test_direction_assessment.py` | 方向评估（LONG/SHORT/NO_TRADE） | ⚠️ 待创建 |
| `test_confidence_calculation.py` | 置信度计算（混合模式） | ⚠️ 待创建 |
| `test_execution_permission.py` | 执行许可（ALLOW/ALLOW_REDUCED/DENY） | ✅ 完成 |

### 🚨 **分类4: 边界和异常测试**
| 测试文件 | 测试内容 | 状态 |
|---------|---------|------|
| `test_extreme_market_conditions.py` | 极端市场条件（暴涨暴跌、闪崩） | ⚠️ 待创建 |
| `test_edge_cases_small_values.py` | 边界条件（小值：0.1%, 0.01%） | ⚠️ 待创建 |
| `test_edge_cases_large_values.py` | 边界条件（大值：50%, 100%） | ⚠️ 待创建 |
| `test_missing_optional_fields.py` | 可选字段缺失处理 | ⚠️ 待创建 |
| `test_zero_values.py` | 零值处理 | ⚠️ 待创建 |
| `test_negative_values.py` | 负值处理（成交量、价格） | ⚠️ 待创建 |

### 🔄 **分类5: 集成和端到端测试**
| 测试文件 | 测试内容 | 状态 |
|---------|---------|------|
| `test_end_to_end_long_scenario.py` | 完整做多场景 | ⚠️ 待创建 |
| `test_end_to_end_short_scenario.py` | 完整做空场景 | ⚠️ 待创建 |
| `test_end_to_end_no_trade_scenario.py` | 完整拒绝交易场景 | ⚠️ 待创建 |
| `test_decision_memory_integration.py` | 决策记忆集成（冷却期、最小间隔） | ⚠️ 待创建 |
| `test_database_integration.py` | 数据库集成 | ✅ 部分完成 |

### 📈 **分类6: 真实数据回放测试**
| 测试文件 | 测试内容 | 状态 |
|---------|---------|------|
| `test_real_data_replay_bull_market.py` | 牛市真实数据回放 | ⚠️ 待创建 |
| `test_real_data_replay_bear_market.py` | 熊市真实数据回放 | ⚠️ 待创建 |
| `test_real_data_replay_sideways.py` | 震荡市真实数据回放 | ⚠️ 待创建 |
| `test_real_data_replay_liquidation.py` | 清算事件真实数据回放 | ⚠️ 待创建 |

### 🎨 **分类7: 配置和启动测试**
| 测试文件 | 测试内容 | 状态 |
|---------|---------|------|
| `test_calibration_validation.py` | 校准验证（小数格式） | ✅ 完成 |
| `test_threshold_consistency.py` | 门槛一致性 | ✅ 完成 |
| `test_reason_tag_spelling.py` | ReasonTag拼写验证 | ✅ 完成 |
| `test_confidence_value_validation.py` | Confidence值验证 | ✅ 完成 |

---

## 测试用例固化原则

### 1. 每个测试必须包含
```python
- 测试名称：清晰描述测试场景
- 输入数据：固定的、可重现的输入
- 预期输出：明确的断言
- 失败说明：为什么失败、影响范围
```

### 2. 测试数据标准
```python
- 使用真实量级的数据（BTC价格50000, 成交量100-2400）
- 百分比统一使用百分比点格式（5.0 = 5%）
- 所有字段完整提供
- 包含边界值（0.1%, 0.5%, 50%, 100%）
```

### 3. 断言标准
```python
- 精确断言：decision == Decision.LONG
- 范围断言：0.95 <= confidence_score <= 1.0
- 包含断言：ReasonTag.CROWDING_RISK in reason_tags
- 排除断言：ReasonTag.INVALID_DATA not in reason_tags
```

### 4. 测试隔离
```python
- 每个测试独立运行
- 不依赖外部状态
- 使用fresh engine实例
- 清理测试数据
```

---

## 运行所有测试

### 方式1: 运行所有测试
```bash
cd /Users/wangqiang/learning/trade-info
python -m pytest tests/ -v
```

### 方式2: 运行指定分类
```bash
# P0修复测试
python -m pytest tests/test_p0_*.py -v

# 数据验证测试
python -m pytest tests/test_data_*.py -v

# 决策逻辑测试
python -m pytest tests/test_market_*.py tests/test_risk_*.py -v
```

### 方式3: 运行单个测试
```bash
python tests/test_p0_percentage_scale_bugfix.py
```

---

## 测试覆盖率要求

| 模块 | 覆盖率目标 | 当前状态 |
|-----|----------|---------|
| `market_state_machine_l1.py` | 90% | 待评估 |
| `binance_data_fetcher.py` | 80% | 待评估 |
| `data_cache.py` | 85% | 待评估 |
| `metrics_normalizer.py` | 95% | 待评估 |
| `models/` | 100% | 待评估 |

---

## 测试维护规范

### 新增功能时
1. 必须同时编写测试用例
2. 测试用例必须通过才能合并
3. 更新本文档的测试清单

### 发现Bug时
1. 先写失败的测试用例（重现bug）
2. 修复bug
3. 确保测试通过
4. 添加到P0测试分类

### 定期回归
- 每次代码提交前：运行所有测试
- 每日自动化：运行完整测试套件
- 每周review：测试覆盖率和失败case

---

## 测试数据模板

### 标准完整数据
```python
STANDARD_COMPLETE_DATA = {
    'price': 50000,
    'price_change_1h': 0.5,    # 0.5% (百分比点)
    'price_change_6h': 2.0,    # 2% (百分比点)
    'volume_1h': 100,          # BTC
    'volume_24h': 2400,        # BTC
    'buy_sell_imbalance': 0.3,
    'funding_rate': 0.01,      # 0.01% (百分比点)
    'oi_change_1h': 1.0,       # 1% (百分比点)
    'oi_change_6h': 5.0        # 5% (百分比点)
}
```

### 极端市场数据模板
```python
EXTREME_BULL_DATA = {
    'price': 52000,
    'price_change_1h': 8.0,    # 8% 暴涨
    'price_change_6h': 15.0,   # 15% 持续上涨
    'volume_1h': 1500,         # 15倍平均成交量
    'volume_24h': 2400,
    'buy_sell_imbalance': 0.85,  # 极端做多
    'funding_rate': 0.15,      # 0.15% 极高费率
    'oi_change_1h': 10.0,      # 10% OI增长
    'oi_change_6h': 25.0       # 25% OI增长（拥挤）
}

LIQUIDATION_DATA = {
    'price': 48000,
    'price_change_1h': -5.0,   # -5% 急跌
    'price_change_6h': -8.0,   # -8%
    'volume_1h': 800,          # 8倍成交量
    'volume_24h': 2400,
    'buy_sell_imbalance': -0.75,  # 恐慌卖出
    'funding_rate': -0.08,     # 负费率
    'oi_change_1h': -15.0,     # -15% OI下降（清算）
    'oi_change_6h': -20.0      # -20%
}
```

### 边界值数据模板
```python
SMALL_CHANGE_DATA = {
    # 测试小幅变化（P0-BugFix-1 场景）
    'price': 50000,
    'price_change_1h': 0.1,    # 0.1% 微小变化
    'price_change_6h': 0.5,    # 0.5%
    'volume_1h': 100,
    'volume_24h': 2400,
    'buy_sell_imbalance': 0.05,
    'funding_rate': 0.001,     # 0.001%
    'oi_change_1h': 0.1,       # 0.1%
    'oi_change_6h': 0.5        # 0.5%
}

ZERO_CHANGE_DATA = {
    # 测试零变化（完全平稳）
    'price': 50000,
    'price_change_1h': 0.0,
    'price_change_6h': 0.0,
    'volume_1h': 100,
    'volume_24h': 2400,
    'buy_sell_imbalance': 0.0,
    'funding_rate': 0.0,
    'oi_change_1h': 0.0,
    'oi_change_6h': 0.0
}
```

---

## 测试失败处理流程

1. **本地失败**
   - 查看详细错误信息
   - 检查输入数据是否正确
   - 逐步调试定位问题

2. **CI失败**
   - 查看CI日志
   - 本地重现失败场景
   - 修复后重新提交

3. **回归失败**
   - 立即回滚代码
   - 创建bug issue
   - 修复后重新测试

---

## 当前测试完成度

### ✅ 已完成（4个P0测试）
- `test_p0_percentage_scale_bugfix.py`
- `test_p0_volume_scale_bugfix.py`
- `test_p0_volume_unit_bugfix.py`
- `test_p0_required_fields_bugfix.py`

### ⚠️ 待补充（优先级排序）
**P1 - 近期必须完成：**
1. `test_data_validation_completeness.py`
2. `test_data_validation_ranges.py`
3. `test_market_regime_detection.py`
4. `test_risk_gates.py`
5. `test_extreme_market_conditions.py`

**P2 - 中期完成：**
6. `test_edge_cases_small_values.py`
7. `test_edge_cases_large_values.py`
8. `test_end_to_end_long_scenario.py`
9. `test_end_to_end_short_scenario.py`
10. `test_end_to_end_no_trade_scenario.py`

**P3 - 长期优化：**
11. 真实数据回放测试（6个）
12. 其他边界测试

---

## 版本历史

| 版本 | 日期 | 变更 | 测试数量 |
|-----|------|------|---------|
| v1.0 | 2026-01-21 | 初始版本，P0修复测试 | 4 |
| v1.1 | 待定 | 补充数据验证测试 | 8 |
| v1.2 | 待定 | 补充决策逻辑测试 | 14 |
| v2.0 | 待定 | 完整测试套件 | 30+ |
