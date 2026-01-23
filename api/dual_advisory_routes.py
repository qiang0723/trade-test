"""
Dual Advisory API Routes - 双周期决策路由
"""

from flask import Blueprint, jsonify
import logging

logger = logging.getLogger(__name__)

dual_advisory_bp = Blueprint('dual_advisory', __name__)


def init_routes(advisory_engine, l1_db, binance_fetcher):
    """
    初始化路由（依赖注入）
    
    Args:
        advisory_engine: L1AdvisoryEngine实例
        l1_db: L1Database实例
        binance_fetcher: BinanceDataFetcher实例
    """
    
    @dual_advisory_bp.route('/advisory-dual/<symbol>')
    def get_advisory_dual(symbol):
        """
        获取指定币种的双周期独立结论
        
        GET /api/l1/advisory-dual/BTC
        """
        try:
            logger.info(f"API request: /api/l1/advisory-dual/{symbol}")
            
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
            
            # 2. L1双周期决策
            result = advisory_engine.on_new_tick_dual(symbol, market_data_dict)
            
            # 2.5 保存到数据库
            try:
                l1_db.save_dual_advisory_result(symbol, result)
            except Exception as e:
                logger.warning(f"Failed to save dual advisory result to database: {e}")
            
            # 3. 返回结果
            return jsonify({
                'success': True,
                'data': result.to_dict(),
                'message': None
            })
        
        except Exception as e:
            logger.error(f'Error in get_advisory_dual: {str(e)}', exc_info=True)
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    return dual_advisory_bp
