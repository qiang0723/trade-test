#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os
os_path = '/root/bian_yuanshi/'
from binance import AsyncClient, BinanceSocketManager
import asyncio
import pickle
import os
from collections import defaultdict
import pandas as pd
import threading
from binance.client import Client
import time
import logging
import sys
sys.path.append(os_path)
from  utils3.tools import *
import diskcache as dc
from datetime import datetime,timedelta
from binance.enums import *  
import math  
import traceback


# In[2]:


class G():
    pass


# In[ ]:


def get_price(symbol,client):  
    ticker = client.futures_symbol_ticker(symbol=symbol)  
    return float(ticker['price'])  

def get_lot_size_filter(symbol,client):  
    info = client.futures_exchange_info()  
    for s in info['symbols']:  
        if s['symbol'] == symbol:  
            for f in s['filters']:  
                if f['filterType'] == 'LOT_SIZE':  
                    return f  
    return None  

def round_to_step_size(quantity, step_size):  
    # 按step_size向下取整  
    precision = int(round(-math.log(float(step_size), 10), 0))  
    return round(math.floor(quantity / float(step_size)) * float(step_size), precision)  

def open_long(symbol, quantity,client):  
    order = client.futures_create_order(  
        symbol=symbol,  
        side=SIDE_BUY,  
        type=ORDER_TYPE_MARKET,  
        quantity=quantity,  
        positionSide="LONG"
    )  
    return order  

def close_long(symbol, quantity,client):  
    order = client.futures_create_order(  
        symbol=symbol,  
        side=SIDE_SELL,  
        type=ORDER_TYPE_MARKET,  
        quantity=quantity,  
        positionSide="LONG" 
    )  
    return order  

def open_long_limit(symbol, quantity, price,client,time_in_force='GTC'):
    """
    在币安合约下限价买入（开多）
    参数:
      - symbol: 交易对字符串，例如 "BTCUSDT"
      - quantity: 订单数量（合约数量或数量单位，按你的合约类型填写）
      - price: 委托价格（字符串或浮点数，通常按字符串以避免精度问题）
      - time_in_force: 'GTC' / 'IOC' / 'FOK'（默认 'GTC'）
    返回:
      - Binance 返回的订单信息 JSON
    """
    order = client.futures_create_order(
        symbol=symbol,
        side='BUY',                 # 或 SIDE_BUY（取决于你用的SDK常量）
        type='LIMIT',               # 限价单
        timeInForce=time_in_force,  # 必须提供 timeInForce
        quantity=quantity,
        price=str(price),           # 建议用字符串避免浮点精度问题
        positionSide="LONG"         # 若是双向持仓模式（HEDGE）可用，单向模式可省略
    )
    return order


def open_short(symbol, quantity,client):  
    order = client.futures_create_order(  
        symbol=symbol,  
        side=SIDE_SELL,  
        type=ORDER_TYPE_MARKET,  
        quantity=quantity,  
        positionSide="SHORT"
    )  
    return order  


def open_short_limit(symbol, quantity, price,client,time_in_force='GTC'):
    """
    在币安合约下限价买入（开空）
    参数:
      - symbol: 交易对字符串，例如 "BTCUSDT"
      - quantity: 订单数量（合约数量或数量单位，按你的合约类型填写）
      - price: 委托价格（字符串或浮点数，通常按字符串以避免精度问题）
      - time_in_force: 'GTC' / 'IOC' / 'FOK'（默认 'GTC'）
    返回:
      - Binance 返回的订单信息 JSON
    """
    order = client.futures_create_order(
        symbol=symbol,
        side='SELL',                 # 或 SIDE_BUY（取决于你用的SDK常量）
        type='LIMIT',               # 限价单
        timeInForce=time_in_force,  # 必须提供 timeInForce
        quantity=quantity,
        price=str(price),           # 建议用字符串避免浮点精度问题
        positionSide="SHORT"         # 若是双向持仓模式（HEDGE）可用，单向模式可省略
    )
    return order

def close_short(symbol, quantity,client):  
    order = client.futures_create_order(  
        symbol=symbol,  
        side=SIDE_BUY,  
        type=ORDER_TYPE_MARKET,  
        quantity=quantity,  
        positionSide="SHORT"
    )  
    return order

def query_order(symbol, orderId=None, origClientOrderId=None,client=None):
    """
    查询指定订单信息。至少提供 orderId 或 origClientOrderId。
    返回 Binance 的订单 JSON（包含 status、executedQty、price 等字段）
    """
    try:
        params = {"symbol": symbol}
        if orderId:
            params["orderId"] = orderId
        if origClientOrderId:
            params["origClientOrderId"] = origClientOrderId

        order = client.futures_get_order(**params)
        return order
    except Exception as e:
        # 根据 SDK，捕获更具体的异常并处理
        print("查询订单异常:", e)
        raise


# In[ ]:


def check_trade(ContextInfo,symbol,client):
    price = get_price(symbol,client)  
    order_amount = ContextInfo.vol_usdt
    lot_size_filter = get_lot_size_filter(symbol,client)  
    step_size = lot_size_filter['stepSize']  
    raw_quantity = order_amount / price  

    quantity = round_to_step_size(raw_quantity, step_size)  
    if  ContextInfo.upper_limit>0:
        if ContextInfo.last_buy_id != '':
            resp = query_order(symbol, orderId=ContextInfo.last_buy_id,client=client)
            if resp['status'] == 'FILLED':
                result = open_long_limit(symbol, quantity, ContextInfo.upper_limit,client=client, time_in_force='GTC')
                ContextInfo.last_buy_id = result['orderId']
                cur_time = time.strftime('%Y-%m-%d %H%M%S')
                msg = f'{cur_time}上份已成交，已下新一份限价买入单！！'
                ContextInfo.log.log_writer(ContextInfo.logger,level='info',source='Init',msg=msg) 
        else:
            result = open_long_limit(symbol, quantity, ContextInfo.upper_limit,client=client, time_in_force='GTC')
            ContextInfo.last_buy_id = result['orderId']
            cur_time = time.strftime('%Y-%m-%d %H%M%S')
            msg = f'{cur_time}买入一份限价买入单！！'   
            ContextInfo.log.log_writer(ContextInfo.logger,level='info',source='Init',msg=msg) 

    if  ContextInfo.down_limit>0:
        if ContextInfo.last_sell_id != '':
            resp = query_order(symbol, orderId=ContextInfo.last_sell_id,clinet=client)
            if resp['status'] == 'FILLED':
                result = open_short_limit(symbol, quantity, ContextInfo.down_limit,client=client,time_in_force='GTC')
                ContextInfo.last_sell_id = result['orderId']
                cur_time = time.strftime('%Y-%m-%d %H%M%S')
                msg = f'{cur_time}上份已成交，已下新一份限价卖出单！！'
                ContextInfo.log.log_writer(ContextInfo.logger,level='info',source='Init',msg=msg) 
        else:
            result = open_short_limit(symbol, quantity, ContextInfo.down_limit,client=client,time_in_force='GTC')
            ContextInfo.last_sell_id = result['orderId']
            cur_time = time.strftime('%Y-%m-%d %H%M%S')
            msg = f'{cur_time}买入一份限价卖出单！！'      
            ContextInfo.log.log_writer(ContextInfo.logger,level='info',source='Init',msg=msg) 

# In[ ]:


if __name__ == "__main__":
    ContextInfo = G()
    ContextInfo.config_path = os.path.join(os.getcwd(),"configs")
    config_path = os.path.join(ContextInfo.config_path,f'策略待启动.json')
    if not os.path.exists(config_path):
        sys.exit(0)
    with open(config_path, 'r', encoding='utf-8') as f:  
        st = f.read() 
    config_dict = json.loads(st) 
    os.remove(config_path) 

    strategy_name = config_dict['name']
    ContextInfo.apikey = config_dict['api_key']
    ContextInfo.secretkey =  config_dict['secret']
    ContextInfo.vol_usdt =  config_dict['vol_usdt']
    ContextInfo.intermin = config_dict['intermin']
    ContextInfo.upper_limit = config_dict['upper_limit']
    ContextInfo.down_limit = config_dict['down_limit']
    
    current_dir = os.getcwd()
    logs_path = os.path.join(current_dir,"logs")
    log_path = os.path.join(logs_path,f'{strategy_name}')
    ContextInfo.log = log_writer(logs_path=log_path)
    cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S') 
    log_name= f'{strategy_name}-{cur_time}.log'
    log_path = ContextInfo.log.log_path(log_name)
    ContextInfo.logger = ContextInfo.log.init_logger(log_name,f'{strategy_name}')
    msg = f'{strategy_name}初始化成功!'
    ContextInfo.log.log_writer(ContextInfo.logger,level='info',source='Init',msg=msg) 
    ContextInfo.last_buy_id = ''
    ContextInfo.last_sell_id = ''
     
    config_dict['is_gendan'] = 0
    config_dict['is_run'] = 1
    config_dict['is_launch'] = 1
    config_dict['update_time'] = cur_time
    config_path = os.path.join(ContextInfo.config_path,f'{strategy_name}.json')
    with open(config_path, 'w', encoding='utf-8') as f:  
        json.dump(config_dict, f, ensure_ascii=False, indent=4) 
    client = Client(ContextInfo.apikey,  ContextInfo.secretkey )  
# In[ ]:


if __name__ == "__main__":
    config_path = os.path.join(ContextInfo.config_path,f'{strategy_name}.json')
    while True:
        try:
            #停止程序
            if config_dict['is_launch'] ==0:
                msg = f'{strategy_name}程序已停止！！'
                config_dict['is_run'] = 0
                with open(config_path, 'w', encoding='utf-8') as f:  
                    json.dump(config_dict, f, ensure_ascii=False, indent=4)    
                ContextInfo.log.log_writer(ContextInfo.logger,level='error',source='Init',msg=msg) 
                sys.exit(0)   
            symbol = 'B2USDT'
            check_trade(ContextInfo,symbol,client)
            with open(config_path, 'r', encoding='utf-8') as f:  
                st = f.read() 
            config_dict = json.loads(st) 

            ContextInfo.vol_usdt =  config_dict['vol_usdt']
            ContextInfo.intermin = config_dict['intermin']
            ContextInfo.upper_limit = config_dict['upper_limit']
            ContextInfo.down_limit = config_dict['down_limit']   
            sleeps = ContextInfo.intermin
            time.sleep(sleeps)
        except:
            msg = f'{strategy_name}运行失败!'
            ContextInfo.log.log_writer(ContextInfo.logger,level='info',source='Init',msg=msg) 
            error = str(traceback.format_exc()) 
            ContextInfo.log.log_writer(ContextInfo.logger, level='error', source='error', msg=error)
            break
    
