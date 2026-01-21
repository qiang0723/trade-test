# 🚀 L1 Advisory Layer - 加密货币决策咨询系统

基于市场数据的智能交易决策咨询系统（L1 Advisory Layer v3.1.5）

[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/python-3.12-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

## ✨ 核心特性

- 🎯 **L1决策咨询层** - 仅提供决策建议，不包含执行逻辑
- 📊 **多维市场分析** - 资金费率、持仓量、买卖压力综合判断
- 🔍 **三态市场识别** - TREND（趋势）/ RANGE（震荡）/ EXTREME（极端）
- ⚖️ **三级执行许可** - ALLOW / ALLOW_REDUCED / DENY
- 🛡️ **四重启动校验** - 配置口径、门槛一致性、拼写、confidence值校验
- 📈 **信心评级系统** - ULTRA / HIGH / MEDIUM / LOW 四级评分
- 🔄 **配置热更新** - 支持YAML配置文件实时重载
- 🐳 **Docker支持** - 一键部署

## 🚀 快速开始

### 方式1：本地运行（推荐）

```bash
# 克隆项目
git clone https://github.com/qiang0723/trade-test.git
cd trade-test

# 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 启动L1服务
./run_l1.sh
```

访问：http://localhost:5001

### 方式2：Docker运行

```bash
# 构建并启动L1容器
./docker-l1-build.sh
./docker-l1-run.sh

# 访问应用
open http://localhost:5001
```

## 🔧 管理命令

### 本地服务管理

```bash
# 启动服务
./run_l1.sh

# 停止服务
pkill -f btc_web_app_l1.py
```

### Docker服务管理

```bash
# 查看日志
docker logs -f trade-info-l1

# 停止服务
./docker-l1-stop.sh

# 重启服务
docker restart trade-info-l1
```

## ⚙️ 配置

### L1阈值配置

编辑 `config/l1_thresholds.yaml` 来调整决策参数：

```yaml
market_regimes:
  trend_threshold: 0.03      # 趋势市场阈值（3%）
  extreme_threshold: 0.10    # 极端市场阈值（10%）

confidence_scoring:
  strong_signal_boost:
    required_tags: [strong_buy_pressure, strong_sell_pressure]
    boost: "ULTRA"
```

配置文件支持热更新，修改后自动生效。

## 📚 文档

详细文档请查看 `doc/` 目录：

- **平台详解3.1.md** - L1系统完整说明（推荐阅读）
- **L1_API完整文档.md** - API接口文档
- **L1_Advisory_Layer使用指南.md** - 使用指南
- **L1字段规范.md** - 数据字段说明
- **L1实施总结.md** - 实施总结

## 🎨 技术栈

- **后端**: Flask + Python 3.12
- **决策引擎**: L1AdvisoryEngine（状态机 + 置信度评分）
- **数据获取**: Binance API + python-binance
- **数据库**: SQLite3（持久化决策记录）
- **前端**: HTML5 + CSS3 + JavaScript
- **部署**: Docker + Docker Compose

## 🏗️ 系统架构

```
┌─────────────────┐
│  Binance API    │ ← 数据源
└────────┬────────┘
         │
┌────────▼────────┐
│ Data Fetcher    │ ← 数据获取
│ + Cache Layer   │
└────────┬────────┘
         │
┌────────▼────────┐
│ L1 Advisory     │ ← 决策引擎
│ Engine          │   (10步决策管道)
└────────┬────────┘
         │
┌────────▼────────┐
│ Database +      │ ← 持久化 + Web界面
│ Flask Web UI    │
└─────────────────┘
```

## 📊 决策输出

L1 Advisory Layer 输出包含：

- **decision**: LONG / SHORT / NO_TRADE
- **confidence**: ULTRA / HIGH / MEDIUM / LOW
- **market_regime**: TREND / RANGE / EXTREME
- **execution_permission**: ALLOW / ALLOW_REDUCED / DENY
- **trade_quality**: GOOD / UNCERTAIN / POOR
- **reason_tags**: 决策原因标签列表

## 🧪 测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_l1_advisory.py
pytest tests/test_pr_h_confidence_validation.py
```

当前测试覆盖：**56个测试用例**

## ⚠️ 注意事项

1. **咨询层定位**: L1仅提供决策建议，不包含执行逻辑
2. **数据依赖**: 需要网络访问币安API
3. **API限制**: 币安API有请求频率限制
4. **投资风险**: 数据仅供参考，不构成投资建议
5. **谨慎决策**: 加密货币投资有风险，请谨慎决策

## 📞 联系

- **GitHub**: [@qiang0723](https://github.com/qiang0723)
- **项目地址**: https://github.com/qiang0723/trade-test

## 📄 许可证

MIT License

---

<div align="center">

**⚠️ 免责声明**

本项目仅用于学习和研究目的。

加密货币投资有风险，请谨慎决策。

---

Made with ❤️ by [qiang0723](https://github.com/qiang0723)

</div>
