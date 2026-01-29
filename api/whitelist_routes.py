"""
Whitelist API Routes - 白名单API路由

提供白名单相关的REST API：
- GET /api/whitelist - 获取白名单摘要
- GET /api/whitelist/check - 检查特定信号是否推荐
- POST /api/whitelist/refresh - 手动刷新白名单
"""

from flask import Blueprint, jsonify, request
import logging

logger = logging.getLogger(__name__)


def init_routes(l1_db):
    """
    初始化白名单路由
    
    Args:
        l1_db: L1DatabaseModular实例
        
    Returns:
        Flask Blueprint
    """
    bp = Blueprint('whitelist', __name__)
    
    # 延迟初始化白名单服务
    _whitelist_service = None
    
    def get_whitelist_service():
        nonlocal _whitelist_service
        if _whitelist_service is None:
            from services.whitelist_service import WhitelistService
            _whitelist_service = WhitelistService(l1_db)
        return _whitelist_service
    
    @bp.route('/whitelist', methods=['GET'])
    def get_whitelist():
        """
        获取白名单摘要
        
        Returns:
            白名单、黑名单、观察期列表及统计信息
        """
        try:
            service = get_whitelist_service()
            summary = service.get_whitelist_summary()
            
            return jsonify({
                'success': True,
                'data': summary,
                'message': None
            })
        except Exception as e:
            logger.error(f"Error getting whitelist: {e}")
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    @bp.route('/whitelist/check', methods=['GET'])
    def check_signal():
        """
        检查特定信号是否推荐执行
        
        Query params:
            symbol: 币种
            direction: 方向 (long/short)
            
        Returns:
            是否推荐及原因
        """
        try:
            symbol = request.args.get('symbol', '').upper()
            direction = request.args.get('direction', '').lower()
            
            if not symbol or not direction:
                return jsonify({
                    'success': False,
                    'data': None,
                    'message': 'Missing symbol or direction parameter'
                }), 400
            
            if direction not in ('long', 'short'):
                return jsonify({
                    'success': False,
                    'data': None,
                    'message': 'Direction must be long or short'
                }), 400
            
            service = get_whitelist_service()
            is_recommended, reason = service.is_signal_recommended(symbol, direction)
            
            # 获取详细状态
            status = l1_db.whitelist.get_status(symbol, direction)
            
            return jsonify({
                'success': True,
                'data': {
                    'symbol': symbol,
                    'direction': direction,
                    'is_recommended': is_recommended,
                    'reason': reason,
                    'details': status
                },
                'message': None
            })
        except Exception as e:
            logger.error(f"Error checking signal: {e}")
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    @bp.route('/whitelist/refresh', methods=['POST'])
    def refresh_whitelist():
        """
        手动刷新白名单
        
        触发重新计算所有币种+方向组合的胜率并更新白名单状态
        
        Returns:
            更新结果摘要
        """
        try:
            service = get_whitelist_service()
            result = service.update_whitelist()
            
            return jsonify({
                'success': True,
                'data': result,
                'message': f"白名单已更新，共{result['total_updated']}个组合"
            })
        except Exception as e:
            logger.error(f"Error refreshing whitelist: {e}")
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    @bp.route('/whitelist/history', methods=['GET'])
    def get_whitelist_history():
        """
        获取白名单变更历史
        
        Query params:
            symbol: 币种（可选）
            direction: 方向（可选）
            limit: 最大记录数（默认50）
            
        Returns:
            历史记录列表
        """
        try:
            symbol = request.args.get('symbol')
            direction = request.args.get('direction')
            limit = request.args.get('limit', 50, type=int)
            
            history = l1_db.whitelist.get_history(symbol, direction, limit)
            
            return jsonify({
                'success': True,
                'data': history,
                'message': None
            })
        except Exception as e:
            logger.error(f"Error getting whitelist history: {e}")
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    @bp.route('/whitelist/simple', methods=['GET'])
    def get_simple_whitelist():
        """
        获取简化的白名单（仅白名单中的记录）
        
        适合前端快速查询使用
        
        Returns:
            白名单列表 [{symbol, direction, win_rate}]
        """
        try:
            whitelist = l1_db.whitelist.get_whitelist_only()
            
            # 转换为更简单的格式
            simple_list = [
                {
                    'key': f"{item['symbol']}_{item['direction']}",
                    'symbol': item['symbol'],
                    'direction': item['direction'],
                    'win_rate': item['win_rate']
                }
                for item in whitelist
            ]
            
            return jsonify({
                'success': True,
                'data': simple_list,
                'message': None
            })
        except Exception as e:
            logger.error(f"Error getting simple whitelist: {e}")
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    return bp
