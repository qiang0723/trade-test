# 回测结果存档

## 2024-01-22 Dual模式优化回测

### 回测配置
- **交易对**: BTCUSDT
- **时间范围**: 2024-01-01 ~ 2024-01-31（1个月）
- **模式**: Dual（双周期独立结论）
- **平仓策略**: signal_reverse（信号反转）
- **初始资金**: $10,000

### 回测结果

| 指标 | 值 |
|------|-----|
| 交易次数 | 75 |
| 胜率 | 24.00% |
| 盈利交易 | 18 |
| 亏损交易 | 57 |
| 平均盈利 | 0.71% |
| 平均亏损 | -0.42% |
| 盈亏比 | 1.68 |
| 总收益率 | -23.34% |
| Buy & Hold收益 | 2.07% |
| 超额收益 | -25.42% |
| 最大回撤 | 21.61% |
| 夏普比率 | -2.55 |
| 最终资金 | $7,665.62 |

### 关键阈值配置

```yaml
# 方向评估阈值
direction:
  trend:
    imbalance: 0.12
    oi_change: 0.02
    price_change: 0.004
  range:
    imbalance: 0.15
    oi_change: 0.025

# 短期评估阈值
dual_timeframe.short_term:
  min_price_change_15m:
    trend: 0.003
    range: 0.006
  min_taker_imbalance: 0.30
  min_volume_ratio: 1.3
  required_signals: 3  # 5选3
```

### 分析结论

1. **信号频率**: 75笔/月 ≈ 2.5笔/天，频率适中
2. **盈亏比正向**: 1.68 > 1，说明盈利时幅度大于亏损
3. **胜率偏低**: 24%需要后续优化
4. **Dual vs Single**: Dual模式交易次数更少(75 vs 194)，信号更精选

### 文件列表
- `BTCUSDT_dual_signal_reverse_20260122_161129.html` - HTML报告
- `BTCUSDT_dual_signal_reverse_20260122_161129.json` - JSON数据
- `BTCUSDT_dual_signal_reverse_20260122_161129_trades.csv` - 交易记录CSV

### 后续优化方向
1. 调整评估方式：按信号准确率而非交易收益评估
2. 测试更多市场环境（牛市/熊市/震荡市）
3. 增加双周期一致性要求
