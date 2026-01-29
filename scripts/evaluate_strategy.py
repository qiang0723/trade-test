#!/usr/bin/env python3
"""
L1 Advisory 策略评价脚本

通用评价方法框架：
1. 胜率评估：按多个维度计算胜率
2. 信号质量评估：分析信号分布和质量
3. 时间段对比：支持配置前后对比
4. 输出标准化报告

使用方法：
    docker exec l1-advisory-layer python3 /app/scripts/evaluate_strategy.py
    或
    python3 scripts/evaluate_strategy.py --db data/db/l1_advisory.db

评价指标：
- 胜率(Win Rate): 信号方向正确的比例
- 信号率(Signal Rate): 产生交易信号的比例
- 盈亏比(Profit Factor): 平均盈利/平均亏损
- 夏普比率(Sharpe Ratio): 风险调整后收益
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


def main():
    parser = argparse.ArgumentParser(description='L1 Advisory 策略评价脚本')
    parser.add_argument('--db', default='/app/data/db/l1_advisory.db', help='数据库路径')
    parser.add_argument('--hours', type=int, default=0, help='只评估最近N小时的数据（0=全部）')
    parser.add_argument('--compare', type=str, default='', help='对比时间点（格式：YYYY-MM-DD HH:MM:SS）')
    parser.add_argument('--whitelist', action='store_true', help='包含白名单效果验证')
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
关键指标:
1. ULTRA信号胜率: {stats_ultra['win_rate']*100:.1f}% ({stats_ultra['total']}条) {get_marker(stats_ultra['win_rate'])}
2. TREND环境胜率: {stats_trend['win_rate']*100:.1f}% ({stats_trend['total']}条) {get_marker(stats_trend['win_rate'])}
3. LONG信号胜率: {stats_long['win_rate']*100:.1f}% ({stats_long['total']}条) {get_marker(stats_long['win_rate'])}
4. SHORT信号胜率: {stats_short['win_rate']*100:.1f}% ({stats_short['total']}条) {get_marker(stats_short['win_rate'])}
5. ULTRA+TREND胜率: {stats_core['win_rate']*100:.1f}% ({stats_core['total']}条) {get_marker(stats_core['win_rate'])} ⭐核心指标

优化建议:
- 胜率 >= 70%: 保持当前策略
- 胜率 55-70%: 可接受，考虑微调
- 胜率 45-55%: 需要优化
- 胜率 < 45%: 需要重大调整或禁用

白名单使用建议:
- 只执行白名单中的 ULTRA + TREND 信号
- 定期检查白名单效果（使用 --whitelist 参数）
- 根据最新数据调整白名单规则
        """)
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
