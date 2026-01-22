# PATCH-1: Normalization 字段族全覆盖

**版本**: v3.3-patch1  
**实施日期**: 2026-01-22  
**优先级**: P0（立即实施）  
**状态**: ✅ 已完成

---

## 📋 问题背景

### 原有问题

1. **静态字段列表**：只覆盖 `1h/6h`，遗漏 `5m/15m`
   ```python
   PERCENTAGE_FIELDS = [
       'price_change_1h', 'price_change_6h',  # ✅ 有
       'oi_change_1h', 'oi_change_6h',        # ✅ 有
       # ❌ 缺少 5m/15m
   ]
   ```

2. **Silent Drift 风险**：新增字段需手动添加，易遗漏
3. **缺少 Trace**：规范化过程不可追溯
4. **元数据依赖不明确**：缺失时行为不可预测

---

## ✅ 解决方案

### 1. 字段族规则（Field Family Patterns）

**从静态列表升级为正则匹配**：

```python
PERCENTAGE_FIELD_PATTERNS = [
    r'^price_change_\w+$',   # 匹配所有 price_change_*
    r'^oi_change_\w+$',      # 匹配所有 oi_change_*
]
```

**效果**：
- ✅ 自动覆盖：`price_change_5m`, `price_change_15m`, `price_change_30m`, ...
- ✅ 新增字段无需改代码
- ✅ 零配置扩展

---

### 2. Trace 输出（可追溯性）

**新增 `NormalizationTrace` 数据类**：

```python
@dataclass
class NormalizationTrace:
    input_percentage_format: str            # 输入格式
    converted_fields: List[str]             # 转换的字段
    skipped_fields: List[str]               # 跳过的字段
    range_fail_fields: List[str]            # 范围校验失败
    metadata_policy_applied: Optional[str]  # 元数据策略
    field_family_matched: Dict              # 字段族匹配结果
```

**集成到 Step1 管道**：
```python
self.last_pipeline_steps.append({
    'step': 1,
    'name': 'validate_data',
    'status': 'success',
    'normalization_trace': norm_trace.to_dict()  # ✅ 完全可追溯
})
```

---

### 3. 元数据处理策略

**三种策略**：

| 策略 | 行为 | 适用场景 |
|------|------|----------|
| `WARN` | 警告并假设 `percent_point` | 生产环境（向后兼容） |
| `FAIL_FAST` | 拒绝处理 | 开发/测试环境（严格模式） |
| `ASSUME_PERCENT_POINT` | 静默假设 | 不推荐 |

---

## 📊 测试覆盖

### 测试文件
`tests/test_patch1_normalization.py` - 40个测试用例

### 测试结果
```
✅ 40 passed in 0.11s
```

### 测试类别

| 类别 | 测试数 | 说明 |
|------|--------|------|
| 字段族匹配 | 14 | 参数化测试所有周期 |
| percent_point转换 | 10 | 参数化测试转换正确性 |
| decimal输入保持 | 1 | 验证不转换 |
| 元数据策略 | 2 | WARN/FAIL_FAST |
| 范围校验 | 6 | 参数化测试边界 |
| Trace完整性 | 1 | 验证输出结构 |
| L1引擎集成 | 2 | 端到端测试 |
| 新字段自动化 | 2 | 验证零配置扩展 |
| 尺度异常检测 | 1 | 极端值拒绝 |
| 向后兼容 | 1 | 旧API仍可用 |

---

## 🔍 关键改进

### Before (v3.2)

```python
# ❌ 静态列表，易遗漏
PERCENTAGE_FIELDS = ['price_change_1h', 'price_change_6h']

# ❌ 无 trace
normalized_data, is_valid, error = normalize_metrics(data)

# ❌ 元数据缺失时静默假设
```

### After (v3.3-patch1)

```python
# ✅ 字段族规则，自动覆盖
PERCENTAGE_FIELD_PATTERNS = [r'^price_change_\w+$', ...]

# ✅ 完整 trace
normalized_data, is_valid, error, trace = normalize_metrics_with_trace(data)

# ✅ 明确策略，可追溯
MetricsNormalizer(metadata_policy=MetadataPolicy.WARN)
trace.metadata_policy_applied == 'WARN_ASSUME_PERCENT_POINT'
```

---

## 📈 收益

| 维度 | 改进 |
|------|------|
| **数据覆盖率** | 100%（所有周期自动覆盖） |
| **Silent Drift 风险** | 消除（字段族规则防止遗漏） |
| **可追溯性** | 完全可追溯（trace 输出） |
| **可测试性** | 40个测试，100%通过 |
| **向后兼容** | 完全兼容（旧API保留） |

---

## 🚀 部署清单

- [x] 重构 `metrics_normalizer.py`
- [x] 更新 `market_state_machine_l1.py` 集成 trace
- [x] 编写 40个参数化测试
- [x] 所有测试通过
- [x] 文档更新
- [ ] 提交到 Git
- [ ] 部署到生产环境

---

## 📝 使用示例

### 自动处理新周期字段

```python
data = {
    'price_change_5m': 1.5,      # ✅ 自动转换
    'price_change_15m': 2.0,     # ✅ 自动转换
    'price_change_30m': 1.2,     # ✅ 自动转换（新字段）
    'oi_change_15m': 5.0,        # ✅ 自动转换
    '_metadata': {'percentage_format': 'percent_point'}
}

normalized, is_valid, error, trace = normalize_metrics_with_trace(data)

# 查看 trace
print(trace.converted_fields)
# ['price_change_5m', 'price_change_15m', 'price_change_30m', 'oi_change_15m']
```

### 查看管道 trace

```python
engine = L1AdvisoryEngine()
result = engine.on_new_tick('BTC', data)

# 查看 Step1 的 normalization_trace
step1 = engine.last_pipeline_steps[0]
print(step1['normalization_trace'])
```

---

## 🎯 下一步

PATCH-1 已完成，可继续实施：
- **PATCH-2**: Cache Lookback（历史取样 floor + gap guardrail）
- **PATCH-3**: 双路径结论增强（基于现有 PR-DUAL）
