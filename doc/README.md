# 🚀 加密货币行情监控系统

一个功能强大的加密货币实时行情监控和智能分析系统。

[![Docker](https://img.shields.io/badge/docker-ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/python-3.12-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

## ✨ 核心特性

- 📊 **实时行情监控** - 多币种、双市场（现货+合约）
- 🎯 **智能市场分析** - 多维度数据综合判断
- 📈 **综合K线图表** - 价格、成交量、持仓量一图展示
- 🐋 **大单追踪** - 多维度筛选和分析
- 💹 **成交统计** - 买卖力量可视化
- 🔔 **价格报警** - 异常波动邮件通知
- 🐳 **Docker支持** - 一键部署

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
# 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 启动应用
python3 btc_web_app_multi.py
```

访问：http://localhost:5001

## 🔧 Docker管理

```bash
# 查看日志
docker logs -f trade-info-app

# 停止服务
./docker-stop.sh

# 重启服务
docker restart trade-info-app
```

## ⚙️ 配置

### 添加币种

编辑 `btc_web_app_multi.py`：

```python
self.symbols = ['TA', 'BTR', 'AT']  # 添加更多币种
```

### 配置邮件报警（可选）

编辑 `btc_web_app_multi.py`：

```python
class EmailAlert:
    def __init__(self):
        self.sender_password = 'your_app_password'  # 配置密码
```

详见：`邮件报警配置说明.md`

## 📚 文档

- `快速开始.md` - 快速上手
- `Docker使用说明.md` - Docker部署
- `数据更新机制说明.md` - 更新机制
- `邮件报警配置说明.md` - 报警配置

## 🎨 技术栈

- **后端**: Flask + python-binance + Pandas
- **前端**: HTML5 + CSS3 + JavaScript + Chart.js
- **部署**: Docker + Docker Compose

## 📊 数据来源

所有数据来自币安交易所（Binance）官方API。

## ⚠️ 注意事项

1. 需要网络访问币安API
2. 币安API有请求频率限制
3. 数据仅供参考，不构成投资建议
4. 加密货币投资有风险，请谨慎决策

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
