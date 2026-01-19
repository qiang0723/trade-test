# Binance API 使用说明

## 📌 当前API配置

### 代码中的API Key

```python
# btc_web_app_multi.py 第27行
self.client = Client("", "")
```

**说明：使用空字符串，即不需要API Key！**

---

## 🔓 为什么不需要API Key？

### 本项目使用的是 **公开API**

币安提供两种类型的API：

| API类型 | 需要Key | 功能范围 | 本项目使用 |
|---------|---------|---------|-----------|
| **公开API** | ❌ 不需要 | 市场数据（价格、K线、成交等） | ✅ **使用** |
| **私有API** | ✅ 需要 | 账户操作（下单、查余额等） | ❌ 不使用 |

---

## 📊 本项目使用的API（全部为公开API）

### 1. 现货市场数据

```python
# 不需要API Key的调用
client = Client("", "")

# ✅ 24小时价格统计
client.get_ticker(symbol='TAUSDT')

# ✅ K线数据
client.get_klines(symbol='TAUSDT', interval='1h', limit=24)

# ✅ 最近成交
client.get_recent_trades(symbol='TAUSDT', limit=1000)

# ✅ 深度数据
client.get_order_book(symbol='TAUSDT', limit=20)
```

### 2. 合约市场数据

```python
# ✅ 合约价格统计
client.futures_ticker(symbol='TAUSDT')

# ✅ 合约K线
client.futures_klines(symbol='TAUSDT', interval='1h', limit=24)

# ✅ 合约最近成交
client.futures_recent_trades(symbol='TAUSDT', limit=1000)

# ✅ 资金费率（实时）
client.futures_mark_price(symbol='TAUSDT')

# ✅ 持仓量
client.futures_open_interest(symbol='TAUSDT')

# ✅ 持仓量历史
client.futures_open_interest_hist(symbol='TAUSDT', period='1h', limit=7)
```

### 3. 深度数据

```python
# ✅ 现货深度
client.get_order_book(symbol='TAUSDT', limit=20)

# ✅ 合约深度
client.futures_order_book(symbol='TAUSDT', limit=20)
```

---

## 🔑 如何创建Binance API Key（如果需要）

### 场景：需要访问私有API时

如果未来要添加以下功能，才需要创建API Key：

- ❌ 自动下单
- ❌ 查询账户余额
- ❌ 查询历史订单
- ❌ 修改/取消订单

### 创建步骤

#### **1. 登录币安账户**
```
网址: https://www.binance.com
登录 → 个人中心
```

#### **2. 进入API管理**
```
个人中心 → API管理
或直接访问: https://www.binance.com/zh-CN/my/settings/api-management
```

#### **3. 创建API Key**

##### **步骤详解：**

**① 点击"创建API"**
```
选择类型: 系统生成的API密钥（推荐）
```

**② 输入标签**
```
标签名称: trade-info-app（自定义）
```

**③ 安全验证**
```
输入: 邮箱验证码
输入: 手机验证码
输入: 双因素验证码（如果开启了2FA）
```

**④ 保存密钥**
```
API Key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Secret Key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

⚠️ 警告: Secret Key只显示一次，请立即保存！
```

**⑤ 配置权限**
```
建议权限设置:
  ✅ 允许读取 (Read)          ← 查询数据
  ❌ 允许现货交易 (Spot)       ← 本项目不需要
  ❌ 允许合约交易 (Futures)    ← 本项目不需要
  ❌ 允许杠杆交易 (Margin)     ← 本项目不需要
  ❌ 允许提现 (Withdrawal)     ← 危险！不要开启

本项目只需查询数据，不需要交易权限！
```

**⑥ IP白名单（可选但推荐）**
```
不限制IP: 任何IP都可以使用（不太安全）
限制IP: 只允许指定IP使用（推荐）

示例:
  服务器IP: 123.456.789.000
  家里IP: 192.168.1.100
```

---

## 🔒 如何在项目中使用API Key

### **方法1: 环境变量（推荐）**

#### ① 创建环境变量文件

```bash
# 在项目根目录创建 .env 文件
cd /Users/wangqiang/learning/trade-info
nano .env
```

#### ② 写入API Key

```bash
# .env 文件内容
BINANCE_API_KEY=你的API_Key
BINANCE_API_SECRET=你的Secret_Key
```

#### ③ 修改代码

```python
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class MultiMarketAPI:
    def __init__(self):
        api_key = os.getenv('BINANCE_API_KEY', '')
        api_secret = os.getenv('BINANCE_API_SECRET', '')
        self.client = Client(api_key, api_secret)
```

#### ④ 安装依赖

```bash
pip install python-dotenv
```

#### ⑤ 添加到.gitignore

```bash
# 确保不提交API Key到GitHub
echo ".env" >> .gitignore
```

---

### **方法2: 配置文件**

#### ① 创建配置文件

```python
# config.py
BINANCE_API_KEY = "你的API_Key"
BINANCE_API_SECRET = "你的Secret_Key"
```

#### ② 使用配置

```python
# btc_web_app_multi.py
from config import BINANCE_API_KEY, BINANCE_API_SECRET

class MultiMarketAPI:
    def __init__(self):
        self.client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
```

#### ③ 添加到.gitignore

```bash
echo "config.py" >> .gitignore
```

---

### **方法3: Docker环境变量**

#### ① 修改docker-compose.yml

```yaml
version: '3.8'
services:
  trade-info:
    build: .
    environment:
      - BINANCE_API_KEY=${BINANCE_API_KEY}
      - BINANCE_API_SECRET=${BINANCE_API_SECRET}
    ports:
      - "5001:5001"
```

#### ② 运行时传入

```bash
# 方式1: 命令行传入
docker run -e BINANCE_API_KEY="xxx" -e BINANCE_API_SECRET="xxx" trade-info

# 方式2: 使用.env文件
docker-compose --env-file .env up
```

---

## 🚨 API Key 安全注意事项

### ⚠️ 重要警告

| 危险操作 | 说明 | 后果 |
|---------|------|------|
| ❌ 提交到GitHub | API Key被公开 | 资金被盗 |
| ❌ 开启提现权限 | 黑客可以提币 | 全部资金损失 |
| ❌ 不限制IP | 任何人都可用 | 账户被盗用 |
| ❌ 共享给他人 | 失去控制 | 不可预测 |

### ✅ 安全建议

```
1. API Key 绝不提交到 GitHub
   - 使用 .gitignore 排除
   - 使用环境变量
   
2. 只开启必要的权限
   - 本项目只需"读取"权限
   - 不要开启交易/提现权限
   
3. 使用IP白名单
   - 只允许你的服务器IP访问
   - 定期更新白名单
   
4. 定期更换API Key
   - 建议每3-6个月更换一次
   - 如果泄露立即删除
   
5. 监控API使用情况
   - 在币安后台查看API调用记录
   - 发现异常立即禁用
```

---

## 📊 API限流说明

### 币安API限流规则

#### **公开API（本项目使用）**

```
限制类型: IP限流
限制规则:
  - 单IP: 1200请求/分钟
  - 单IP: 每秒最多10个订单相关请求（本项目不涉及）
  
超限惩罚:
  - 1分钟内超限 → 封禁1-2分钟
  - 多次超限 → 封禁时间递增
```

#### **本项目的API调用频率**

```python
# 自动刷新频率
数据刷新: 每10秒
大单分析: 用户点击时
K线图: 用户切换时
市场分析: 用户点击更新时

估算: 每分钟约6-12次请求
状态: ✅ 远低于限制（1200次/分钟）
```

#### **优化建议**

如果未来扩展更多币种或功能：

```python
# 1. 添加请求缓存
from functools import lru_cache

@lru_cache(maxsize=128)
def get_cached_ticker(symbol, timestamp):
    """缓存5秒内的数据"""
    return client.get_ticker(symbol=symbol)

# 2. 批量请求
# 币安支持一次获取多个币种的数据
tickers = client.get_all_tickers()  # 一次获取所有币种

# 3. WebSocket连接（推荐）
from binance.websockets import BinanceSocketManager
# 使用WebSocket接收实时推送，不占用API请求次数
```

---

## 🔍 验证API连接

### 测试脚本

```python
#!/usr/bin/env python3
"""测试Binance API连接"""

from binance.client import Client

# 方式1: 公开API（无需Key）
print("=" * 50)
print("测试公开API（无需Key）")
print("=" * 50)

client = Client("", "")

try:
    # 测试获取BTC价格
    ticker = client.get_ticker(symbol='BTCUSDT')
    print(f"✅ BTC价格: ${ticker['lastPrice']}")
    
    # 测试获取服务器时间
    server_time = client.get_server_time()
    print(f"✅ 服务器时间: {server_time['serverTime']}")
    
    print("\n✅ 公开API连接成功！")
except Exception as e:
    print(f"❌ 连接失败: {e}")

# 方式2: 私有API（需要Key）
print("\n" + "=" * 50)
print("测试私有API（需要Key）")
print("=" * 50)

api_key = "你的API_Key"
api_secret = "你的Secret_Key"

if api_key and api_secret and api_key != "你的API_Key":
    client_auth = Client(api_key, api_secret)
    try:
        # 测试账户信息
        account = client_auth.get_account()
        print(f"✅ 账户权限: {account['canTrade']}")
        print("✅ 私有API连接成功！")
    except Exception as e:
        print(f"❌ 认证失败: {e}")
else:
    print("⚠️  未配置API Key，跳过私有API测试")
```

---

## 🎯 总结

### 本项目API使用情况

```
当前配置: Client("", "")
API类型: 公开API
需要Key: ❌ 不需要
功能: ✅ 市场数据查询
交易: ❌ 不支持（也不需要）
安全性: ✅ 高（无密钥泄露风险）
限流: ✅ 1200次/分钟（足够使用）
```

### 何时需要创建API Key？

```
如果需要以下功能，才需要创建API Key:

❌ 自动下单/交易
❌ 查询账户余额
❌ 查询历史订单
❌ 提现/转账

本项目只查询市场数据，不需要API Key！✅
```

### 优势

```
✅ 无需注册币安账户
✅ 无需创建API Key
✅ 无API Key泄露风险
✅ 部署简单
✅ 维护方便
```

---

## 📚 相关文档

- [币安API官方文档](https://binance-docs.github.io/apidocs/spot/cn/)
- [python-binance库文档](https://python-binance.readthedocs.io/)
- [币安API管理页面](https://www.binance.com/zh-CN/my/settings/api-management)

---

## ❓ 常见问题

### Q1: 为什么代码中API Key是空的？

**A:** 因为本项目只使用公开API查询市场数据，不需要API Key。

### Q2: 空Key会不会有限制？

**A:** 会有限流（1200次/分钟），但远超本项目需求。

### Q3: 如果要自动交易怎么办？

**A:** 需要按照上述步骤创建API Key，并开启交易权限。但建议先用模拟交易测试！

### Q4: API Key泄露了怎么办？

**A:** 立即登录币安后台删除该Key，并创建新的Key。

### Q5: 本项目会收集我的API Key吗？

**A:** 不会！代码完全开源，且使用空Key，不涉及用户账户信息。

---

**本项目使用币安公开API，无需创建API Key！** 🎉✨🚀
