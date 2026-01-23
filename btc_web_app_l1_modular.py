"""
L1 Advisory Layer - Flask Web Application (模块化版本)

这是重构后的精简版本，将路由和服务逻辑拆分到独立模块：
- api/: API路由模块
- services/: 业务逻辑服务

原始版本 btc_web_app_l1.py 保持不变，确保向后兼容。
"""

from flask import Flask, jsonify, render_template
from flask_cors import CORS
from market_state_machine_l1 import L1AdvisoryEngine
from database import L1DatabaseModular  # 使用新模块化数据库
from binance_data_fetcher import get_fetcher
import logging
from datetime import datetime
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__)
CORS(app)

# 初始化核心组件
advisory_engine = L1AdvisoryEngine()
l1_db = L1DatabaseModular()  # 使用新模块化数据库
binance_fetcher = get_fetcher()

logger.info("Flask app (modular) initialized with L1 Advisory Engine")


# ========================================
# 配置加载
# ========================================

def load_monitored_symbols():
    """加载监控的交易对配置"""
    try:
        config = advisory_engine.config
        symbol_universe = config.get('symbol_universe', {})
        enabled_symbols = symbol_universe.get('enabled_symbols', ['BTC'])
        symbols = [f"{s}USDT" if not s.endswith('USDT') else s for s in enabled_symbols]
        
        return {
            'periodic_update': config.get('periodic_update', {
                'enabled': True, 
                'interval_minutes': 1, 
                'market_type': 'futures'
            }),
            'symbols': symbols,
            'data_retention': config.get('data_retention', {
                'keep_hours': 24,
                'cleanup_interval_hours': 6
            }),
            'error_handling': config.get('error_handling', {
                'max_retries': 3,
                'retry_delay_seconds': 5,
                'continue_on_error': True
            })
        }
    
    except Exception as e:
        logger.error(f"Error loading monitored symbols config: {e}")
        return {
            'periodic_update': {'enabled': True, 'interval_minutes': 1, 'market_type': 'futures'},
            'symbols': ['BTCUSDT'],
            'data_retention': {'keep_hours': 24, 'cleanup_interval_hours': 6},
            'error_handling': {'max_retries': 3, 'retry_delay_seconds': 5, 'continue_on_error': True}
        }


# ========================================
# 初始化服务
# ========================================

from services import SchedulerService, ConfigWatcherService

# 加载配置
monitored_config = load_monitored_symbols()

# 启动定时任务
scheduler_service = SchedulerService(advisory_engine, l1_db, binance_fetcher, monitored_config)
scheduler = scheduler_service.start()

# 启动配置监控
config_dir = os.path.join(os.path.dirname(__file__), 'config')
config_watcher = ConfigWatcherService(advisory_engine, config_dir)
config_observer = config_watcher.start()


# ========================================
# 注册API路由（模块化）
# ========================================

from api.dual_advisory_routes import init_routes as init_dual_routes
from api.history_routes import init_routes as init_history_routes
from api.config_routes import init_routes as init_config_routes
from api.market_routes import init_routes as init_market_routes

# 初始化所有路由（依赖注入）
dual_advisory_bp = init_dual_routes(advisory_engine, l1_db, binance_fetcher)
history_bp = init_history_routes(advisory_engine, l1_db)
config_bp = init_config_routes(advisory_engine)
market_bp = init_market_routes(advisory_engine)

# 注册蓝图
app.register_blueprint(dual_advisory_bp, url_prefix='/api/l1')
app.register_blueprint(history_bp, url_prefix='/api/l1')
app.register_blueprint(config_bp, url_prefix='/api/l1')
app.register_blueprint(market_bp, url_prefix='/api')

logger.info("✅ All API routes registered (modular)")


# ========================================
# Web页面路由
# ========================================

@app.route('/')
def index():
    """L1 Advisory主页 - 双周期决策页面"""
    return render_template('index_l1_dual.html')


@app.route('/dual')
def index_dual():
    """L1 Advisory双周期决策页面（别名）"""
    return render_template('index_l1_dual.html')


# ========================================
# 健康检查
# ========================================

@app.route('/health')
def health_check():
    """健康检查端点"""
    return jsonify({
        'status': 'healthy',
        'service': 'L1 Advisory Layer (Modular)',
        'timestamp': datetime.now().isoformat()
    })


# ========================================
# 错误处理
# ========================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'data': None,
        'message': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f'Internal server error: {error}')
    return jsonify({
        'success': False,
        'data': None,
        'message': 'Internal server error'
    }), 500


# ========================================
# 应用启动
# ========================================

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("L1 Advisory Layer - Flask Application (Modular Version)")
    logger.info("=" * 60)
    logger.info(f"Engine initialized with {len(advisory_engine.thresholds)} thresholds")
    logger.info(f"Database: {l1_db.db_path}")
    logger.info(f"Config watcher: {'Enabled' if config_observer else 'Disabled'}")
    logger.info(f"Scheduler: {'Enabled' if scheduler else 'Disabled'}")
    logger.info("=" * 60)
    
    try:
        app.run(
            host='0.0.0.0', 
            port=5001,
            debug=True
        )
    finally:
        # 应用关闭时停止服务
        if config_observer:
            config_watcher.stop()
        
        if scheduler:
            scheduler_service.stop()
