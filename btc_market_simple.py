#!/usr/bin/env python
# coding: utf-8

"""
BTC行情和交易数据获取脚本 - 简化版
直接运行即可获取完整市场数据，无需交互
"""

from binance.client import Client
import pandas as pd
from datetime import datetime

class BTCMarketData:
    def __init__(self):
        """初始化客户端（不需要API密钥即可获取公开数据）"""
        self.client = Client("", "")
        self.symbol = "BTCUSDT"
    
    def get_current_price(self):
        """获取BTC当前价格"""
        try:
            ticker = self.client.get_symbol_ticker(symbol=self.symbol)
            price = float(ticker['price'])
            print(f"\n{'='*60}")
            print(f"💰 BTC 当前价格: ${price:,.2f} USDT")
            print(f"{'='*60}")
            return price
        except Exception as e:
            print(f"❌ 获取价格失败: {e}")
            return None
    
    def get_24h_ticker(self):
        """获取BTC 24小时行情统计"""
        try:
            ticker = self.client.get_ticker(symbol=self.symbol)
            
            print(f"\n{'='*60}")
            print(f"📊 BTC 24小时行情数据")
            print(f"{'='*60}")
            print(f"当前价格:       ${float(ticker['lastPrice']):>15,.2f}")
            print(f"24h最高价:      ${float(ticker['highPrice']):>15,.2f}")
            print(f"24h最低价:      ${float(ticker['lowPrice']):>15,.2f}")
            
            change_percent = float(ticker['priceChangePercent'])
            change_symbol = "📈" if change_percent > 0 else "📉"
            print(f"24h涨跌幅:      {change_symbol} {change_percent:>14.2f}%")
            print(f"24h涨跌额:      ${float(ticker['priceChange']):>15,.2f}")
            print(f"24h成交量:      {float(ticker['volume']):>15,.2f} BTC")
            print(f"24h成交额:      ${float(ticker['quoteVolume']):>15,.2f}")
            print(f"开盘价:         ${float(ticker['openPrice']):>15,.2f}")
            print(f"加权平均价:     ${float(ticker['weightedAvgPrice']):>15,.2f}")
            print(f"{'='*60}")
            
            return ticker
        except Exception as e:
            print(f"❌ 获取24小时行情失败: {e}")
            return None
    
    def get_orderbook(self, limit=5):
        """获取订单簿（交易深度）"""
        try:
            depth = self.client.get_order_book(symbol=self.symbol, limit=limit)
            
            print(f"\n{'='*60}")
            print(f"📖 BTC 订单深度 (前{limit}档)")
            print(f"{'='*60}")
            
            print(f"\n🔴 卖单 (Ask):")
            print(f"{'价格':<20} {'数量':<20}")
            print("-" * 40)
            for ask in reversed(depth['asks'][:limit]):
                price = float(ask[0])
                qty = float(ask[1])
                print(f"${price:<19,.2f} {qty:<20,.6f}")
            
            print(f"\n{'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━':^40}")
            current_price = float(self.client.get_symbol_ticker(symbol=self.symbol)['price'])
            print(f"{'当前价格: $' + f'{current_price:,.2f}':^40}")
            print(f"{'━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━':^40}")
            
            print(f"\n🟢 买单 (Bid):")
            print(f"{'价格':<20} {'数量':<20}")
            print("-" * 40)
            for bid in depth['bids'][:limit]:
                price = float(bid[0])
                qty = float(bid[1])
                print(f"${price:<19,.2f} {qty:<20,.6f}")
            
            print(f"{'='*60}")
            return depth
        except Exception as e:
            print(f"❌ 获取订单深度失败: {e}")
            return None
    
    def get_recent_trades(self, limit=15):
        """获取最近成交记录"""
        try:
            trades = self.client.get_recent_trades(symbol=self.symbol, limit=limit)
            
            print(f"\n{'='*60}")
            print(f"💹 BTC 最近{limit}笔成交")
            print(f"{'='*60}")
            print(f"{'时间':<20} {'价格':<15} {'数量':<15} {'方向':<10}")
            print("-" * 60)
            
            for trade in trades:
                timestamp = datetime.fromtimestamp(trade['time']/1000).strftime('%Y-%m-%d %H:%M:%S')
                price = float(trade['price'])
                qty = float(trade['qty'])
                side = "🟢买入" if trade['isBuyerMaker'] == False else "🔴卖出"
                print(f"{timestamp:<20} ${price:<14,.2f} {qty:<15,.6f} {side:<10}")
            
            print(f"{'='*60}")
            return trades
        except Exception as e:
            print(f"❌ 获取成交记录失败: {e}")
            return None
    
    def get_klines(self, interval='1h', limit=12):
        """
        获取K线数据
        interval: 时间间隔 '1m', '5m', '15m', '1h', '4h', '1d', '1w', '1M'
        limit: 获取数量
        """
        try:
            klines = self.client.get_klines(
                symbol=self.symbol,
                interval=interval,
                limit=limit
            )
            
            # 转换为DataFrame
            df = pd.DataFrame(klines, columns=[
                '开盘时间', '开盘价', '最高价', '最低价', '收盘价', '成交量',
                '收盘时间', '成交额', '成交笔数', '主动买入成交量', '主动买入成交额', '忽略'
            ])
            
            # 转换数据类型
            df['开盘时间'] = pd.to_datetime(df['开盘时间'], unit='ms')
            df['收盘时间'] = pd.to_datetime(df['收盘时间'], unit='ms')
            
            for col in ['开盘价', '最高价', '最低价', '收盘价', '成交量', '成交额']:
                df[col] = df[col].astype(float)
            
            print(f"\n{'='*60}")
            print(f"📈 BTC K线数据 (间隔: {interval}, 数量: {limit})")
            print(f"{'='*60}")
            
            # 显示最近的数据
            display_df = df[['开盘时间', '开盘价', '最高价', '最低价', '收盘价', '成交量']].tail(10)
            
            print(f"\n{'时间':<20} {'开盘':<12} {'最高':<12} {'最低':<12} {'收盘':<12} {'成交量':<12}")
            print("-" * 80)
            for _, row in display_df.iterrows():
                time_str = row['开盘时间'].strftime('%Y-%m-%d %H:%M')
                print(f"{time_str:<20} ${row['开盘价']:<11,.2f} ${row['最高价']:<11,.2f} "
                      f"${row['最低价']:<11,.2f} ${row['收盘价']:<11,.2f} {row['成交量']:<12,.2f}")
            
            print(f"{'='*60}")
            return df
        except Exception as e:
            print(f"❌ 获取K线数据失败: {e}")
            return None
    
    def get_all_market_data(self):
        """一次性获取所有市场数据"""
        print(f"\n{'#'*60}")
        print(f"{'🚀 BTC 完整市场数据报告 🚀':^60}")
        print(f"{'#'*60}")
        print(f"⏰ 生成时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
        
        # 1. 当前价格
        self.get_current_price()
        
        # 2. 24小时统计
        self.get_24h_ticker()
        
        # 3. 订单深度
        self.get_orderbook(limit=5)
        
        # 4. 最近成交
        self.get_recent_trades(limit=15)
        
        # 5. K线数据 - 1小时
        self.get_klines(interval='1h', limit=12)
        
        # 6. K线数据 - 日线
        print(f"\n")
        self.get_klines(interval='1d', limit=7)
        
        print(f"\n{'#'*60}")
        print(f"{'✅ 报告生成完成 ✅':^60}")
        print(f"{'#'*60}\n")


def main():
    """主函数"""
    print("\n" + "="*60)
    print(f"{'🌟 BTC行情数据获取工具 🌟':^60}")
    print("="*60)
    
    # 创建实例并获取完整市场数据
    btc = BTCMarketData()
    btc.get_all_market_data()
    
    print("\n💡 提示: 数据来源于币安交易所 (Binance)")
    print("💡 所有数据为实时公开市场数据\n")


if __name__ == "__main__":
    main()
