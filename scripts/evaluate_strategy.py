#!/usr/bin/env python3
"""
L1 Advisory 策略评价脚本

通用评价方法框架：
1. 胜率评估：按多个维度计算胜率（传统30分钟验证）
2. 信号质量评估：分析信号分布和质量
3. 时间段对比：支持配置前后对比
4. 止损止盈回测：使用1小时验证窗口验证止损止盈策略效果
5. 止损止盈优化：基于历史数据寻找最优止损止盈参数
6. 综合胜率评估：整合传统胜率和止损止盈策略评估

使用方法：
    # 基础评估
    docker exec l1-advisory-layer python3 /app/scripts/evaluate_strategy.py
    
    # 包含止损止盈分析
    docker exec l1-advisory-layer python3 /app/scripts/evaluate_strategy.py --stoploss
    
    # 包含止损止盈参数优化
    docker exec l1-advisory-layer python3 /app/scripts/evaluate_strategy.py --stoploss --optimize
    
    # 完整分析（含白名单+止损止盈+优化）
    docker exec l1-advisory-layer python3 /app/scripts/evaluate_strategy.py --whitelist --stoploss --optimize
    
    # 只分析最近24小时数据
    docker exec l1-advisory-layer python3 /app/scripts/evaluate_strategy.py --hours 24 --stoploss --optimize

评价指标：
- 胜率(Win Rate): 信号方向正确的比例
- 信号率(Signal Rate): 产生交易信号的比例
- 盈亏比(Profit Factor): 平均盈利/平均亏损
- 止损触发率(SL Hit Rate): 止损被触发的比例（基于时间顺序）
- 止盈触发率(TP Hit Rate): 止盈被触发的比例（基于时间顺序）
- 实际盈亏比(Actual RR): 实际的盈亏比
- 期望收益(Expected Return): win_rate * avg_profit - (1 - win_rate) * avg_loss

止损止盈回测说明：
- 使用1小时验证窗口
- 按时间顺序判断止损/止盈触发（谁先触发谁算）
- 分别按币种、市场环境、置信度分组统计
- 优化功能会测试不同止损%和盈亏比组合，寻找最优参数
"""

import sqlite3
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import json

# 评价标准
WIN_RATE_THRESHOLDS = {
    'excellent': 0.70,  # 70%以上为优秀
    'good': 0.55,       # 55%以上为良好
    'acceptable': 0.45, # 45%以上为可接受
    'poor': 0.0         # 45%以下为差
}

def get_marker(win_rate: float) -> str:
    """根据胜率返回标记"""
    if win_rate >= WIN_RATE_THRESHOLDS['excellent']:
        return '✅ 优秀'
    elif win_rate >= WIN_RATE_THRESHOLDS['good']:
        return '👍 良好'
    elif win_rate >= WIN_RATE_THRESHOLDS['acceptable']:
        return '⚠️ 一般'
    else:
        return '❌ 差'


def calculate_win_rate(
    cursor,
    where_clause: str = "",
    params: tuple = (),
    hold_minutes: int = 30,
    price_threshold: float = 0.1
) -> Dict:
    """
    计算胜率
    
    Args:
        cursor: 数据库游标
        where_clause: SQL WHERE子句
        params: SQL参数
        hold_minutes: 持有时间（分钟）
        price_threshold: 价格变化阈值（%）
    
    Returns:
        包含胜率统计的字典
    """
    query = f'''
        SELECT r1.symbol, r1.recommended_action, r1.price, r1.created_at
        FROM l1_dual_advisory_results r1
        WHERE r1.recommended_action != 'no_trade'
        AND r1.price IS NOT NULL AND r1.price > 0
        {where_clause}
    '''
    cursor.execute(query, params)
    signals = cursor.fetchall()
    
    win = loss = neutral = 0
    total_profit = 0.0
    total_loss = 0.0
    
    for symbol, action, price, created_at in signals:
        # 查找持有时间后的价格
        min_time = hold_minutes - 5
        max_time = hold_minutes + 5
        cursor.execute(f'''
            SELECT price FROM l1_dual_advisory_results 
            WHERE symbol = ? 
            AND created_at > datetime(?, '+{min_time} minutes')
            AND created_at < datetime(?, '+{max_time} minutes')
            AND price IS NOT NULL
            LIMIT 1
        ''', (symbol, created_at, created_at))
        future = cursor.fetchone()
        
        if not future or not future[0]:
            continue
        
        change = (future[0] - price) / price * 100
        
        if action == 'long':
            if change > price_threshold:
                win += 1
                total_profit += change
            elif change < -price_threshold:
                loss += 1
                total_loss += abs(change)
            else:
                neutral += 1
        else:  # short
            if change < -price_threshold:
                win += 1
                total_profit += abs(change)
            elif change > price_threshold:
                loss += 1
                total_loss += change
            else:
                neutral += 1
    
    total = win + loss + neutral
    win_rate = win / total if total > 0 else 0
    avg_profit = total_profit / win if win > 0 else 0
    avg_loss = total_loss / loss if loss > 0 else 0
    profit_factor = avg_profit / avg_loss if avg_loss > 0 else float('inf')
    
    return {
        'win': win,
        'loss': loss,
        'neutral': neutral,
        'total': total,
        'win_rate': win_rate,
        'avg_profit': avg_profit,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor
    }


def print_evaluation_report(cursor, time_filter: str = "", time_desc: str = "全部数据"):
    """打印评价报告"""
    
    print("=" * 80)
    print(f"📊 L1 Advisory 策略评价报告 - {time_desc}")
    print("=" * 80)
    print(f"评价时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"评价标准: 持有30分钟，价格变化>0.1%判定胜负")
    
    # 1. 总体概览
    cursor.execute(f'''
        SELECT COUNT(*) FROM l1_dual_advisory_results {time_filter}
    ''')
    total_records = cursor.fetchone()[0]
    
    cursor.execute(f'''
        SELECT COUNT(*) FROM l1_dual_advisory_results 
        WHERE recommended_action != 'no_trade' {time_filter.replace('WHERE', 'AND') if time_filter else ''}
    ''')
    signal_records = cursor.fetchone()[0]
    
    signal_rate = signal_records / total_records * 100 if total_records > 0 else 0
    
    print(f"\n📈 数据概览")
    print(f"  总记录数: {total_records}")
    print(f"  信号数: {signal_records} ({signal_rate:.1f}%)")
    
    # 辅助函数：构建时间过滤条件
    def get_time_filter_and():
        """将WHERE格式的时间过滤转为AND格式"""
        if not time_filter:
            return ""
        # time_filter格式: WHERE created_at > datetime(...) 
        # 需要转为: AND created_at > datetime(...)
        return time_filter.replace("WHERE ", "AND ")
    
    time_and = get_time_filter_and()
    
    # 2. 按置信度级别评估
    print(f"\n📊 按置信度级别评估")
    print(f"{'级别':10} | {'胜':5} | {'负':5} | {'平':5} | {'总':6} | {'胜率':8} | {'盈亏比':8} | {'评价':8}")
    print("-" * 75)
    
    for conf in ['ultra', 'high', 'medium', 'low']:
        full_where = f"{time_and} AND recommended_confidence = ?"
        stats = calculate_win_rate(cursor, full_where, (conf,))
        
        if stats['total'] > 0:
            pf = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "∞"
            marker = get_marker(stats['win_rate'])
            print(f"{conf:10} | {stats['win']:5} | {stats['loss']:5} | {stats['neutral']:5} | "
                  f"{stats['total']:6} | {stats['win_rate']*100:6.1f}% | {pf:8} | {marker}")
    
    # 3. 按市场环境评估
    print(f"\n📊 按市场环境评估")
    print(f"{'环境':10} | {'胜':5} | {'负':5} | {'平':5} | {'总':6} | {'胜率':8} | {'盈亏比':8} | {'评价':8}")
    print("-" * 75)
    
    for regime in ['trend', 'range', 'extreme']:
        full_where = f"{time_and} AND short_term_regime = ?"
        stats = calculate_win_rate(cursor, full_where, (regime,))
        
        if stats['total'] > 0:
            pf = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "∞"
            marker = get_marker(stats['win_rate'])
            print(f"{regime:10} | {stats['win']:5} | {stats['loss']:5} | {stats['neutral']:5} | "
                  f"{stats['total']:6} | {stats['win_rate']*100:6.1f}% | {pf:8} | {marker}")
    
    # 4. 按方向评估
    print(f"\n📊 按交易方向评估")
    print(f"{'方向':10} | {'胜':5} | {'负':5} | {'平':5} | {'总':6} | {'胜率':8} | {'盈亏比':8} | {'评价':8}")
    print("-" * 75)
    
    for action in ['long', 'short']:
        full_where = f"{time_and} AND recommended_action = ?"
        stats = calculate_win_rate(cursor, full_where, (action,))
        
        if stats['total'] > 0:
            pf = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "∞"
            marker = get_marker(stats['win_rate'])
            print(f"{action:10} | {stats['win']:5} | {stats['loss']:5} | {stats['neutral']:5} | "
                  f"{stats['total']:6} | {stats['win_rate']*100:6.1f}% | {pf:8} | {marker}")
    
    # 5. 按币种评估
    print(f"\n📊 按币种评估")
    print(f"{'币种':10} | {'胜':5} | {'负':5} | {'平':5} | {'总':6} | {'胜率':8} | {'盈亏比':8} | {'评价':8}")
    print("-" * 75)
    
    cursor.execute('SELECT DISTINCT symbol FROM l1_dual_advisory_results WHERE symbol NOT LIKE "%USDT"')
    symbols = [r[0] for r in cursor.fetchall()]
    
    for symbol in sorted(symbols):
        full_where = f"{time_and} AND symbol = ?"
        stats = calculate_win_rate(cursor, full_where, (symbol,))
        
        if stats['total'] > 0:
            pf = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "∞"
            marker = get_marker(stats['win_rate'])
            print(f"{symbol:10} | {stats['win']:5} | {stats['loss']:5} | {stats['neutral']:5} | "
                  f"{stats['total']:6} | {stats['win_rate']*100:6.1f}% | {pf:8} | {marker}")
    
    # 6. 核心指标 - TREND + ULTRA
    print(f"\n⭐ 核心指标 - TREND + ULTRA")
    full_where = f"{time_and} AND short_term_regime = 'trend' AND recommended_confidence = 'ultra'"
    stats = calculate_win_rate(cursor, full_where, ())
    
    if stats['total'] > 0:
        pf = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float('inf') else "∞"
        marker = get_marker(stats['win_rate'])
        print(f"  胜{stats['win']} 负{stats['loss']} 平{stats['neutral']} 总{stats['total']}")
        print(f"  胜率: {stats['win_rate']*100:.1f}% | 盈亏比: {pf} | 评价: {marker}")
    else:
        print("  数据不足")
    
    # 7. 信号分布
    print(f"\n📊 信号分布")
    base_where = time_filter if time_filter else ""
    cursor.execute(f'''
        SELECT short_term_regime, recommended_action, recommended_confidence, COUNT(*) as cnt
        FROM l1_dual_advisory_results 
        {base_where}
        GROUP BY short_term_regime, recommended_action, recommended_confidence
        ORDER BY short_term_regime, recommended_confidence DESC, cnt DESC
    ''')
    
    results = cursor.fetchall()
    print(f"{'环境':10} | {'动作':10} | {'置信度':8} | {'数量':6}")
    print("-" * 45)
    for row in results:
        marker = '⭐' if row[2] in ('high', 'ultra') and row[1] != 'no_trade' else ''
        print(f"{row[0]:10} | {row[1]:10} | {row[2]:8} | {row[3]:6} {marker}")


def print_symbol_direction_report(cursor, time_filter: str = ""):
    """
    打印币种+方向组合评估报告（与白名单服务保持一致）
    
    只评估 ULTRA + TREND 信号，这是白名单使用的标准
    """
    print(f"\n📊 币种+方向组合评估（ULTRA + TREND信号）")
    print("=" * 85)
    print("（此评估与白名单计算逻辑一致）")
    print(f"{'币种':8} | {'方向':6} | {'胜':5} | {'负':5} | {'总':6} | {'胜率':8} | {'平均盈':8} | {'平均亏':8} | {'白名单建议'}")
    print("-" * 95)
    
    # 获取所有币种
    cursor.execute('SELECT DISTINCT symbol FROM l1_dual_advisory_results WHERE symbol NOT LIKE "%USDT"')
    symbols = [r[0] for r in cursor.fetchall()]
    
    results = []
    
    # 转换时间过滤为AND格式
    time_and = time_filter.replace("WHERE ", "AND ") if time_filter else ""
    
    for symbol in sorted(symbols):
        for direction in ['long', 'short']:
            # 只评估 ULTRA + TREND 信号（与白名单服务一致）
            base_where = f"""
                {time_and}
                AND symbol = ? 
                AND recommended_action = ?
                AND recommended_confidence = 'ultra'
                AND short_term_regime = 'trend'
            """
            
            stats = calculate_win_rate(cursor, base_where, (symbol, direction))
            
            if stats['total'] >= 3:  # 至少3个样本
                # 白名单建议
                if stats['total'] >= 10 and stats['win_rate'] >= 0.60:
                    wl_status = "✅ 白名单"
                elif stats['total'] >= 5 and stats['win_rate'] <= 0.40:
                    wl_status = "❌ 黑名单"
                else:
                    wl_status = "👀 观察中"
                
                results.append({
                    'symbol': symbol,
                    'direction': direction,
                    'stats': stats,
                    'wl_status': wl_status
                })
    
    # 按胜率排序
    results.sort(key=lambda x: x['stats']['win_rate'], reverse=True)
    
    for r in results:
        s = r['stats']
        print(f"{r['symbol']:8} | {r['direction']:6} | {s['win']:5} | {s['loss']:5} | "
              f"{s['total']:6} | {s['win_rate']*100:6.1f}% | {s['avg_profit']:+6.2f}% | "
              f"{s['avg_loss']:+6.2f}% | {r['wl_status']}")
    
    # 白名单统计
    whitelist = [r for r in results if '白名单' in r['wl_status']]
    blacklist = [r for r in results if '黑名单' in r['wl_status']]
    observation = [r for r in results if '观察' in r['wl_status']]
    
    print(f"\n白名单统计: ✅白名单 {len(whitelist)} | ❌黑名单 {len(blacklist)} | 👀观察中 {len(observation)}")
    
    return results


def print_whitelist_validation(cursor, time_filter: str = ""):
    """
    白名单效果验证
    
    验证白名单信号vs非白名单信号的实际表现
    """
    print(f"\n📊 白名单效果验证")
    print("=" * 80)
    
    # 先获取当前白名单
    cursor.execute('SELECT symbol, direction FROM l1_whitelist WHERE in_whitelist = 1')
    whitelist_combos = set((r[0], r[1]) for r in cursor.fetchall())
    
    if not whitelist_combos:
        print("（尚无白名单数据，跳过验证）")
        return
    
    print(f"当前白名单: {', '.join([f'{s} {d.upper()}' for s, d in whitelist_combos])}")
    
    # 获取所有ULTRA信号
    base_query = """
        SELECT r1.symbol, r1.recommended_action, r1.price, r1.created_at
        FROM l1_dual_advisory_results r1
        WHERE r1.recommended_action IN ('long', 'short')
        AND r1.recommended_confidence = 'ultra'
        AND r1.price IS NOT NULL AND r1.price > 0
    """
    if time_filter:
        base_query += f" {time_filter.replace('WHERE', 'AND')}"
    
    cursor.execute(base_query)
    signals = cursor.fetchall()
    
    # 分组统计
    wl_win = wl_loss = wl_neutral = 0
    non_wl_win = non_wl_loss = non_wl_neutral = 0
    
    for symbol, action, price, created_at in signals:
        # 查找30分钟后的价格
        cursor.execute('''
            SELECT price FROM l1_dual_advisory_results 
            WHERE symbol = ? 
            AND created_at > datetime(?, '+25 minutes')
            AND created_at < datetime(?, '+35 minutes')
            AND price IS NOT NULL
            LIMIT 1
        ''', (symbol, created_at, created_at))
        future = cursor.fetchone()
        
        if not future or not future[0]:
            continue
        
        change = (future[0] - price) / price * 100
        is_whitelist = (symbol, action) in whitelist_combos
        
        if action == 'long':
            if change > 0.1:
                if is_whitelist: wl_win += 1
                else: non_wl_win += 1
            elif change < -0.1:
                if is_whitelist: wl_loss += 1
                else: non_wl_loss += 1
            else:
                if is_whitelist: wl_neutral += 1
                else: non_wl_neutral += 1
        else:
            if change < -0.1:
                if is_whitelist: wl_win += 1
                else: non_wl_win += 1
            elif change > 0.1:
                if is_whitelist: wl_loss += 1
                else: non_wl_loss += 1
            else:
                if is_whitelist: wl_neutral += 1
                else: non_wl_neutral += 1
    
    wl_total = wl_win + wl_loss + wl_neutral
    non_wl_total = non_wl_win + non_wl_loss + non_wl_neutral
    
    wl_rate = wl_win / wl_total if wl_total > 0 else 0
    non_wl_rate = non_wl_win / non_wl_total if non_wl_total > 0 else 0
    
    print(f"\n{'类别':15} | {'胜':5} | {'负':5} | {'平':5} | {'总':6} | {'胜率':8} | {'评价'}")
    print("-" * 70)
    print(f"{'✅ 白名单信号':15} | {wl_win:5} | {wl_loss:5} | {wl_neutral:5} | "
          f"{wl_total:6} | {wl_rate*100:6.1f}% | {get_marker(wl_rate)}")
    print(f"{'❌ 非白名单信号':15} | {non_wl_win:5} | {non_wl_loss:5} | {non_wl_neutral:5} | "
          f"{non_wl_total:6} | {non_wl_rate*100:6.1f}% | {get_marker(non_wl_rate)}")
    
    # 效果评估
    improvement = (wl_rate - non_wl_rate) * 100
    print(f"\n白名单过滤效果: {'+' if improvement > 0 else ''}{improvement:.1f}% 胜率提升")
    
    if improvement > 10:
        print("评估结论: ✅ 白名单过滤效果显著")
    elif improvement > 0:
        print("评估结论: 👍 白名单过滤有正面效果")
    else:
        print("评估结论: ⚠️ 白名单需要重新校准")


def print_stoploss_analysis(cursor, time_filter: str = ""):
    """
    止损止盈策略分析
    
    分析使用止损止盈后的实际表现：
    1. 止损触发率：多少信号触发了止损
    2. 止盈触发率：多少信号触发了止盈
    3. 实际盈亏比：实际的盈亏比与预设的对比
    4. 按币种和市场环境细分分析
    5. 最优止损止盈点位建议
    """
    print(f"\n📊 止损止盈策略分析")
    print("=" * 85)
    
    # 获取带止损止盈的信号
    base_query = """
        SELECT r1.symbol, r1.recommended_action, r1.price, r1.created_at, r1.full_json,
               r1.recommended_confidence, r1.short_term_regime
        FROM l1_dual_advisory_results r1
        WHERE r1.recommended_action IN ('long', 'short')
        AND r1.price IS NOT NULL AND r1.price > 0
    """
    if time_filter:
        base_query += f" {time_filter.replace('WHERE', 'AND')}"
    
    cursor.execute(base_query)
    signals = cursor.fetchall()
    
    # 统计变量
    total_with_sl = 0
    sl_hit = 0  # 止损触发
    tp_hit = 0  # 止盈触发
    neither_hit = 0  # 都未触发
    total_profit = 0.0
    total_loss = 0.0
    win_count = 0
    loss_count = 0
    
    # 不同止损比例的统计
    sl_pct_stats = defaultdict(lambda: {'hit': 0, 'total': 0})
    
    # 按币种统计
    symbol_stats = defaultdict(lambda: {'sl_hit': 0, 'tp_hit': 0, 'neither': 0, 'total': 0})
    
    # 按市场环境统计
    regime_stats = defaultdict(lambda: {'sl_hit': 0, 'tp_hit': 0, 'neither': 0, 'total': 0})
    
    # 按置信度统计
    conf_stats = defaultdict(lambda: {'sl_hit': 0, 'tp_hit': 0, 'neither': 0, 'total': 0})
    
    # 详细信号记录（用于触发顺序分析）
    detailed_results = []
    
    for symbol, action, entry_price, created_at, full_json, confidence, regime in signals:
        data = json.loads(full_json)
        sl_target = data.get('stop_loss_target')
        
        if not sl_target:
            continue
        
        total_with_sl += 1
        
        sl_price = sl_target.get('stop_loss_price', 0)
        tp_price = sl_target.get('take_profit_price', 0)
        # 存储的是百分比值（如1.18表示1.18%），需要转换为小数形式（0.0118）
        sl_pct = sl_target.get('stop_loss_pct', 0) / 100
        tp_pct = sl_target.get('take_profit_pct', 0) / 100
        
        if not sl_price or not tp_price:
            continue
        
        # 查询验证窗口内的价格序列（用于判断触发顺序）
        cursor.execute('''
            SELECT price, created_at 
            FROM l1_dual_advisory_results 
            WHERE symbol = ? 
            AND created_at > ?
            AND created_at < datetime(?, '+60 minutes')
            AND price IS NOT NULL AND price > 0
            ORDER BY created_at ASC
        ''', (symbol, created_at, created_at))
        
        price_sequence = cursor.fetchall()
        if not price_sequence:
            continue
        
        # 判断止损止盈触发顺序
        hit_sl = False
        hit_tp = False
        hit_first = None
        
        for price_data, _ in price_sequence:
            if action == 'long':
                # LONG: 止损在下方，止盈在上方
                if not hit_sl and price_data <= sl_price:
                    hit_sl = True
                    if hit_first is None:
                        hit_first = 'sl'
                if not hit_tp and price_data >= tp_price:
                    hit_tp = True
                    if hit_first is None:
                        hit_first = 'tp'
            else:
                # SHORT: 止损在上方，止盈在下方
                if not hit_sl and price_data >= sl_price:
                    hit_sl = True
                    if hit_first is None:
                        hit_first = 'sl'
                if not hit_tp and price_data <= tp_price:
                    hit_tp = True
                    if hit_first is None:
                        hit_first = 'tp'
            
            # 都触发了，以先触发的为准
            if hit_sl and hit_tp:
                break
        
        # 根据先触发的确定结果
        result = None
        if hit_first == 'sl':
            sl_hit += 1
            loss_count += 1
            total_loss += sl_pct
            result = 'loss'
        elif hit_first == 'tp':
            tp_hit += 1
            win_count += 1
            total_profit += tp_pct
            result = 'win'
        else:
            neither_hit += 1
            result = 'pending'
        
        # 更新分组统计
        symbol_stats[symbol]['total'] += 1
        regime_stats[regime or 'unknown']['total'] += 1
        conf_stats[confidence or 'unknown']['total'] += 1
        
        if result == 'loss':
            symbol_stats[symbol]['sl_hit'] += 1
            regime_stats[regime or 'unknown']['sl_hit'] += 1
            conf_stats[confidence or 'unknown']['sl_hit'] += 1
        elif result == 'win':
            symbol_stats[symbol]['tp_hit'] += 1
            regime_stats[regime or 'unknown']['tp_hit'] += 1
            conf_stats[confidence or 'unknown']['tp_hit'] += 1
        else:
            symbol_stats[symbol]['neither'] += 1
            regime_stats[regime or 'unknown']['neither'] += 1
            conf_stats[confidence or 'unknown']['neither'] += 1
        
        # 按止损比例分组统计
        sl_pct_bucket = round(sl_pct * 100, 1)  # 转为百分比
        sl_pct_stats[sl_pct_bucket]['total'] += 1
        if result == 'loss':
            sl_pct_stats[sl_pct_bucket]['hit'] += 1
        
        # 记录详细结果
        detailed_results.append({
            'symbol': symbol,
            'action': action,
            'confidence': confidence,
            'regime': regime,
            'result': result,
            'sl_pct': sl_pct,
            'tp_pct': tp_pct
        })
    
    if total_with_sl == 0:
        print("（尚无带止损止盈的信号数据）")
        print("提示：止损止盈功能刚部署，需要等待新信号产生后才能分析")
        return {'total': 0}
    
    # 计算统计指标
    sl_hit_rate = sl_hit / total_with_sl if total_with_sl > 0 else 0
    tp_hit_rate = tp_hit / total_with_sl if total_with_sl > 0 else 0
    neither_rate = neither_hit / total_with_sl if total_with_sl > 0 else 0
    
    avg_profit = total_profit / win_count if win_count > 0 else 0
    avg_loss = total_loss / loss_count if loss_count > 0 else 0
    actual_rr = avg_profit / avg_loss if avg_loss > 0 else float('inf')
    
    win_rate = win_count / (win_count + loss_count) if (win_count + loss_count) > 0 else 0
    
    print(f"\n📈 止损止盈触发统计（1小时验证窗口，按触发顺序判定）")
    print(f"  带止损止盈的信号: {total_with_sl}条")
    print(f"  止损触发（亏损）: {sl_hit}条 ({sl_hit_rate*100:.1f}%)")
    print(f"  止盈触发（盈利）: {tp_hit}条 ({tp_hit_rate*100:.1f}%)")
    print(f"  未触发（持仓中）: {neither_hit}条 ({neither_rate*100:.1f}%)")
    
    print(f"\n📊 策略表现（使用止损止盈）")
    print(f"  胜率: {win_rate*100:.1f}% ({win_count}胜 / {loss_count}负)")
    print(f"  平均盈利: {avg_profit*100:.2f}%")
    print(f"  平均亏损: {avg_loss*100:.2f}%")
    print(f"  实际盈亏比: {actual_rr:.2f}:1")
    
    # 期望收益计算
    expected_return = (win_rate * avg_profit - (1 - win_rate) * avg_loss) * 100
    print(f"  期望收益: {expected_return:+.3f}% 每笔交易")
    
    # 按置信度分析
    print(f"\n📊 按置信度分析止损止盈效果")
    print(f"{'置信度':10} | {'总数':5} | {'止盈':5} | {'止损':5} | {'未触发':5} | {'胜率':8} | {'评价'}")
    print("-" * 65)
    
    for conf in ['ultra', 'high', 'medium', 'low']:
        s = conf_stats.get(conf, {'total': 0, 'tp_hit': 0, 'sl_hit': 0, 'neither': 0})
        if s['total'] > 0:
            decided = s['tp_hit'] + s['sl_hit']
            wr = s['tp_hit'] / decided if decided > 0 else 0
            marker = get_marker(wr)
            print(f"{conf:10} | {s['total']:5} | {s['tp_hit']:5} | {s['sl_hit']:5} | {s['neither']:5} | {wr*100:6.1f}% | {marker}")
    
    # 按市场环境分析
    print(f"\n📊 按市场环境分析止损止盈效果")
    print(f"{'环境':10} | {'总数':5} | {'止盈':5} | {'止损':5} | {'未触发':5} | {'胜率':8} | {'评价'}")
    print("-" * 65)
    
    for regime in ['trend', 'range', 'extreme']:
        s = regime_stats.get(regime, {'total': 0, 'tp_hit': 0, 'sl_hit': 0, 'neither': 0})
        if s['total'] > 0:
            decided = s['tp_hit'] + s['sl_hit']
            wr = s['tp_hit'] / decided if decided > 0 else 0
            marker = get_marker(wr)
            print(f"{regime:10} | {s['total']:5} | {s['tp_hit']:5} | {s['sl_hit']:5} | {s['neither']:5} | {wr*100:6.1f}% | {marker}")
    
    # 按币种分析
    print(f"\n📊 按币种分析止损止盈效果")
    print(f"{'币种':10} | {'总数':5} | {'止盈':5} | {'止损':5} | {'未触发':5} | {'胜率':8} | {'评价'}")
    print("-" * 65)
    
    sorted_symbols = sorted(symbol_stats.items(), key=lambda x: x[1]['total'], reverse=True)
    for symbol, s in sorted_symbols:
        if s['total'] >= 3:  # 至少3个样本
            decided = s['tp_hit'] + s['sl_hit']
            wr = s['tp_hit'] / decided if decided > 0 else 0
            marker = get_marker(wr)
            print(f"{symbol:10} | {s['total']:5} | {s['tp_hit']:5} | {s['sl_hit']:5} | {s['neither']:5} | {wr*100:6.1f}% | {marker}")
    
    # 止损比例分析
    if sl_pct_stats:
        print(f"\n📋 止损比例分析")
        print(f"{'止损%':8} | {'信号数':6} | {'触发数':6} | {'触发率':8} | {'建议'}")
        print("-" * 50)
        
        for sl_pct in sorted(sl_pct_stats.keys()):
            stats = sl_pct_stats[sl_pct]
            hit_rate = stats['hit'] / stats['total'] if stats['total'] > 0 else 0
            
            if hit_rate < 0.2:
                suggestion = "✅ 合适"
            elif hit_rate < 0.4:
                suggestion = "👍 可接受"
            else:
                suggestion = "⚠️ 过紧"
            
            print(f"{sl_pct:6.1f}% | {stats['total']:6} | {stats['hit']:6} | {hit_rate*100:6.1f}% | {suggestion}")
    
    # 优化建议
    print(f"\n💡 止损止盈优化建议")
    
    if sl_hit_rate > 0.5:
        print("  ⚠️ 止损触发率过高(>50%)，建议：")
        print("     - 适当放宽止损比例（如1.5% → 2%）")
        print("     - 检查入场时机是否过早")
    elif sl_hit_rate < 0.2:
        print("  ✅ 止损触发率正常(<20%)")
    
    if tp_hit_rate < 0.3:
        print("  ⚠️ 止盈触发率较低(<30%)，建议：")
        print("     - 适当降低止盈比例")
        print("     - 或使用移动止盈策略")
    elif tp_hit_rate > 0.6:
        print("  ✅ 止盈触发率良好(>60%)")
    
    if actual_rr < 1.5:
        print("  ⚠️ 实际盈亏比偏低(<1.5)，建议：")
        print("     - 提高止盈/止损比例")
        print("     - 只在高胜率场景开仓")
    
    # 返回分析结果供后续使用
    return {
        'total': total_with_sl,
        'win_rate': win_rate,
        'avg_profit': avg_profit,
        'avg_loss': avg_loss,
        'expected_return': expected_return,
        'sl_hit_rate': sl_hit_rate,
        'tp_hit_rate': tp_hit_rate,
        'symbol_stats': dict(symbol_stats),
        'regime_stats': dict(regime_stats),
        'conf_stats': dict(conf_stats)
    }


def print_stoploss_optimization(cursor, time_filter: str = ""):
    """
    止损止盈参数优化分析
    
    通过历史数据回测不同止损止盈比例的效果
    """
    print(f"\n📊 止损止盈参数优化")
    print("=" * 85)
    
    # 获取所有信号
    base_query = """
        SELECT r1.symbol, r1.recommended_action, r1.price, r1.created_at, r1.short_term_regime,
               r1.recommended_confidence
        FROM l1_dual_advisory_results r1
        WHERE r1.recommended_action IN ('long', 'short')
        AND r1.recommended_confidence IN ('ultra', 'high')
        AND r1.price IS NOT NULL AND r1.price > 0
    """
    if time_filter:
        base_query += f" {time_filter.replace('WHERE', 'AND')}"
    
    cursor.execute(base_query)
    signals = cursor.fetchall()
    
    if not signals:
        print("（无足够数据进行优化分析）")
        return None
    
    # 预先获取所有信号的价格序列
    print(f"\n正在分析{len(signals)}条HIGH/ULTRA信号...")
    signal_prices = {}
    
    for symbol, action, entry_price, created_at, regime, conf in signals:
        key = (symbol, created_at)
        cursor.execute('''
            SELECT price, created_at 
            FROM l1_dual_advisory_results 
            WHERE symbol = ? 
            AND created_at > ?
            AND created_at < datetime(?, '+60 minutes')
            AND price IS NOT NULL AND price > 0
            ORDER BY created_at ASC
        ''', (symbol, created_at, created_at))
        signal_prices[key] = cursor.fetchall()
    
    # 测试不同止损止盈比例 - 更细粒度的搜索
    sl_ratios = [0.008, 0.01, 0.012, 0.015, 0.018, 0.02, 0.025, 0.03]  # 0.8% ~ 3%
    rr_ratios = [1.0, 1.5, 2.0, 2.5, 3.0]  # 盈亏比
    
    print(f"\n验证窗口：1小时，按触发顺序判定")
    print(f"\n{'止损%':6} | {'盈亏比':6} | {'止盈%':6} | {'胜':5} | {'负':5} | {'未决':5} | {'胜率':8} | {'期望收益':10} | {'评价'}")
    print("-" * 90)
    
    best_params = None
    best_expected = -float('inf')
    all_results = []
    
    for sl_pct in sl_ratios:
        for rr in rr_ratios:
            tp_pct = sl_pct * rr
            
            wins = 0
            losses = 0
            pending = 0
            
            for symbol, action, entry_price, created_at, regime, conf in signals:
                key = (symbol, created_at)
                price_sequence = signal_prices.get(key, [])
                
                if not price_sequence:
                    continue
                
                # 计算止损止盈价
                if action == 'long':
                    sl_price = entry_price * (1 - sl_pct)
                    tp_price = entry_price * (1 + tp_pct)
                else:
                    sl_price = entry_price * (1 + sl_pct)
                    tp_price = entry_price * (1 - tp_pct)
                
                # 按时间顺序判断触发
                hit_first = None
                for price_data, _ in price_sequence:
                    if action == 'long':
                        if price_data <= sl_price:
                            hit_first = 'sl'
                            break
                        if price_data >= tp_price:
                            hit_first = 'tp'
                            break
                    else:
                        if price_data >= sl_price:
                            hit_first = 'sl'
                            break
                        if price_data <= tp_price:
                            hit_first = 'tp'
                            break
                
                if hit_first == 'tp':
                    wins += 1
                elif hit_first == 'sl':
                    losses += 1
                else:
                    pending += 1
            
            total = wins + losses
            if total == 0:
                continue
            
            win_rate = wins / total
            expected = win_rate * tp_pct - (1 - win_rate) * sl_pct
            
            result = {
                'sl_pct': sl_pct,
                'rr': rr,
                'tp_pct': tp_pct,
                'wins': wins,
                'losses': losses,
                'pending': pending,
                'total': total,
                'win_rate': win_rate,
                'expected': expected
            }
            all_results.append(result)
            
            if expected > best_expected:
                best_expected = expected
                best_params = result
            
            marker = get_marker(win_rate)
            print(f"{sl_pct*100:5.1f}% | {rr:6.1f} | {tp_pct*100:5.1f}% | {wins:5} | {losses:5} | {pending:5} | {win_rate*100:6.1f}% | {expected*100:+8.3f}% | {marker}")
    
    # 按市场环境分析最优参数
    print(f"\n📊 按市场环境分析最优参数")
    print("=" * 85)
    
    for target_regime in ['trend', 'range', 'extreme']:
        regime_signals = [(s, a, p, c, r, cf) for s, a, p, c, r, cf in signals if r == target_regime]
        
        if len(regime_signals) < 5:
            print(f"\n{target_regime.upper()}: 数据不足（{len(regime_signals)}条）")
            continue
        
        regime_best = None
        regime_best_exp = -float('inf')
        
        for sl_pct in [0.01, 0.015, 0.02]:
            for rr in [1.5, 2.0, 2.5]:
                tp_pct = sl_pct * rr
                wins = 0
                losses = 0
                
                for symbol, action, entry_price, created_at, regime, conf in regime_signals:
                    key = (symbol, created_at)
                    price_sequence = signal_prices.get(key, [])
                    
                    if not price_sequence:
                        continue
                    
                    if action == 'long':
                        sl_price = entry_price * (1 - sl_pct)
                        tp_price = entry_price * (1 + tp_pct)
                    else:
                        sl_price = entry_price * (1 + sl_pct)
                        tp_price = entry_price * (1 - tp_pct)
                    
                    hit_first = None
                    for price_data, _ in price_sequence:
                        if action == 'long':
                            if price_data <= sl_price:
                                hit_first = 'sl'
                                break
                            if price_data >= tp_price:
                                hit_first = 'tp'
                                break
                        else:
                            if price_data >= sl_price:
                                hit_first = 'sl'
                                break
                            if price_data <= tp_price:
                                hit_first = 'tp'
                                break
                    
                    if hit_first == 'tp':
                        wins += 1
                    elif hit_first == 'sl':
                        losses += 1
                
                total = wins + losses
                if total < 3:
                    continue
                
                win_rate = wins / total
                expected = win_rate * tp_pct - (1 - win_rate) * sl_pct
                
                if expected > regime_best_exp:
                    regime_best_exp = expected
                    regime_best = {
                        'sl_pct': sl_pct,
                        'rr': rr,
                        'win_rate': win_rate,
                        'expected': expected,
                        'total': total
                    }
        
        if regime_best:
            print(f"\n{target_regime.upper()} 环境 ({len(regime_signals)}条信号):")
            print(f"  最优止损: {regime_best['sl_pct']*100:.1f}%")
            print(f"  最优盈亏比: {regime_best['rr']:.1f}:1")
            print(f"  预期胜率: {regime_best['win_rate']*100:.1f}%")
            print(f"  预期收益: {regime_best['expected']*100:+.3f}%/笔")
    
    # 最优参数汇总和配置建议
    if best_params:
        print(f"\n" + "=" * 85)
        print(f"🏆 全局最优参数组合")
        print("=" * 85)
        print(f"  止损: {best_params['sl_pct']*100:.1f}%")
        print(f"  止盈: {best_params['tp_pct']*100:.1f}% (盈亏比 {best_params['rr']:.1f}:1)")
        print(f"  测试样本: {best_params['total']}条")
        print(f"  预期胜率: {best_params['win_rate']*100:.1f}%")
        print(f"  预期收益: {best_params['expected']*100:+.3f}% 每笔")
        
        # 生成配置建议
        print(f"\n📝 推荐配置 (services/stop_loss_service.py):")
        print(f"""
CONFIG = {{
    'stop_loss_multiplier': 1.0,  # 基于波动率的倍数
    
    'take_profit_multiplier': {{
        'trend': {best_params['rr']:.1f},
        'range': {best_params['rr']:.1f},
        'extreme': 1.0,
    }},
    
    'min_stop_loss_pct': {best_params['sl_pct']:.3f},  # {best_params['sl_pct']*100:.1f}%
    'max_stop_loss_pct': {best_params['sl_pct']*1.5:.3f},  # {best_params['sl_pct']*150:.1f}%
    'default_volatility': {best_params['sl_pct']:.3f},
}}
""")
        
        return best_params
    
    return None


def main():
    parser = argparse.ArgumentParser(description='L1 Advisory 策略评价脚本')
    parser.add_argument('--db', default='/app/data/db/l1_advisory.db', help='数据库路径')
    parser.add_argument('--hours', type=int, default=0, help='只评估最近N小时的数据（0=全部）')
    parser.add_argument('--compare', type=str, default='', help='对比时间点（格式：YYYY-MM-DD HH:MM:SS）')
    parser.add_argument('--whitelist', action='store_true', help='包含白名单效果验证')
    parser.add_argument('--stoploss', action='store_true', help='包含止损止盈策略分析')
    parser.add_argument('--optimize', action='store_true', help='包含止损止盈参数优化')
    args = parser.parse_args()
    
    conn = sqlite3.connect(args.db)
    cursor = conn.cursor()
    
    try:
        if args.hours > 0:
            time_filter = f"WHERE created_at > datetime('now', '-{args.hours} hours')"
            time_desc = f"最近{args.hours}小时"
        else:
            time_filter = ""
            time_desc = "全部数据"
        
        print_evaluation_report(cursor, time_filter, time_desc)
        
        # 币种+方向组合评估（与白名单一致）
        print_symbol_direction_report(cursor, time_filter)
        
        # 白名单效果验证
        if args.whitelist:
            print_whitelist_validation(cursor, time_filter)
        
        # 如果指定了对比时间点
        if args.compare:
            print("\n" + "=" * 80)
            print(f"📊 时间对比分析 - 以 {args.compare} 为分界")
            print("=" * 80)
            
            # 分界前
            print(f"\n【分界前】")
            before_filter = f"WHERE created_at < '{args.compare}'"
            print_evaluation_report(cursor, before_filter, f"{args.compare} 之前")
            
            # 分界后
            print(f"\n【分界后】")
            after_filter = f"WHERE created_at >= '{args.compare}'"
            print_evaluation_report(cursor, after_filter, f"{args.compare} 之后")
        
        # 止损止盈分析（如果启用）
        sl_analysis = None
        sl_optimization = None
        if args.stoploss:
            sl_analysis = print_stoploss_analysis(cursor, time_filter)
        
        if args.optimize:
            sl_optimization = print_stoploss_optimization(cursor, time_filter)
        
        # 综合评价
        print("\n" + "=" * 80)
        print("📋 综合评价结论")
        print("=" * 80)
        
        # 核心指标
        stats_ultra = calculate_win_rate(cursor, "AND recommended_confidence = 'ultra'", ())
        stats_trend = calculate_win_rate(cursor, "AND short_term_regime = 'trend'", ())
        stats_long = calculate_win_rate(cursor, "AND recommended_action = 'long'", ())
        stats_short = calculate_win_rate(cursor, "AND recommended_action = 'short'", ())
        
        # ULTRA + TREND 核心组合
        stats_core = calculate_win_rate(
            cursor, 
            "AND recommended_confidence = 'ultra' AND short_term_regime = 'trend'", 
            ()
        )
        
        print(f"""
📊 传统胜率指标（30分钟后价格变化）:
1. ULTRA信号胜率: {stats_ultra['win_rate']*100:.1f}% ({stats_ultra['total']}条) {get_marker(stats_ultra['win_rate'])}
2. TREND环境胜率: {stats_trend['win_rate']*100:.1f}% ({stats_trend['total']}条) {get_marker(stats_trend['win_rate'])}
3. LONG信号胜率: {stats_long['win_rate']*100:.1f}% ({stats_long['total']}条) {get_marker(stats_long['win_rate'])}
4. SHORT信号胜率: {stats_short['win_rate']*100:.1f}% ({stats_short['total']}条) {get_marker(stats_short['win_rate'])}
5. ULTRA+TREND胜率: {stats_core['win_rate']*100:.1f}% ({stats_core['total']}条) {get_marker(stats_core['win_rate'])} ⭐核心指标""")
        
        # 如果有止损止盈分析，输出更完整的评估
        if sl_analysis and sl_analysis.get('total', 0) > 0:
            print(f"""
📊 止损止盈策略指标（1小时验证窗口）:
- 使用止损止盈的信号: {sl_analysis['total']}条
- 策略胜率: {sl_analysis['win_rate']*100:.1f}% {get_marker(sl_analysis['win_rate'])}
- 平均盈利: {sl_analysis['avg_profit']*100:.2f}%
- 平均亏损: {sl_analysis['avg_loss']*100:.2f}%
- 期望收益: {sl_analysis['expected_return']:+.3f}%/笔
- 止损触发率: {sl_analysis['sl_hit_rate']*100:.1f}%
- 止盈触发率: {sl_analysis['tp_hit_rate']*100:.1f}%""")
        
        if sl_optimization:
            print(f"""
📊 优化后止损止盈参数:
- 最优止损: {sl_optimization['sl_pct']*100:.1f}%
- 最优止盈: {sl_optimization['tp_pct']*100:.1f}% (盈亏比 {sl_optimization['rr']:.1f}:1)
- 优化后胜率: {sl_optimization['win_rate']*100:.1f}%
- 优化后期望收益: {sl_optimization['expected']*100:+.3f}%/笔""")
        
        print(f"""
优化建议:
- 胜率 >= 70%: 保持当前策略
- 胜率 55-70%: 可接受，考虑微调
- 胜率 45-55%: 需要优化
- 胜率 < 45%: 需要重大调整或禁用

白名单使用建议:
- 只执行白名单中的 ULTRA + TREND 信号
- 定期检查白名单效果（使用 --whitelist 参数）
- 根据最新数据调整白名单规则

止损止盈使用建议:
- 使用 --stoploss 参数分析止损止盈效果
- 使用 --optimize 参数寻找最优止损止盈比例
- 根据分析结果调整 services/stop_loss_service.py 中的配置
- 优先使用止损止盈的胜率和期望收益作为策略评价标准
        """)
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
