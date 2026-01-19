# 🚀 加密货币多币种行情监控系统

一个功能强大的加密货币实时行情监控和智能分析系统，支持多币种、双市场（现货+合约）监控，提供专业的市场分析和交易决策支持。

[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/python-3.12-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

## ✨ 核心特性

### 📊 实时行情监控
- 🪙 **多币种支持**：TA、BTR、AT等（可扩展）
- 🏪 **双市场**：现货 + 合约
- 💰 **高精度**：价格4位小数，数据精准
- 📈 **实时更新**：每10秒自动刷新
- 🔄 **6小时变化**：持仓量、成交量变化追踪

### 🎯 智能市场分析
- ⚡ **1小时买卖量**：短期多空力量对比
- 📊 **6小时趋势**：中期持仓量和成交量变化
- 💰 **资金费率**：市场情绪和多空平衡
- 🎲 **风险评估**：高/中/低风险等级
- 💡 **操作建议**：基于多维度数据的智能建议

### 📈 综合可视化
- 📉 **四合一K线图**：价格、成交量、成交额、持仓量
- 🎨 **颜色分类**：蓝/绿/橙/紫四色标识
- ⏰ **多时间维度**：15分钟/1小时/4小时/1天
- 📊 **交互式图表**：Chart.js驱动，可缩放查看

### 🐋 大单追踪
- 🔍 **7×3筛选矩阵**：7个时间维度 × 3个金额阈值
- 💵 **金额范围**：1K/5K/10K USDT可选
- ⏰ **时间范围**：1-12小时可选
- 📊 **买卖统计**：大单买卖力量对比

### 💹 成交分析
- ⏱️ **4时间维度**：1分钟/5分钟/30分钟/2小时
- 🟢🔴 **买卖力量**：可视化力量条
- 📊 **详细统计**：笔数、数量、金额全覆盖

### 🔔 价格报警
- ⚡ **实时监控**：后台线程持续监控
- 📧 **邮件报警**：1分钟内涨跌幅≥5%触发
- ⏰ **智能冷却**：5分钟冷却避免骚扰
- 📝 **控制台日志**：即时输出报警信息

### 🐳 Docker支持
- 📦 **容器化部署**：一键构建启动
- 🔄 **自动重启**：异常自动恢复
- 💾 **数据持久化**：挂载本地目录
- 🛠️ **便捷脚本**：build/run/stop一条命令

## 🖥️ 界面预览

### 主界面
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌟 多币种行情监控系统
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[TA] [BTR] [AT]  |  [现货] [合约]

┌────────────┬────────────┬────────────┐
│💰 当前价格  │📊 24h涨跌   │📈 24h最高   │
│$0.0630     │-8.88% 📉   │$0.0732     │
├────────────┼────────────┼────────────┤
│💹 成交量    │💵 成交额    │📊 持仓量    │
│311.9M      │$21.4M      │70.3M       │
│📈+277.84%  │📈+257.61%  │📉-11.67%   │
└────────────┴────────────┴────────────┘
```

### 市场分析
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 市场分析  BTR/USDT  [🔄 更新分析]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌──────────┬──────────┬──────────────────┐
│市场情绪   │风险等级   │1h买卖力量         │
│看跌 🔴   │高 🔴    │🟢████🔴████████  │
│          │         │🟢15.8%    84.2%🔴│
└──────────┴──────────┴──────────────────┘

💡 空头强势打压，短期看跌，建议顺势做空

📋 详细分析
• 1h卖出力量占优 84.2%，短期卖盘强劲
• 6h持仓量大幅减少 -14.05%
• 资金费率 -0.3695%（空头过热）
• 警惕空头过度后的技术性反弹
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## 🚀 快速开始

### Docker运行（推荐）

```bash
# 克隆项目
git clone https://github.com/qiang0723/trade-test.git
cd trade-test

# 构建并启动
./docker-build.sh
./docker-run.sh

# 访问应用
open http://localhost:5001
```

### Python直接运行

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动应用
python3 btc_web_app_multi.py
```

访问：http://localhost:5001

## 📦 项目结构

```
trade-test/
├── btc_web_app_multi.py      # 主应用程序
├── btc_market_*.py            # 数据获取模块
├── templates/                 # HTML模板
│   └── index_multi.html       # 主页面
├── static/                    # 静态资源
│   ├── css/                   # 样式表
│   └── js/                    # JavaScript
├── Dockerfile                 # Docker镜像配置
├── docker-compose.yml         # Docker编排文件
├── docker-*.sh                # Docker便捷脚本
├── requirements.txt           # Python依赖
└── docs/                      # 详细文档
```

## 🎯 功能详解

### 1. 实时行情

| 数据项 | 现货 | 合约 | 精度 |
|--------|------|------|------|
| 当前价格 | ✅ | ✅ | 4位小数 |
| 24h涨跌 | ✅ | ✅ | 2位小数 |
| 成交量 | ✅ | ✅ | 6位小数 |
| 成交额 | ✅ | ✅ | 自动格式化 |
| 资金费率 | ❌ | ✅ | 4位小数 |
| 持仓量 | ❌ | ✅ | 自动格式化 |

### 2. 变化追踪

- **6小时持仓量变化**：反映中期趋势
- **6小时成交量变化**：活跃度对比（前3h vs 后3h）
- **6小时成交额变化**：资金流入流出

### 3. 市场分析

#### 分析维度
1. **1小时买卖量**（短期）
   - 买入笔数和金额
   - 卖出笔数和金额
   - 多空力量对比

2. **6小时数据**（中期）
   - 持仓量变化
   - 成交量变化
   - 价格趋势

3. **24小时数据**（长期）
   - 整体价格走势
   - 资金费率情绪

#### 分析输出
- 市场情绪：看涨/看跌/中性/转多/转空
- 风险等级：高/中/低
- 主要操作：具体建议
- 详细分析：多条结论说明

### 4. 综合K线图

单张图表集成：
- 💰 **价格K线**（蓝色线图）
- 📊 **成交量**（绿色柱状图）
- 💵 **成交额**（橙色线图）
- 📈 **持仓量**（紫色线图，仅合约）

## ⚙️ 配置

### 币种配置

编辑 `btc_web_app_multi.py`：

```python
class MultiMarketAPI:
    def __init__(self):
        # 添加更多币种
        self.symbols = ['TA', 'BTR', 'AT', 'BTC', 'ETH']
```

### 邮件报警配置

编辑 `btc_web_app_multi.py`：

```python
class EmailAlert:
    def __init__(self):
        self.sender_email = 'your_email@outlook.com'
        self.sender_password = 'your_app_password'  # Outlook应用密码
        self.receiver_email = 'receiver@example.com'
```

详细配置见：`邮件报警配置说明.md`

### 报警参数调整

```python
# 价格监控阈值（默认5%）
if abs(change_percent) >= 5.0:  # 修改这里

# 监控检查间隔（默认10秒）
price_monitor = PriceMonitor(market_api, email_alert, check_interval=10)

# 报警冷却时间（默认5分钟）
if current_time - self.alert_cooldown.get(key, 0) > 300:  # 修改这里
```

## 🔧 Docker管理

### 构建镜像
```bash
docker build -t trade-info:latest .
# 或
./docker-build.sh
```

### 启动服务
```bash
docker run -d --name trade-info-app -p 5001:5001 \
  -v "$(pwd)/btc_market_data:/app/btc_market_data" \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  trade-info:latest
# 或
./docker-run.sh
```

### 管理命令
```bash
# 查看日志
docker logs -f trade-info-app

# 查看状态
docker ps | grep trade-info

# 停止服务
docker stop trade-info-app
# 或
./docker-stop.sh

# 重启服务
docker restart trade-info-app

# 删除容器
docker stop trade-info-app && docker rm trade-info-app
```

## 📊 数据来源

所有数据均来自 **币安交易所（Binance）官方API**：
- ✅ 实时行情数据
- ✅ K线历史数据
- ✅ 订单深度数据
- ✅ 成交记录数据
- ✅ 资金费率数据
- ✅ 持仓量数据

## 📚 详细文档

| 文档 | 说明 |
|------|------|
| `快速开始.md` | 快速上手指南 |
| `Docker使用说明.md` | Docker部署详解 |
| `数据更新机制说明.md` | 数据更新频率和机制 |
| `1小时买卖量分析说明.md` | 买卖力量分析方法 |
| `6小时变化计算说明.md` | 变化百分比计算 |
| `BTR持仓量计算详解.md` | 持仓量计算示例 |
| `BTR资金费率说明.md` | 资金费率含义解释 |
| `邮件报警配置说明.md` | 报警功能配置 |

## 🎨 技术栈

### 后端
- **Flask** - Web框架
- **python-binance** - 币安API客户端
- **Pandas** - 数据处理
- **smtplib** - 邮件发送

### 前端
- **HTML5/CSS3** - 页面结构和样式
- **JavaScript ES6+** - 交互逻辑
- **Chart.js** - 数据可视化

### 部署
- **Docker** - 容器化
- **Docker Compose** - 容器编排

## 💡 使用场景

### 1. 实时监控
```
多币种价格实时跟踪
自动刷新，无需手动
移动端友好访问
```

### 2. 短线交易
```
1小时买卖力量判断
快速捕捉入场时机
实时大单追踪
```

### 3. 趋势分析
```
6小时数据确认方向
持仓量变化验证趋势
综合K线图全景展示
```

### 4. 风险控制
```
资金费率预警
持仓量异常提示
价格异常波动报警
```

## 📈 数据精度

| 指标 | 精度 | 说明 |
|------|------|------|
| 价格 | 4位小数 | $0.0634 |
| 成交量 | 6位小数 | 1.234567 BTC |
| 百分比 | 2位小数 | +12.34% |
| 金额 | K/M/B | $1.5M |
| 时间 | 秒级 | 12:34:56 |

## 🔄 更新机制

### 自动更新（每10秒）
- 实时价格
- 24h涨跌
- 成交量/成交额
- 资金费率
- 持仓量
- 订单深度
- 最近成交

### 手动更新（按需）
- K线图表（切换时间间隔）
- 市场分析（点击更新按钮）
- 大单分析（切换筛选条件）

## 🎯 支持的币种

| 币种 | 现货 | 合约 | 说明 |
|------|------|------|------|
| TA | ❌ | ✅ | 仅合约 |
| BTR | ❌ | ✅ | 仅合约 |
| AT | ✅ | ✅ | 双市场 |

> 💡 可在代码中轻松添加更多币种

## ⚠️ 注意事项

1. **网络要求**
   - 需要访问币安API（api.binance.com）
   - Docker容器需要网络权限

2. **API限制**
   - 币安API有请求频率限制
   - 建议不要修改自动刷新频率

3. **邮件报警**
   - 需要配置Outlook应用密码
   - 未配置时仅控制台输出

4. **数据延迟**
   - 实时数据：<1秒
   - 持仓量：<1分钟
   - 资金费率：每8小时更新

5. **风险提示**
   - 数据仅供参考
   - 不构成投资建议
   - 加密货币投资有风险

## 🛠️ 开发

### 添加新币种

```python
# 编辑 btc_web_app_multi.py
self.symbols = ['TA', 'BTR', 'AT', 'NEW_SYMBOL']
```

### 调整分析参数

```python
# 持仓量变化阈值
if abs(oi_change) > 5:  # 改为其他值

# 买卖力量阈值
if buy_ratio_1h > 60:  # 改为其他值
```

### 自定义UI

```css
/* 编辑 static/css/style_multi.css */
/* 修改主题色、间距、字体等 */
```

## 📞 联系方式

- **GitHub**: [@qiang0723](https://github.com/qiang0723)
- **项目地址**: https://github.com/qiang0723/trade-test
- **问题反馈**: [提交Issue](https://github.com/qiang0723/trade-test/issues)

## 🤝 贡献

欢迎提交 Pull Request 或 Issue！

### 贡献指南
1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE)

## 🙏 致谢

- [Binance API](https://binance-docs.github.io/apidocs/) - 数据来源
- [Chart.js](https://www.chartjs.org/) - 图表库
- [Flask](https://flask.palletsprojects.com/) - Web框架

## 📊 项目统计

- **代码行数**: 15,536+
- **文件数**: 45+
- **文档数**: 15+
- **支持币种**: 3+（可扩展）
- **筛选组合**: 21种（大单分析）

## 🔮 未来计划

- [ ] 支持更多币种
- [ ] 添加策略回测功能
- [ ] K线技术指标（MA/MACD/RSI等）
- [ ] 用户自定义报警条件
- [ ] 移动端App
- [ ] 多语言支持

---

## ⚡ 快速访问

**在线演示**: http://localhost:5001 （本地部署后）

**完整文档**: 见项目 `docs/` 目录

---

<div align="center">

**⚠️ 免责声明**

本项目仅用于学习和研究目的。

加密货币投资有风险，请谨慎决策。

项目提供的数据和分析仅供参考，不构成投资建议。

---

Made with ❤️ by [qiang0723](https://github.com/qiang0723)

⭐ 如果觉得有用，欢迎 Star！

</div>
