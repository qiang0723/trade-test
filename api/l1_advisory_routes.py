"""
L1 Advisory API Routes - 单周期决策路由
"""

from flask import Blueprint, jsonify, request
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

l1_advisory_bp = Blueprint('l1_advisory', __name__)


def init_routes(advisory_engine, l1_db, binance_fetcher):
    """
    初始化路由（依赖注入）
    
    Args:
        advisory_engine: L1AdvisoryEngine实例
        l1_db: L1Database实例
        binance_fetcher: BinanceDataFetcher实例
    """
    
    @l1_advisory_bp.route('/advisory/<symbol>')
    def get_advisory(symbol):
        """
        获取指定币种的最新L1决策
        
        GET /api/l1/advisory/BTC
        """
        try:
            logger.info(f"API request: /api/l1/advisory/{symbol}")
            
            # 0. 验证 symbol 有效性
            config = advisory_engine.config
            symbol_universe = config.get('symbol_universe', {})
            enabled_symbols = symbol_universe.get('enabled_symbols', [])
            
            if symbol not in enabled_symbols:
                logger.warning(f"Invalid symbol requested: {symbol}")
                return jsonify({
                    'success': False,
                    'data': None,
                    'message': f'Invalid symbol: {symbol}. Enabled symbols: {", ".join(enabled_symbols)}'
                }), 400
            
            # 1. 获取市场数据
            market_data_dict = binance_fetcher.fetch_market_data(symbol)
            
            if not market_data_dict:
                logger.warning(f"Failed to fetch market data for {symbol}")
                return jsonify({
                    'success': False,
                    'data': None,
                    'message': f'Failed to fetch market data for {symbol}'
                }), 404
            
            # 2. L1决策
            result = advisory_engine.on_new_tick(symbol, market_data_dict)
            
            # 3. 保存到数据库
            try:
                advisory_id = l1_db.save_advisory_result(symbol, result)
                if advisory_engine.last_pipeline_steps:
                    l1_db.save_pipeline_steps(advisory_id, symbol, advisory_engine.last_pipeline_steps)
            except Exception as e:
                logger.error(f"Error saving to database: {e}")
            
            # 4. 返回结果
            return jsonify({
                'success': True,
                'data': result.to_dict(),
                'message': None
            })
        
        except Exception as e:
            logger.error(f'Error in get_advisory: {str(e)}', exc_info=True)
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    @l1_advisory_bp.route('/pipeline/<symbol>')
    def get_pipeline_status(symbol):
        """
        获取决策管道状态（用于可视化）
        
        Query Parameters:
            advisory_id: (可选) 从数据库读取指定决策的steps
        """
        try:
            # 验证 symbol 有效性
            config = advisory_engine.config
            symbol_universe = config.get('symbol_universe', {})
            enabled_symbols = symbol_universe.get('enabled_symbols', [])
            
            if symbol not in enabled_symbols:
                logger.warning(f"Invalid symbol requested for pipeline: {symbol}")
                return jsonify({
                    'success': False,
                    'error': f'Invalid symbol: {symbol}. Enabled symbols: {", ".join(enabled_symbols)}'
                }), 400
            
            advisory_id = request.args.get('advisory_id', type=int)
            
            if advisory_id:
                steps = l1_db.get_pipeline_steps(advisory_id)
                source = 'database'
            else:
                steps = advisory_engine.last_pipeline_steps
                source = 'memory'
            
            if not steps:
                return jsonify({
                    'success': True,
                    'symbol': symbol,
                    'data': {
                        'steps': [],
                        'message': f'暂无管道执行记录 (source: {source})',
                        'timestamp': datetime.now().isoformat(),
                        'source': source
                    }
                })
            
            return jsonify({
                'success': True,
                'symbol': symbol,
                'data': {
                    'steps': steps,
                    'timestamp': datetime.now().isoformat(),
                    'source': source
                }
            })
        
        except Exception as e:
            logger.error(f"Error getting pipeline status: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
    
    return l1_advisory_bp
