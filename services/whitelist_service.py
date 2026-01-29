"""
Whitelist Service - 动态白名单服务

职责：
1. 基于历史数据计算各"币种+方向"组合的胜率
2. 根据规则自动更新白名单状态
3. 提供白名单查询接口

白名单规则：
- 胜率 >= 60% 且 样本数 >= 10 → 加入白名单
- 胜率 < 40% 且 样本数 >= 5 → 加入黑名单
- 连续3次失败 → 临时移出白名单
- 新币种 → 观察期（只记录不推荐）
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class WhitelistService:
    """动态白名单服务"""
    
    # 白名单规则配置
    CONFIG = {
        # 加入白名单的条件
        'whitelist_min_win_rate': 0.60,      # 最低胜率 60%
        'whitelist_min_samples': 10,          # 最少样本数 10
        
        # 加入黑名单的条件
        'blacklist_max_win_rate': 0.40,      # 低于 40% 进入黑名单
        'blacklist_min_samples': 5,           # 判定黑名单的最少样本数
        
        # 观察期配置
        'observation_min_samples': 5,         # 观察期最少样本数
        
        # 连续失败移出
        'max_consecutive_losses': 3,          # 连续失败次数
        
        # 回测窗口
        'lookback_hours': 24,                 # 回测数据窗口（小时）
        
        # 胜负判定阈值
        'win_threshold': 0.001,               # 盈利 > 0.1% 算赢
        'loss_threshold': -0.001,             # 亏损 < -0.1% 算输
        
        # 验证时间（信号后多少分钟验证结果）
        'verify_minutes': 30,                 # 30分钟后验证
    }
    
    def __init__(self, l1_db, config: Dict = None):
        """
        初始化白名单服务
        
        Args:
            l1_db: L1DatabaseModular实例
            config: 可选的配置覆盖
        """
        self.l1_db = l1_db
        self.config = {**self.CONFIG, **(config or {})}
        
        # 用于追踪连续失败
        self._consecutive_losses = defaultdict(int)
    
    def calculate_win_rates(self, lookback_hours: int = None) -> Dict[Tuple[str, str], Dict]:
        """
        计算所有"币种+方向"组合的胜率
        
        Args:
            lookback_hours: 回测窗口（小时），默认使用配置
            
        Returns:
            {(symbol, direction): stats_dict}
        """
        lookback = lookback_hours or self.config['lookback_hours']
        verify_minutes = self.config['verify_minutes']
        win_threshold = self.config['win_threshold']
        loss_threshold = self.config['loss_threshold']
        
        results = {}
        
        with self.l1_db.connection.connect() as conn:
            cursor = conn.cursor()
            
            # 获取所有ULTRA置信度+TREND环境的信号
            # 注意：数据库存储的是UTC时间，所以这里使用utcnow()
            cutoff_time = datetime.utcnow() - timedelta(hours=lookback)
            
            cursor.execute('''
                SELECT r1.symbol, r1.recommended_action, r1.price, r1.created_at,
                       r1.short_term_regime, r1.recommended_confidence
                FROM l1_dual_advisory_results r1
                WHERE r1.recommended_action IN ('long', 'short')
                AND r1.recommended_confidence = 'ultra'
                AND r1.short_term_regime = 'trend'
                AND r1.price IS NOT NULL AND r1.price > 0
                AND r1.created_at >= ?
                ORDER BY r1.symbol, r1.recommended_action
            ''', (cutoff_time.strftime('%Y-%m-%d %H:%M:%S'),))
            
            signals = cursor.fetchall()
            
            # 按币种+方向分组计算
            grouped = defaultdict(list)
            for row in signals:
                symbol, action, price, created_at, regime, confidence = row
                grouped[(symbol, action)].append({
                    'price': price,
                    'created_at': created_at,
                    'regime': regime,
                    'confidence': confidence
                })
            
            # 计算每个组合的胜率
            for (symbol, direction), signals_list in grouped.items():
                stats = self._calculate_stats_for_group(
                    cursor, symbol, direction, signals_list,
                    verify_minutes, win_threshold, loss_threshold
                )
                results[(symbol, direction)] = stats
        
        return results
    
    def _calculate_stats_for_group(
        self, cursor, symbol: str, direction: str, 
        signals: List[Dict], verify_minutes: int,
        win_threshold: float, loss_threshold: float
    ) -> Dict:
        """
        计算单个币种+方向组合的统计数据
        
        Args:
            cursor: 数据库游标
            symbol: 币种
            direction: 方向
            signals: 信号列表
            verify_minutes: 验证时间（分钟）
            win_threshold: 胜利阈值
            loss_threshold: 失败阈值
            
        Returns:
            统计数据字典
        """
        win_count = 0
        loss_count = 0
        total_profit = 0.0
        total_loss = 0.0
        last_signal_at = None
        
        for signal in signals:
            price = signal['price']
            created_at = signal['created_at']
            
            if not price or price <= 0:
                continue
            
            # 查找验证价格（30分钟后的价格）
            cursor.execute('''
                SELECT price FROM l1_dual_advisory_results 
                WHERE symbol = ? 
                AND created_at > datetime(?, '+25 minutes')
                AND created_at < datetime(?, '+35 minutes')
                AND price IS NOT NULL AND price > 0
                LIMIT 1
            ''', (symbol, created_at, created_at))
            
            future = cursor.fetchone()
            if not future or not future[0]:
                continue
            
            future_price = future[0]
            change = (future_price - price) / price
            
            # 根据方向判定胜负
            if direction == 'long':
                if change > win_threshold:
                    win_count += 1
                    total_profit += change
                elif change < loss_threshold:
                    loss_count += 1
                    total_loss += abs(change)
            else:  # short
                if change < loss_threshold:
                    win_count += 1
                    total_profit += abs(change)
                elif change > win_threshold:
                    loss_count += 1
                    total_loss += change
            
            last_signal_at = created_at
        
        total = win_count + loss_count
        win_rate = win_count / total if total > 0 else 0.0
        avg_profit = total_profit / win_count if win_count > 0 else 0.0
        avg_loss = total_loss / loss_count if loss_count > 0 else 0.0
        
        return {
            'symbol': symbol,
            'direction': direction,
            'total_signals': total,
            'win_count': win_count,
            'loss_count': loss_count,
            'win_rate': win_rate,
            'avg_profit': avg_profit * 100,  # 转为百分比
            'avg_loss': avg_loss * 100,      # 转为百分比
            'last_signal_at': last_signal_at
        }
    
    def update_whitelist(self, stats_by_combo: Dict[Tuple[str, str], Dict] = None) -> Dict:
        """
        根据最新统计数据更新白名单
        
        Args:
            stats_by_combo: 统计数据，如果不提供则重新计算
            
        Returns:
            更新结果摘要
        """
        if stats_by_combo is None:
            stats_by_combo = self.calculate_win_rates()
        
        updated = []
        added_to_whitelist = []
        removed_from_whitelist = []
        added_to_blacklist = []
        
        for (symbol, direction), stats in stats_by_combo.items():
            old_status = self.l1_db.whitelist.get_status(symbol, direction)
            was_in_whitelist = old_status['in_whitelist'] if old_status else False
            
            # 判定新状态
            new_status = self._determine_status(stats)
            stats['in_whitelist'] = new_status['in_whitelist']
            stats['status'] = new_status['status']
            
            # 更新数据库
            self.l1_db.whitelist.upsert(symbol, direction, stats)
            
            # 记录状态变化
            if was_in_whitelist and not new_status['in_whitelist']:
                removed_from_whitelist.append(f"{symbol} {direction.upper()}")
                self.l1_db.whitelist.record_history(
                    symbol, direction, stats,
                    f"移出白名单: 胜率{stats['win_rate']*100:.1f}%"
                )
            elif not was_in_whitelist and new_status['in_whitelist']:
                added_to_whitelist.append(f"{symbol} {direction.upper()}")
                self.l1_db.whitelist.record_history(
                    symbol, direction, stats,
                    f"加入白名单: 胜率{stats['win_rate']*100:.1f}%"
                )
            elif new_status['status'] == 'blacklist' and (not old_status or old_status['status'] != 'blacklist'):
                added_to_blacklist.append(f"{symbol} {direction.upper()}")
                self.l1_db.whitelist.record_history(
                    symbol, direction, stats,
                    f"加入黑名单: 胜率{stats['win_rate']*100:.1f}%"
                )
            
            updated.append({
                'symbol': symbol,
                'direction': direction,
                'win_rate': stats['win_rate'],
                'in_whitelist': new_status['in_whitelist'],
                'status': new_status['status']
            })
        
        # 记录日志
        logger.info(f"📋 白名单更新完成: {len(updated)}个组合")
        if added_to_whitelist:
            logger.info(f"  ✅ 新增白名单: {', '.join(added_to_whitelist)}")
        if removed_from_whitelist:
            logger.info(f"  ⚠️ 移出白名单: {', '.join(removed_from_whitelist)}")
        if added_to_blacklist:
            logger.info(f"  ❌ 新增黑名单: {', '.join(added_to_blacklist)}")
        
        return {
            'total_updated': len(updated),
            'added_to_whitelist': added_to_whitelist,
            'removed_from_whitelist': removed_from_whitelist,
            'added_to_blacklist': added_to_blacklist,
            'updated_at': datetime.now().isoformat()
        }
    
    def _determine_status(self, stats: Dict) -> Dict:
        """
        根据统计数据判定白名单状态
        
        Args:
            stats: 统计数据
            
        Returns:
            {'in_whitelist': bool, 'status': str}
        """
        total = stats['total_signals']
        win_rate = stats['win_rate']
        
        # 样本不足 → 观察期
        if total < self.config['observation_min_samples']:
            return {'in_whitelist': False, 'status': 'observation'}
        
        # 高胜率 → 白名单
        if (win_rate >= self.config['whitelist_min_win_rate'] and 
            total >= self.config['whitelist_min_samples']):
            return {'in_whitelist': True, 'status': 'whitelist'}
        
        # 低胜率 → 黑名单
        if (win_rate <= self.config['blacklist_max_win_rate'] and 
            total >= self.config['blacklist_min_samples']):
            return {'in_whitelist': False, 'status': 'blacklist'}
        
        # 中间状态 → 观察期
        return {'in_whitelist': False, 'status': 'observation'}
    
    def is_signal_recommended(self, symbol: str, direction: str) -> Tuple[bool, str]:
        """
        检查信号是否推荐执行
        
        Args:
            symbol: 币种
            direction: 方向
            
        Returns:
            (是否推荐, 原因)
        """
        status = self.l1_db.whitelist.get_status(symbol, direction)
        
        if not status:
            return False, "未知组合，需要更多数据"
        
        if status['in_whitelist']:
            return True, f"白名单信号，胜率{status['win_rate']*100:.1f}%"
        
        if status['status'] == 'blacklist':
            return False, f"黑名单信号，胜率{status['win_rate']*100:.1f}%"
        
        if status['status'] == 'observation':
            return False, f"观察期，样本数{status['total_signals']}"
        
        return False, "未知状态"
    
    def get_whitelist_summary(self) -> Dict:
        """
        获取白名单摘要
        
        Returns:
            白名单摘要信息
        """
        all_records = self.l1_db.whitelist.get_all()
        
        whitelist = [r for r in all_records if r['in_whitelist']]
        blacklist = [r for r in all_records if r['status'] == 'blacklist']
        observation = [r for r in all_records if r['status'] == 'observation']
        
        return {
            'whitelist': whitelist,
            'blacklist': blacklist,
            'observation': observation,
            'stats': {
                'whitelist_count': len(whitelist),
                'blacklist_count': len(blacklist),
                'observation_count': len(observation),
                'total': len(all_records)
            },
            'config': {
                'min_win_rate': self.config['whitelist_min_win_rate'],
                'min_samples': self.config['whitelist_min_samples'],
                'lookback_hours': self.config['lookback_hours']
            },
            'updated_at': datetime.now().isoformat()
        }
    
    def record_signal_result(self, symbol: str, direction: str, is_win: bool):
        """
        记录信号结果（用于连续失败追踪）
        
        Args:
            symbol: 币种
            direction: 方向
            is_win: 是否盈利
        """
        key = (symbol.upper(), direction.lower())
        
        if is_win:
            self._consecutive_losses[key] = 0
        else:
            self._consecutive_losses[key] += 1
            
            # 检查是否需要临时移出白名单
            if self._consecutive_losses[key] >= self.config['max_consecutive_losses']:
                status = self.l1_db.whitelist.get_status(symbol, direction)
                if status and status['in_whitelist']:
                    logger.warning(
                        f"⚠️ {symbol} {direction} 连续{self._consecutive_losses[key]}次失败，临时移出白名单"
                    )
                    stats = dict(status)
                    stats['in_whitelist'] = False
                    stats['status'] = 'suspended'
                    self.l1_db.whitelist.upsert(symbol, direction, stats)
                    self.l1_db.whitelist.record_history(
                        symbol, direction, stats,
                        f"连续{self._consecutive_losses[key]}次失败，临时暂停"
                    )
