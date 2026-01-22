"""
回测框架 - 报告生成器

功能：
1. 生成HTML格式回测报告
2. 导出CSV交易记录
3. 生成图表（可选）
"""

import os
import json
from typing import Dict, List
from datetime import datetime


class ReportGenerator:
    """
    回测报告生成器
    
    支持：
    - HTML报告
    - CSV导出
    - JSON导出
    """
    
    @staticmethod
    def generate_html_report(
        result: Dict,
        output_file: str = "backtest_report.html"
    ):
        """
        生成HTML格式回测报告
        
        Args:
            result: 回测结果
            output_file: 输出文件路径
        """
        perf = result['performance']
        trades = result['trades']
        
        # 构建HTML
        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>回测报告 - {result['symbol']}</title>
    <style>
        body {{
            font-family: 'Arial', sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 8px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #4CAF50;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }}
        .metric-value.positive {{
            color: #4CAF50;
        }}
        .metric-value.negative {{
            color: #f44336;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #4CAF50;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .trade-long {{
            color: #4CAF50;
            font-weight: bold;
        }}
        .trade-short {{
            color: #f44336;
            font-weight: bold;
        }}
        .pnl-positive {{
            color: #4CAF50;
        }}
        .pnl-negative {{
            color: #f44336;
        }}
        .summary-box {{
            background: #e8f5e9;
            padding: 20px;
            border-radius: 6px;
            margin: 20px 0;
        }}
        .timestamp {{
            color: #999;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 回测报告</h1>
        <p class="timestamp">生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <div class="summary-box">
            <h3>基本信息</h3>
            <p><strong>交易对:</strong> {result['symbol']}</p>
            <p><strong>回测模式:</strong> {result['mode']}</p>
            <p><strong>平仓策略:</strong> {result['exit_strategy']}</p>
            <p><strong>初始资金:</strong> ${result['initial_capital']:,.2f}</p>
            <p><strong>最终资金:</strong> ${result['final_capital']:,.2f}</p>
        </div>
        
        <h2>📈 绩效指标</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">总收益率</div>
                <div class="metric-value {'positive' if perf['total_return'] > 0 else 'negative'}">
                    {perf['total_return']*100:.2f}%
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">胜率</div>
                <div class="metric-value">
                    {perf['win_rate']*100:.2f}%
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">总交易次数</div>
                <div class="metric-value">
                    {perf['total_trades']}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">夏普比率</div>
                <div class="metric-value">
                    {perf['sharpe_ratio']:.2f}
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">最大回撤</div>
                <div class="metric-value negative">
                    {perf['max_drawdown']*100:.2f}%
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">盈亏比</div>
                <div class="metric-value">
                    {perf['profit_factor']:.2f}
                </div>
            </div>
        </div>
        
        <h2>📊 收益对比</h2>
        <table>
            <tr>
                <th>策略</th>
                <th>收益率</th>
                <th>说明</th>
            </tr>
            <tr>
                <td>L1策略</td>
                <td class="{'pnl-positive' if perf['total_return'] > 0 else 'pnl-negative'}">
                    {perf['total_return']*100:.2f}%
                </td>
                <td>基于L1决策的主动交易</td>
            </tr>
            <tr>
                <td>Buy & Hold</td>
                <td class="{'pnl-positive' if perf['buy_hold_return'] > 0 else 'pnl-negative'}">
                    {perf['buy_hold_return']*100:.2f}%
                </td>
                <td>买入持有基准</td>
            </tr>
            <tr>
                <td>超额收益</td>
                <td class="{'pnl-positive' if perf['excess_return'] > 0 else 'pnl-negative'}">
                    {perf['excess_return']*100:.2f}%
                </td>
                <td>相对基准的超额表现</td>
            </tr>
        </table>
        
        <h2>📝 交易记录</h2>
        <p>共 {len(trades)} 笔交易，显示前50笔：</p>
        <table>
            <tr>
                <th>方向</th>
                <th>开仓时间</th>
                <th>开仓价格</th>
                <th>平仓时间</th>
                <th>平仓价格</th>
                <th>P&L</th>
                <th>P&L金额</th>
                <th>平仓原因</th>
            </tr>
"""
        
        # 添加交易记录（最多50条）
        for trade in trades[:50]:
            entry_time = datetime.fromtimestamp(trade.entry_time / 1000).strftime("%Y-%m-%d %H:%M")
            exit_time = datetime.fromtimestamp(trade.exit_time / 1000).strftime("%Y-%m-%d %H:%M")
            
            direction_class = "trade-long" if trade.direction.value == "long" else "trade-short"
            pnl_class = "pnl-positive" if trade.pnl > 0 else "pnl-negative"
            
            html += f"""
            <tr>
                <td class="{direction_class}">{trade.direction.value.upper()}</td>
                <td>{entry_time}</td>
                <td>${trade.entry_price:,.2f}</td>
                <td>{exit_time}</td>
                <td>${trade.exit_price:,.2f}</td>
                <td class="{pnl_class}">{trade.pnl*100:.2f}%</td>
                <td class="{pnl_class}">${trade.pnl_amount:,.2f}</td>
                <td>{trade.reason}</td>
            </tr>
"""
        
        html += """
        </table>
        
        <h2>💡 总结</h2>
        <div class="summary-box">
"""
        
        # 添加总结
        if perf['total_return'] > 0:
            html += f"""
            <p>✅ <strong>策略表现良好</strong></p>
            <p>总收益率 {perf['total_return']*100:.2f}% 超过Buy & Hold的 {perf['buy_hold_return']*100:.2f}%，
            获得 {perf['excess_return']*100:.2f}% 的超额收益。</p>
"""
        else:
            html += f"""
            <p>⚠️ <strong>策略表现不佳</strong></p>
            <p>总收益率 {perf['total_return']*100:.2f}% 低于Buy & Hold的 {perf['buy_hold_return']*100:.2f}%。</p>
"""
        
        html += f"""
            <p>胜率为 {perf['win_rate']*100:.2f}%，盈亏比为 {perf['profit_factor']:.2f}。</p>
            <p>最大回撤为 {perf['max_drawdown']*100:.2f}%，夏普比率为 {perf['sharpe_ratio']:.2f}。</p>
        </div>
        
    </div>
</body>
</html>
"""
        
        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"✅ HTML报告已生成: {output_file}")
    
    @staticmethod
    def export_trades_csv(
        trades: List,
        output_file: str = "trades.csv"
    ):
        """
        导出交易记录为CSV
        
        Args:
            trades: 交易列表
            output_file: 输出文件路径
        """
        import csv
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # 写入表头
            writer.writerow([
                'Symbol', 'Direction', 'Entry Time', 'Entry Price',
                'Exit Time', 'Exit Price', 'P&L %', 'P&L Amount', 'Reason'
            ])
            
            # 写入数据
            for trade in trades:
                entry_time = datetime.fromtimestamp(trade.entry_time / 1000).strftime("%Y-%m-%d %H:%M:%S")
                exit_time = datetime.fromtimestamp(trade.exit_time / 1000).strftime("%Y-%m-%d %H:%M:%S")
                
                writer.writerow([
                    trade.symbol,
                    trade.direction.value,
                    entry_time,
                    f"{trade.entry_price:.2f}",
                    exit_time,
                    f"{trade.exit_price:.2f}",
                    f"{trade.pnl*100:.2f}",
                    f"{trade.pnl_amount:.2f}",
                    trade.reason
                ])
        
        print(f"✅ CSV文件已导出: {output_file}")
    
    @staticmethod
    def export_result_json(
        result: Dict,
        output_file: str = "backtest_result.json"
    ):
        """
        导出完整回测结果为JSON
        
        Args:
            result: 回测结果
            output_file: 输出文件路径
        """
        # 转换trades为可序列化格式
        serializable_result = {
            'symbol': result['symbol'],
            'mode': result['mode'],
            'exit_strategy': result['exit_strategy'],
            'initial_capital': result['initial_capital'],
            'final_capital': result['final_capital'],
            'performance': result['performance'],
            'trades': [
                {
                    'symbol': t.symbol,
                    'direction': t.direction.value,
                    'entry_time': t.entry_time,
                    'entry_price': t.entry_price,
                    'exit_time': t.exit_time,
                    'exit_price': t.exit_price,
                    'pnl': t.pnl,
                    'pnl_amount': t.pnl_amount,
                    'reason': t.reason
                }
                for t in result['trades']
            ]
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_result, f, indent=2, ensure_ascii=False)
        
        print(f"✅ JSON文件已导出: {output_file}")
