"""
Config API Routes - 配置管理路由
"""

from flask import Blueprint, jsonify, request
from models.reason_tags import REASON_TAG_EXPLANATIONS, get_reason_tag_category, ReasonTag
import logging

logger = logging.getLogger(__name__)

config_bp = Blueprint('config', __name__)


def init_routes(advisory_engine):
    """
    初始化路由（依赖注入）
    
    Args:
        advisory_engine: L1AdvisoryEngine实例
    """
    
    @config_bp.route('/thresholds', methods=['GET'])
    def get_thresholds():
        """
        获取当前阈值配置
        
        GET /api/l1/thresholds
        """
        try:
            return jsonify({
                'success': True,
                'data': advisory_engine.thresholds,
                'message': None
            })
        
        except Exception as e:
            logger.error(f'Error in get_thresholds: {str(e)}')
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    @config_bp.route('/thresholds', methods=['POST'])
    def update_thresholds():
        """
        更新阈值配置（需要管理员权限）
        
        POST /api/l1/thresholds
        Body: {"thresholds": {...}}
        """
        try:
            new_thresholds = request.json.get('thresholds')
            
            if not new_thresholds:
                return jsonify({
                    'success': False,
                    'data': None,
                    'message': 'Missing thresholds in request body'
                }), 400
            
            advisory_engine.update_thresholds(new_thresholds)
            
            return jsonify({
                'success': True,
                'data': None,
                'message': f'Thresholds updated: {len(new_thresholds)} items'
            })
        
        except Exception as e:
            logger.error(f'Error in update_thresholds: {str(e)}')
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 400
    
    @config_bp.route('/reason-tags/explain')
    def get_reason_tag_explanations_api():
        """
        获取所有reason_tags的中文解释
        
        GET /api/l1/reason-tags/explain
        """
        try:
            # 添加分类信息
            enriched_explanations = {}
            for tag_value, explanation in REASON_TAG_EXPLANATIONS.items():
                try:
                    tag = ReasonTag(tag_value)
                    category = get_reason_tag_category(tag)
                    enriched_explanations[tag_value] = {
                        'explanation': explanation,
                        'category': category
                    }
                except ValueError:
                    enriched_explanations[tag_value] = {
                        'explanation': explanation,
                        'category': 'info'
                    }
            
            return jsonify({
                'success': True,
                'data': enriched_explanations,
                'message': None
            })
        
        except Exception as e:
            logger.error(f'Error in get_reason_tag_explanations: {str(e)}')
            return jsonify({
                'success': False,
                'data': None,
                'message': str(e)
            }), 500
    
    return config_bp
