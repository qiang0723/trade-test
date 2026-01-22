"""
回测框架 - 主程序

使用方法:
    python backtest/run_backtest.py

或指定配置文件:
    python backtest/run_backtest.py --config backtest/config.yaml
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
import yaml
import logging
from datetime import datetime

from backtest.data_loader import HistoricalDataLoader
from backtest.backtest_engine import BacktestEngine
from backtest.performance_analyzer import PerformanceAnalyzer
from backtest.report_generator import ReportGenerator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_file: str) -> dict:
    """加载配置文件"""
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def run_single_backtest(
    symbol: str,
    market_data_list: list,
    mode: str,
    exit_strategy: str,
    backtest_config: dict
) -> dict:
    """
    运行单次回测
    
    Args:
        symbol: 交易对
        market_data_list: 市场数据列表
        mode: 回测模式
        exit_strategy: 平仓策略
        backtest_config: 回测配置
    
    Returns:
        dict: 回测结果
    """
    logger.info(f"Running backtest: mode={mode}, exit_strategy={exit_strategy}")
    
    # 创建回测引擎
    engine = BacktestEngine(
        initial_capital=backtest_config['initial_capital'],
        position_size=backtest_config['position_size'],
        commission_rate=backtest_config['commission_rate'],
        slippage=backtest_config['slippage']
    )
    
    # 运行回测
    result = engine.run_backtest(
        symbol=symbol,
        market_data_list=market_data_list,
        mode=mode,
        exit_strategy=exit_strategy
    )
    
    return result


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='L1 Backtest Framework')
    parser.add_argument(
        '--config',
        type=str,
        default='backtest/config.yaml',
        help='配置文件路径'
    )
    args = parser.parse_args()
    
    # 加载配置
    logger.info(f"Loading config from: {args.config}")
    config = load_config(args.config)
    
    data_config = config['data']
    backtest_config = config['backtest']
    output_config = config['output']
    
    # 创建输出目录
    os.makedirs(output_config['reports_dir'], exist_ok=True)
    os.makedirs('backtest/cache', exist_ok=True)
    
    print("=" * 60)
    print("🚀 L1 回测框架")
    print("=" * 60)
    print(f"交易对: {data_config['symbol']}")
    print(f"时间范围: {data_config['start_date']} ~ {data_config['end_date']}")
    print(f"初始资金: ${backtest_config['initial_capital']:,.2f}")
    print("=" * 60)
    print()
    
    # 1. 加载历史数据
    print("📊 步骤1: 加载历史数据...")
    loader = HistoricalDataLoader()
    
    try:
        klines_1m = loader.load_historical_data(
            symbol=data_config['symbol'],
            start_date=data_config['start_date'],
            end_date=data_config['end_date'],
            interval=data_config['interval'],
            use_cache=data_config['use_cache']
        )
        print(f"✅ 加载完成: {len(klines_1m)} 条K线数据")
    except Exception as e:
        logger.error(f"数据加载失败: {e}")
        print(f"❌ 数据加载失败: {e}")
        print("\n💡 提示:")
        print("  1. 首次运行需要从Binance API获取数据")
        print("  2. 确保已安装: pip install python-binance")
        print("  3. 或使用缓存数据: use_cache: true")
        return
    
    # 2. 准备市场数据
    print("\n📈 步骤2: 准备市场数据...")
    market_data_list = []
    
    for i, kline in enumerate(klines_1m):
        market_data = loader.prepare_market_data(klines_1m, kline['timestamp'])
        if market_data:
            market_data_list.append(market_data)
        
        if (i + 1) % 1000 == 0:
            print(f"  处理进度: {i + 1}/{len(klines_1m)}")
    
    print(f"✅ 准备完成: {len(market_data_list)} 个数据点")
    
    if len(market_data_list) < 100:
        print("❌ 数据点不足，无法进行回测")
        return
    
    # 3. 运行回测
    print("\n🔄 步骤3: 运行回测...")
    results = {}
    
    for mode in backtest_config['modes']:
        for exit_strategy in backtest_config['exit_strategies']:
            key = f"{mode}_{exit_strategy}"
            print(f"\n  运行: {mode} + {exit_strategy}")
            
            result = run_single_backtest(
                symbol=data_config['symbol'],
                market_data_list=market_data_list,
                mode=mode,
                exit_strategy=exit_strategy,
                backtest_config=backtest_config
            )
            
            results[key] = result
            
            # 打印简要结果
            perf = result['performance']
            print(f"    总收益: {perf['total_return']*100:.2f}%")
            print(f"    胜率: {perf['win_rate']*100:.2f}%")
            print(f"    交易次数: {perf['total_trades']}")
    
    # 4. 生成报告
    print("\n📝 步骤4: 生成报告...")
    
    for key, result in results.items():
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{data_config['symbol']}_{key}_{timestamp}"
        
        # HTML报告
        if output_config['generate_html']:
            html_file = os.path.join(output_config['reports_dir'], f"{base_name}.html")
            ReportGenerator.generate_html_report(result, html_file)
        
        # CSV导出
        if output_config['export_csv']:
            csv_file = os.path.join(output_config['reports_dir'], f"{base_name}_trades.csv")
            ReportGenerator.export_trades_csv(result['trades'], csv_file)
        
        # JSON导出
        if output_config['export_json']:
            json_file = os.path.join(output_config['reports_dir'], f"{base_name}.json")
            ReportGenerator.export_result_json(result, json_file)
    
    # 5. 对比分析（如果有多个策略）
    if len(results) > 1:
        print("\n📊 步骤5: 对比分析...")
        
        result_list = list(results.values())
        comparison = PerformanceAnalyzer.compare_strategies(
            result_list[0], result_list[1]
        )
        
        print(f"\n策略对比: {comparison['strategy1']} vs {comparison['strategy2']}")
        print(f"  收益率差异: {comparison['total_return_diff']*100:.2f}%")
        print(f"  胜率差异: {comparison['win_rate_diff']*100:.2f}%")
        print(f"  更优策略（收益）: {comparison['better_return']}")
        print(f"  更优策略（夏普）: {comparison['better_sharpe']}")
    
    # 6. 打印摘要
    print("\n" + "=" * 60)
    print("📋 回测摘要")
    print("=" * 60)
    
    for key, result in results.items():
        print(f"\n{key}:")
        print(PerformanceAnalyzer.generate_summary(result))
    
    print("=" * 60)
    print("✅ 回测完成！")
    print(f"📁 报告目录: {output_config['reports_dir']}")
    print("=" * 60)


if __name__ == '__main__':
    main()
