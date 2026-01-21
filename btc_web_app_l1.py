"""
L1 Advisory Layer - Flask Web Application

Flask后端应用，提供：
1. L1 Advisory决策API
2. 历史决策查询
3. Web UI界面
4. 阈值配置管理
"""

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from market_state_machine_l1 import L1AdvisoryEngine
from database_l1 import L1Database
from models.reason_tags import REASON_TAG_EXPLANATIONS, get_reason_tag_category
from binance_data_fetcher import get_fetcher
import logging
from datetime import datetime
import yaml
import os

# ⚠️  修复：先配置日志，再使用logger（PR-M 建议A相关）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 可选：Watchdog文件监控（如果安装了）
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog not installed, config hot reload disabled. Install: pip install watchdog")

# 可选：APScheduler定时任务（如果安装了）
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("apscheduler not installed, auto cleanup disabled. Install: pip install apscheduler")

# 创建Flask应用
app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 初始化L1引擎、数据库和Binance数据获取器
advisory_engine = L1AdvisoryEngine()
l1_db = L1Database()
binance_fetcher = get_fetcher()

logger.info("Flask app initialized with L1 Advisory Engine and Binance Fetcher")


# ========================================
# 配置热更新（Watchdog）
# ========================================

class ConfigReloader(FileSystemEventHandler):
    """配置文件监控和热更新"""
    
    def __init__(self, engine: L1AdvisoryEngine):
        self.engine = engine
        self.config_path = os.path.join(
            os.path.dirname(__file__), 
            'config', 
            'l1_thresholds.yaml'
        )
    
    def on_modified(self, event):
        """文件修改时触发"""
        if not event.is_directory and event.src_path.endswith('l1_thresholds.yaml'):
            logger.info(f"Config file modified: {event.src_path}")
            self._reload_config()
    
    def _reload_config(self):
        """重载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                new_config = yaml.safe_load(f)
            
            # 扁平化阈值
            new_thresholds = self.engine._flatten_thresholds(new_config)
            
            # 更新引擎阈值
            self.engine.update_thresholds(new_thresholds)
            
            logger.info(f"✅ Config reloaded successfully: {len(new_thresholds)} thresholds updated")
            
        except Exception as e:
            logger.error(f"❌ Error reloading config: {e}", exc_info=True)


def start_config_watcher():
    """启动配置文件监控"""
    if not WATCHDOG_AVAILABLE:
        logger.warning("Watchdog not available, skipping config file watcher")
        return None
    
    try:
        config_dir = os.path.join(os.path.dirname(__file__), 'config')
        
        if not os.path.exists(config_dir):
            logger.warning(f"Config directory not found: {config_dir}")
            return None
        
        observer = Observer()
        event_handler = ConfigReloader(advisory_engine)
        observer.schedule(event_handler, config_dir, recursive=False)
        observer.start()
        
        logger.info(f"📁 Config file watcher started: {config_dir}")
        return observer
    
    except Exception as e:
        logger.error(f"Error starting config watcher: {e}")
        return None


# 启动配置监控
config_observer = start_config_watcher()


# ========================================
# 定时清理数据库（APScheduler）
# ========================================

def cleanup_old_records_job():
    """定时清理旧记录的任务（保留24小时）"""
    try:
        deleted = l1_db.cleanup_old_records(days=1)  # 只保留1天（24小时）
        logger.info(f"🗑️  Auto cleanup completed: {deleted} old records deleted")
    except Exception as e:
        logger.error(f"Error in auto cleanup job: {e}", exc_info=True)


def load_monitored_symbols():
    """加载监控的交易对配置"""
    try:
        config_path = os.path.join(
            os.path.dirname(__file__), 
            'config', 
            'monitored_symbols.yaml'
        )
        
        if not os.path.exists(config_path):
            logger.warning(f"Monitored symbols config not found: {config_path}, using default [BTCUSDT]")
            return {
                'periodic_update': {'enabled': True, 'interval_minutes': 1, 'market_type': 'futures'},
                'symbols': ['BTCUSDT']
            }
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        logger.info(f"Loaded monitored symbols config: {len(config.get('symbols', []))} symbols")
        return config
    
    except Exception as e:
        logger.error(f"Error loading monitored symbols config: {e}")
        return {
            'periodic_update': {'enabled': True, 'interval_minutes': 1, 'market_type': 'futures'},
            'symbols': ['BTCUSDT']
        }


def periodic_advisory_update():
    """
    定时更新任务：每分钟自动获取市场数据并生成决策
    
    这确保即使前端关闭，历史决策记录也会持续更新，不会出现数据缺失
    
    包含重试机制：利用配置中的 error_handling.max_retries 和 retry_delay_seconds
    """
    try:
        logger.info("⏰ Running periodic advisory update...")
        
        # 从配置文件加载监控的交易对和错误处理策略
        config = load_monitored_symbols()
        symbols = config.get('symbols', ['BTCUSDT'])
        market_type = config.get('periodic_update', {}).get('market_type', 'futures')
        
        # 读取重试配置
        error_config = config.get('error_handling', {})
        max_retries = error_config.get('max_retries', 3)
        retry_delay = error_config.get('retry_delay_seconds', 5)
        continue_on_error = error_config.get('continue_on_error', True)
        
        if not symbols:
            logger.warning("No symbols configured for monitoring")
            return
        
        for symbol in symbols:
            market_data = None
            last_error = None
            
            # 重试逻辑
            for attempt in range(max_retries):
                try:
                    # 1. 获取市场数据（带重试）
                    market_data = binance_fetcher.fetch_market_data(symbol, market_type=market_type)
                    
                    if market_data:
                        break  # 成功获取，跳出重试循环
                    else:
                        last_error = f"No market data returned for {symbol}"
                        if attempt < max_retries - 1:
                            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {symbol}, retrying in {retry_delay}s...")
                            import time
                            time.sleep(retry_delay)
                        
                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries - 1:
                        logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {symbol}: {e}, retrying in {retry_delay}s...")
                        import time
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"All {max_retries} attempts failed for {symbol}: {e}", exc_info=True)
            
            # 检查是否成功获取数据
            if not market_data:
                logger.error(f"❌ Failed to fetch {symbol} after {max_retries} attempts: {last_error}")
                if continue_on_error:
                    continue  # 继续处理下一个symbol
                else:
                    break  # 中断整个任务
            
            # 2. 生成L1决策
            try:
                result = advisory_engine.on_new_tick(symbol, market_data)
                
                # 3. 保存到数据库
                advisory_id = l1_db.save_advisory_result(symbol, result)
                
                # 4. 保存管道步骤
                if hasattr(advisory_engine, 'last_pipeline_steps'):
                    l1_db.save_pipeline_steps(advisory_id, symbol, advisory_engine.last_pipeline_steps)
                
                logger.info(
                    f"✅ Periodic update saved: {symbol} → {result.decision.value} "
                    f"(confidence: {result.confidence.value}, executable: {result.executable})"
                )
            
            except Exception as e:
                logger.error(f"Error processing decision for {symbol}: {e}", exc_info=True)
                if continue_on_error:
                    continue
                else:
                    break
        
    except Exception as e:
        logger.error(f"Error in periodic_advisory_update: {e}", exc_info=True)


def start_scheduler():
    """启动定时任务调度器"""
    if not APSCHEDULER_AVAILABLE:
        logger.warning("APScheduler not available, skipping auto cleanup and periodic updates")
        return None
    
    try:
        # 加载配置
        config = load_monitored_symbols()
        periodic_config = config.get('periodic_update', {})
        
        # 检查是否启用定时更新
        if not periodic_config.get('enabled', True):
            logger.warning("Periodic advisory update is disabled in config")
            return None
        
        scheduler = BackgroundScheduler()
        
        # 任务1: 定时自动获取决策并保存（核心功能）
        interval_minutes = periodic_config.get('interval_minutes', 1)
        scheduler.add_job(
            func=periodic_advisory_update,
            trigger='interval',
            minutes=interval_minutes,
            id='periodic_advisory',
            name=f'Periodic L1 advisory update (every {interval_minutes} minute(s))',
            max_instances=1,  # 防止并发执行
            next_run_time=None  # 立即执行第一次
        )
        
        # 任务2: 定期清理旧数据
        retention_config = config.get('data_retention', {})
        cleanup_interval = retention_config.get('cleanup_interval_hours', 6)
        scheduler.add_job(
            func=cleanup_old_records_job,
            trigger='cron',
            hour=f'*/{cleanup_interval}',
            minute=0,
            id='cleanup_old_records',
            name=f'Cleanup old L1 advisory records (every {cleanup_interval}h)'
        )
        
        scheduler.start()
        logger.info("⏰ Scheduler started:")
        logger.info(f"  - Periodic advisory update: Every {interval_minutes} minute(s)")
        logger.info(f"  - Cleanup old records: Every {cleanup_interval} hours")
        logger.info(f"  - Monitored symbols: {config.get('symbols', [])}")
        
        return scheduler
    
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}")
        return None


# 启动定时任务
scheduler = start_scheduler()


# ========================================
# Web页面路由
# ========================================

@app.route('/')
def index():
    """L1 Advisory主页"""
    return render_template('index_l1.html')


# ========================================
# API路由 - L1 Advisory
# ========================================

@app.route('/api/l1/advisory/<symbol>')
def get_advisory(symbol):
    """
    获取指定币种的最新L1决策
    
    GET /api/l1/advisory/BTC
    
    Response:
    {
      "success": true,
      "data": {
        "decision": "long",
        "confidence": "high",
        "market_regime": "trend",
        "system_state": "long_active",
        "risk_exposure_allowed": true,
        "trade_quality": "good",
        "reason_tags": ["strong_buy_pressure", "oi_growing"],
        "timestamp": "2026-01-20T15:30:45.123456"
      }
    }
    """
    try:
        logger.info(f"API request: /api/l1/advisory/{symbol}")
        
        # 1. 获取市场数据
        market_data_dict = fetch_market_data(symbol)
        
        if not market_data_dict:
            logger.warning(f"Failed to fetch market data for {symbol}")
            return jsonify({
                'success': False,
                'data': None,
                'message': f'Failed to fetch market data for {symbol}'
            }), 404
        
        # 2. L1决策
        result = advisory_engine.on_new_tick(symbol, market_data_dict)
        
        # 3. 保存到数据库（包含pipeline steps，PR-007）
        try:
            advisory_id = l1_db.save_advisory_result(symbol, result)
            # PR-007: 保存pipeline执行步骤
            if advisory_engine.last_pipeline_steps:
                l1_db.save_pipeline_steps(advisory_id, symbol, advisory_engine.last_pipeline_steps)
        except Exception as e:
            logger.error(f"Error saving to database: {e}")
            # 不影响API返回
        
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


@app.route('/api/l1/history/<symbol>')
def get_history(symbol):
    """
    获取历史决策
    
    GET /api/l1/history/BTC?hours=24&limit=1500
    
    Query Parameters:
    - hours: 回溯小时数（默认24）
    - limit: 返回条数（默认1500，按1分钟一次，24小时约1440次）
    
    Response:
    {
      "success": true,
      "data": [
        {
          "decision": "long",
          "confidence": "high",
          "timestamp": "2026-01-20T15:30:45",
          "reason_tags": ["..."],
          ...
        },
        ...
      ]
    }
    """
    try:
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


@app.route('/api/l1/stats/<symbol>')
def get_stats(symbol):
    """
    获取决策统计信息
    
    GET /api/l1/stats/BTC?hours=24
    
    Response:
    {
      "success": true,
      "data": {
        "total": 100,
        "long": 30,
        "short": 20,
        "no_trade": 50,
        "high_confidence": 15,
        ...
      }
    }
    """
    try:
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


@app.route('/api/l1/pipeline/<symbol>')
def get_pipeline_status(symbol):
    """
    获取决策管道状态（用于可视化）
    
    PR-007: 支持从数据库读取历史pipeline steps
    
    Args:
        symbol: 币种符号
    
    Query Parameters:
        advisory_id: (可选) 从数据库读取指定决策的steps
    
    Returns:
        JSON: 管道步骤详情
    """
    try:
        advisory_id = request.args.get('advisory_id', type=int)
        
        if advisory_id:
            # PR-007: 从数据库读取历史steps
            steps = l1_db.get_pipeline_steps(advisory_id)
            source = 'database'
        else:
            # 获取最后一次管道执行的步骤记录（内存）
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


@app.route('/api/l1/reason-tags/explain')
def get_reason_tag_explanations_api():
    """
    获取所有reason_tags的中文解释
    
    GET /api/l1/reason-tags/explain
    
    Response:
    {
      "success": true,
      "data": {
        "extreme_regime": "极端行情：价格波动超过阈值",
        "crowding_risk": "拥挤风险：资金费率极端且持仓量快速增长",
        ...
      }
    }
    """
    try:
        # 添加分类信息
        enriched_explanations = {}
        for tag_value, explanation in REASON_TAG_EXPLANATIONS.items():
            from models.reason_tags import ReasonTag
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


@app.route('/api/l1/thresholds', methods=['GET'])
def get_thresholds():
    """
    获取当前阈值配置
    
    GET /api/l1/thresholds
    
    Response:
    {
      "success": true,
      "data": {
        "extreme_price_change_1h": 5.0,
        "trend_price_change_6h": 3.0,
        ...
      }
    }
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


@app.route('/api/l1/thresholds', methods=['POST'])
def update_thresholds():
    """
    更新阈值配置（需要管理员权限）
    
    POST /api/l1/thresholds
    Body:
    {
      "thresholds": {
        "extreme_price_change_1h": 6.0,
        ...
      }
    }
    
    TODO: 添加身份验证
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
        
        # TODO: 保存到配置文件
        
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


# ========================================
# API路由 - 市场数据（代理现有API）
# ========================================

@app.route('/api/markets')
def get_markets():
    """
    获取可用市场信息（PR-010: 从配置读取Symbol Universe）
    
    Response:
    {
      "success": true,
      "data": {
        "symbols": ["BTC", "ETH", "BNB", "SOL", "XRP"],
        "default_symbol": "BTC",
        "markets": {
          "BTC": {"spot": false, "futures": true},
          "ETH": {"spot": false, "futures": true},
          ...
        }
      }
    }
    """
    try:
        # PR-010: 从配置读取币种列表
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


# ========================================
# 辅助函数
# ========================================

def fetch_market_data(symbol: str, market_type: str = 'futures') -> dict:
    """
    获取市场数据（使用真实Binance API）
    
    Args:
        symbol: 币种符号（如 "BTC"）
        market_type: 市场类型（'futures' 或 'spot'）
    
    Returns:
        dict: 市场数据字典，包含L1所需的所有字段
    """
    try:
        # 使用Binance数据获取器（已集成数据缓存）
        data = binance_fetcher.fetch_market_data(symbol, market_type)
        
        if data:
            logger.info(f"Fetched market data for {symbol} ({market_type}): price={data['price']:.2f}")
            return data
        else:
            logger.warning(f"Failed to fetch data for {symbol}, using fallback")
            # 如果获取失败，返回None（不再使用mock数据）
            return None
    
    except Exception as e:
        logger.error(f"Error fetching market data for {symbol}: {e}", exc_info=True)
        return None


# ========================================
# 健康检查
# ========================================

@app.route('/health')
def health_check():
    """健康检查端点"""
    return jsonify({
        'status': 'healthy',
        'service': 'L1 Advisory Layer',
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
    logger.info("L1 Advisory Layer - Flask Application Starting")
    logger.info("=" * 60)
    logger.info(f"Engine initialized with {len(advisory_engine.thresholds)} thresholds")
    logger.info(f"Database: {l1_db.db_path}")
    logger.info(f"Config watcher: {'Enabled' if config_observer else 'Disabled'}")
    logger.info(f"Scheduler: {'Enabled' if scheduler else 'Disabled'}")
    logger.info("=" * 60)
    
    try:
        # 启动Flask应用
        # 使用不同端口避免与旧版冲突
        app.run(
            host='0.0.0.0', 
            port=5001,  # 旧版使用5000，新版使用5001
            debug=True
        )
    finally:
        # 应用关闭时停止监控和调度器
        if config_observer:
            config_observer.stop()
            config_observer.join()
            logger.info("Config watcher stopped")
        
        if scheduler:
            scheduler.shutdown()
            logger.info("Scheduler stopped")
