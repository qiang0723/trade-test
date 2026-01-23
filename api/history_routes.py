"""
History API Routes - 历史查询路由
"""

from flask import Blueprint, jsonify, request
import logging

logger = logging.getLogger(__name__)

history_bp = Blueprint('history', __name__)


def init_routes(advisory_engine, l1_db):
    """
    初始化路由（依赖注入）
    
    Args:
        advisory_engine: L1AdvisoryEngine实例
        l1_db: L1Database实例
    """
    
    @history_bp.route('/history/<symbol>')
    def get_history(symbol):
        """
        获取历史决策
        
        GET /api/l1/history/BTC?hours=24&limit=1500
        
        Query Parameters:
        - hours: 回溯小时数（默认24）
        - limit: 返回条数（默认1500）
        """
        try:
            # 验证 symbol 有效性
            config = advisory_engine.config
            symbol_universe = config.get('symbol_universe', {})
            enabled_symbols = symbol_universe.get('enabled_symbols', [])
            
            if symbol not in enabled_symbols:
                logger.warning(f"Invalid symbol requested for history: {symbol}")
                return jsonify({
                    'success': False,
                    'data': None,
                    'message': f'Invalid symbol: {symbol}. Enabled symbols: {", ".join(enabled_symbols)}'
                }), 400
            
            hours = int(request.args.get('hours', 24))
            limit = int(request.args.get('limit', 1500))
            
            logger.info(f"API request: /api/l1/history/{symbol}?hours={hours}&limit={limit}")
            
            history = l1_db.get_history_advisory(symbol, hours, limit)
            
            return jsonify({
                'success': True,
                'data': history,
                'count': len(history),
                'message': None
            })
        
        except Exception as e:
            logger.error(f'Error in get_history: {str(e)}', exc_info=True)
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    @history_bp.route('/history-dual/<symbol>')
    def get_history_dual(symbol):
        """
        获取指定币种的双周期决策历史记录
        
        GET /api/l1/history-dual/BTC?hours=24&limit=1500
        """
        try:
            # 验证 symbol 有效性
            config = advisory_engine.config
            symbol_universe = config.get('symbol_universe', {})
            enabled_symbols = symbol_universe.get('enabled_symbols', [])
            
            if symbol not in enabled_symbols:
                logger.warning(f"Invalid symbol requested for dual history: {symbol}")
                return jsonify({
                    'success': False,
                    'data': None,
                    'message': f'Invalid symbol: {symbol}. Enabled symbols: {", ".join(enabled_symbols)}'
                }), 400
            
            hours = int(request.args.get('hours', 24))
            limit = int(request.args.get('limit', 1500))
            
            # 从数据库获取历史记录
            history = l1_db.get_dual_advisory_history(symbol, hours=hours, limit=limit)
            
            return jsonify({
                'success': True,
                'data': history,
                'message': None
            })
        
        except Exception as e:
            logger.error(f'Error in get_history_dual: {str(e)}', exc_info=True)
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    @history_bp.route('/stats/<symbol>')
    def get_stats(symbol):
        """
        获取决策统计信息
        
        GET /api/l1/stats/BTC?hours=24
        """
        try:
            # 验证 symbol 有效性
            config = advisory_engine.config
            symbol_universe = config.get('symbol_universe', {})
            enabled_symbols = symbol_universe.get('enabled_symbols', [])
            
            if symbol not in enabled_symbols:
                logger.warning(f"Invalid symbol requested for stats: {symbol}")
                return jsonify({
                    'success': False,
                    'data': None,
                    'message': f'Invalid symbol: {symbol}. Enabled symbols: {", ".join(enabled_symbols)}'
                }), 400
            
            hours = int(request.args.get('hours', 24))
            
            logger.info(f"API request: /api/l1/stats/{symbol}?hours={hours}")
            
            stats = l1_db.get_decision_stats(symbol, hours)
            
            return jsonify({
                'success': True,
                'data': stats,
                'message': None
            })
        
        except Exception as e:
            logger.error(f'Error in get_stats: {str(e)}', exc_info=True)
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    @history_bp.route('/stats-dual/<symbol>')
    def get_stats_dual(symbol):
        """
        获取指定币种的双周期决策统计信息
        
        GET /api/l1/stats-dual/BTC
        """
        try:
            # 验证 symbol 有效性
            config = advisory_engine.config
            symbol_universe = config.get('symbol_universe', {})
            enabled_symbols = symbol_universe.get('enabled_symbols', [])
            
            if symbol not in enabled_symbols:
                logger.warning(f"Invalid symbol requested for dual stats: {symbol}")
                return jsonify({
                    'success': False,
                    'data': None,
                    'message': f'Invalid symbol: {symbol}. Enabled symbols: {", ".join(enabled_symbols)}'
                }), 400
            
            # 从数据库获取统计信息
            stats = l1_db.get_dual_decision_stats(symbol)
            
            return jsonify({
                'success': True,
                'data': stats,
                'message': None
            })
        
        except Exception as e:
            logger.error(f'Error in get_stats_dual: {str(e)}', exc_info=True)
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    return history_bp
