#!/usr/bin/env python
# coding: utf-8

"""
BTC行情数据Web展示应用
使用Flask创建Web服务，实时展示BTC行情数据
"""

from flask import Flask, render_template, jsonify, request
from binance.client import Client
import pandas as pd
from datetime import datetime
import json

app = Flask(__name__)

class BTCMarketAPI:
    def __init__(self):
        """初始化币安客户端"""
        self.client = Client("", "")
        self.symbol = "BTCUSDT"
    
    def get_current_price(self):
        """获取当前价格"""
        try:
            ticker = self.client.get_symbol_ticker(symbol=self.symbol)
            return {
                'success': True,
                'price': float(ticker['price']),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_24h_ticker(self):
        """获取24小时统计"""
        try:
            ticker = self.client.get_ticker(symbol=self.symbol)
            return {
                'success': True,
                'data': {
                    'last_price': float(ticker['lastPrice']),
                    'high_price': float(ticker['highPrice']),
                    'low_price': float(ticker['lowPrice']),
                    'price_change': float(ticker['priceChange']),
                    'price_change_percent': float(ticker['priceChangePercent']),
                    'volume': float(ticker['volume']),
                    'quote_volume': float(ticker['quoteVolume']),
                    'open_price': float(ticker['openPrice']),
                    'weighted_avg_price': float(ticker['weightedAvgPrice'])
                },
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_orderbook(self, limit=10):
        """获取订单深度"""
        try:
            depth = self.client.get_order_book(symbol=self.symbol, limit=limit)
            return {
                'success': True,
                'data': {
                    'bids': [[float(x[0]), float(x[1])] for x in depth['bids'][:limit]],
                    'asks': [[float(x[0]), float(x[1])] for x in depth['asks'][:limit]]
                },
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_recent_trades(self, limit=20):
        """获取最近成交"""
        try:
            trades = self.client.get_recent_trades(symbol=self.symbol, limit=limit)
            return {
                'success': True,
                'data': [{
                    'time': datetime.fromtimestamp(t['time']/1000).strftime('%H:%M:%S'),
                    'price': float(t['price']),
                    'qty': float(t['qty']),
                    'is_buyer_maker': t['isBuyerMaker']
                } for t in trades],
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_klines(self, interval='1h', limit=24):
        """获取K线数据"""
        try:
            klines = self.client.get_klines(
                symbol=self.symbol,
                interval=interval,
                limit=limit
            )
            
            data = []
            for k in klines:
                data.append({
                    'time': datetime.fromtimestamp(k[0]/1000).strftime('%m-%d %H:%M'),
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5])
                })
            
            return {
                'success': True,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_multi_symbols(self):
        """获取多个币种数据"""
        symbols = [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
            "XRPUSDT", "ADAUSDT", "DOGEUSDT", "DOTUSDT"
        ]
        
        try:
            data = []
            for symbol in symbols:
                ticker = self.client.get_ticker(symbol=symbol)
                data.append({
                    'symbol': symbol.replace('USDT', ''),
                    'price': float(ticker['lastPrice']),
                    'change_percent': float(ticker['priceChangePercent']),
                    'high': float(ticker['highPrice']),
                    'low': float(ticker['lowPrice']),
                    'volume': float(ticker['volume'])
                })
            
            return {
                'success': True,
                'data': sorted(data, key=lambda x: x['change_percent'], reverse=True),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


# 创建API实例
market_api = BTCMarketAPI()


# 路由定义
@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/price')
def api_price():
    """API: 获取当前价格"""
    return jsonify(market_api.get_current_price())


@app.route('/api/ticker')
def api_ticker():
    """API: 获取24小时统计"""
    return jsonify(market_api.get_24h_ticker())


@app.route('/api/orderbook')
def api_orderbook():
    """API: 获取订单深度"""
    limit = int(request.args.get('limit', 10))
    return jsonify(market_api.get_orderbook(limit))


@app.route('/api/trades')
def api_trades():
    """API: 获取最近成交"""
    limit = int(request.args.get('limit', 20))
    return jsonify(market_api.get_recent_trades(limit))


@app.route('/api/klines')
def api_klines():
    """API: 获取K线数据"""
    interval = request.args.get('interval', '1h')
    limit = int(request.args.get('limit', 24))
    return jsonify(market_api.get_klines(interval, limit))


@app.route('/api/multi-symbols')
def api_multi_symbols():
    """API: 获取多币种数据"""
    return jsonify(market_api.get_multi_symbols())


if __name__ == '__main__':
    print("\n" + "="*60)
    print(f"{'🌟 BTC行情数据Web应用 🌟':^60}")
    print("="*60)
    print("\n🚀 服务启动中...")
    print(f"\n📡 请在浏览器中访问: http://localhost:5000")
    print(f"📡 或访问: http://127.0.0.1:5000")
    print("\n💡 按 Ctrl+C 停止服务\n")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
