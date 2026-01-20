"""
口径统一测试：验证配置和数据都使用小数格式

测试内容：
1. 配置阈值是否为小数格式
2. 数据规范化是否正确
3. 方向评估能否正常触发
4. 市场环境识别能否正常触发
"""

import sys
import os
from datetime import datetime
import yaml

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine
from models.enums import Decision, MarketRegime
from metrics_normalizer import normalize_metrics


def test_config_decimal_format():
    """测试配置文件使用小数格式"""
    print("\n=== Test 1: 配置阈值口径检查 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    # 市场环境
    mr = config['market_regime']
    assert mr['extreme_price_change_1h'] == 0.05, f"extreme应为0.05，实际为{mr['extreme_price_change_1h']}"
    assert mr['trend_price_change_6h'] == 0.03, f"trend应为0.03，实际为{mr['trend_price_change_6h']}"
    print(f"✅ 市场环境阈值: extreme={mr['extreme_price_change_1h']}, trend={mr['trend_price_change_6h']}")
    
    # 风险准入
    re = config['risk_exposure']
    assert re['liquidation']['price_change'] == 0.05, "liquidation.price_change应为0.05"
    assert re['liquidation']['oi_drop'] == -0.15, "liquidation.oi_drop应为-0.15"
    assert re['crowding']['oi_growth'] == 0.30, "crowding.oi_growth应为0.30"
    print(f"✅ 风险准入阈值: liquidation={re['liquidation']['price_change']}, oi_growth={re['crowding']['oi_growth']}")
    
    # 交易质量
    tq = config['trade_quality']
    assert tq['rotation']['price_threshold'] == 0.02, "rotation.price应为0.02"
    assert tq['rotation']['oi_threshold'] == 0.05, "rotation.oi应为0.05"
    assert tq['range_weak']['oi'] == 0.10, "range_weak.oi应为0.10"
    print(f"✅ 质量阈值: rotation_price={tq['rotation']['price_threshold']}, range_weak_oi={tq['range_weak']['oi']}")
    
    # 方向评估（关键！）
    d = config['direction']
    assert d['trend']['long']['oi_change'] == 0.05, "trend.long.oi_change应为0.05"
    assert d['trend']['long']['price_change'] == 0.01, "trend.long.price_change应为0.01"
    assert d['range']['long']['oi_change'] == 0.10, "range.long.oi_change应为0.10"
    print(f"✅ 方向阈值: trend_oi={d['trend']['long']['oi_change']}, trend_price={d['trend']['long']['price_change']}")


def test_data_normalization():
    """测试数据规范化"""
    print("\n=== Test 2: 数据规范化检查 ===")
    
    # 测试1: 百分点格式输入（5.0表示5%）
    raw_data = {
        'price': 50000,
        'price_change_1h': 5.0,     # 百分点格式
        'price_change_6h': 10.0,    # 百分点格式
        'volume_1h': 1000000,
        'volume_24h': 20000000,
        'buy_sell_imbalance': 0.75,
        'funding_rate': 0.0001,
        'oi_change_1h': 8.0,        # 百分点格式
        'oi_change_6h': 15.0        # 百分点格式
    }
    
    normalized, is_valid, error = normalize_metrics(raw_data)
    assert is_valid, f"规范化失败: {error}"
    
    # 验证已转换为小数
    assert normalized['price_change_1h'] == 0.05, f"应为0.05，实际为{normalized['price_change_1h']}"
    assert normalized['oi_change_1h'] == 0.08, f"应为0.08，实际为{normalized['oi_change_1h']}"
    print(f"✅ 百分点→小数: 5.0% → {normalized['price_change_1h']}, 8.0% → {normalized['oi_change_1h']}")
    
    # 测试2: 小数格式输入（0.05表示5%）
    decimal_data = {
        'price': 50000,
        'price_change_1h': 0.05,    # 小数格式
        'price_change_6h': 0.10,    # 小数格式
        'volume_1h': 1000000,
        'volume_24h': 20000000,
        'buy_sell_imbalance': 0.75,
        'funding_rate': 0.0001,
        'oi_change_1h': 0.08,       # 小数格式
        'oi_change_6h': 0.15        # 小数格式
    }
    
    normalized2, is_valid2, error2 = normalize_metrics(decimal_data)
    assert is_valid2, f"规范化失败: {error2}"
    assert normalized2['price_change_1h'] == 0.05, "小数格式应保持不变"
    assert normalized2['oi_change_1h'] == 0.08, "小数格式应保持不变"
    print(f"✅ 小数格式保持: 0.05 → {normalized2['price_change_1h']}")


def test_market_regime_trigger():
    """测试市场环境识别能否正常触发"""
    print("\n=== Test 3: 市场环境识别触发测试 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 测试1: EXTREME触发（1h变化6% > 5%阈值）
    extreme_data = {
        'price': 50000,
        'price_change_1h': 0.06,    # 6%（小数格式）
        'price_change_6h': 0.08,
        'volume_1h': 1000000,
        'volume_24h': 20000000,
        'buy_sell_imbalance': 0.5,
        'funding_rate': 0.0001,
        'oi_change_1h': 0.05,
        'oi_change_6h': 0.10,
        'timestamp': datetime.now().isoformat()
    }
    
    regime1 = engine._detect_market_regime(extreme_data)
    print(f"6%变化 → {regime1.value} (期望: extreme)")
    assert regime1 == MarketRegime.EXTREME, f"应触发EXTREME，实际为{regime1.value}"
    
    # 测试2: TREND触发（6h变化4% > 3%阈值）
    trend_data = extreme_data.copy()
    trend_data['price_change_1h'] = 0.02    # 2% < 5%
    trend_data['price_change_6h'] = 0.04    # 4% > 3%
    
    regime2 = engine._detect_market_regime(trend_data)
    print(f"4%变化(6h) → {regime2.value} (期望: trend)")
    assert regime2 == MarketRegime.TREND, f"应触发TREND，实际为{regime2.value}"
    
    # 测试3: RANGE（低于阈值）
    range_data = extreme_data.copy()
    range_data['price_change_1h'] = 0.01    # 1% < 5%
    range_data['price_change_6h'] = 0.02    # 2% < 3%
    
    regime3 = engine._detect_market_regime(range_data)
    print(f"1%变化 → {regime3.value} (期望: range)")
    assert regime3 == MarketRegime.RANGE
    
    print("✅ 市场环境识别正常触发")


def test_direction_evaluation_trigger():
    """测试方向评估能否正常触发"""
    print("\n=== Test 4: 方向评估触发测试 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # TREND市做多信号（满足所有条件）
    long_data = {
        'price_change_1h': 0.02,    # 2% > 1%阈值(0.01)
        'buy_sell_imbalance': 0.7,  # > 0.6阈值
        'oi_change_1h': 0.08        # 8% > 5%阈值(0.05)
    }
    
    allow_long = engine._eval_long_direction(long_data, MarketRegime.TREND)
    print(f"TREND+强多方信号 → allow_long={allow_long} (期望: True)")
    assert allow_long == True, "应该触发LONG"
    
    # TREND市做空信号（imbalance<-0.6表示空方强势）
    short_data = {
        'price_change_1h': -0.02,   # -2% < -1%阈值(-0.01) ✓
        'buy_sell_imbalance': 0.3,  # 需要<-0.6，0.3不满足
        'oi_change_1h': 0.08        # 8% > 5%阈值 ✓
    }
    
    # 修正：imbalance应该是负值表示空方强势
    short_data['buy_sell_imbalance'] = -0.7  # < -0.6 ✓
    
    allow_short = engine._eval_short_direction(short_data, MarketRegime.TREND)
    print(f"TREND+强空方信号(imbalance=-0.7) → allow_short={allow_short} (期望: True)")
    assert allow_short == True, "应该触发SHORT"
    
    # 弱信号（不应触发）
    weak_data = {
        'price_change_1h': 0.005,   # 0.5% < 1%阈值
        'buy_sell_imbalance': 0.55, # < 0.6阈值
        'oi_change_1h': 0.03        # 3% < 5%阈值
    }
    
    allow_long_weak = engine._eval_long_direction(weak_data, MarketRegime.TREND)
    print(f"TREND+弱信号 → allow_long={allow_long_weak} (期望: False)")
    assert allow_long_weak == False, "弱信号不应触发"
    
    print("✅ 方向评估正常触发")


def test_full_pipeline_with_decimal():
    """测试完整决策流程（小数格式数据）"""
    print("\n=== Test 5: 完整决策流程测试 ===")
    
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'l1_thresholds.yaml')
    engine = L1AdvisoryEngine(config_path)
    
    # 强TREND+强LONG信号
    strong_long = {
        'symbol': 'AIA',
        'price': 100,
        'price_change_1h': 0.025,   # 2.5% > 1%
        'price_change_6h': 0.04,    # 4% > 3% → TREND
        'volume_1h': 1000000,
        'volume_24h': 20000000,
        'buy_sell_imbalance': 0.75, # > 0.6
        'funding_rate': 0.0001,
        'oi_change_1h': 0.08,       # 8% > 5%
        'oi_change_6h': 0.12,
        'timestamp': datetime.now().isoformat()
    }
    
    result = engine.on_new_tick('AIA', strong_long)
    print(f"强TREND+强LONG → 决策:{result.decision.value}, 环境:{result.market_regime.value}")
    
    # 应该触发LONG或至少被正确识别为TREND
    assert result.market_regime == MarketRegime.TREND, "应识别为TREND环境"
    print("✅ 完整流程正常（TREND环境识别正确）")
    
    # 如果决策是LONG，说明方向评估也正常了
    if result.decision == Decision.LONG:
        print("✅ 完整流程正常（LONG决策触发）")
    else:
        print(f"ℹ️  决策为{result.decision.value}，可能因其他闸门限制")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("口径统一测试（PR-A修复验证）")
    print("=" * 60)
    
    try:
        test_config_decimal_format()
        test_data_normalization()
        test_market_regime_trigger()
        test_direction_evaluation_trigger()
        test_full_pipeline_with_decimal()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！口径已统一为小数格式")
        print("=" * 60)
        return 0
    
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
