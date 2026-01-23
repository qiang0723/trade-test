"""
Market API Routes - 市场信息路由
"""

from flask import Blueprint, jsonify
import logging

logger = logging.getLogger(__name__)

market_bp = Blueprint('market', __name__)


def init_routes(advisory_engine):
    """
    初始化路由（依赖注入）
    
    Args:
        advisory_engine: L1AdvisoryEngine实例
    """
    
    @market_bp.route('/markets')
    def get_markets():
        """
        获取可用市场信息
        
        Response:
        {
          "success": true,
          "data": {
            "symbols": ["BTC", "ETH", "BNB", "SOL", "XRP"],
            "default_symbol": "BTC",
            "markets": {...}
          }
        }
        """
        try:
            # 从配置读取币种列表
            config = advisory_engine.config
            symbol_universe = config.get('symbol_universe', {})
            enabled_symbols = symbol_universe.get('enabled_symbols', ['BTC'])
            default_symbol = symbol_universe.get('default_symbol', 'BTC')
            
            # 构造市场信息（L1只支持futures）
            markets = {}
            for symbol in enabled_symbols:
                markets[symbol] = {
                    'spot': False,      # L1只分析合约市场
                    'futures': True     # 合约市场
                }
            
            return jsonify({
                'success': True,
                'data': {
                    'symbols': enabled_symbols,
                    'default_symbol': default_symbol,
                    'markets': markets
                },
                'message': None
            })
        
        except Exception as e:
            logger.error(f'Error in get_markets: {str(e)}')
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    return market_bp
