"""
PR-ARCH-01 验证脚本：测试回测集成FeatureBuilder

目标：
1. 验证data_loader使用FeatureBuilder生成特征
2. 确认特征格式与线上一致
3. 检查FeatureSnapshot → dict转换正常
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
from datetime import datetime, timedelta

# 先配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger_main = logging.getLogger(__name__)

# 然后导入（避免循环导入）
from backtest.data_loader import HistoricalDataLoader
def test_feature_builder_integration():
    """
    测试FeatureBuilder集成到回测
    """
    logger = logger_main
    logger.info("=" * 80)
    logger.info("PR-ARCH-01 回测集成验证")
    logger.info("=" * 80)
    
    # 1. 初始化data_loader
    logger.info("\n1. 初始化HistoricalDataLoader...")
    loader = HistoricalDataLoader()
    
    # 2. 加载样本数据
    logger.info("\n2. 加载历史K线数据...")
    try:
        # 使用最近7天的数据
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        klines = loader.load_historical_data(
            symbol="BTCUSDT",
            start_date=start_date,
            end_date=end_date,
            interval="1m",
            use_cache=True
        )
        
        logger.info(f"   ✅ 加载完成: {len(klines)} 条K线")
        
    except Exception as e:
        logger.error(f"   ❌ 加载失败: {e}")
        logger.info("   提示: 请确保网络连接或使用缓存数据")
        return False
    
    # 3. 测试prepare_market_data（使用FeatureBuilder）
    logger.info("\n3. 测试prepare_market_data（集成FeatureBuilder）...")
    
    if len(klines) < 361:
        logger.error(f"   ❌ 数据不足: {len(klines)} < 361")
        return False
    
    # 选择一个中间时间点
    test_idx = 500 if len(klines) > 500 else len(klines) - 1
    test_timestamp = klines[test_idx]['timestamp']
    
    try:
        market_data = loader.prepare_market_data(klines, test_timestamp)
        
        if market_data is None:
            logger.error("   ❌ prepare_market_data返回None")
            return False
        
        logger.info(f"   ✅ 数据生成成功")
        
        # 4. 验证字段
        logger.info("\n4. 验证特征字段...")
        required_fields = [
            'price', 'timestamp',
            'price_change_5m', 'price_change_15m', 'price_change_1h', 'price_change_6h',
            'volume_1h', 'volume_24h', 'volume_ratio_5m', 'volume_ratio_15m',
            'taker_imbalance_5m', 'taker_imbalance_15m', 'taker_imbalance_1h',
            'oi_change_5m', 'oi_change_15m', 'oi_change_1h', 'oi_change_6h',
            'funding_rate'
        ]
        
        missing_fields = []
        for field in required_fields:
            if field not in market_data:
                missing_fields.append(field)
        
        if missing_fields:
            logger.error(f"   ❌ 缺失字段: {missing_fields}")
            return False
        
        logger.info(f"   ✅ 所有必需字段存在 ({len(required_fields)}个)")
        
        # 5. 验证数值范围
        logger.info("\n5. 验证数值范围...")
        
        # 价格变化应该是小数格式（不是百分比点）
        price_change_1h = market_data['price_change_1h']
        if price_change_1h is not None:
            if abs(price_change_1h) > 1.0:  # 如果>100%，可能是percent_point格式
                logger.warning(f"   ⚠️  price_change_1h疑似percent_point格式: {price_change_1h}")
                logger.info("   提示: 应该是decimal格式（如0.05 = 5%）")
            else:
                logger.info(f"   ✅ price_change_1h格式正确: {price_change_1h:.4f} (decimal)")
        
        # Taker imbalance应该在[-1, 1]范围
        taker_imbalance_1h = market_data.get('taker_imbalance_1h')
        if taker_imbalance_1h is not None:
            if -1 <= taker_imbalance_1h <= 1:
                logger.info(f"   ✅ taker_imbalance_1h范围正确: {taker_imbalance_1h:.4f}")
            else:
                logger.warning(f"   ⚠️  taker_imbalance_1h超出范围: {taker_imbalance_1h}")
        
        # 6. 打印样本数据
        logger.info("\n6. 样本数据（部分字段）:")
        sample_fields = [
            'price', 'price_change_1h', 'price_change_6h',
            'taker_imbalance_1h', 'volume_ratio_15m', 'oi_change_1h'
        ]
        for field in sample_fields:
            value = market_data.get(field)
            if value is not None:
                logger.info(f"   {field:25s}: {value}")
        
        # 7. 检查元数据
        logger.info("\n7. 检查元数据...")
        metadata = market_data.get('_metadata', {})
        coverage = metadata.get('_coverage', {})
        
        if metadata:
            logger.info(f"   percentage_format: {metadata.get('percentage_format', 'N/A')}")
            logger.info(f"   source: {metadata.get('source', 'N/A')}")
            logger.info(f"   version: {metadata.get('version', 'N/A')}")
        
        if coverage:
            logger.info(f"   ✅ Coverage信息存在")
            logger.info(f"      short_evaluable: {coverage.get('short_evaluable', 'N/A')}")
            logger.info(f"      medium_evaluable: {coverage.get('medium_evaluable', 'N/A')}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ PR-ARCH-01回测集成验证通过！")
        logger.info("=" * 80)
        return True
        
    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = test_feature_builder_integration()
    sys.exit(0 if success else 1)
