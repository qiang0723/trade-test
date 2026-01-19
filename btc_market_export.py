#!/usr/bin/env python
# coding: utf-8

"""
BTC行情数据获取并导出
支持导出为JSON和CSV格式
"""

from binance.client import Client
import pandas as pd
from datetime import datetime
import json
import os

class BTCMarketExporter:
    def __init__(self):
        """初始化客户端"""
        self.client = Client("", "")
        self.symbol = "BTCUSDT"
        self.export_dir = "btc_market_data"
        
        # 创建导出目录
        if not os.path.exists(self.export_dir):
            os.makedirs(self.export_dir)
            print(f"✅ 创建导出目录: {self.export_dir}")
    
    def get_all_data(self):
        """获取所有市场数据"""
        print("\n📡 正在获取BTC市场数据...")
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "symbol": self.symbol
        }
        
        try:
            # 1. 当前价格
            print("  ├─ 获取当前价格...")
            ticker = self.client.get_symbol_ticker(symbol=self.symbol)
            data['current_price'] = float(ticker['price'])
            
            # 2. 24小时统计
            print("  ├─ 获取24小时统计...")
            ticker_24h = self.client.get_ticker(symbol=self.symbol)
            data['ticker_24h'] = {
                'last_price': float(ticker_24h['lastPrice']),
                'high_price': float(ticker_24h['highPrice']),
                'low_price': float(ticker_24h['lowPrice']),
                'price_change': float(ticker_24h['priceChange']),
                'price_change_percent': float(ticker_24h['priceChangePercent']),
                'volume': float(ticker_24h['volume']),
                'quote_volume': float(ticker_24h['quoteVolume']),
                'open_price': float(ticker_24h['openPrice']),
                'weighted_avg_price': float(ticker_24h['weightedAvgPrice'])
            }
            
            # 3. 订单深度
            print("  ├─ 获取订单深度...")
            depth = self.client.get_order_book(symbol=self.symbol, limit=10)
            data['orderbook'] = {
                'bids': [[float(x[0]), float(x[1])] for x in depth['bids'][:10]],
                'asks': [[float(x[0]), float(x[1])] for x in depth['asks'][:10]]
            }
            
            # 4. 最近成交
            print("  ├─ 获取最近成交...")
            trades = self.client.get_recent_trades(symbol=self.symbol, limit=20)
            data['recent_trades'] = [{
                'time': datetime.fromtimestamp(t['time']/1000).isoformat(),
                'price': float(t['price']),
                'qty': float(t['qty']),
                'is_buyer_maker': t['isBuyerMaker']
            } for t in trades]
            
            # 5. K线数据 - 1小时
            print("  ├─ 获取1小时K线...")
            klines_1h = self.client.get_klines(symbol=self.symbol, interval='1h', limit=24)
            data['klines_1h'] = self._process_klines(klines_1h)
            
            # 6. K线数据 - 日线
            print("  └─ 获取日线K线...")
            klines_1d = self.client.get_klines(symbol=self.symbol, interval='1d', limit=30)
            data['klines_1d'] = self._process_klines(klines_1d)
            
            print("✅ 数据获取完成！\n")
            return data
            
        except Exception as e:
            print(f"❌ 获取数据失败: {e}")
            return None
    
    def _process_klines(self, klines):
        """处理K线数据"""
        processed = []
        for k in klines:
            processed.append({
                'open_time': datetime.fromtimestamp(k[0]/1000).isoformat(),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
                'close_time': datetime.fromtimestamp(k[6]/1000).isoformat(),
                'quote_volume': float(k[7]),
                'trades': int(k[8])
            })
        return processed
    
    def export_json(self, data):
        """导出为JSON格式"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{self.export_dir}/btc_market_{timestamp}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ JSON文件已保存: {filename}")
            return filename
        except Exception as e:
            print(f"❌ 保存JSON失败: {e}")
            return None
    
    def export_csv(self, data):
        """导出为CSV格式"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        try:
            # 1. 导出24小时统计
            ticker_df = pd.DataFrame([data['ticker_24h']])
            ticker_df.insert(0, 'timestamp', data['timestamp'])
            ticker_file = f"{self.export_dir}/btc_ticker_24h_{timestamp}.csv"
            ticker_df.to_csv(ticker_file, index=False, encoding='utf-8-sig')
            print(f"✅ 24小时统计已保存: {ticker_file}")
            
            # 2. 导出订单深度 - 买单
            bids_df = pd.DataFrame(data['orderbook']['bids'], columns=['price', 'quantity'])
            bids_df.insert(0, 'type', 'bid')
            bids_file = f"{self.export_dir}/btc_orderbook_bids_{timestamp}.csv"
            bids_df.to_csv(bids_file, index=False, encoding='utf-8-sig')
            print(f"✅ 买单深度已保存: {bids_file}")
            
            # 3. 导出订单深度 - 卖单
            asks_df = pd.DataFrame(data['orderbook']['asks'], columns=['price', 'quantity'])
            asks_df.insert(0, 'type', 'ask')
            asks_file = f"{self.export_dir}/btc_orderbook_asks_{timestamp}.csv"
            asks_df.to_csv(asks_file, index=False, encoding='utf-8-sig')
            print(f"✅ 卖单深度已保存: {asks_file}")
            
            # 4. 导出最近成交
            trades_df = pd.DataFrame(data['recent_trades'])
            trades_file = f"{self.export_dir}/btc_recent_trades_{timestamp}.csv"
            trades_df.to_csv(trades_file, index=False, encoding='utf-8-sig')
            print(f"✅ 最近成交已保存: {trades_file}")
            
            # 5. 导出1小时K线
            klines_1h_df = pd.DataFrame(data['klines_1h'])
            klines_1h_file = f"{self.export_dir}/btc_klines_1h_{timestamp}.csv"
            klines_1h_df.to_csv(klines_1h_file, index=False, encoding='utf-8-sig')
            print(f"✅ 1小时K线已保存: {klines_1h_file}")
            
            # 6. 导出日线K线
            klines_1d_df = pd.DataFrame(data['klines_1d'])
            klines_1d_file = f"{self.export_dir}/btc_klines_1d_{timestamp}.csv"
            klines_1d_df.to_csv(klines_1d_file, index=False, encoding='utf-8-sig')
            print(f"✅ 日线K线已保存: {klines_1d_file}")
            
            return True
        except Exception as e:
            print(f"❌ 保存CSV失败: {e}")
            return False
    
    def print_summary(self, data):
        """打印数据摘要"""
        print("\n" + "="*60)
        print(f"{'📊 BTC市场数据摘要':^60}")
        print("="*60)
        print(f"⏰ 时间: {data['timestamp']}")
        print(f"💰 当前价格: ${data['current_price']:,.2f}")
        print(f"📈 24h最高: ${data['ticker_24h']['high_price']:,.2f}")
        print(f"📉 24h最低: ${data['ticker_24h']['low_price']:,.2f}")
        
        change_percent = data['ticker_24h']['price_change_percent']
        symbol = "📈" if change_percent > 0 else "📉"
        print(f"{symbol} 24h涨跌: {change_percent:.2f}%")
        print(f"💹 24h成交量: {data['ticker_24h']['volume']:,.2f} BTC")
        print(f"💵 24h成交额: ${data['ticker_24h']['quote_volume']:,.2f}")
        print("="*60 + "\n")


def main():
    """主函数"""
    print("\n" + "="*60)
    print(f"{'🌟 BTC行情数据导出工具 🌟':^60}")
    print("="*60 + "\n")
    
    # 创建导出器
    exporter = BTCMarketExporter()
    
    # 获取数据
    data = exporter.get_all_data()
    
    if data:
        # 打印摘要
        exporter.print_summary(data)
        
        # 导出JSON
        print("📝 正在导出数据...\n")
        exporter.export_json(data)
        
        # 导出CSV
        print()
        exporter.export_csv(data)
        
        print("\n" + "="*60)
        print(f"{'✅ 所有数据导出完成！':^60}")
        print("="*60)
        print(f"\n💡 数据已保存到目录: {exporter.export_dir}/")
        print("💡 包含JSON和CSV两种格式")
        print("💡 可使用Excel或其他工具打开CSV文件\n")
    else:
        print("\n❌ 数据获取失败，请检查网络连接\n")


if __name__ == "__main__":
    main()
