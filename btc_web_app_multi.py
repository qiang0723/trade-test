#!/usr/bin/env python
# coding: utf-8

"""
多币种行情数据Web展示应用（现货+合约）
支持TA、BTR、AT等多个币种
支持现货和合约两种交易类型
"""

from flask import Flask, render_template, jsonify, request
from binance.client import Client
import pandas as pd
from datetime import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time
from collections import defaultdict

app = Flask(__name__)

class MultiMarketAPI:
    def __init__(self):
        """初始化币安客户端"""
        self.client = Client("", "")
        
        # 定义支持的币种和交易类型
        self.symbols = ['TA', 'BTR', 'AT']  # 可以添加更多币种
        self.quote_currency = 'USDT'
        
        # 检测哪些币种支持合约交易
        self.available_markets = self.check_available_markets()
    
    def check_available_markets(self):
        """检查哪些币种支持现货和合约交易"""
        available = {}
        
        for symbol in self.symbols:
            available[symbol] = {
                'spot': False,
                'futures': False,
                'spot_symbol': f"{symbol}{self.quote_currency}",
                'futures_symbol': f"{symbol}{self.quote_currency}"
            }
            
            # 检查现货
            try:
                self.client.get_symbol_ticker(symbol=f"{symbol}{self.quote_currency}")
                available[symbol]['spot'] = True
                print(f"✅ {symbol} 现货交易可用")
            except Exception as e:
                print(f"❌ {symbol} 现货交易不可用: {str(e)[:50]}")
            
            # 检查合约
            try:
                self.client.futures_symbol_ticker(symbol=f"{symbol}{self.quote_currency}")
                available[symbol]['futures'] = True
                print(f"✅ {symbol} 合约交易可用")
            except Exception as e:
                print(f"⚠️  {symbol} 合约交易不可用，跳过")
        
        return available
    
    def get_spot_ticker(self, symbol):
        """获取现货24小时统计"""
        try:
            spot_symbol = f"{symbol}{self.quote_currency}"
            ticker = self.client.get_ticker(symbol=spot_symbol)
            
            # 通过K线数据计算成交量和成交额的变化（6小时）
            volume_change_percent = 0
            quote_volume_change_percent = 0
            try:
                # 获取最近7个1小时K线（确保有6小时前的数据）
                klines = self.client.get_klines(symbol=spot_symbol, interval='1h', limit=7)
                if len(klines) >= 7:
                    # 计算前3小时和后3小时的累计成交量
                    # 前3小时（索引0-2）
                    prev_volume = sum(float(k[5]) for k in klines[0:3])
                    prev_quote_volume = sum(float(k[7]) for k in klines[0:3])
                    # 后3小时（索引4-6，最近3小时）
                    curr_volume = sum(float(k[5]) for k in klines[4:7])
                    curr_quote_volume = sum(float(k[7]) for k in klines[4:7])
                    
                    if prev_volume > 0:
                        volume_change_percent = ((curr_volume - prev_volume) / prev_volume) * 100
                    if prev_quote_volume > 0:
                        quote_volume_change_percent = ((curr_quote_volume - prev_quote_volume) / prev_quote_volume) * 100
            except Exception as e:
                pass  # 如果获取失败，保持为0
            
            return {
                'success': True,
                'market_type': 'spot',
                'symbol': symbol,
                'data': {
                    'last_price': float(ticker['lastPrice']),
                    'high_price': float(ticker['highPrice']),
                    'low_price': float(ticker['lowPrice']),
                    'price_change': float(ticker['priceChange']),
                    'price_change_percent': float(ticker['priceChangePercent']),
                    'volume': float(ticker['volume']),
                    'quote_volume': float(ticker['quoteVolume']),
                    'volume_change_percent': volume_change_percent,
                    'quote_volume_change_percent': quote_volume_change_percent
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'symbol': symbol, 'market_type': 'spot'}
    
    def get_futures_ticker(self, symbol):
        """获取合约24小时统计"""
        try:
            futures_symbol = f"{symbol}{self.quote_currency}"
            ticker = self.client.futures_ticker(symbol=futures_symbol)
            
            # 获取实时资金费率（使用mark_price获取最新数据）
            funding_rate_data = {'funding_rate': 0, 'next_funding_time': 0}
            try:
                mark_price = self.client.futures_mark_price(symbol=futures_symbol)
                if mark_price:
                    # lastFundingRate 是当前实时的资金费率
                    funding_rate_data['funding_rate'] = float(mark_price['lastFundingRate'])
                    funding_rate_data['next_funding_time'] = mark_price['nextFundingTime']
            except Exception as e:
                print(f"获取{symbol}资金费率失败: {str(e)}")
            
            # 获取持仓量和持仓量变化
            open_interest = 0
            open_interest_change_percent = 0
            try:
                oi_data = self.client.futures_open_interest(symbol=futures_symbol)
                if oi_data:
                    open_interest = float(oi_data['openInterest'])
                
                # 获取6小时前的持仓量数据来计算变化
                # 使用1小时间隔获取6小时的历史数据
                try:
                    oi_history = self.client.futures_open_interest_hist(
                        symbol=futures_symbol,
                        period='1h',
                        limit=7  # 获取7个小时数据（确保有6小时前数据）
                    )
                    if oi_history and len(oi_history) >= 6:
                        # 使用最早的数据（索引0）作为6小时前的基准
                        # oi_history[0] 是最早的数据点（约6小时前）
                        # oi_history[-1] 是最新的数据点
                        old_oi = float(oi_history[0]['sumOpenInterest'])
                        if old_oi > 0 and open_interest > 0:
                            open_interest_change_percent = ((open_interest - old_oi) / old_oi) * 100
                    elif oi_history and len(oi_history) > 0:
                        # 如果数据不足6小时，使用最早的数据
                        old_oi = float(oi_history[0]['sumOpenInterest'])
                        if old_oi > 0 and open_interest > 0:
                            open_interest_change_percent = ((open_interest - old_oi) / old_oi) * 100
                except Exception as e2:
                    pass  # 忽略历史数据获取失败
            except Exception as e:
                print(f"获取{symbol}持仓量失败: {str(e)}")
            
            # 通过K线数据计算成交量和成交额的变化（6小时）
            volume_change_percent = 0
            quote_volume_change_percent = 0
            try:
                # 获取最近7个1小时K线（确保有6小时前的数据）
                klines = self.client.futures_klines(symbol=futures_symbol, interval='1h', limit=7)
                if len(klines) >= 7:
                    # 计算前3小时和后3小时的累计成交量
                    # 前3小时（索引0-2）
                    prev_volume = sum(float(k[5]) for k in klines[0:3])
                    prev_quote_volume = sum(float(k[7]) for k in klines[0:3])
                    # 后3小时（索引4-6，最近3小时）
                    curr_volume = sum(float(k[5]) for k in klines[4:7])
                    curr_quote_volume = sum(float(k[7]) for k in klines[4:7])
                    
                    if prev_volume > 0:
                        volume_change_percent = ((curr_volume - prev_volume) / prev_volume) * 100
                    if prev_quote_volume > 0:
                        quote_volume_change_percent = ((curr_quote_volume - prev_quote_volume) / prev_quote_volume) * 100
            except Exception as e:
                pass  # 如果获取失败，保持为0
            
            return {
                'success': True,
                'market_type': 'futures',
                'symbol': symbol,
                'data': {
                    'last_price': float(ticker['lastPrice']),
                    'high_price': float(ticker['highPrice']),
                    'low_price': float(ticker['lowPrice']),
                    'price_change': float(ticker['priceChange']),
                    'price_change_percent': float(ticker['priceChangePercent']),
                    'volume': float(ticker['volume']),
                    'quote_volume': float(ticker['quoteVolume']),
                    'volume_change_percent': volume_change_percent,
                    'quote_volume_change_percent': quote_volume_change_percent,
                    'funding_rate': funding_rate_data['funding_rate'],
                    'next_funding_time': funding_rate_data['next_funding_time'],
                    'open_interest': open_interest,
                    'open_interest_change_percent': open_interest_change_percent
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e), 'symbol': symbol, 'market_type': 'futures'}
    
    def get_all_tickers(self):
        """获取所有币种的现货和合约数据"""
        result = {
            'timestamp': datetime.now().isoformat(),
            'markets': []
        }
        
        for symbol in self.symbols:
            markets_info = self.available_markets.get(symbol, {})
            symbol_data = {
                'symbol': symbol,
                'spot': None,
                'futures': None
            }
            
            # 获取现货数据
            if markets_info.get('spot', False):
                symbol_data['spot'] = self.get_spot_ticker(symbol)
            
            # 获取合约数据
            if markets_info.get('futures', False):
                symbol_data['futures'] = self.get_futures_ticker(symbol)
            
            result['markets'].append(symbol_data)
        
        return result
    
    def get_spot_orderbook(self, symbol, limit=10):
        """获取现货订单深度"""
        try:
            spot_symbol = f"{symbol}{self.quote_currency}"
            depth = self.client.get_order_book(symbol=spot_symbol, limit=limit)
            
            return {
                'success': True,
                'market_type': 'spot',
                'symbol': symbol,
                'data': {
                    'bids': [[float(x[0]), float(x[1])] for x in depth['bids'][:limit]],
                    'asks': [[float(x[0]), float(x[1])] for x in depth['asks'][:limit]]
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_futures_orderbook(self, symbol, limit=10):
        """获取合约订单深度"""
        try:
            futures_symbol = f"{symbol}{self.quote_currency}"
            depth = self.client.futures_order_book(symbol=futures_symbol, limit=limit)
            
            return {
                'success': True,
                'market_type': 'futures',
                'symbol': symbol,
                'data': {
                    'bids': [[float(x[0]), float(x[1])] for x in depth['bids'][:limit]],
                    'asks': [[float(x[0]), float(x[1])] for x in depth['asks'][:limit]]
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_spot_klines(self, symbol, interval='1h', limit=24):
        """获取现货K线数据"""
        try:
            spot_symbol = f"{symbol}{self.quote_currency}"
            klines = self.client.get_klines(
                symbol=spot_symbol,
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
                    'volume': float(k[5]),
                    'quote_volume': float(k[7])  # 添加成交额
                })
            
            return {
                'success': True,
                'market_type': 'spot',
                'symbol': symbol,
                'data': data
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_futures_klines(self, symbol, interval='1h', limit=24):
        """获取合约K线数据"""
        try:
            futures_symbol = f"{symbol}{self.quote_currency}"
            klines = self.client.futures_klines(
                symbol=futures_symbol,
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
                    'volume': float(k[5]),
                    'quote_volume': float(k[7])  # 添加成交额
                })
            
            return {
                'success': True,
                'market_type': 'futures',
                'symbol': symbol,
                'data': data
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_open_interest_history(self, symbol, period='5m', limit=288):
        """获取持仓量历史数据"""
        try:
            futures_symbol = f"{symbol}{self.quote_currency}"
            oi_history = self.client.futures_open_interest_hist(
                symbol=futures_symbol,
                period=period,
                limit=limit
            )
            
            data = []
            for item in oi_history:
                data.append({
                    'time': datetime.fromtimestamp(item['timestamp']/1000).strftime('%m-%d %H:%M'),
                    'open_interest': float(item['sumOpenInterest']),
                    'open_interest_value': float(item['sumOpenInterestValue'])
                })
            
            return {
                'success': True,
                'symbol': symbol,
                'data': data
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_spot_trades(self, symbol, limit=50, time_range_minutes=None):
        """获取现货最近成交记录
        
        Args:
            symbol: 交易对符号
            limit: 获取数量
            time_range_minutes: 时间范围（分钟），None表示不限制
        """
        try:
            spot_symbol = f"{symbol}{self.quote_currency}"
            # 限制最大获取1000条（币安API限制）
            actual_limit = min(limit, 1000)
            trades = self.client.get_recent_trades(symbol=spot_symbol, limit=actual_limit)
            
            data = []
            current_time = datetime.now().timestamp() * 1000  # 当前时间（毫秒）
            
            for trade in trades:
                # 如果指定了时间范围，过滤数据
                if time_range_minutes is not None:
                    time_threshold = current_time - (time_range_minutes * 60 * 1000)
                    if trade['time'] < time_threshold:
                        continue
                
                data.append({
                    'id': trade['id'],
                    'time': datetime.fromtimestamp(trade['time']/1000).strftime('%H:%M:%S'),
                    'timestamp': trade['time'],
                    'price': float(trade['price']),
                    'qty': float(trade['qty']),
                    'quote_qty': float(trade['quoteQty']),
                    'is_buyer_maker': trade['isBuyerMaker']
                })
            
            return {
                'success': True,
                'market_type': 'spot',
                'symbol': symbol,
                'data': data,
                'time_range_minutes': time_range_minutes
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_futures_trades(self, symbol, limit=50, time_range_minutes=None):
        """获取合约最近成交记录
        
        Args:
            symbol: 交易对符号
            limit: 获取数量
            time_range_minutes: 时间范围（分钟），None表示不限制
        """
        try:
            futures_symbol = f"{symbol}{self.quote_currency}"
            # 限制最大获取1000条（币安API限制）
            actual_limit = min(limit, 1000)
            trades = self.client.futures_recent_trades(symbol=futures_symbol, limit=actual_limit)
            
            data = []
            current_time = datetime.now().timestamp() * 1000  # 当前时间（毫秒）
            
            for trade in trades:
                # 如果指定了时间范围，过滤数据
                if time_range_minutes is not None:
                    time_threshold = current_time - (time_range_minutes * 60 * 1000)
                    if trade['time'] < time_threshold:
                        continue
                
                data.append({
                    'id': trade['id'],
                    'time': datetime.fromtimestamp(trade['time']/1000).strftime('%H:%M:%S'),
                    'timestamp': trade['time'],
                    'price': float(trade['price']),
                    'qty': float(trade['qty']),
                    'quote_qty': float(trade['price']) * float(trade['qty']),
                    'is_buyer_maker': trade['isBuyerMaker']
                })
            
            return {
                'success': True,
                'market_type': 'futures',
                'symbol': symbol,
                'data': data,
                'time_range_minutes': time_range_minutes
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def analyze_large_orders(self, trades_data, threshold_usdt=10000, time_range_hours=None):
        """分析大单买入情况
        
        Args:
            trades_data: 成交数据
            threshold_usdt: 大单阈值（USDT）
            time_range_hours: 时间范围（小时），None表示不限制
        """
        if not trades_data or 'data' not in trades_data:
            return {'success': False, 'error': 'No data'}
        
        trades = trades_data['data']
        
        # 如果指定了时间范围，过滤数据
        if time_range_hours is not None:
            current_time = datetime.now().timestamp() * 1000  # 转换为毫秒
            time_threshold = current_time - (time_range_hours * 60 * 60 * 1000)  # 时间范围（毫秒）
            trades = [t for t in trades if t['timestamp'] >= time_threshold]
        
        large_orders = []
        
        buy_volume = 0
        sell_volume = 0
        buy_amount = 0
        sell_amount = 0
        large_buy_count = 0
        large_sell_count = 0
        
        for trade in trades:
            quote_qty = trade['quote_qty']
            is_buy = not trade['is_buyer_maker']
            
            # 统计买卖量
            if is_buy:
                buy_volume += trade['qty']
                buy_amount += quote_qty
            else:
                sell_volume += trade['qty']
                sell_amount += quote_qty
            
            # 识别大单
            if quote_qty >= threshold_usdt:
                large_orders.append({
                    'time': trade['time'],
                    'timestamp': trade['timestamp'],
                    'price': trade['price'],
                    'qty': trade['qty'],
                    'amount': quote_qty,
                    'type': 'buy' if is_buy else 'sell'
                })
                
                if is_buy:
                    large_buy_count += 1
                else:
                    large_sell_count += 1
        
        # 计算买卖比
        total_amount = buy_amount + sell_amount
        buy_ratio = (buy_amount / total_amount * 100) if total_amount > 0 else 50
        
        return {
            'success': True,
            'symbol': trades_data['symbol'],
            'market_type': trades_data['market_type'],
            'time_range_hours': time_range_hours,
            'analysis': {
                'total_trades': len(trades),
                'buy_volume': buy_volume,
                'sell_volume': sell_volume,
                'buy_amount': buy_amount,
                'sell_amount': sell_amount,
                'buy_ratio': buy_ratio,
                'sell_ratio': 100 - buy_ratio,
                'large_orders_count': len(large_orders),
                'large_buy_count': large_buy_count,
                'large_sell_count': large_sell_count,
                'large_orders': sorted(large_orders, key=lambda x: x['amount'], reverse=True)[:20]
            }
        }
    
    def analyze_futures_market(self, symbol):
        """分析合约市场情况并给出结论
        
        分析维度：
        1. 持仓量变化 + 价格变化 = 判断多空操作
        2. 资金费率 = 判断市场情绪
        3. 成交量变化 = 判断市场活跃度
        """
        try:
            futures_symbol = f"{symbol}{self.quote_currency}"
            
            # 获取当前行情数据
            ticker = self.get_futures_ticker(symbol)
            if not ticker['success']:
                return {'success': False, 'error': '获取行情数据失败'}
            
            ticker_data = ticker['data']
            
            # 获取K线数据（最近24小时）
            klines = self.client.futures_klines(symbol=futures_symbol, interval='1h', limit=25)
            if len(klines) < 24:
                return {'success': False, 'error': 'K线数据不足'}
            
            # 分析数据
            current_price = ticker_data['last_price']
            price_change_24h = ticker_data['price_change_percent']
            funding_rate = ticker_data['funding_rate']
            oi_change = ticker_data['open_interest_change_percent']
            volume_change = ticker_data['volume_change_percent']
            
            # 计算最近几小时的价格趋势
            recent_prices = [float(k[4]) for k in klines[-6:]]  # 最近6小时
            price_trend_6h = ((recent_prices[-1] - recent_prices[0]) / recent_prices[0]) * 100
            
            # 获取1小时内的买卖量数据
            buy_volume_1h = 0
            sell_volume_1h = 0
            buy_amount_1h = 0
            sell_amount_1h = 0
            buy_trades_1h = 0
            sell_trades_1h = 0
            
            try:
                # 获取最近1小时的成交数据（估算500笔）
                trades_data = self.get_futures_trades(symbol, limit=500, time_range_minutes=60)
                if trades_data['success'] and trades_data['data']:
                    for trade in trades_data['data']:
                        is_buy = not trade['is_buyer_maker']  # True表示主动买入
                        if is_buy:
                            buy_volume_1h += trade['qty']
                            buy_amount_1h += trade['quote_qty']
                            buy_trades_1h += 1
                        else:
                            sell_volume_1h += trade['qty']
                            sell_amount_1h += trade['quote_qty']
                            sell_trades_1h += 1
            except Exception as e:
                print(f"获取{symbol}1小时成交数据失败: {str(e)}")
            
            # 计算买卖比例
            total_amount_1h = buy_amount_1h + sell_amount_1h
            buy_ratio_1h = (buy_amount_1h / total_amount_1h * 100) if total_amount_1h > 0 else 50
            sell_ratio_1h = 100 - buy_ratio_1h
            
            # 转换资金费率为百分比（提前计算，供后面使用）
            funding_rate_percent = funding_rate * 100
            
            # 生成分析结论
            conclusions = []
            market_sentiment = "中性"
            main_operation = ""
            risk_level = "中"
            trading_signal = "观望"  # 交易信号：做多、做空、观望
            
            # ========== 标准做多模型评分 ==========
            long_score = 0
            long_conditions = []
            
            # 条件1: 结构向上（或刚突破）
            structure_up = False
            if price_change_24h > 3 and price_trend_6h > 1:
                long_score += 2
                structure_up = True
                long_conditions.append("✓ 结构向上：24h涨幅>3%且6h延续上涨")
            elif price_change_24h > 0 and price_trend_6h > 2:
                long_score += 1.5
                structure_up = True
                long_conditions.append("✓ 刚突破：6h涨幅>2%，突破初期")
            elif 0 < price_change_24h <= 3 and price_trend_6h > 0:
                long_score += 1
                long_conditions.append("○ 结构偏多：价格缓慢向上")
            
            # 条件2: 突破放量 / 回调缩量
            volume_quality = False
            if structure_up:
                # 如果是上涨，应该放量
                if volume_change > 15:
                    long_score += 2
                    volume_quality = True
                    long_conditions.append("✓ 突破放量：成交量放大>15%")
                elif volume_change > 0:
                    long_score += 1
                    long_conditions.append("○ 量能一般：成交量小幅增加")
            else:
                # 如果是回调，应该缩量
                if volume_change < -10:
                    long_score += 1.5
                    volume_quality = True
                    long_conditions.append("✓ 回调缩量：成交量萎缩>10%")
                elif volume_change < 0:
                    long_score += 0.5
                    long_conditions.append("○ 量能缩减：成交量小幅下降")
            
            # 条件3: OI 小幅持续上升（不是暴涨）
            oi_quality = False
            if 2 <= oi_change <= 8:
                long_score += 2
                oi_quality = True
                long_conditions.append(f"✓ OI小幅增长：持仓量+{oi_change:.1f}%（健康区间2-8%）")
            elif 0 < oi_change < 2:
                long_score += 1
                long_conditions.append(f"○ OI温和增长：持仓量+{oi_change:.1f}%")
            elif oi_change > 8:
                long_score -= 0.5
                long_conditions.append(f"⚠ OI暴涨：持仓量+{oi_change:.1f}%（过热风险）")
            
            # 条件4: 资金费率温和
            funding_quality = False
            if -0.03 <= funding_rate_percent <= 0.08:
                long_score += 1.5
                funding_quality = True
                long_conditions.append(f"✓ 资金费率温和：{funding_rate_percent:+.4f}%（正常范围）")
            elif 0.08 < funding_rate_percent <= 0.15:
                long_score += 0.5
                long_conditions.append(f"○ 资金费率偏高：{funding_rate_percent:+.4f}%（多头偏热）")
            elif funding_rate_percent > 0.15:
                long_score -= 1
                long_conditions.append(f"⚠ 资金费率过高：{funding_rate_percent:+.4f}%（极度过热）")
            
            # 条件5: 主动买单略占优
            buy_quality = False
            if 53 <= buy_ratio_1h <= 65:
                long_score += 2
                buy_quality = True
                long_conditions.append(f"✓ 买单略占优：买入{buy_ratio_1h:.1f}%（理想范围53-65%）")
            elif 65 < buy_ratio_1h <= 70:
                long_score += 1
                long_conditions.append(f"○ 买单占优：买入{buy_ratio_1h:.1f}%（偏强）")
            elif buy_ratio_1h > 70:
                long_score += 0.5
                long_conditions.append(f"⚠ 买单过强：买入{buy_ratio_1h:.1f}%（追涨风险）")
            elif 45 <= buy_ratio_1h < 53:
                long_score += 0.5
                long_conditions.append(f"○ 买卖均衡：买入{buy_ratio_1h:.1f}%")
            
            # ========== 标准做多模型判断 ==========
            perfect_long = (structure_up and volume_quality and oi_quality and 
                          funding_quality and buy_quality)
            
            if long_score >= 8 or perfect_long:
                trading_signal = "强烈做多"
                market_sentiment = "极度看涨"
                risk_level = "低"
                main_operation = "🚀 标准做多模型：高胜率做多机会！"
                conclusions.insert(0, "=" * 50)
                conclusions.insert(1, "🎯 【标准做多模型】满足条件！")
                conclusions.insert(2, f"📊 做多评分：{long_score:.1f}/10.0 分")
                conclusions.insert(3, "=" * 50)
                for cond in long_conditions:
                    conclusions.insert(4, cond)
                conclusions.insert(4 + len(long_conditions), "=" * 50)
                conclusions.insert(5 + len(long_conditions), "💡 操作建议：顺势做多，设置合理止损")
                conclusions.insert(6 + len(long_conditions), "=" * 50)
            elif long_score >= 6:
                trading_signal = "偏多"
                market_sentiment = "看涨"
                risk_level = "中"
                main_operation = f"✅ 做多信号较强（评分{long_score:.1f}/10），可考虑做多"
                conclusions.insert(0, "─" * 50)
                conclusions.insert(1, f"📈 做多模型评分：{long_score:.1f}/10.0 分（偏多）")
                for cond in long_conditions:
                    conclusions.insert(2, cond)
                conclusions.insert(2 + len(long_conditions), "─" * 50)
            elif long_score >= 4:
                trading_signal = "观望"
                main_operation = f"⚖️ 做多信号一般（评分{long_score:.1f}/10），建议观望"
                if long_conditions:
                    conclusions.append("─" * 50)
                    conclusions.append(f"📊 做多模型评分：{long_score:.1f}/10.0 分（中性）")
                    for cond in long_conditions:
                        conclusions.append(cond)
            else:
                trading_signal = "不建议做多"
                if price_change_24h < -3:
                    market_sentiment = "看跌"
                if long_conditions:
                    conclusions.append(f"❌ 不符合做多模型（评分{long_score:.1f}/10）")
            
            # ========== 标准做空模型评分 ==========
            short_score = 0
            short_conditions = []
            short_signal = "观望"  # 默认值
            
            # 条件1: 结构向下（或刚破位）
            structure_down = False
            if price_change_24h < -3 and price_trend_6h < -1:
                short_score += 2
                structure_down = True
                short_conditions.append("✓ 结构向下：24h跌幅>3%且6h延续下跌")
            elif price_change_24h < 0 and price_trend_6h < -2:
                short_score += 1.5
                structure_down = True
                short_conditions.append("✓ 刚破位：6h跌幅>2%，破位初期")
            elif -3 < price_change_24h <= 0 and price_trend_6h < 0:
                short_score += 1
                short_conditions.append("○ 结构偏空：价格缓慢向下")
            
            # 条件2: 下跌放量 / 反弹缩量
            volume_quality_short = False
            if structure_down:
                # 如果是下跌，应该放量
                if volume_change > 15:
                    short_score += 2
                    volume_quality_short = True
                    short_conditions.append("✓ 下跌放量：成交量放大>15%")
                elif volume_change > 0:
                    short_score += 1
                    short_conditions.append("○ 量能一般：成交量小幅增加")
            else:
                # 如果是反弹，应该缩量
                if volume_change < -10:
                    short_score += 1.5
                    volume_quality_short = True
                    short_conditions.append("✓ 反弹缩量：成交量萎缩>10%")
                elif volume_change < 0:
                    short_score += 0.5
                    short_conditions.append("○ 量能缩减：成交量小幅下降")
            
            # 条件3: OI堆积或上涨配合下跌
            oi_quality_short = False
            if 8 <= oi_change <= 15:
                short_score += 2
                oi_quality_short = True
                short_conditions.append(f"✓ OI堆积：持仓量+{oi_change:.1f}%（风险堆积区间8-15%）")
            elif price_change_24h < -1 and oi_change > 2:
                short_score += 2
                oi_quality_short = True
                short_conditions.append(f"✓ 价格下跌+OI上升：空头增仓，OI+{oi_change:.1f}%")
            elif 2 < oi_change < 8:
                short_score += 1
                short_conditions.append(f"○ OI温和增长：持仓量+{oi_change:.1f}%")
            
            # 条件4: 资金费率过热或极度过热
            funding_quality_short = False
            if funding_rate_percent > 0.15:
                short_score += 1.5
                funding_quality_short = True
                short_conditions.append(f"✓ 资金费率极度过热：{funding_rate_percent:+.4f}%（>0.15%）")
            elif 0.1 < funding_rate_percent <= 0.15:
                short_score += 1
                funding_quality_short = True
                short_conditions.append(f"✓ 资金费率过热：{funding_rate_percent:+.4f}%（>0.1%）")
            elif 0.08 < funding_rate_percent <= 0.1:
                short_score += 0.5
                short_conditions.append(f"○ 资金费率偏高：{funding_rate_percent:+.4f}%")
            
            # 条件5: 主动卖单占优
            sell_quality = False
            if 53 <= sell_ratio_1h <= 65:
                short_score += 2
                sell_quality = True
                short_conditions.append(f"✓ 卖单略占优：卖出{sell_ratio_1h:.1f}%（理想范围53-65%）")
            elif 65 < sell_ratio_1h <= 70:
                short_score += 1
                short_conditions.append(f"○ 卖单占优：卖出{sell_ratio_1h:.1f}%（偏强）")
            elif sell_ratio_1h > 70:
                short_score += 0.5
                short_conditions.append(f"⚠ 卖单过强：卖出{sell_ratio_1h:.1f}%（杀跌风险）")
            elif 45 <= sell_ratio_1h < 53:
                short_score += 0.5
                short_conditions.append(f"○ 买卖均衡：卖出{sell_ratio_1h:.1f}%")
            
            # ========== 标准做空模型判断 ==========
            perfect_short = (structure_down and volume_quality_short and oi_quality_short and 
                           funding_quality_short and sell_quality)
            
            # 添加做空模型结论到详细分析中
            if short_score >= 8 or perfect_short:
                short_signal = "强烈做空"
                if not main_operation or "做空" not in main_operation:
                    if not extreme_condition and market_sentiment != "看涨":
                        market_sentiment = "极度看跌"
                        risk_level = "低"
                conclusions.append("")
                conclusions.append("=" * 50)
                conclusions.append("🎯 【标准做空模型】满足条件！")
                conclusions.append(f"📊 做空评分：{short_score:.1f}/10.0 分")
                conclusions.append("=" * 50)
                for cond in short_conditions:
                    conclusions.append(cond)
                conclusions.append("=" * 50)
                conclusions.append("💡 操作建议：顺势做空，设置合理止损")
                conclusions.append("=" * 50)
            elif short_score >= 6:
                short_signal = "偏空"
                conclusions.append("")
                conclusions.append("─" * 50)
                conclusions.append(f"📉 做空模型评分：{short_score:.1f}/10.0 分（偏空）")
                for cond in short_conditions:
                    conclusions.append(cond)
                conclusions.append("─" * 50)
            elif short_score >= 4:
                short_signal = "观望"
                if short_conditions:
                    conclusions.append("")
                    conclusions.append("─" * 50)
                    conclusions.append(f"📊 做空模型评分：{short_score:.1f}/10.0 分（中性）")
                    for cond in short_conditions:
                        conclusions.append(cond)
            else:
                short_signal = "不建议做空"
                if short_conditions:
                    conclusions.append(f"❌ 不符合做空模型（评分{short_score:.1f}/10）")
            
            # ========== 三态交易信号判断 ==========
            # 根据成交量、OI、资金费率、买卖行为，判断 LONG / SHORT / NO_TRADE
            trade_action = "NO_TRADE"
            action_reasons = []
            
            # 极端情况判断 - 优先判断 NO_TRADE
            extreme_condition = False
            
            # 1. 资金费率极端
            if funding_rate_percent > 0.2 or funding_rate_percent < -0.2:
                extreme_condition = True
                action_reasons.append(f"❌ 资金费率极端 {funding_rate_percent:+.4f}%（超过±0.2%）")
            
            # 2. OI极端变化（暴涨暴跌）
            if oi_change > 15 or oi_change < -15:
                extreme_condition = True
                action_reasons.append(f"❌ 持仓量极端变化 {oi_change:+.2f}%（超过±15%）")
            
            # 3. 集中平仓情绪（OI大降+价格大幅波动）
            if oi_change < -8 and abs(price_change_24h) > 5:
                extreme_condition = True
                action_reasons.append(f"❌ 集中平仓情绪：OI降{oi_change:.2f}%，价格波动{price_change_24h:+.2f}%")
            
            if not extreme_condition:
                # 非极端情况，判断 LONG 或 SHORT
                
                # ========== LONG 条件判断 ==========
                long_signals = 0
                long_reasons = []
                
                # 1. 上涨放量 or 回调缩量
                if price_change_24h > 2 and volume_change > 15:
                    long_signals += 2
                    long_reasons.append(f"✓ 上涨放量：价格+{price_change_24h:.2f}%，成交量+{volume_change:.2f}%")
                elif price_change_24h < 0 and volume_change < -10:
                    long_signals += 1.5
                    long_reasons.append(f"✓ 回调缩量：价格{price_change_24h:.2f}%，成交量{volume_change:.2f}%")
                
                # 2. 价格上涨且 OI 上升
                if price_change_24h > 1 and oi_change > 2 and oi_change <= 10:
                    long_signals += 2
                    long_reasons.append(f"✓ 价格上涨+OI上升：价格+{price_change_24h:.2f}%，OI+{oi_change:.2f}%")
                
                # 3. 资金费率温和
                if -0.05 <= funding_rate_percent <= 0.1:
                    long_signals += 1.5
                    long_reasons.append(f"✓ 资金费率温和：{funding_rate_percent:+.4f}%")
                
                # 4. 买单推动价格
                if buy_ratio_1h > 55 and price_change_24h > 0:
                    long_signals += 1.5
                    long_reasons.append(f"✓ 买单推动价格：买入{buy_ratio_1h:.1f}%，价格+{price_change_24h:.2f}%")
                
                # ========== SHORT 条件判断 ==========
                short_signals = 0
                short_reasons = []
                
                # 1. 上涨无量或滞涨
                if price_change_24h > 1 and volume_change < 0:
                    short_signals += 2
                    short_reasons.append(f"✓ 上涨无量：价格+{price_change_24h:.2f}%，成交量{volume_change:.2f}%")
                elif -1 <= price_change_24h <= 1 and oi_change > 8:
                    short_signals += 1.5
                    short_reasons.append(f"✓ 滞涨：价格{price_change_24h:.2f}%，OI+{oi_change:.2f}%")
                
                # 2. OI堆积（暴涨但未极端）
                if 10 < oi_change <= 15:
                    short_signals += 2
                    short_reasons.append(f"✓ OI堆积：持仓量+{oi_change:.2f}%（风险堆积）")
                
                # 3. 资金费率过热
                if funding_rate_percent > 0.1:
                    short_signals += 1.5
                    short_reasons.append(f"✓ 资金费率过热：{funding_rate_percent:+.4f}%（多头过热）")
                
                # 4. 反弹买弱、卖压增强
                if price_change_24h > 0 and sell_ratio_1h > 55:
                    short_signals += 1.5
                    short_reasons.append(f"✓ 反弹卖压增强：卖出{sell_ratio_1h:.1f}%，价格勉强+{price_change_24h:.2f}%")
                elif price_change_24h < -2 and sell_ratio_1h > 60:
                    short_signals += 2
                    short_reasons.append(f"✓ 卖压持续增强：卖出{sell_ratio_1h:.1f}%，价格{price_change_24h:.2f}%")
                
                # ========== 最终判断 ==========
                if long_signals >= 4 and long_signals > short_signals:
                    trade_action = "LONG"
                    action_reasons = long_reasons
                elif short_signals >= 4 and short_signals > long_signals:
                    trade_action = "SHORT"
                    action_reasons = short_reasons
                else:
                    trade_action = "NO_TRADE"
                    action_reasons.append(f"⚠️ 信号不明确：多头信号{long_signals:.1f}分，空头信号{short_signals:.1f}分")
                    if long_signals > 0:
                        action_reasons.append(f"📊 多头因素：{', '.join([r.split('：')[0] for r in long_reasons])}")
                    if short_signals > 0:
                        action_reasons.append(f"📊 空头因素：{', '.join([r.split('：')[0] for r in short_reasons])}")
            else:
                # 极端情况，输出 NO_TRADE
                trade_action = "NO_TRADE"
            
            # 插入三态信号分析到结论开头
            conclusions.insert(0, "")
            conclusions.insert(0, "=" * 50)
            for reason in reversed(action_reasons):
                conclusions.insert(0, reason)
            
            if trade_action == "LONG":
                conclusions.insert(0, "🟢 【交易信号】LONG - 建议做多")
                conclusions.insert(0, "=" * 50)
                main_operation = "🟢 LONG：建议做多" if not main_operation or "做多" not in main_operation else main_operation
                market_sentiment = "看涨"
                risk_level = "低" if long_signals >= 6 else "中"
            elif trade_action == "SHORT":
                conclusions.insert(0, "🔴 【交易信号】SHORT - 建议做空")
                conclusions.insert(0, "=" * 50)
                main_operation = "🔴 SHORT：建议做空"
                market_sentiment = "看跌"
                risk_level = "中" if short_signals >= 6 else "高"
            else:
                conclusions.insert(0, "⚪ 【交易信号】NO_TRADE - 不建议交易")
                conclusions.insert(0, "=" * 50)
                main_operation = "⚪ NO_TRADE：暂时观望，等待更明确信号"
                risk_level = "高" if extreme_condition else "中"
            
            # ========== 补充详细分析 ==========
            conclusions.append("")
            conclusions.append("📋 详细数据分析：")
            conclusions.append("─" * 50)
            
            # 1. 1小时买卖量分析（短期多空力量对比）
            if total_amount_1h > 0:
                conclusions.append(f"💹 1h成交统计: {buy_trades_1h}笔买入 vs {sell_trades_1h}笔卖出")
                
                if buy_ratio_1h > 60:
                    conclusions.append(f"🟢 1h买入力量占优 {buy_ratio_1h:.1f}%，短期买盘强劲")
                    if price_change_24h > 1:
                        conclusions.append("📈 买盘配合价格上涨，短期看涨信号明确")
                        if market_sentiment == "中性":
                            market_sentiment = "看涨"
                    elif price_change_24h < -1:
                        conclusions.append("⚠️ 买盘增加但价格下跌，可能是抄底或承接盘")
                elif sell_ratio_1h > 60:
                    conclusions.append(f"🔴 1h卖出力量占优 {sell_ratio_1h:.1f}%，短期卖盘强劲")
                    if price_change_24h < -1:
                        conclusions.append("📉 卖盘配合价格下跌，短期看跌信号明确")
                        if market_sentiment == "中性":
                            market_sentiment = "看跌"
                    elif price_change_24h > 1:
                        conclusions.append("⚠️ 卖盘增加但价格上涨，可能是获利了结或派发")
                else:
                    conclusions.append(f"⚖️ 1h买卖力量均衡（买{buy_ratio_1h:.1f}% vs 卖{sell_ratio_1h:.1f}%），多空胶着")
                
                # 买卖金额分析
                buy_amount_m = buy_amount_1h / 1000000
                sell_amount_m = sell_amount_1h / 1000000
                conclusions.append(f"💵 1h买入${buy_amount_m:.2f}M vs 卖出${sell_amount_m:.2f}M")
            
            # 2. 持仓量分析（6小时变化）
            if abs(oi_change) > 5:
                if oi_change > 5:
                    conclusions.append(f"📈 6h持仓量大幅增加 {oi_change:+.2f}%")
                    if price_change_24h > 2:
                        main_operation = "主力正在增加多头仓位"
                        market_sentiment = "看涨"
                        conclusions.append("🟢 持仓量与价格同步上涨，多头增仓明显")
                    elif price_change_24h < -2:
                        main_operation = "主力正在增加空头仓位"
                        market_sentiment = "看跌"
                        conclusions.append("🔴 持仓量上涨但价格下跌，空头增仓明显")
                    else:
                        conclusions.append("⚠️ 持仓量增加但价格震荡，多空分歧加大")
                elif oi_change < -5:
                    conclusions.append(f"📉 6h持仓量大幅减少 {oi_change:+.2f}%")
                    if price_change_24h > 2:
                        main_operation = "主力正在平空单（空头止损）"
                        market_sentiment = "转多"
                        conclusions.append("🟢 持仓量下降但价格上涨，空头平仓/止损")
                    elif price_change_24h < -2:
                        main_operation = "主力正在平多单（多头止损）"
                        market_sentiment = "转空"
                        conclusions.append("🔴 持仓量下降且价格下跌，多头平仓/止损")
                    else:
                        conclusions.append("📊 持仓量下降，获利了结为主")
            elif abs(oi_change) > 2:
                if oi_change > 0:
                    conclusions.append(f"📊 6h持仓量小幅增加 {oi_change:+.2f}%，市场关注度提升")
                else:
                    conclusions.append(f"📊 6h持仓量小幅减少 {oi_change:+.2f}%，部分获利了结")
            else:
                conclusions.append(f"📊 6h持仓量基本持平 {oi_change:+.2f}%，市场观望情绪浓厚")
            
            # 2. 资金费率分析（反映多空情绪）
            if abs(funding_rate_percent) > 0.05:
                if funding_rate_percent > 0.05:
                    conclusions.append(f"💰 资金费率偏高 {funding_rate_percent:+.4f}%，多头支付空头")
                    conclusions.append("⚠️ 市场多头情绪过热，警惕回调风险")
                    if market_sentiment == "看涨":
                        risk_level = "高"
                elif funding_rate_percent < -0.05:
                    conclusions.append(f"💰 资金费率偏低 {funding_rate_percent:+.4f}%，空头支付多头")
                    conclusions.append("⚠️ 市场空头情绪过热，警惕反弹风险")
                    if market_sentiment == "看跌":
                        risk_level = "高"
            else:
                conclusions.append(f"💰 资金费率正常 {funding_rate_percent:+.4f}%，多空平衡")
            
            # 3. 成交量分析（6小时变化）
            if abs(volume_change) > 20:
                if volume_change > 20:
                    conclusions.append(f"📊 6h成交量激增 {volume_change:+.2f}%，市场活跃度大增")
                    if abs(price_change_24h) > 3:
                        conclusions.append("🔥 成交量放大配合价格变动，趋势可能延续")
                    else:
                        conclusions.append("⚠️ 成交量放大但价格未动，可能是洗盘行为")
                else:
                    conclusions.append(f"📊 6h成交量萎缩 {volume_change:+.2f}%，市场观望情绪浓厚")
            elif abs(volume_change) > 10:
                if volume_change > 0:
                    conclusions.append(f"📊 6h成交量小幅增加 {volume_change:+.2f}%")
                else:
                    conclusions.append(f"📊 6h成交量小幅减少 {volume_change:+.2f}%")
            
            # 4. 价格趋势分析
            if abs(price_change_24h) > 5:
                if price_change_24h > 5:
                    conclusions.append(f"🚀 24h大幅上涨 {price_change_24h:+.2f}%")
                    if price_trend_6h > 2:
                        conclusions.append("📈 近6小时继续上涨，上涨动能充足")
                    elif price_trend_6h < -2:
                        conclusions.append("⚠️ 近6小时出现回调，上涨动能减弱")
                else:
                    conclusions.append(f"📉 24h大幅下跌 {price_change_24h:+.2f}%")
                    if price_trend_6h < -2:
                        conclusions.append("📉 近6小时继续下跌，下跌动能充足")
                    elif price_trend_6h > 2:
                        conclusions.append("⚠️ 近6小时出现反弹，下跌动能减弱")
            
            # 5. 综合判断（结合1小时买卖力量）
            if not main_operation:
                # 优先考虑1小时买卖力量作为短期信号
                if buy_ratio_1h > 65:
                    if price_change_24h > 3 and oi_change > 2:
                        main_operation = "多头强势增仓，短期看涨，建议顺势做多"
                    elif price_change_24h > 0:
                        main_operation = "短期买盘积极，关注能否突破"
                    else:
                        main_operation = "买盘强劲但价格承压，观察能否企稳反弹"
                elif sell_ratio_1h > 65:
                    if price_change_24h < -3 and oi_change < -2:
                        main_operation = "空头强势打压，短期看跌，建议顺势做空"
                    elif price_change_24h < 0:
                        main_operation = "短期卖盘积极，关注是否继续下探"
                    else:
                        main_operation = "卖盘强劲但价格抗跌，观察能否止跌企稳"
                else:
                    # 买卖力量均衡，参考中长期指标
                    if price_change_24h > 3 and oi_change > 2:
                        main_operation = "多头主导市场，建议关注回调机会"
                    elif price_change_24h < -3 and oi_change < -2:
                        main_operation = "空头主导市场，建议关注反弹机会"
                    elif abs(price_change_24h) < 2 and abs(oi_change) < 2:
                        main_operation = "市场观望为主，等待方向明确"
                    else:
                        main_operation = "市场处于整理阶段"
            
            return {
                'success': True,
                'symbol': symbol,
                'analysis': {
                    'trade_action': trade_action,  # 三态交易信号 LONG/SHORT/NO_TRADE
                    'market_sentiment': market_sentiment,
                    'main_operation': main_operation,
                    'risk_level': risk_level,
                    'trading_signal': trading_signal,  # 做多模型信号
                    'long_score': long_score,  # 做多模型评分
                    'short_signal': short_signal,  # 做空模型信号
                    'short_score': short_score,  # 做空模型评分
                    'conclusions': conclusions,
                    'data': {
                        'current_price': current_price,
                        'price_change_24h': price_change_24h,
                        'price_trend_6h': price_trend_6h,
                        'oi_change': oi_change,
                        'funding_rate': funding_rate_percent,
                        'volume_change': volume_change,
                        'buy_ratio_1h': buy_ratio_1h,
                        'sell_ratio_1h': sell_ratio_1h,
                        'buy_amount_1h': buy_amount_1h,
                        'sell_amount_1h': sell_amount_1h,
                        'buy_trades_1h': buy_trades_1h,
                        'sell_trades_1h': sell_trades_1h
                    }
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_available_markets_info(self):
        """获取可用市场信息"""
        return {
            'success': True,
            'data': self.available_markets
        }


class EmailAlert:
    """邮件报警类"""
    def __init__(self, smtp_server='smtp-mail.outlook.com', smtp_port=587):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        # 使用Outlook邮箱发送（需要配置应用密码）
        self.sender_email = 'johntmp2026@outlook.com'
        self.sender_password = ''  # 需要设置应用密码
        self.receiver_email = 'johntmp2026@outlook.com'
    
    def send_alert(self, subject, message):
        """发送邮件报警"""
        try:
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = self.receiver_email
            msg['Subject'] = subject
            
            # 邮件正文
            body = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2 style="color: #dc2626;">⚠️ 价格异常波动报警</h2>
    {message}
    <hr>
    <p style="color: #666; font-size: 12px;">
        报警时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
        此邮件由交易监控系统自动发送，请勿回复。
    </p>
</body>
</html>
"""
            msg.attach(MIMEText(body, 'html'))
            
            # 发送邮件
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                if self.sender_password:  # 只在有密码时尝试登录
                    server.login(self.sender_email, self.sender_password)
                    server.send_message(msg)
                    print(f"✅ 邮件报警已发送: {subject}")
                    return True
                else:
                    print("⚠️ 未配置邮件密码，跳过发送")
                    return False
        except Exception as e:
            print(f"❌ 邮件发送失败: {str(e)}")
            return False


class PriceMonitor:
    """价格监控类 - 监控1分钟内涨跌幅超过5%"""
    def __init__(self, market_api, email_alert, check_interval=10):
        self.market_api = market_api
        self.email_alert = email_alert
        self.check_interval = check_interval  # 检查间隔（秒）
        self.price_history = defaultdict(list)  # 存储价格历史
        self.alert_cooldown = defaultdict(int)  # 报警冷却时间
        self.running = False
        self.monitor_thread = None
    
    def start(self):
        """启动监控"""
        if self.running:
            return
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        print("🚀 价格监控已启动")
    
    def stop(self):
        """停止监控"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        print("⏸️ 价格监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                self._check_prices()
            except Exception as e:
                print(f"❌ 价格监控错误: {str(e)}")
            time.sleep(self.check_interval)
    
    def _check_prices(self):
        """检查价格变化"""
        current_time = time.time()
        all_tickers = self.market_api.get_all_tickers()
        
        for market_data in all_tickers.get('markets', []):
            symbol = market_data['symbol']
            
            # 检查现货价格
            if market_data.get('spot') and market_data['spot'].get('success'):
                self._check_symbol_price(
                    symbol, 
                    'spot', 
                    market_data['spot']['data']['last_price'],
                    current_time
                )
            
            # 检查合约价格
            if market_data.get('futures') and market_data['futures'].get('success'):
                self._check_symbol_price(
                    symbol, 
                    'futures', 
                    market_data['futures']['data']['last_price'],
                    current_time
                )
    
    def _check_symbol_price(self, symbol, market_type, current_price, current_time):
        """检查单个币种价格"""
        # 数据验证
        if current_price <= 0:
            return
        
        key = f"{symbol}_{market_type}"
        
        # 添加当前价格到历史记录
        self.price_history[key].append({
            'price': current_price,
            'time': current_time
        })
        
        # 只保留1分钟内的数据（精确到1分钟=60秒）
        one_minute_ago = current_time - 60
        self.price_history[key] = [
            p for p in self.price_history[key] 
            if p['time'] > one_minute_ago
        ]
        
        # 需要至少2个数据点才能计算变化
        if len(self.price_history[key]) < 2:
            return
        
        # 获取1分钟前的价格（最旧的数据点）
        old_price = self.price_history[key][0]['price']
        
        # 数据验证
        if old_price <= 0:
            return
        
        # 计算涨跌幅（精确计算）
        change_percent = ((current_price - old_price) / old_price) * 100
        
        # 检查是否超过5%（使用绝对值）
        if abs(change_percent) >= 5.0:
            # 检查冷却时间（避免频繁报警，5分钟=300秒）
            if current_time - self.alert_cooldown.get(key, 0) > 300:
                self._send_alert(symbol, market_type, old_price, current_price, change_percent)
                self.alert_cooldown[key] = current_time
    
    def _send_alert(self, symbol, market_type, old_price, new_price, change_percent):
        """发送报警邮件"""
        direction = "上涨" if change_percent > 0 else "下跌"
        emoji = "📈" if change_percent > 0 else "📉"
        color = "#10b981" if change_percent > 0 else "#ef4444"
        
        market_type_cn = "现货" if market_type == "spot" else "合约"
        
        subject = f"⚠️ {symbol} {market_type_cn}价格异常波动 {emoji}"
        
        message = f"""
<div style="padding: 20px; background-color: #f9fafb; border-radius: 10px;">
    <h3 style="color: {color};">{emoji} {symbol} ({market_type_cn}) 1分钟内{direction} {abs(change_percent):.2f}%</h3>
    <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
        <tr style="background-color: white;">
            <td style="padding: 10px; border: 1px solid #e5e7eb;">币种</td>
            <td style="padding: 10px; border: 1px solid #e5e7eb;"><strong>{symbol}</strong></td>
        </tr>
        <tr>
            <td style="padding: 10px; border: 1px solid #e5e7eb;">市场类型</td>
            <td style="padding: 10px; border: 1px solid #e5e7eb;">{market_type_cn}</td>
        </tr>
        <tr style="background-color: white;">
            <td style="padding: 10px; border: 1px solid #e5e7eb;">1分钟前价格</td>
            <td style="padding: 10px; border: 1px solid #e5e7eb;">${old_price:,.4f}</td>
        </tr>
        <tr>
            <td style="padding: 10px; border: 1px solid #e5e7eb;">当前价格</td>
            <td style="padding: 10px; border: 1px solid #e5e7eb;"><strong style="color: {color};">${new_price:,.4f}</strong></td>
        </tr>
        <tr style="background-color: white;">
            <td style="padding: 10px; border: 1px solid #e5e7eb;">涨跌幅</td>
            <td style="padding: 10px; border: 1px solid #e5e7eb;">
                <strong style="color: {color}; font-size: 18px;">{change_percent:+.2f}%</strong>
            </td>
        </tr>
    </table>
    <p style="margin-top: 15px; padding: 10px; background-color: #fff3cd; border-left: 4px solid #ffc107; color: #856404;">
        <strong>⚠️ 注意：</strong>此为自动监控报警，请谨慎操作，注意风险控制。
    </p>
</div>
"""
        
        # 同时在控制台输出
        print(f"\n{'='*60}")
        print(f"⚠️ 价格报警: {symbol} {market_type_cn}")
        print(f"   1分钟前: ${old_price:,.4f}")
        print(f"   当前价格: ${new_price:,.4f}")
        print(f"   涨跌幅: {change_percent:+.2f}%")
        print(f"{'='*60}\n")
        
        # 发送邮件
        self.email_alert.send_alert(subject, message)


# 创建API实例
market_api = MultiMarketAPI()

# 创建邮件报警实例
email_alert = EmailAlert()

# 创建价格监控实例（每10秒检查一次）
price_monitor = PriceMonitor(market_api, email_alert, check_interval=10)


# 路由定义
@app.route('/')
def index():
    """主页"""
    return render_template('index_multi.html')


@app.route('/api/markets')
def api_markets():
    """API: 获取可用市场信息"""
    return jsonify(market_api.get_available_markets_info())


@app.route('/api/market-analysis/futures/<symbol>')
def api_market_analysis(symbol):
    """API: 获取合约市场分析"""
    return jsonify(market_api.analyze_futures_market(symbol))


@app.route('/api/all-tickers')
def api_all_tickers():
    """API: 获取所有币种的现货和合约数据"""
    return jsonify(market_api.get_all_tickers())


@app.route('/api/orderbook/<market_type>/<symbol>')
def api_orderbook(market_type, symbol):
    """API: 获取订单深度"""
    limit = int(request.args.get('limit', 10))
    
    if market_type == 'spot':
        return jsonify(market_api.get_spot_orderbook(symbol, limit))
    elif market_type == 'futures':
        return jsonify(market_api.get_futures_orderbook(symbol, limit))
    else:
        return jsonify({'success': False, 'error': 'Invalid market type'})


@app.route('/api/klines/<market_type>/<symbol>')
def api_klines(market_type, symbol):
    """API: 获取K线数据"""
    interval = request.args.get('interval', '1h')
    limit = int(request.args.get('limit', 24))
    
    if market_type == 'spot':
        return jsonify(market_api.get_spot_klines(symbol, interval, limit))
    elif market_type == 'futures':
        return jsonify(market_api.get_futures_klines(symbol, interval, limit))
    else:
        return jsonify({'success': False, 'error': 'Invalid market type'})


@app.route('/api/open-interest-history/<symbol>')
def api_open_interest_history(symbol):
    """API: 获取持仓量历史数据（仅合约）"""
    period = request.args.get('period', '5m')  # 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d
    limit = int(request.args.get('limit', 288))  # 默认288个5分钟数据点（24小时）
    
    return jsonify(market_api.get_open_interest_history(symbol, period, limit))


@app.route('/api/trades/<market_type>/<symbol>')
def api_trades(market_type, symbol):
    """API: 获取最近成交记录"""
    # 获取时间范围（分钟）
    time_range_minutes = request.args.get('time_range', type=float)
    
    # 根据时间范围估算需要的数据量
    if time_range_minutes:
        # 估算：主流币种平均每秒1-2笔成交
        # 1分钟约100笔，5分钟约500笔，30分钟约1000笔（达到上限）
        estimated_limit = int(time_range_minutes * 100)
        # 限制在50到1000之间
        limit = max(50, min(estimated_limit, 1000))
    else:
        limit = int(request.args.get('limit', 50))
    
    if market_type == 'spot':
        return jsonify(market_api.get_spot_trades(symbol, limit, time_range_minutes))
    elif market_type == 'futures':
        return jsonify(market_api.get_futures_trades(symbol, limit, time_range_minutes))
    else:
        return jsonify({'success': False, 'error': 'Invalid market type'})


@app.route('/api/large-orders/<market_type>/<symbol>')
def api_large_orders(market_type, symbol):
    """API: 获取大单分析"""
    # 根据时间范围计算需要获取的成交数量
    time_range_hours = request.args.get('time_range', type=float)
    threshold = float(request.args.get('threshold', 10000))
    
    # 根据时间范围估算需要的数据量
    # 加密货币交易频繁，每小时可能有数百笔成交
    if time_range_hours:
        # 估算：每小时约200-500笔成交，取较大值以确保数据完整
        estimated_limit = int(time_range_hours * 400)
        # 限制在100到1000之间（币安API限制）
        limit = max(100, min(estimated_limit, 1000))
        # 将小时转换为分钟传递给trades函数
        time_range_minutes = time_range_hours * 60
    else:
        limit = int(request.args.get('limit', 100))
        time_range_minutes = None
    
    # 先获取成交数据（传递时间范围以提前过滤）
    if market_type == 'spot':
        trades_data = market_api.get_spot_trades(symbol, limit, time_range_minutes)
    elif market_type == 'futures':
        trades_data = market_api.get_futures_trades(symbol, limit, time_range_minutes)
    else:
        return jsonify({'success': False, 'error': 'Invalid market type'})
    
    # 分析大单（再次应用时间过滤以确保精确）
    if trades_data['success']:
        return jsonify(market_api.analyze_large_orders(trades_data, threshold, time_range_hours))
    else:
        return jsonify(trades_data)


if __name__ == '__main__':
    print("\n" + "="*70)
    print(f"{'🌟 多币种行情数据Web应用（现货+合约）🌟':^70}")
    print("="*70)
    print("\n🚀 服务启动中...")
    print("\n📊 支持币种: TA, BTR, AT")
    print("📈 支持类型: 现货 (Spot) + 合约 (Futures)")
    print("\n🔍 正在检测可用市场...")
    print("-" * 70)
    
    # 初始化时会自动检测
    
    print("-" * 70)
    print(f"\n📡 请在浏览器中访问: http://localhost:5001")
    print(f"📡 或访问: http://127.0.0.1:5001")
    print("\n💡 按 Ctrl+C 停止服务\n")
    print("="*70 + "\n")
    
    # 启动价格监控
    print("🔔 价格监控功能：1分钟内涨跌幅超过5%将发送邮件报警")
    print(f"📧 报警邮箱: {email_alert.receiver_email}")
    if not email_alert.sender_password:
        print("⚠️ 提示: 未配置邮件密码，报警功能将仅在控制台显示")
    price_monitor.start()
    print()
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5001, use_reloader=False)
    finally:
        price_monitor.stop()
