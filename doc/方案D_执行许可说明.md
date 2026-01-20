# 方案D: 三级执行许可 + 双门槛机制

**更新日期**: 2026-01-20  
**问题**: NOISY/UNCERTAIN被cap到MEDIUM，但executable要求HIGH，导致DEGRADE语义被事实上否决  
**解决方案**: 引入ExecutionPermission三级许可 + 双门槛机制

---

## 1. 问题背景

### 1.1 原始冲突

**PR-D配置**：
```yaml
caps:
  uncertain_quality_max: "MEDIUM"    # UNCERTAIN最高MEDIUM
  tag_caps:
    noisy_market: "MEDIUM"            # NOISY_MARKET最高MEDIUM
```

**PR-B executable要求**：
```python
if self.confidence not in [Confidence.ULTRA, Confidence.HIGH]:
    return False  # 要求至少HIGH
```

**冲突结果**：
```
NOISY_MARKET → cap to MEDIUM → executable检查 → MEDIUM not in [ULTRA, HIGH] → False
```

**结论**: DEGRADE级别标签（NOISY_MARKET）实际上被完全禁止，与"降级执行"语义冲突。

---

## 2. 方案D设计

### 2.1 核心概念

**ExecutionPermission枚举**（新增）：
```python
class ExecutionPermission(Enum):
    ALLOW = "allow"                    # 正常执行
    ALLOW_REDUCED = "allow_reduced"    # 降级执行（更严格门槛）
    DENY = "deny"                      # 拒绝执行
```

**映射规则**：
```
ExecutabilityLevel → ExecutionPermission
- BLOCK → DENY（拒绝执行）
- DEGRADE → ALLOW_REDUCED（降级执行）
- ALLOW → ALLOW（正常执行）
```

### 2.2 双门槛机制

**配置**：
```yaml
executable_control:
  min_confidence_normal: "HIGH"      # ALLOW 的最低要求
  min_confidence_reduced: "MEDIUM"   # ALLOW_REDUCED 的最低要求
```

**逻辑**：
```python
if execution_permission == ExecutionPermission.ALLOW:
    return confidence >= min_confidence_normal  # HIGH/ULTRA

elif execution_permission == ExecutionPermission.ALLOW_REDUCED:
    return confidence >= min_confidence_reduced  # MEDIUM/HIGH/ULTRA

elif execution_permission == ExecutionPermission.DENY:
    return False  # 永远False
```

### 2.3 Cap调整

**修订配置**（配合双门槛）：
```yaml
caps:
  uncertain_quality_max: "HIGH"    # MEDIUM → HIGH
  tag_caps:
    noisy_market: "HIGH"            # MEDIUM → HIGH
    weak_signal_in_range: "HIGH"    # MEDIUM → HIGH
```

**逻辑保证**：
```
noisy_market → cap to HIGH → ALLOW_REDUCED + MEDIUM门槛 → HIGH >= MEDIUM → executable=True ✓
```

---

## 3. 实施内容

### 3.1 代码修改

**新增枚举** (`models/enums.py`):
- `ExecutionPermission`（ALLOW/ALLOW_REDUCED/DENY）

**修改数据结构** (`models/advisory_result.py`):
- 添加 `execution_permission` 字段
- 重写 `compute_executable()` 为双门槛逻辑
- 添加 `_confidence_meets_threshold()` 辅助方法

**新增方法** (`market_state_machine_l1.py`):
- `_compute_execution_permission()`: 根据ReasonTag计算执行许可级别

**更新决策管道** (`market_state_machine_l1.py::on_new_tick`):
- Step 8: 计算execution_permission
- Step 9: 置信度计算（原Step 8）
- Step 10: 构造结果（原Step 8，新增execution_permission参数）

**更新配置** (`config/l1_thresholds.yaml`):
- caps: MEDIUM → HIGH
- 新增 `executable_control` 配置段

### 3.2 测试覆盖

**新增测试文件**: `tests/test_execution_permission.py` (5个测试)

```
✅ Test 1: ExecutionPermission映射正确
✅ Test 2: 双门槛机制生效
✅ Test 3: NOISY_MARKET可降级执行（核心验证）
✅ Test 4: EXTREME场景拒绝执行
✅ Test 5: Cap与门槛配置一致
```

---

## 4. 影响分析

### 4.1 修复前 vs 修复后

| 场景 | 修复前 | 修复后 |
|------|-------|-------|
| **强信号** (GOOD, 无降级标签) | confidence=ULTRA, execution_permission=N/A, executable=True | confidence=ULTRA, execution_permission=ALLOW, executable=True ✅ |
| **噪声市场** (UNCERTAIN, NOISY_MARKET) | cap to MEDIUM, executable=False ❌ | cap to HIGH, execution_permission=ALLOW_REDUCED, executable=True ✅ |
| **震荡弱信号** (UNCERTAIN, WEAK_SIGNAL) | cap to MEDIUM, executable=False ❌ | cap to HIGH, execution_permission=ALLOW_REDUCED, executable=True ✅ |
| **极端风险** (POOR, EXTREME_VOLUME) | executable=False ✅ | execution_permission=DENY, executable=False ✅ |

### 4.2 语义一致性

**DEGRADE级别**:
- 修复前: 实际上是BLOCK（cap到MEDIUM，永远不可执行）
- 修复后: 真正实现"降级执行"（cap到HIGH，使用MEDIUM门槛，可执行）

---

## 5. API响应变化

### 5.1 新增字段

```json
{
  "decision": "long",
  "confidence": "high",
  "execution_permission": "allow_reduced",  // 新增字段
  "executable": true,
  "market_regime": "trend",
  "trade_quality": "uncertain",
  "reason_tags": ["noisy_market", "strong_buy_pressure"]
}
```

### 5.2 三种状态示例

**ALLOW**（正常执行）：
```json
{
  "decision": "long",
  "confidence": "ultra",
  "execution_permission": "allow",
  "executable": true,
  "reason_tags": ["strong_buy_pressure"]
}
```

**ALLOW_REDUCED**（降级执行）：
```json
{
  "decision": "long",
  "confidence": "high",
  "execution_permission": "allow_reduced",
  "executable": true,
  "reason_tags": ["noisy_market", "strong_buy_pressure"]
}
```

**DENY**（拒绝执行）：
```json
{
  "decision": "no_trade",
  "confidence": "low",
  "execution_permission": "deny",
  "executable": false,
  "reason_tags": ["extreme_volume"]
}
```

---

## 6. 配置示例

### 6.1 完整配置

```yaml
# 置信度配置
confidence_scoring:
  caps:
    uncertain_quality_max: "HIGH"     # 方案D修订：允许降级执行
    tag_caps:
      noisy_market: "HIGH"             # 方案D修订
      weak_signal_in_range: "HIGH"     # 方案D修订

# 执行控制（方案D新增）
executable_control:
  min_confidence_normal: "HIGH"        # ALLOW 门槛
  min_confidence_reduced: "MEDIUM"     # ALLOW_REDUCED 门槛
  
  # 说明：
  # - ALLOW: 无降级标签，要求 HIGH/ULTRA
  # - ALLOW_REDUCED: 有DEGRADE标签（如NOISY_MARKET），要求 MEDIUM及以上
  # - DENY: 有BLOCK标签（如EXTREME_VOLUME），永远不可执行
```

### 6.2 调整策略

**保守策略**（更严格）：
```yaml
executable_control:
  min_confidence_normal: "ULTRA"       # 正常执行要求ULTRA
  min_confidence_reduced: "HIGH"       # 降级执行要求HIGH
```

**激进策略**（更宽松）：
```yaml
executable_control:
  min_confidence_normal: "HIGH"        # 正常执行要求HIGH
  min_confidence_reduced: "MEDIUM"     # 降级执行要求MEDIUM（当前配置）
```

---

## 7. 总结

### 7.1 核心成果

✅ **完美映射ExecutabilityLevel**:
- ALLOW → ALLOW（正常执行）
- DEGRADE → ALLOW_REDUCED（降级执行）✓
- BLOCK → DENY（拒绝执行）

✅ **解决DEGRADE语义冲突**:
- NOISY_MARKET + HIGH → ALLOW_REDUCED + executable=True

✅ **灵活可配**:
- 双门槛独立配置
- 适应不同风险偏好

✅ **可追溯性强**:
- `execution_permission` 明确标记执行级别

### 7.2 测试结果

```
============================================================
✅ 所有测试通过！方案D实现正确
============================================================

核心成果：
1. ExecutionPermission映射正确（BLOCK→DENY, DEGRADE→ALLOW_REDUCED）
2. 双门槛机制生效（ALLOW要求HIGH, ALLOW_REDUCED要求MEDIUM）
3. NOISY_MARKET可降级执行（解决原问题）
4. Cap与门槛配置一致（HIGH >= MEDIUM）
```

### 7.3 向后兼容

- `from_dict` 方法默认 `execution_permission='allow'`（兼容旧数据）
- API响应新增字段，不影响现有字段
- 配置文件新增段落，不影响现有配置

---

**方案D完美解决DEGRADE语义被否决的问题，实现真正的"降级执行"！** ✅
