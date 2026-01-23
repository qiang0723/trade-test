# Pytest迁移指南 - P0-04

**目的**: 将旧风格测试（`print + exit(1)`）迁移到标准pytest风格  
**创建日期**: 2026-01-23  
**状态**: P0-04实施指南

---

## 📋 为什么需要迁移

### 旧风格的问题

```python
# ❌ 旧风格（有问题）
def test_something():
    result = engine.evaluate(data)
    if result.decision != Decision.LONG:
        print("FAIL: Expected LONG")
        sys.exit(1)  # 问题1: 破坏pytest收集
    print("PASS")
    sys.exit(0)  # 问题2: 破坏CI流程
```

**问题**:
1. **破坏pytest收集**: `sys.exit()` 导致pytest无法收集所有测试
2. **破坏CI**: 第一个失败就退出，后续测试不执行
3. **无法聚合结果**: 无法生成测试报告
4. **难以调试**: 没有详细的失败信息

---

## ✅ 新风格（pytest标准）

```python
# ✅ 新风格（推荐）
def test_something():
    # Given: 准备测试数据
    data = {
        'price_change_1h': 0.03,
        '_metadata': {'percentage_format': 'decimal'}  # P0-04要求
    }
    
    # When: 执行被测试代码
    result = engine.evaluate(data)
    
    # Then: pytest断言
    assert result.decision == Decision.LONG
    assert 'strong_buy_pressure' in result.reason_tags
    assert result.executable is True
```

**优势**:
- ✅ pytest可以收集所有测试
- ✅ 失败后继续运行其他测试
- ✅ 生成详细的测试报告
- ✅ 支持pytest插件（coverage, xdist等）

---

## 🔧 迁移步骤

### Step 1: 移除main函数和sys.exit

**旧代码**:
```python
def main():
    print("Test 1...")
    if not test1():
        sys.exit(1)
    print("PASS")
    sys.exit(0)

if __name__ == '__main__':
    main()
```

**新代码**:
```python
def test_feature_1():
    """描述这个测试验证什么"""
    # Given/When/Then...
    assert condition

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

### Step 2: 转换断言

| 旧写法 | 新写法 |
|-------|--------|
| `if x != y: print("FAIL"); exit(1)` | `assert x == y` |
| `if not condition: sys.exit(1)` | `assert condition` |
| `if x < 10: sys.exit(1)` | `assert x >= 10` |
| `print("PASS")` | （删除，pytest会显示） |

### Step 3: 添加metadata（P0-04要求）

**所有测试数据必须包含metadata**:

```python
# ❌ 错误：缺少metadata
data = {
    'price_change_1h': 0.03,
    'oi_change_1h': 0.06,
}

# ✅ 正确：包含metadata
data = {
    'price_change_1h': 0.03,
    'oi_change_1h': 0.06,
    '_metadata': {
        'percentage_format': 'decimal'  # 输入已是小数格式
    }
}
```

### Step 4: 使用pytest fixtures

```python
# ✅ 推荐：使用fixture减少重复代码
@pytest.fixture
def engine():
    """创建测试引擎"""
    return L1AdvisoryEngine(config_path='config/l1_thresholds.yaml')

@pytest.fixture
def test_data():
    """创建测试数据"""
    return {
        'price': 50000,
        'volume_24h': 1000,
        'price_change_1h': 0.03,
        '_metadata': {'percentage_format': 'decimal'}
    }

def test_with_fixtures(engine, test_data):
    """使用fixtures的测试"""
    result = engine.on_new_tick('BTC', test_data)
    assert result.decision == Decision.LONG
```

---

## 📝 迁移示例

### 示例1: 简单断言

**旧代码**:
```python
def test_basic():
    engine = L1AdvisoryEngine()
    data = {'price_change_1h': 0.03}
    result = engine.on_new_tick('BTC', data)
    
    if result.decision != Decision.LONG:
        print("FAIL: Expected LONG")
        sys.exit(1)
    
    print("PASS: test_basic")
    sys.exit(0)
```

**新代码**:
```python
def test_basic():
    """验证LONG决策可触发"""
    # Given
    engine = L1AdvisoryEngine()
    data = {
        'price_change_1h': 0.03,
        '_metadata': {'percentage_format': 'decimal'}  # P0-04要求
    }
    
    # When
    result = engine.on_new_tick('BTC', data)
    
    # Then
    assert result.decision == Decision.LONG
```

### 示例2: 多个断言

**旧代码**:
```python
def test_multiple_checks():
    result = engine.evaluate(data)
    
    if result.decision != Decision.LONG:
        print("FAIL: Wrong decision")
        sys.exit(1)
    
    if result.confidence != Confidence.HIGH:
        print("FAIL: Wrong confidence")
        sys.exit(1)
    
    if not result.executable:
        print("FAIL: Should be executable")
        sys.exit(1)
    
    print("PASS")
```

**新代码**:
```python
def test_multiple_checks():
    """验证决策、置信度和可执行性"""
    # Given
    data = make_test_data()
    
    # When
    result = engine.evaluate(data)
    
    # Then: 多个断言
    assert result.decision == Decision.LONG, "决策应为LONG"
    assert result.confidence == Confidence.HIGH, "置信度应为HIGH"
    assert result.executable is True, "应可执行"
```

### 示例3: 异常测试

**旧代码**:
```python
def test_exception():
    try:
        engine.evaluate(invalid_data)
        print("FAIL: Should raise ValueError")
        sys.exit(1)
    except ValueError:
        print("PASS: Correctly raised ValueError")
```

**新代码**:
```python
def test_exception():
    """验证异常输入抛出ValueError"""
    # Given
    invalid_data = {'price': -100}  # 无效数据
    
    # When/Then: 验证抛出异常
    with pytest.raises(ValueError, match="Invalid price"):
        engine.evaluate(invalid_data)
```

### 示例4: 警告测试

**旧代码**:
```python
def test_warning():
    # 无法测试警告
    result = engine.evaluate(data_missing_metadata)
    # 只能假设它工作了
    print("PASS")
```

**新代码**:
```python
def test_warning():
    """验证缺失metadata时发出警告"""
    # Given: 缺少metadata
    data = {
        'price_change_1h': 3.0,
        # 缺少_metadata
    }
    
    # When/Then: 验证警告
    with pytest.warns(UserWarning, match="Missing _metadata"):
        result = engine.evaluate(data)
```

---

## 🎯 迁移优先级

### 高优先级（立即迁移）
1. ✅ `test_p0_none_safe_validation.py` - 已完成（P0-06新增）
2. `test_case_a.py` - 使用`exit(0)`, `exit(1)`
3. P0相关的所有测试文件

### 中优先级（逐步迁移）
1. PR系列测试（test_pr_*.py）
2. PATCH系列测试（test_patch*.py）

### 低优先级（可延后）
1. 已经部分使用pytest的文件（只需补充metadata）
2. 辅助测试脚本

---

## ✅ 迁移检查清单

完成迁移后，确保：

- [ ] 移除所有`sys.exit()` / `exit()`
- [ ] 移除所有`print("PASS")` / `print("FAIL")`
- [ ] 所有测试数据包含`_metadata`
- [ ] 使用pytest断言（`assert`）
- [ ] 函数名以`test_`开头
- [ ] 添加docstring说明测试目的
- [ ] 运行`pytest文件名.py -v`通过

---

## 🚀 运行pytest

### 单个文件
```bash
pytest tests/test_p0_none_safe_validation.py -v
```

### 所有测试
```bash
pytest tests/ -v --tb=short
```

### 带覆盖率
```bash
pytest tests/ -v --cov=l1_engine --cov=market_state_machine_l1
```

### 只运行P0测试
```bash
pytest tests/ -v -k "p0"
```

---

## 📖 参考示例

完整的pytest风格示例文件：
- ✅ `tests/test_p0_none_safe_validation.py` - P0改进验收测试
- 参考pytest官方文档: https://docs.pytest.org/

---

**迁移指南版本**: 1.0  
**适用范围**: 所有tests/目录下的测试文件  
**状态**: P0-04指南 ✅ 完成  
