#!/usr/bin/env python
# coding: utf-8

"""
多币种行情数据获取脚本
支持同时获取多个加密货币的行情数据
"""

from binance.client import Client
import pandas as pd
from datetime import datetime
import time

class MultiSymbolMarketData:
    def __init__(self):
        """初始化客户端"""
        self.client = Client("", "")
        
    def get_symbol_data(self, symbol):
        """获取单个交易对的数据"""
        try:
            # 获取24小时统计
            ticker = self.client.get_ticker(symbol=symbol)
            
            data = {
                'symbol': symbol,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'price': float(ticker['lastPrice']),
                'high_24h': float(ticker['highPrice']),
                'low_24h': float(ticker['lowPrice']),
                'change_24h': float(ticker['priceChange']),
                'change_percent_24h': float(ticker['priceChangePercent']),
                'volume_24h': float(ticker['volume']),
                'quote_volume_24h': float(ticker['quoteVolume'])
            }
            
            return data
        except Exception as e:
            print(f"❌ 获取 {symbol} 数据失败: {e}")
            return None
    
    def get_multiple_symbols(self, symbols):
        """获取多个交易对的数据"""
        print(f"\n{'='*80}")
        print(f"{'📊 加密货币市场数据':^80}")
        print(f"{'='*80}")
        print(f"⏰ 时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
        
        all_data = []
        
        for i, symbol in enumerate(symbols, 1):
            print(f"[{i}/{len(symbols)}] 正在获取 {symbol} 数据...", end=' ')
            data = self.get_symbol_data(symbol)
            
            if data:
                all_data.append(data)
                print("✅")
            else:
                print("❌")
            
            # 避免请求过快
            if i < len(symbols):
                time.sleep(0.2)
        
        return all_data
    
    def display_data(self, data_list):
        """显示数据表格"""
        if not data_list:
            print("\n❌ 没有获取到任何数据")
            return
        
        # 转换为DataFrame
        df = pd.DataFrame(data_list)
        
        # 添加涨跌标识
        df['trend'] = df['change_percent_24h'].apply(lambda x: '📈' if x > 0 else '📉')
        
        # 按涨跌幅排序
        df = df.sort_values('change_percent_24h', ascending=False)
        
        print(f"\n{'='*80}")
        print(f"{'💹 市场行情总览':^80}")
        print(f"{'='*80}\n")
        
        # 显示表格
        print(f"{'币种':<12} {'当前价格':<15} {'24h最高':<15} {'24h最低':<15} {'24h涨跌':<12} {'24h成交量':<15}")
        print("-" * 100)
        
        for _, row in df.iterrows():
            symbol_short = row['symbol'].replace('USDT', '')
            price = f"${row['price']:,.2f}"
            high = f"${row['high_24h']:,.2f}"
            low = f"${row['low_24h']:,.2f}"
            change = f"{row['trend']} {row['change_percent_24h']:+.2f}%"
            volume = f"{row['volume_24h']:,.0f}"
            
            print(f"{symbol_short:<12} {price:<15} {high:<15} {low:<15} {change:<12} {volume:<15}")
        
        print(f"\n{'='*80}")
        
        # 统计信息
        avg_change = df['change_percent_24h'].mean()
        up_count = len(df[df['change_percent_24h'] > 0])
        down_count = len(df[df['change_percent_24h'] < 0])
        
        print(f"\n📊 市场统计:")
        print(f"  • 总币种数: {len(df)}")
        print(f"  • 上涨: {up_count} 个 📈")
        print(f"  • 下跌: {down_count} 个 📉")
        print(f"  • 平均涨跌幅: {avg_change:+.2f}%")
        
        # 涨幅榜
        print(f"\n🏆 24小时涨幅榜 TOP 3:")
        for i, (_, row) in enumerate(df.head(3).iterrows(), 1):
            symbol_short = row['symbol'].replace('USDT', '')
            print(f"  {i}. {symbol_short:<10} {row['change_percent_24h']:+.2f}%  (${row['price']:,.2f})")
        
        # 跌幅榜
        print(f"\n📉 24小时跌幅榜 TOP 3:")
        for i, (_, row) in enumerate(df.tail(3).iloc[::-1].iterrows(), 1):
            symbol_short = row['symbol'].replace('USDT', '')
            print(f"  {i}. {symbol_short:<10} {row['change_percent_24h']:+.2f}%  (${row['price']:,.2f})")
        
        print(f"\n{'='*80}\n")
        
        return df
    
    def export_to_csv(self, df, filename=None):
        """导出为CSV文件"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"crypto_market_{timestamp}.csv"
        
        try:
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"✅ 数据已保存到: {filename}\n")
            return filename
        except Exception as e:
            print(f"❌ 保存文件失败: {e}\n")
            return None


def main():
    """主函数"""
    print("\n" + "="*80)
    print(f"{'🌟 多币种行情数据获取工具 🌟':^80}")
    print("="*80 + "\n")
    
    # 定义要获取的交易对
    symbols = [
        "BTCUSDT",   # 比特币
        "ETHUSDT",   # 以太坊
        "BNBUSDT",   # 币安币
        "SOLUSDT",   # Solana
        "XRPUSDT",   # 瑞波币
        "ADAUSDT",   # 艾达币
        "DOGEUSDT",  # 狗狗币
        "DOTUSDT",   # 波卡
        "MATICUSDT", # Polygon
        "LINKUSDT",  # Chainlink
        "AVAXUSDT",  # Avalanche
        "UNIUSDT",   # Uniswap
        "ATOMUSDT",  # Cosmos
        "LTCUSDT",   # 莱特币
        "ETCUSDT",   # 以太经典
    ]
    
    print(f"📋 将获取以下 {len(symbols)} 个币种的数据:")
    for i, symbol in enumerate(symbols, 1):
        symbol_short = symbol.replace('USDT', '')
        print(f"  {i:2d}. {symbol_short}")
    
    # 创建实例
    market = MultiSymbolMarketData()
    
    # 获取数据
    data_list = market.get_multiple_symbols(symbols)
    
    # 显示数据
    df = market.display_data(data_list)
    
    # 导出数据
    if df is not None and not df.empty:
        market.export_to_csv(df)
    
    print("💡 提示: 数据来源于币安交易所 (Binance)")
    print("💡 可以修改代码中的 symbols 列表来获取其他币种\n")


if __name__ == "__main__":
    main()
