#!/usr/bin/env python
# coding: utf-8

"""
BTC行情和交易数据获取脚本
支持获取实时价格、24小时统计、K线数据、交易深度等
"""

from binance.client import Client
import pandas as pd
from datetime import datetime
import json

class BTCMarketData:
    def __init__(self, api_key=None, api_secret=None):
        """
        初始化客户端
        api_key 和 api_secret 可选，获取公开数据不需要
        """
        if api_key and api_secret:
            self.client = Client(api_key, api_secret)
        else:
            # 不需要API密钥也能获取公开市场数据
            self.client = Client("", "")
        self.symbol = "BTCUSDT"
    
    def get_current_price(self):
        """获取BTC当前价格"""
        try:
            ticker = self.client.get_symbol_ticker(symbol=self.symbol)
            price = float(ticker['price'])
            print(f"\n{'='*50}")
            print(f"BTC 当前价格: ${price:,.2f}")
            print(f"{'='*50}")
            return price
        except Exception as e:
            print(f"获取价格失败: {e}")
            return None
    
    def get_24h_ticker(self):
        """获取BTC 24小时行情统计"""
        try:
            ticker = self.client.get_ticker(symbol=self.symbol)
            
            print(f"\n{'='*50}")
            print(f"BTC 24小时行情数据")
            print(f"{'='*50}")
            print(f"当前价格:     ${float(ticker['lastPrice']):,.2f}")
            print(f"24h最高价:    ${float(ticker['highPrice']):,.2f}")
            print(f"24h最低价:    ${float(ticker['lowPrice']):,.2f}")
            print(f"24h涨跌幅:    {float(ticker['priceChangePercent']):.2f}%")
            print(f"24h涨跌额:    ${float(ticker['priceChange']):,.2f}")
            print(f"24h成交量:    {float(ticker['volume']):,.2f} BTC")
            print(f"24h成交额:    ${float(ticker['quoteVolume']):,.2f}")
            print(f"开盘价:       ${float(ticker['openPrice']):,.2f}")
            print(f"加权平均价:   ${float(ticker['weightedAvgPrice']):,.2f}")
            print(f"{'='*50}\n")
            
            return ticker
        except Exception as e:
            print(f"获取24小时行情失败: {e}")
            return None
    
    def get_orderbook(self, limit=10):
        """获取订单簿（交易深度）"""
        try:
            depth = self.client.get_order_book(symbol=self.symbol, limit=limit)
            
            print(f"\n{'='*50}")
            print(f"BTC 订单深度 (前{limit}档)")
            print(f"{'='*50}")
            
            print(f"\n卖单 (Ask):")
            print(f"{'价格':<15} {'数量':<15}")
            print("-" * 30)
            for ask in reversed(depth['asks'][:limit]):
                price = float(ask[0])
                qty = float(ask[1])
                print(f"${price:<14,.2f} {qty:<15,.4f}")
            
            print(f"\n{'当前价格':^30}")
            current = self.get_current_price()
            
            print(f"\n买单 (Bid):")
            print(f"{'价格':<15} {'数量':<15}")
            print("-" * 30)
            for bid in depth['bids'][:limit]:
                price = float(bid[0])
                qty = float(bid[1])
                print(f"${price:<14,.2f} {qty:<15,.4f}")
            
            print(f"{'='*50}\n")
            return depth
        except Exception as e:
            print(f"获取订单深度失败: {e}")
            return None
    
    def get_recent_trades(self, limit=20):
        """获取最近成交记录"""
        try:
            trades = self.client.get_recent_trades(symbol=self.symbol, limit=limit)
            
            print(f"\n{'='*50}")
            print(f"BTC 最近{limit}笔成交")
            print(f"{'='*50}")
            print(f"{'时间':<20} {'价格':<15} {'数量':<15} {'方向':<10}")
            print("-" * 60)
            
            for trade in trades:
                timestamp = datetime.fromtimestamp(trade['time']/1000).strftime('%Y-%m-%d %H:%M:%S')
                price = float(trade['price'])
                qty = float(trade['qty'])
                side = "买入" if trade['isBuyerMaker'] == False else "卖出"
                print(f"{timestamp:<20} ${price:<14,.2f} {qty:<15,.6f} {side:<10}")
            
            print(f"{'='*50}\n")
            return trades
        except Exception as e:
            print(f"获取成交记录失败: {e}")
            return None
    
    def get_klines(self, interval='1h', limit=24):
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
            
            print(f"\n{'='*50}")
            print(f"BTC K线数据 (间隔: {interval}, 数量: {limit})")
            print(f"{'='*50}")
            print(df[['开盘时间', '开盘价', '最高价', '最低价', '收盘价', '成交量']].tail(10).to_string(index=False))
            print(f"{'='*50}\n")
            
            return df
        except Exception as e:
            print(f"获取K线数据失败: {e}")
            return None
    
    def get_all_market_data(self):
        """一次性获取所有市场数据"""
        print(f"\n{'#'*60}")
        print(f"{'BTC 完整市场数据报告':^60}")
        print(f"{'#'*60}")
        print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. 当前价格
        self.get_current_price()
        
        # 2. 24小时统计
        self.get_24h_ticker()
        
        # 3. 订单深度
        self.get_orderbook(limit=5)
        
        # 4. 最近成交
        self.get_recent_trades(limit=10)
        
        # 5. K线数据
        self.get_klines(interval='1h', limit=12)
        
        print(f"{'#'*60}")
        print(f"{'报告结束':^60}")
        print(f"{'#'*60}\n")


def main():
    """主函数"""
    print("\n欢迎使用BTC行情数据获取工具！\n")
    
    # 创建实例（不需要API密钥即可获取公开数据）
    btc = BTCMarketData()
    
    while True:
        print("\n请选择功能:")
        print("1. 获取当前价格")
        print("2. 获取24小时行情统计")
        print("3. 获取订单深度")
        print("4. 获取最近成交记录")
        print("5. 获取K线数据")
        print("6. 获取完整市场报告")
        print("0. 退出")
        
        choice = input("\n请输入选项 (0-6): ").strip()
        
        if choice == '1':
            btc.get_current_price()
        elif choice == '2':
            btc.get_24h_ticker()
        elif choice == '3':
            limit = input("请输入深度档位数量 (默认10): ").strip()
            limit = int(limit) if limit.isdigit() else 10
            btc.get_orderbook(limit=limit)
        elif choice == '4':
            limit = input("请输入成交记录数量 (默认20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            btc.get_recent_trades(limit=limit)
        elif choice == '5':
            print("\n时间间隔选项: 1m, 5m, 15m, 1h, 4h, 1d, 1w")
            interval = input("请输入时间间隔 (默认1h): ").strip()
            interval = interval if interval else '1h'
            limit = input("请输入K线数量 (默认24): ").strip()
            limit = int(limit) if limit.isdigit() else 24
            btc.get_klines(interval=interval, limit=limit)
        elif choice == '6':
            btc.get_all_market_data()
        elif choice == '0':
            print("\n感谢使用，再见！\n")
            break
        else:
            print("\n无效选项，请重新选择！")


if __name__ == "__main__":
    main()
