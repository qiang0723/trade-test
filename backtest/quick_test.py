"""
回测框架快速测试

使用模拟数据快速验证回测框架功能
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import random
from datetime import datetime, timedelta
from backtest import BacktestEngine, PerformanceAnalyzer, ReportGenerator


def generate_mock_data(days: int = 7) -> list:
    """
    生成模拟市场数据
    
    Args:
        days: 天数
    
    Returns:
        list: 市场数据列表
    """
    print(f"生成 {days} 天的模拟数据...")
    
    data_list = []
    start_time = int(datetime.now().timestamp() * 1000) - days * 24 * 3600 * 1000
    base_price = 50000.0
    
    # 每分钟一个数据点
    for i in range(days * 24 * 60):
        timestamp = start_time + i * 60 * 1000
        
        # 模拟价格波动（随机游走 + 趋势）
        trend = 0.0001 if i % 1440 < 720 else -0.0001  # 半天上涨，半天下跌
        price_change = random.gauss(trend, 0.002)
        base_price *= (1 + price_change)
        
        # 模拟各周期变化
        price_change_5m = random.gauss(0, 0.003)
        price_change_15m = random.gauss(0, 0.005)
        price_change_1h = random.gauss(trend * 60, 0.01)
        price_change_6h = random.gauss(trend * 360, 0.02)
        
        # 模拟成交量和失衡
        volume_1h = random.uniform(800000, 1200000)
        volume_24h = volume_1h * 24
        
        taker_imbalance_5m = random.gauss(0, 0.3)
        taker_imbalance_15m = random.gauss(0, 0.4)
        buy_sell_imbalance = random.gauss(0, 0.3)
        
        volume_ratio_5m = random.uniform(0.8, 1.5)
        volume_ratio_15m = random.uniform(0.8, 1.5)
        
        data = {
            'price': base_price,
            'timestamp': timestamp,
            
            'price_change_5m': price_change_5m,
            'price_change_15m': price_change_15m,
            'price_change_1h': price_change_1h,
            'price_change_6h': price_change_6h,
            
            'volume_1h': volume_1h,
            'volume_24h': volume_24h,
            'volume_ratio_5m': volume_ratio_5m,
            'volume_ratio_15m': volume_ratio_15m,
            
            'taker_imbalance_5m': taker_imbalance_5m,
            'taker_imbalance_15m': taker_imbalance_15m,
            'buy_sell_imbalance': buy_sell_imbalance,
            
            'oi_change_1h': random.gauss(0, 0.01),
            'oi_change_6h': random.gauss(0, 0.02),
            'oi_change_5m': random.gauss(0, 0.005),
            'oi_change_15m': random.gauss(0, 0.008),
            
            'funding_rate': 0.0001,
        }
        
        data_list.append(data)
    
    print(f"✅ 生成完成: {len(data_list)} 个数据点")
    return data_list


def main():
    """主函数"""
    print("=" * 60)
    print("🧪 回测框架快速测试")
    print("=" * 60)
    print()
    
    # 1. 生成模拟数据
    market_data_list = generate_mock_data(days=7)
    
    # 2. 运行单一决策回测
    print("\n📊 运行单一决策回测...")
    engine_single = BacktestEngine(
        initial_capital=10000.0,
        position_size=1.0,
        commission_rate=0.001,
        slippage=0.0005
    )
    
    result_single = engine_single.run_backtest(
        symbol="MOCK_BTC",
        market_data_list=market_data_list,
        mode="single",
        exit_strategy="signal_reverse"
    )
    
    print(f"✅ 单一决策完成")
    print(f"   交易次数: {result_single['performance']['total_trades']}")
    print(f"   总收益: {result_single['performance']['total_return']*100:.2f}%")
    
    # 3. 运行双周期决策回测
    print("\n📊 运行双周期决策回测...")
    engine_dual = BacktestEngine(
        initial_capital=10000.0,
        position_size=1.0,
        commission_rate=0.001,
        slippage=0.0005
    )
    
    result_dual = engine_dual.run_backtest(
        symbol="MOCK_BTC",
        market_data_list=market_data_list,
        mode="dual",
        exit_strategy="signal_reverse"
    )
    
    print(f"✅ 双周期决策完成")
    print(f"   交易次数: {result_dual['performance']['total_trades']}")
    print(f"   总收益: {result_dual['performance']['total_return']*100:.2f}%")
    
    # 4. 对比分析
    print("\n📈 策略对比...")
    comparison = PerformanceAnalyzer.compare_strategies(result_single, result_dual)
    
    print(f"   更优策略（收益）: {comparison['better_return']}")
    print(f"   收益率差异: {comparison['total_return_diff']*100:.2f}%")
    print(f"   胜率差异: {comparison['win_rate_diff']*100:.2f}%")
    
    # 5. 生成报告
    print("\n📝 生成报告...")
    os.makedirs("backtest/reports", exist_ok=True)
    
    ReportGenerator.generate_html_report(
        result_single,
        "backtest/reports/quick_test_single.html"
    )
    
    ReportGenerator.generate_html_report(
        result_dual,
        "backtest/reports/quick_test_dual.html"
    )
    
    # 6. 打印摘要
    print("\n" + "=" * 60)
    print("📋 单一决策摘要")
    print("=" * 60)
    print(PerformanceAnalyzer.generate_summary(result_single))
    
    print("\n" + "=" * 60)
    print("📋 双周期决策摘要")
    print("=" * 60)
    print(PerformanceAnalyzer.generate_summary(result_dual))
    
    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("📁 报告位置: backtest/reports/")
    print("=" * 60)


if __name__ == '__main__':
    main()
