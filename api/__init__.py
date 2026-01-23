"""
API Routes - Flask路由模块

将原始btc_web_app_l1.py中的路由拆分为多个模块：
- l1_advisory_routes: L1决策API
- dual_advisory_routes: 双周期决策API
- history_routes: 历史查询API
- config_routes: 配置管理API
- market_routes: 市场信息API
"""

from flask import Blueprint

__all__ = [
    'register_all_routes',
]


def register_all_routes(app):
    """
    注册所有API路由到Flask app
    
    Args:
        app: Flask应用实例
    """
    from .l1_advisory_routes import l1_advisory_bp
    from .dual_advisory_routes import dual_advisory_bp
    from .history_routes import history_bp
    from .config_routes import config_bp
    from .market_routes import market_bp
    
    # 注册蓝图
    app.register_blueprint(l1_advisory_bp, url_prefix='/api/l1')
    app.register_blueprint(dual_advisory_bp, url_prefix='/api/l1')
    app.register_blueprint(history_bp, url_prefix='/api/l1')
    app.register_blueprint(config_bp, url_prefix='/api/l1')
    app.register_blueprint(market_bp, url_prefix='/api')
    
    return app
