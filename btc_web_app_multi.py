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

# 导入数据库模块
try:
    from database import get_signal_db
    DB_ENABLED = True
    print("✅ 数据库模块已加载，历史信号记录功能已启用")
except ImportError:
    DB_ENABLED = False
    print("⚠️ 数据库模块未找到，历史信号记录功能将被禁用")

# 导入状态机模块
try:
    from market_state_machine import get_state_machine
    STATE_MACHINE_ENABLED = True
    print("✅ 状态机模块已加载，市场分析v3.0（状态机）已启用")
except ImportError:
    STATE_MACHINE_ENABLED = False
    print("⚠️ 状态机模块未找到，将使用v2.0分析逻辑")

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
        """分析合约市场情况并给出状态判断
        
        v3.0 (状态机版本) - 如果启用状态机模块
        v2.0 (规则版本) - 如果未启用状态机模块
        
        设计哲学：
        1. 只做状态判断，不做价格预测
        2. 输出仅限：LONG / SHORT / NO_TRADE
        3. 决策优先级：NO_TRADE > SHORT > LONG
        4. 适用范围：永续合约市场
        5. 数据来源：成交量 / OI / 资金费率 / 短时买卖行为
        
        参数:
            symbol: 交易对符号（如'BTC'）
        
        返回:
            dict: {
                'success': bool,
                'symbol': str,
                'analysis': {
                    'trade_action': str,  # LONG / SHORT / NO_TRADE
                    'state_reason': str,  # 状态判断原因
                    'system_state': str,  # v3.0: 系统状态（INIT/WAIT/LONG_ACTIVE/SHORT_ACTIVE/COOL_DOWN）
                    'market_regime': str, # v3.0: 市场环境（TREND/RANGE/EXTREME）
                    'risk_warning': list, # v2.0: 风险提示列表
                    'data_summary': dict, # 数据摘要
                    'detailed_analysis': list  # 详细分析结论
                }
            }
        """
        # 如果启用状态机，使用v3.0逻辑
        if STATE_MACHINE_ENABLED:
            return self._analyze_with_state_machine(symbol)
        
        # 否则使用v2.0逻辑
        try:
            # ========== 步骤0：数据获取与预处理 ==========
            # 获取合约行情数据
            ticker = self.get_futures_ticker(symbol)
            if not ticker['success']:
                return {
                    'success': False,
                    'error': '无法获取市场数据',
                    'symbol': symbol
                }
            
            ticker_data = ticker['data']
            current_price = float(ticker_data['last_price'])
            price_change_24h = float(ticker_data['price_change_percent'])
            volume_24h = float(ticker_data['volume'])
            quote_volume_24h = float(ticker_data['quote_volume'])
            open_interest = float(ticker_data.get('open_interest', 0))
            funding_rate = float(ticker_data.get('funding_rate', 0))
            volume_change = float(ticker_data.get('volume_change_percent', 0))
            quote_volume_change = float(ticker_data.get('quote_volume_change_percent', 0))
            oi_change = float(ticker_data.get('open_interest_change_percent', 0))
            
            # 获取6小时价格趋势
            klines_result = self.get_futures_klines(symbol, interval='1h', limit=7)
            price_trend_6h = 0
            if klines_result['success'] and len(klines_result['data']) >= 7:
                klines = klines_result['data']
                price_6h_ago = float(klines[0]['close'])
                price_now = float(klines[-1]['close'])
                price_trend_6h = ((price_now - price_6h_ago) / price_6h_ago) * 100
            
            # 获取1小时内的买卖量数据
            buy_amount_1h = 0
            sell_amount_1h = 0
            buy_trades_1h = 0
            sell_trades_1h = 0
            
            try:
                trades_data = self.get_futures_trades(symbol, limit=500, time_range_minutes=60)
                if trades_data['success'] and trades_data['data']:
                    for trade in trades_data['data']:
                        is_buy = not trade['is_buyer_maker']
                        if is_buy:
                            buy_amount_1h += trade['quote_qty']
                            buy_trades_1h += 1
                        else:
                            sell_amount_1h += trade['quote_qty']
                            sell_trades_1h += 1
            except Exception as e:
                print(f"获取{symbol}1小时成交数据失败: {str(e)}")
            
            total_amount_1h = buy_amount_1h + sell_amount_1h
            buy_ratio_1h = (buy_amount_1h / total_amount_1h * 100) if total_amount_1h > 0 else 50
            sell_ratio_1h = 100 - buy_ratio_1h
            
            funding_rate_percent = funding_rate * 100
            
            # 数据摘要
            data_summary = {
                'price': current_price,
                'price_change_24h': price_change_24h,
                'price_trend_6h': price_trend_6h,
                'volume_change_6h': volume_change,
                'oi_change_6h': oi_change,
                'funding_rate': funding_rate_percent,
                'buy_ratio_1h': buy_ratio_1h,
                'sell_ratio_1h': sell_ratio_1h,
                'total_amount_1h': total_amount_1h
            }
            
            # ========== 步骤1：系统保护与数据异常检查 ==========
            data_anomaly_reasons = []
            
            # 检查数据有效性
            if total_amount_1h < 1000:  # 1小时成交额小于1000 USDT
                data_anomaly_reasons.append("⚠️ 数据异常：1小时成交额过低，数据可能不完整")
            
            if abs(price_change_24h) > 50:  # 24小时涨跌幅超过50%
                data_anomaly_reasons.append("⚠️ 数据异常：价格变动超过50%，可能是数据错误或极端事件")
            
            if open_interest == 0:  # 持仓量为0
                data_anomaly_reasons.append("⚠️ 数据异常：持仓量为0，市场可能不活跃或数据缺失")
            
            # 如果有数据异常，直接返回NO_TRADE
            if data_anomaly_reasons:
                return {
                    'success': True,
                    'symbol': symbol,
                    'analysis': {
                        'trade_action': 'NO_TRADE',
                        'state_reason': '数据异常保护',
                        'risk_warning': data_anomaly_reasons,
                        'data_summary': data_summary,
                        'detailed_analysis': ['系统检测到数据异常，为保护账户安全，暂停交易信号输出'] + data_anomaly_reasons
                    }
                }
            
            # ========== 步骤2：NO_TRADE条件检查（最高优先级） ==========
            no_trade_reasons = []
            
            # 2.1 极端行情规则
            # 极端资金费率
            if abs(funding_rate_percent) > 0.2:
                no_trade_reasons.append(f"❌ 极端资金费率：{funding_rate_percent:+.4f}%（阈值±0.2%）- 市场情绪极端失衡")
            
            # OI极端波动
            if abs(oi_change) > 15:
                no_trade_reasons.append(f"❌ OI极端波动：{oi_change:+.2f}%（阈值±15%）- 持仓剧烈变化，市场不稳定")
            
            # 成交量异常放大
            if volume_change > 200:
                no_trade_reasons.append(f"❌ 成交量异常暴增：{volume_change:+.2f}%（阈值200%）- 可能是异常交易或极端事件")
            
            # 2.2 情绪释放规则
            # 集中平仓：OI大降 + 价格大幅波动
            if oi_change < -8 and abs(price_change_24h) > 5:
                no_trade_reasons.append(f"❌ 集中平仓：OI{oi_change:.2f}% + 价格{price_change_24h:+.2f}% - 大量止损/清算，市场混乱")
            
            # 连续大K线（价格剧烈波动）
            if abs(price_change_24h) > 15:
                no_trade_reasons.append(f"❌ 价格剧烈波动：24h{price_change_24h:+.2f}% - 情绪释放期，不宜入场")
            
            # 2.3 冲突态规则（后续会填充）
            conflict_reasons = []
            
            # 如果已经有NO_TRADE原因，直接返回
            if no_trade_reasons:
                return {
                    'success': True,
                    'symbol': symbol,
                    'analysis': {
                        'trade_action': 'NO_TRADE',
                        'state_reason': '极端市场保护',
                        'risk_warning': no_trade_reasons,
                        'data_summary': data_summary,
                        'detailed_analysis': [
                            '=' * 50,
                            '⚪ 【状态判断】NO_TRADE',
                            '=' * 50,
                            '系统检测到极端市场条件，为保护账户安全，不建议参与交易：',
                            ''
                        ] + no_trade_reasons + [
                            '',
                            '=' * 50,
                            '💡 建议：等待市场稳定后再考虑交易',
                            '=' * 50
                        ]
                    }
                }
            
            # ========== 步骤3：SHORT条件判断（优先于LONG） ==========
            short_signals = 0
            short_reasons = []
            short_disqualifiers = []  # 做空否决条件
            
            # 3.1 上涨动能衰竭
            # 上涨无量：价格上涨但成交量萎缩
            if price_change_24h > 1 and volume_change < -5:
                short_signals += 2
                short_reasons.append(f"✓ 上涨无量：价格+{price_change_24h:.2f}% 但成交量{volume_change:.2f}% - 上涨乏力")
            
            # 滞涨：价格不动但OI堆积
            if -1 <= price_change_24h <= 1 and oi_change > 8:
                short_signals += 1.5
                short_reasons.append(f"✓ 滞涨堆积：价格{price_change_24h:+.2f}% 但OI+{oi_change:.2f}% - 多头吸引力下降")
            
            # 3.2 OI堆积规则
            # OI在8-15%区间，风险堆积
            if 8 <= oi_change <= 15:
                short_signals += 2
                short_reasons.append(f"✓ OI堆积：{oi_change:+.2f}%（8-15%风险区间）- 持仓拥挤，回调风险高")
            
            # 3.3 资金费率过热
            # 资金费率>0.1%，多头成本高
            if funding_rate_percent > 0.1:
                short_signals += 1.5
                short_reasons.append(f"✓ 资金费率过热：{funding_rate_percent:+.4f}% - 多头持仓成本高，不可持续")
            
            # 3.4 反弹失败行为
            # 反弹遇阻：反弹但卖压明显
            if price_change_24h > 0 and sell_ratio_1h > 55:
                short_signals += 1.5
                short_reasons.append(f"✓ 反弹卖压：价格+{price_change_24h:.2f}% 但卖出{sell_ratio_1h:.1f}% - 反弹遇阻")
            
            # 下跌加速：价格下跌且卖压持续
            if price_change_24h < -2 and sell_ratio_1h > 60:
                short_signals += 2
                short_reasons.append(f"✓ 下跌加速：价格{price_change_24h:.2f}% + 卖出{sell_ratio_1h:.1f}% - 抛压持续")
            
            # 3.5 做空否决条件检查
            # 多头止损释放：OI大降+价格下跌
            if oi_change < -5 and price_change_24h < -3:
                short_disqualifiers.append(f"⚠️ 多头止损已释放：OI{oi_change:.2f}% + 价格{price_change_24h:.2f}% - 做空风险收益比差")
            
            # 空头拥挤：资金费率已经很负
            if funding_rate_percent < -0.08:
                short_disqualifiers.append(f"⚠️ 空头已拥挤：资金费率{funding_rate_percent:+.4f}% - 不宜追空")
            
            # 情绪尾声：极端下跌
            if price_change_24h < -10:
                short_disqualifiers.append(f"⚠️ 下跌过度：24h{price_change_24h:.2f}% - 可能进入情绪尾声")
            
            # ========== 步骤4：LONG条件判断（最后检查） ==========
            long_signals = 0
            long_reasons = []
            long_disqualifiers = []  # 做多否决条件
            
            # 4.1 新多头持续进场检查
            # 上涨放量：价格上涨 + 成交量放大
            if price_change_24h > 2 and volume_change > 15:
                long_signals += 2
                long_reasons.append(f"✓ 上涨放量：价格+{price_change_24h:.2f}% + 成交量+{volume_change:.2f}% - 突破有效")
            
            # 回调缩量：价格回调但成交量萎缩
            if price_change_24h < 0 and volume_change < -10:
                long_signals += 1.5
                long_reasons.append(f"✓ 回调缩量：价格{price_change_24h:.2f}% + 成交量{volume_change:.2f}% - 回调健康")
            
            # 4.2 OI增长规则
            # OI温和增长：2-8%区间 + 价格上涨
            if 2 <= oi_change <= 8 and price_change_24h > 1:
                long_signals += 2
                long_reasons.append(f"✓ 多头增仓：OI+{oi_change:.2f}%（温和区间）+ 价格+{price_change_24h:.2f}% - 新多头进场")
            
            # 4.3 资金费率健康规则
            # 资金费率温和：-0.05% ~ 0.1%
            if -0.05 <= funding_rate_percent <= 0.1:
                long_signals += 1.5
                long_reasons.append(f"✓ 资金费率健康：{funding_rate_percent:+.4f}% - 多头持仓成本可接受")
            
            # 4.4 短时买卖推动规则
            # 买单推动：买单占优 + 价格上涨
            if buy_ratio_1h > 55 and price_change_24h > 0:
                long_signals += 1.5
                long_reasons.append(f"✓ 买单推动：买入{buy_ratio_1h:.1f}% + 价格+{price_change_24h:.2f}% - 主动买盘强")
            
            # 4.5 做多否决条件检查
            # 空头回补：OI下降 + 价格上涨
            if oi_change < -3 and price_change_24h > 3:
                long_disqualifiers.append(f"⚠️ 可能是空头回补：OI{oi_change:.2f}% + 价格+{price_change_24h:.2f}% - 非新增多头")
            
            # 多头拥挤：OI暴涨
            if oi_change > 15:
                long_disqualifiers.append(f"⚠️ 多头拥挤：OI+{oi_change:.2f}% - 持仓过度拥挤")
            
            # 上方吸收：资金费率过高
            if funding_rate_percent > 0.15:
                long_disqualifiers.append(f"⚠️ 资金费率过高：{funding_rate_percent:+.4f}% - 多头成本不可持续")
            
            # ========== 步骤5：冲突态检测 ==========
            # 如果LONG和SHORT信号都较强（都>=3分），视为冲突态
            if long_signals >= 3 and short_signals >= 3:
                conflict_reasons.append(f"⚠️ 信号冲突：做多信号{long_signals:.1f}分 vs 做空信号{short_signals:.1f}分")
                conflict_reasons.append("⚠️ 多空指标方向矛盾，市场处于过渡态或转折期")
            
            # 核心指标方向不一致
            price_up = price_change_24h > 1
            oi_up = oi_change > 2
            volume_up = volume_change > 10
            
            # 价格与OI、成交量背离
            if price_up and (not oi_up) and (not volume_up):
                conflict_reasons.append("⚠️ 价格上涨但OI和成交量未跟进 - 上涨质量存疑")
            elif (not price_up) and oi_up and volume_up:
                conflict_reasons.append("⚠️ OI和成交量增加但价格未涨 - 多空分歧明显")
            
            # 如果检测到冲突态，返回NO_TRADE
            if conflict_reasons:
                return {
                    'success': True,
                    'symbol': symbol,
                    'analysis': {
                        'trade_action': 'NO_TRADE',
                        'state_reason': '市场冲突态',
                        'risk_warning': conflict_reasons,
                        'data_summary': data_summary,
                        'detailed_analysis': [
                            '=' * 50,
                            '⚪ 【状态判断】NO_TRADE',
                            '=' * 50,
                            '系统检测到市场信号冲突，多空方向不明确：',
                            ''
                        ] + conflict_reasons + [
                            '',
                            f'📊 做多信号：{long_signals:.1f}分',
                            *long_reasons,
                            '',
                            f'📊 做空信号：{short_signals:.1f}分',
                            *short_reasons,
                            '',
                            '=' * 50,
                            '💡 建议：等待市场方向明确后再行动',
                            '=' * 50
                        ]
                    }
                }
            
            # ========== 步骤6：最终决策（按优先级：SHORT > LONG） ==========
            final_action = 'NO_TRADE'
            state_reason = '信号不足'
            risk_warning = []
            detailed_analysis = []
            
            # 优先检查SHORT（需要信号≥4分 且 无否决条件）
            if short_signals >= 4 and len(short_disqualifiers) == 0:
                final_action = 'SHORT'
                state_reason = '空头状态成立'
                risk_warning = ['⚠️ 做空不等于追空，注意止损设置', '⚠️ 建议等待反弹后入场']
                detailed_analysis = [
                    '=' * 50,
                    '🔴 【状态判断】SHORT',
                    '=' * 50,
                    f'空头信号评分：{short_signals:.1f}/10.0 分',
                    '系统判定当前市场处于空头优势状态：',
                    ''
                ] + short_reasons + [
                    '',
                    '=' * 50,
                    '💡 状态解读：多头难以继续吸引新资金，市场偏向下行',
                    '💡 操作建议：可考虑做空，但需注意止损和仓位管理',
                    '⚠️ 风险提示：SHORT状态不等于立即追空，建议等待反弹后入场',
                    '=' * 50
                ]
            
            # 其次检查LONG（需要信号≥4分 且 无否决条件 且 SHORT不成立）
            elif long_signals >= 4 and len(long_disqualifiers) == 0:
                final_action = 'LONG'
                state_reason = '多头状态成立'
                risk_warning = ['⚠️ 做多不等于追涨，注意止损设置', '⚠️ 建议等待回调后入场']
                detailed_analysis = [
                    '=' * 50,
                    '🟢 【状态判断】LONG',
                    '=' * 50,
                    f'多头信号评分：{long_signals:.1f}/10.0 分',
                    '系统判定当前市场处于多头优势状态：',
                    ''
                ] + long_reasons + [
                    '',
                    '=' * 50,
                    '💡 状态解读：新多头在更高价位持续进场，市场偏向上行',
                    '💡 操作建议：可考虑做多，但需注意止损和仓位管理',
                    '⚠️ 风险提示：LONG状态不等于立即追涨，建议等待回调后入场',
                    '=' * 50
                ]
            
            # 如果有否决条件，输出NO_TRADE并说明原因
            elif short_signals >= 4 and short_disqualifiers:
                final_action = 'NO_TRADE'
                state_reason = '做空信号存在但有否决条件'
                risk_warning = short_disqualifiers
                detailed_analysis = [
                    '=' * 50,
                    '⚪ 【状态判断】NO_TRADE',
                    '=' * 50,
                    f'空头信号评分：{short_signals:.1f}分（达标）',
                    '但检测到以下否决条件：',
                    ''
                ] + short_disqualifiers + [
                    '',
                    '=' * 50,
                    '💡 建议：虽有做空信号，但风险收益比不佳，暂不参与',
                    '=' * 50
                ]
            
            elif long_signals >= 4 and long_disqualifiers:
                final_action = 'NO_TRADE'
                state_reason = '做多信号存在但有否决条件'
                risk_warning = long_disqualifiers
                detailed_analysis = [
                    '=' * 50,
                    '⚪ 【状态判断】NO_TRADE',
                    '=' * 50,
                    f'多头信号评分：{long_signals:.1f}分（达标）',
                    '但检测到以下否决条件：',
                    ''
                ] + long_disqualifiers + [
                    '',
                    '=' * 50,
                    '💡 建议：虽有做多信号，但风险收益比不佳，暂不参与',
                    '=' * 50
                ]
            
            # 信号不足，输出NO_TRADE
            else:
                final_action = 'NO_TRADE'
                state_reason = '多空信号均不足'
                risk_warning = ['市场信号不明确，建议观望']
                detailed_analysis = [
                    '=' * 50,
                    '⚪ 【状态判断】NO_TRADE',
                    '=' * 50,
                    '多空信号均未达到入场标准（需≥4分）：',
                    '',
                    f'📊 多头信号：{long_signals:.1f}/10.0 分'
                ]
                if long_reasons:
                    detailed_analysis.extend([''] + long_reasons)
                
                detailed_analysis.extend([
                    '',
                    f'📊 空头信号：{short_signals:.1f}/10.0 分'
                ])
                if short_reasons:
                    detailed_analysis.extend([''] + short_reasons)
                
                detailed_analysis.extend([
                    '',
                    '=' * 50,
                    '💡 建议：信号不足，继续观望，等待更明确的市场状态',
                    '=' * 50
                ])
            
            # 添加数据摘要到详细分析
            detailed_analysis.extend([
                '',
                '📋 数据摘要：',
                '─' * 50,
                f'💹 价格：${current_price:.4f} (24h: {price_change_24h:+.2f}%, 6h: {price_trend_6h:+.2f}%)',
                f'📊 成交量6h变化：{volume_change:+.2f}%',
                f'📈 持仓量6h变化：{oi_change:+.2f}%',
                f'💰 资金费率：{funding_rate_percent:+.4f}%',
                f'🔄 1h买卖比：买{buy_ratio_1h:.1f}% vs 卖{sell_ratio_1h:.1f}%',
                f'💵 1h成交额：${total_amount_1h/1000000:.2f}M',
                '─' * 50
            ])
            
            # 构造返回结果
            result = {
                'success': True,
                'symbol': symbol,
                'analysis': {
                    'trade_action': final_action,
                    'state_reason': state_reason,
                    'risk_warning': risk_warning,
                    'data_summary': data_summary,
                    'detailed_analysis': detailed_analysis,
                    # 保留内部评分供参考
                    '_internal_scores': {
                        'long_score': long_signals,
                        'short_score': short_signals,
                        'long_reasons': long_reasons,
                        'short_reasons': short_reasons,
                        'long_disqualifiers': long_disqualifiers,
                        'short_disqualifiers': short_disqualifiers
                    }
                }
            }
            
            # 保存信号到数据库（异步，不影响主功能）
            if DB_ENABLED:
                try:
                    db = get_signal_db()
                    db.save_signal(result)
                except Exception as db_error:
                    # 数据库保存失败不影响主功能，只记录日志
                    print(f"⚠️ 数据库保存失败: {str(db_error)}")
            
            # 返回最终结果
            return result
            
        except Exception as e:
            import traceback
            print(f"分析{symbol}合约市场失败: {str(e)}")
            print(traceback.format_exc())
            return {
                'success': False,
                'error': f'分析失败: {str(e)}',
                'symbol': symbol
            }
    
    def _analyze_with_state_machine(self, symbol):
        """使用状态机分析合约市场（v3.0）
        
        Args:
            symbol: 交易对符号
            
        Returns:
            dict: 分析结果
        """
        try:
            # ========== 数据获取 ==========
            # 获取合约行情数据
            ticker = self.get_futures_ticker(symbol)
            if not ticker['success']:
                return {
                    'success': False,
                    'error': '无法获取市场数据',
                    'symbol': symbol
                }
            
            ticker_data = ticker['data']
            current_price = float(ticker_data['last_price'])
            price_change_24h = float(ticker_data['price_change_percent'])
            volume_24h = float(ticker_data['volume'])
            quote_volume_24h = float(ticker_data['quote_volume'])
            open_interest = float(ticker_data.get('open_interest', 0))
            funding_rate = float(ticker_data.get('funding_rate', 0))
            volume_change = float(ticker_data.get('volume_change_percent', 0))
            oi_change = float(ticker_data.get('open_interest_change_percent', 0))
            
            # 获取6小时价格趋势
            klines_result = self.get_futures_klines(symbol, interval='1h', limit=7)
            price_trend_6h = 0
            if klines_result['success'] and len(klines_result['data']) >= 7:
                klines = klines_result['data']
                price_6h_ago = float(klines[0]['close'])
                price_now = float(klines[-1]['close'])
                price_trend_6h = ((price_now - price_6h_ago) / price_6h_ago)
            
            # 计算平均成交量（用于判断放量/缩量）
            volume_avg = volume_24h / 24  # 简单平均
            
            # 计算波动率（使用24h高低价差）
            high_24h = float(ticker_data['high_price'])
            low_24h = float(ticker_data['low_price'])
            volatility = (high_24h - low_24h) / current_price if current_price > 0 else 0
            
            # 判断价格结构是否连续（简化版：6h趋势明确视为连续）
            price_structure_continuous = abs(price_trend_6h) > 0.01  # 6h涨跌超过1%视为有方向
            
            # 获取1小时内的买卖量数据
            buy_amount_1h = 0
            sell_amount_1h = 0
            
            try:
                trades_data = self.get_futures_trades(symbol, limit=500, time_range_minutes=60)
                if trades_data['success'] and trades_data['data']:
                    for trade in trades_data['data']:
                        is_buy = not trade['is_buyer_maker']
                        if is_buy:
                            buy_amount_1h += trade['quote_qty']
                        else:
                            sell_amount_1h += trade['quote_qty']
            except Exception as e:
                print(f"获取{symbol}1小时成交数据失败: {str(e)}")
            
            total_amount_1h = buy_amount_1h + sell_amount_1h
            aggressive_buy_ratio = (buy_amount_1h / total_amount_1h) if total_amount_1h > 0 else 0.5
            aggressive_sell_ratio = 1 - aggressive_buy_ratio
            
            # 计算 OI 变化速率和 delta
            oi_delta = oi_change / 100  # 转换为小数
            oi_delta_rate = abs(oi_delta)
            
            # ========== 准备状态机输入数据 ==========
            market_data = {
                'price': current_price,
                'price_change_24h': price_change_24h / 100,  # 转换为小数
                'price_trend_6h': price_trend_6h,
                'volume': volume_24h,
                'volume_avg': volume_avg,
                'volume_change_6h': volume_change / 100,  # 转换为小数
                'oi': open_interest,
                'oi_delta': oi_delta,
                'oi_delta_rate': oi_delta_rate,
                'oi_change_6h': oi_change / 100,  # 转换为小数
                'funding_rate': funding_rate,
                'aggressive_buy_ratio': aggressive_buy_ratio,
                'aggressive_sell_ratio': aggressive_sell_ratio,
                'volatility': volatility,
                'price_structure_continuous': price_structure_continuous,
                'total_amount_1h': total_amount_1h
            }
            
            # ========== 调用状态机 ==========
            state_machine = get_state_machine()
            result = state_machine.on_new_tick(symbol, market_data)
            
            # ========== 保存到数据库 ==========
            if DB_ENABLED:
                try:
                    db = get_signal_db()
                    db.save_signal(result)
                except Exception as db_error:
                    print(f"⚠️ 数据库保存失败: {str(db_error)}")
            
            return result
            
        except Exception as e:
            import traceback
            print(f"状态机分析{symbol}失败: {str(e)}")
            print(traceback.format_exc())
            return {
                'success': False,
                'error': f'分析失败: {str(e)}',
                'symbol': symbol
            }
    
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


@app.route('/api/signal-history')
def api_signal_history():
    """API: 获取历史信号记录"""
    if not DB_ENABLED:
        return jsonify({
            'success': False,
            'error': '数据库功能未启用'
        })
    
    try:
        symbol = request.args.get('symbol', None)
        limit = int(request.args.get('limit', 10))
        
        db = get_signal_db()
        signals = db.get_latest_signals(symbol, limit)
        
        return jsonify({
            'success': True,
            'symbol': symbol,
            'count': len(signals),
            'signals': signals
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/signal-stats')
def api_signal_stats():
    """API: 获取信号统计数据"""
    if not DB_ENABLED:
        return jsonify({
            'success': False,
            'error': '数据库功能未启用'
        })
    
    try:
        symbol = request.args.get('symbol', None)
        days = int(request.args.get('days', 7))
        
        db = get_signal_db()
        stats = db.get_signal_stats(symbol, days)
        
        return jsonify({
            'success': True,
            'symbol': symbol,
            'days': days,
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/database-info')
def api_database_info():
    """API: 获取数据库信息"""
    if not DB_ENABLED:
        return jsonify({
            'success': False,
            'error': '数据库功能未启用'
        })
    
    try:
        db = get_signal_db()
        info = db.get_database_info()
        
        return jsonify({
            'success': True,
            'info': info
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


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
