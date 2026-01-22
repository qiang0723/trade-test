# L1 回测框架

**版本**: 1.0.0  
**日期**: 2026-01-21

---

## 📋 概述

L1回测框架是一个完整的回测系统，用于验证L1 Advisory Layer决策的有效性。支持单一决策和双周期决策的对比分析。

### 核心功能

- ✅ **历史数据加载**: 从Binance API获取或使用缓存数据
- ✅ **多周期指标计算**: 自动计算5m/15m/1h/6h多周期指标
- ✅ **L1决策回测**: 支持单一决策和双周期决策
- ✅ **仓位管理**: 模拟真实交易的开平仓逻辑
- ✅ **绩效分析**: 详细的收益、风险、交易统计
- ✅ **报告生成**: HTML/CSV/JSON多格式输出
- ✅ **策略对比**: 单一 vs 双周期决策对比

---

## 🏗️ 架构

```
backtest/
├── __init__.py              # 模块初始化
├── config.yaml              # 配置文件
├── run_backtest.py          # 主程序
├── data_loader.py           # 数据加载器
├── backtest_engine.py       # 回测引擎
├── performance_analyzer.py  # 绩效分析
├── report_generator.py      # 报告生成
├── cache/                   # 数据缓存目录
└── reports/                 # 报告输出目录
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install python-binance pyyaml
```

### 2. 配置回测参数

编辑 `backtest/config.yaml`:

```yaml
data:
  symbol: "BTCUSDT"
  start_date: "2024-01-01"
  end_date: "2024-01-31"
  interval: "1m"
  use_cache: true

backtest:
  initial_capital: 10000.0
  position_size: 1.0
  commission_rate: 0.001
  slippage: 0.0005
  
  modes:
    - "single"    # 单一决策
    - "dual"      # 双周期决策
  
  exit_strategies:
    - "signal_reverse"  # 信号反转平仓
```

### 3. 运行回测

```bash
# 使用默认配置
python backtest/run_backtest.py

# 指定配置文件
python backtest/run_backtest.py --config backtest/config.yaml
```

### 4. 查看报告

回测完成后，在 `backtest/reports/` 目录查看：
- HTML报告（可视化）
- CSV交易记录（Excel可打开）
- JSON完整数据（程序可读）

---

## 📊 回测流程

```
1. 加载历史数据
   ↓
2. 计算多周期指标
   ↓
3. 遍历数据生成L1决策
   ↓
4. 模拟开平仓交易
   ↓
5. 计算P&L和绩效
   ↓
6. 生成报告
```

---

## 🔧 核心组件

### 1. HistoricalDataLoader

**功能**: 加载和准备历史数据

```python
from backtest import HistoricalDataLoader

loader = HistoricalDataLoader()

# 加载K线数据
klines = loader.load_historical_data(
    symbol="BTCUSDT",
    start_date="2024-01-01",
    end_date="2024-01-31",
    interval="1m",
    use_cache=True
)

# 准备L1输入数据
market_data = loader.prepare_market_data(klines, timestamp)
```

**特点**:
- 自动从Binance API获取数据
- 本地缓存加速后续回测
- 计算多周期指标（5m/15m/1h/6h）
- 数据质量验证

### 2. BacktestEngine

**功能**: 核心回测引擎

```python
from backtest import BacktestEngine

engine = BacktestEngine(
    initial_capital=10000.0,
    position_size=1.0,
    commission_rate=0.001,
    slippage=0.0005
)

# 运行回测
result = engine.run_backtest(
    symbol="BTCUSDT",
    market_data_list=market_data_list,
    mode="single",  # "single" | "dual"
    exit_strategy="signal_reverse"
)
```

**特点**:
- 支持单一决策和双周期决策
- 真实的手续费和滑点模拟
- 多种平仓策略（信号反转、止损、固定时间）
- 详细的交易记录

### 3. PerformanceAnalyzer

**功能**: 绩效分析

```python
from backtest import PerformanceAnalyzer

# 分析交易
trade_analysis = PerformanceAnalyzer.analyze_trades(result['trades'])

# 计算风险指标
risk_metrics = PerformanceAnalyzer.calculate_risk_metrics(
    result['trades'],
    initial_capital
)

# 策略对比
comparison = PerformanceAnalyzer.compare_strategies(result1, result2)
```

**指标**:
- 收益指标: 总收益率、超额收益、盈亏比
- 风险指标: 最大回撤、夏普比率、索提诺比率
- 交易指标: 胜率、平均盈亏、连续盈亏

### 4. ReportGenerator

**功能**: 报告生成

```python
from backtest import ReportGenerator

# 生成HTML报告
ReportGenerator.generate_html_report(result, "report.html")

# 导出CSV
ReportGenerator.export_trades_csv(result['trades'], "trades.csv")

# 导出JSON
ReportGenerator.export_result_json(result, "result.json")
```

---

## 📈 回测指标说明

### 收益指标

| 指标 | 说明 | 计算公式 |
|------|------|---------|
| 总收益率 | 策略总收益 | (最终资金 - 初始资金) / 初始资金 |
| Buy & Hold收益 | 买入持有基准 | (结束价 - 开始价) / 开始价 |
| 超额收益 | 相对基准的超额表现 | 总收益率 - Buy & Hold收益 |
| 盈亏比 | 平均盈利/平均亏损 | |avg_win| / |avg_loss| |

### 风险指标

| 指标 | 说明 | 优秀标准 |
|------|------|---------|
| 最大回撤 | 资金曲线最大跌幅 | < 20% |
| 夏普比率 | 风险调整后收益 | > 1.0 |
| 索提诺比率 | 下行风险调整后收益 | > 1.5 |
| 波动率 | 收益标准差 | 越低越好 |

### 交易指标

| 指标 | 说明 | 优秀标准 |
|------|------|---------|
| 胜率 | 盈利交易占比 | > 50% |
| 总交易次数 | 交易频率 | 适中 |
| 平均持仓时间 | 单笔交易时长 | - |
| 连续盈亏 | 最大连续盈利/亏损次数 | - |

---

## 🎯 平仓策略

### 1. signal_reverse（信号反转）

**逻辑**: 当L1决策方向改变时平仓

- 持多时，出现做空或不交易信号 → 平仓
- 持空时，出现做多或不交易信号 → 平仓

**适用**: 跟随L1信号的主动交易

### 2. stop_loss（止损）

**逻辑**: 固定止损 + 信号反转

- 亏损超过5% → 止损平仓
- 同时检查信号反转

**适用**: 风险控制严格的场景

### 3. time_based（固定时间）

**逻辑**: 固定持仓时间（1小时）

- 持仓超过1小时 → 平仓

**适用**: 日内交易场景

---

## 📝 使用示例

### 示例1: 基础回测

```python
from backtest import (
    HistoricalDataLoader,
    BacktestEngine,
    PerformanceAnalyzer,
    ReportGenerator
)

# 1. 加载数据
loader = HistoricalDataLoader()
klines = loader.load_historical_data(
    symbol="BTCUSDT",
    start_date="2024-01-01",
    end_date="2024-01-31",
    interval="1m"
)

# 2. 准备市场数据
market_data_list = []
for kline in klines:
    data = loader.prepare_market_data(klines, kline['timestamp'])
    if data:
        market_data_list.append(data)

# 3. 运行回测
engine = BacktestEngine(initial_capital=10000.0)
result = engine.run_backtest(
    symbol="BTCUSDT",
    market_data_list=market_data_list,
    mode="single",
    exit_strategy="signal_reverse"
)

# 4. 生成报告
ReportGenerator.generate_html_report(result, "report.html")

# 5. 打印摘要
print(PerformanceAnalyzer.generate_summary(result))
```

### 示例2: 策略对比

```python
# 运行单一决策回测
result_single = engine.run_backtest(
    symbol="BTCUSDT",
    market_data_list=market_data_list,
    mode="single",
    exit_strategy="signal_reverse"
)

# 运行双周期决策回测
result_dual = engine.run_backtest(
    symbol="BTCUSDT",
    market_data_list=market_data_list,
    mode="dual",
    exit_strategy="signal_reverse"
)

# 对比分析
comparison = PerformanceAnalyzer.compare_strategies(
    result_single,
    result_dual
)

print(f"更优策略（收益）: {comparison['better_return']}")
print(f"收益率差异: {comparison['total_return_diff']*100:.2f}%")
```

---

## 🔍 常见问题

### Q1: 首次运行很慢？

**A**: 首次运行需要从Binance API获取数据，可能需要几分钟。数据会自动缓存，后续运行会很快。

### Q2: 如何使用缓存数据？

**A**: 在配置文件中设置 `use_cache: true`，或在代码中传入 `use_cache=True`。

### Q3: 回测结果不理想怎么办？

**A**: 
1. 检查L1配置（`config/l1_thresholds.yaml`）
2. 尝试不同的平仓策略
3. 调整手续费和滑点参数
4. 使用更长的回测周期

### Q4: 如何回测多个币种？

**A**: 修改配置文件中的 `symbol` 字段，或编写循环脚本。

### Q5: 数据不足怎么办？

**A**: 
- 至少需要6小时历史数据（360条1分钟K线）
- 建议使用1个月以上的数据
- 检查Binance API是否可访问

---

## 🛠️ 高级配置

### 自定义平仓策略

在 `backtest_engine.py` 的 `_should_exit()` 方法中添加自定义逻辑：

```python
def _should_exit(self, ...):
    # 自定义策略
    if strategy == "custom":
        # 你的逻辑
        if some_condition:
            return (True, "custom_reason")
    
    return (False, "")
```

### 自定义绩效指标

在 `performance_analyzer.py` 中添加新的分析方法：

```python
@staticmethod
def custom_metric(trades: List) -> float:
    # 你的计算逻辑
    return result
```

---

## 📚 参考资料

- [L1 Advisory Layer文档](../doc/平台详解3.2.md)
- [PR-DUAL双周期文档](../doc/PR-DUAL_双周期独立结论.md)
- [Binance API文档](https://binance-docs.github.io/apidocs/)

---

## 🤝 贡献

欢迎提交Issue和Pull Request！

---

## 📄 许可

MIT License

---

**版本历史**:

- **v1.0.0** (2026-01-21): 初始版本，支持单一和双周期决策回测
