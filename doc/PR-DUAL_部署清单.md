# PR-DUAL 部署清单

**版本**: 1.0  
**日期**: 2026-01-21  
**目标**: 确保PR-DUAL双周期独立结论功能正确部署

---

## ✅ 部署前检查

### 1. 代码完整性

- [x] `models/enums.py` - 新增 Timeframe, AlignmentType, ConflictResolution 枚举
- [x] `models/dual_timeframe_result.py` - 新增双周期数据结构
- [x] `models/__init__.py` - 导出新类型
- [x] `market_state_machine_l1.py` - 新增 `on_new_tick_dual()` 方法
- [x] `btc_web_app_l1.py` - 新增 `/api/l1/advisory-dual/{symbol}` 端点
- [x] `btc_web_app_l1.py` - 新增 `/dual` 页面路由
- [x] `templates/index_l1_dual.html` - 双周期UI页面
- [x] `config/l1_thresholds.yaml` - 新增 `dual_timeframe` 配置

### 2. 配置文件

检查 `config/l1_thresholds.yaml` 包含以下配置：

```yaml
dual_timeframe:
  enabled: true
  
  short_term:
    min_price_change_15m: 0.003
    min_taker_imbalance: 0.40
    min_volume_ratio: 1.2
    required_signals: 3
  
  conflict_resolution:
    default_strategy: "no_trade"
  
  alignment_bonus:
    confidence_boost: 1
    relax_executable_threshold: false
```

### 3. 测试文件

- [x] `tests/test_pr_dual_timeframe.py` - 6个测试用例
- [x] `quick-test-dual.sh` - 快速测试脚本

### 4. 文档

- [x] `doc/PR-DUAL_双周期独立结论.md` - 完整设计文档
- [x] `doc/PR-DUAL_部署清单.md` - 本文档
- [x] `README_QUICK.md` - 更新快速指南

---

## 🚀 本地部署步骤

### 步骤1: 安装依赖

```bash
# 确保Python环境正确
python3 --version  # 应该 >= 3.8

# 安装依赖（如果尚未安装）
pip3 install -r requirements.txt
```

### 步骤2: 运行测试

```bash
# 运行PR-DUAL测试
python3 tests/test_pr_dual_timeframe.py

# 或使用快速测试脚本
./quick-test-dual.sh
```

**预期输出**：
```
============================================================
测试 PR-DUAL: 双周期独立结论
============================================================
✅ test_dual_both_long passed
✅ test_dual_both_short passed
✅ test_dual_conflict_long_short passed
✅ test_dual_partial_long passed
✅ test_dual_global_risk_denial passed
✅ test_dual_backward_compatibility passed
⚠️  test_dual_conflict_resolution_strategies skipped
============================================================
✅ 所有测试通过！
============================================================
```

### 步骤3: 启动服务

```bash
# 方式1: 直接启动
python3 btc_web_app_l1.py

# 方式2: Docker启动
docker compose -f docker-compose-l1.yml up -d
```

### 步骤4: 验证功能

#### 4.1 验证API端点

```bash
# 测试单一决策API（原有功能，应正常工作）
curl http://localhost:8001/api/l1/advisory/BTC | python3 -m json.tool

# 测试双周期API（新功能）
curl http://localhost:8001/api/l1/advisory-dual/BTC | python3 -m json.tool
```

**预期响应结构**：
```json
{
  "success": true,
  "data": {
    "short_term": { ... },
    "medium_term": { ... },
    "alignment": { ... },
    "symbol": "BTC",
    "timestamp": "...",
    "decision": "long",  // 向后兼容
    "executable": true
  }
}
```

#### 4.2 验证Web页面

```bash
# 原有页面（应正常工作）
open http://localhost:8001/

# 新增双周期页面
open http://localhost:8001/dual
```

**检查项**：
- [ ] 页面正常加载
- [ ] 左右分栏显示短期和中长期结论
- [ ] 底部显示一致性分析
- [ ] 币种切换功能正常
- [ ] 自动刷新功能正常

---

## 🐳 Docker部署步骤

### 步骤1: 构建镜像

```bash
# 停止旧容器
docker compose -f docker-compose-l1.yml down

# 重新构建
docker compose -f docker-compose-l1.yml build

# 启动
docker compose -f docker-compose-l1.yml up -d
```

### 步骤2: 验证容器状态

```bash
# 检查容器运行状态
docker ps --filter "name=l1-advisory-layer"

# 查看日志
docker logs -f l1-advisory-layer

# 检查健康状态
docker inspect l1-advisory-layer | grep -A 5 Health
```

### 步骤3: 容器内测试

```bash
# 运行测试
docker exec l1-advisory-layer python tests/test_pr_dual_timeframe.py

# 检查配置
docker exec l1-advisory-layer cat config/l1_thresholds.yaml | grep -A 20 dual_timeframe
```

---

## ☁️ AWS生产环境部署

### 步骤1: 上传代码

```bash
# 同步代码到AWS服务器
rsync -avz --exclude '.git' --exclude '__pycache__' \
  ./ ubuntu@43.212.176.169:~/trade-info-l1/
```

### 步骤2: SSH登录并部署

```bash
# 登录服务器
ssh ubuntu@43.212.176.169

# 进入目录
cd ~/trade-info-l1

# 停止旧服务
docker compose -f docker-compose-l1.yml down

# 重新构建和启动
docker compose -f docker-compose-l1.yml build
docker compose -f docker-compose-l1.yml up -d

# 查看日志
docker logs -f l1-advisory-layer
```

### 步骤3: 生产环境验证

```bash
# 测试API（从本地）
curl http://43.212.176.169:8001/api/l1/advisory-dual/BTC | python3 -m json.tool

# 访问Web页面
open http://43.212.176.169:8001/dual
```

---

## 🔍 验证检查清单

### 功能验证

- [ ] **单一决策API** - `/api/l1/advisory/{symbol}` 正常工作（向后兼容）
- [ ] **双周期API** - `/api/l1/advisory-dual/{symbol}` 返回正确结构
- [ ] **短期评估** - `short_term` 字段包含5m/15m数据
- [ ] **中长期评估** - `medium_term` 字段包含1h/6h数据
- [ ] **一致性分析** - `alignment` 字段正确分类（BOTH_LONG/CONFLICT等）
- [ ] **冲突处理** - 冲突时按配置策略处理
- [ ] **向后兼容** - 响应包含 `decision`, `confidence`, `executable` 字段
- [ ] **全局风险** - 极端行情时双周期都返回NO_TRADE

### UI验证

- [ ] **原有页面** - `/` 正常显示，不受影响
- [ ] **双周期页面** - `/dual` 正常显示
- [ ] **短期面板** - 显示5m/15m决策和指标
- [ ] **中长期面板** - 显示1h/6h决策和指标
- [ ] **一致性面板** - 显示一致性状态和综合建议
- [ ] **币种切换** - 可切换BTC/ETH/SOL等
- [ ] **自动刷新** - 每30秒自动更新

### 性能验证

- [ ] **响应时间** - API响应 < 500ms
- [ ] **CPU使用** - 双周期计算不显著增加CPU
- [ ] **内存使用** - 内存占用正常
- [ ] **并发处理** - 多币种同时请求正常

### 配置验证

- [ ] **阈值生效** - 修改 `short_term.required_signals` 后行为改变
- [ ] **策略生效** - 修改 `conflict_resolution.default_strategy` 后结果改变
- [ ] **热更新** - 修改配置后重启服务生效

---

## 🐛 问题排查

### 问题1: API返回500错误

**检查**：
```bash
# 查看详细错误日志
docker logs l1-advisory-layer | tail -50

# 检查是否缺少数据字段
curl -v http://localhost:8001/api/l1/advisory-dual/BTC
```

**可能原因**：
- 数据源缺少5m/15m数据
- 配置文件格式错误
- 代码导入错误

### 问题2: 双周期页面空白

**检查**：
```bash
# 浏览器控制台查看JS错误
# 检查API是否可访问
curl http://localhost:8001/api/l1/advisory-dual/BTC

# 检查模板文件是否存在
ls -la templates/index_l1_dual.html
```

### 问题3: 一致性分析错误

**检查**：
```bash
# 运行测试查看详细输出
python3 tests/test_pr_dual_timeframe.py -v

# 检查配置
cat config/l1_thresholds.yaml | grep -A 20 dual_timeframe
```

### 问题4: 测试失败

**检查**：
```bash
# 确保依赖已安装
pip3 list | grep -E "yaml|flask|requests"

# 检查Python版本
python3 --version

# 查看详细错误
python3 tests/test_pr_dual_timeframe.py 2>&1 | tee test_output.log
```

---

## 📊 监控指标

部署后建议监控以下指标：

### API指标

- **双周期API调用次数** - 每分钟
- **双周期API响应时间** - P50, P95, P99
- **双周期API错误率** - 4xx, 5xx
- **一致性类型分布** - BOTH_LONG, CONFLICT等占比

### 决策指标

- **双周期一致率** - 一致决策占比
- **冲突频率** - 每小时冲突次数
- **综合建议分布** - LONG/SHORT/NO_TRADE占比
- **可执行率** - executable=true 占比

### 系统指标

- **CPU使用率** - 双周期计算增加的CPU
- **内存使用** - 新数据结构占用
- **响应时间** - 与单一决策对比

---

## 🎯 回滚方案

如果PR-DUAL出现严重问题，可快速回滚：

### 方案1: 禁用双周期功能

```yaml
# config/l1_thresholds.yaml
dual_timeframe:
  enabled: false  # 改为false
```

重启服务后，双周期API将返回错误，但不影响原有功能。

### 方案2: 代码回滚

```bash
# 回滚到PR-DUAL之前的commit
git log --oneline -10  # 找到PR-DUAL之前的commit
git checkout <commit-hash>

# 重新部署
docker compose -f docker-compose-l1.yml down
docker compose -f docker-compose-l1.yml build
docker compose -f docker-compose-l1.yml up -d
```

### 方案3: 仅移除UI

如果只是UI有问题，可以临时移除双周期页面：

```bash
# 重命名模板文件
mv templates/index_l1_dual.html templates/index_l1_dual.html.bak

# 重启服务
docker compose -f docker-compose-l1.yml restart
```

---

## ✅ 部署完成确认

部署完成后，确认以下所有项：

- [ ] 单元测试全部通过
- [ ] API端点正常响应
- [ ] Web页面正常显示
- [ ] 多币种测试正常
- [ ] 配置修改生效
- [ ] 日志无ERROR级别错误
- [ ] 性能指标正常
- [ ] 向后兼容性验证通过

**签字确认**：

- 部署人员: __________
- 日期: __________
- 环境: [ ] 本地 [ ] Docker [ ] AWS生产

---

## 📚 相关文档

- [PR-DUAL设计文档](./PR-DUAL_双周期独立结论.md)
- [平台详解3.2](./平台详解3.2.md)
- [快速操作指南](../README_QUICK.md)
- [测试套件说明](../tests/README_TEST_SUITE.md)

---

**部署支持**：如有问题，请查看日志或联系开发团队。
