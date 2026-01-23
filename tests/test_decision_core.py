"""
PR-ARCH-02 M6: DecisionCore确定性单测

测试DecisionCore的纯函数特性和确定性行为。

测试覆盖：
1. 确定性基础测试
2. 市场环境识别测试
3. 风险准入评估测试
4. 交易质量评估测试
5. 方向评估测试
6. None-safe行为测试
"""

from datetime import datetime
from typing import Optional

# 导入被测试的模块
from l1_engine.decision_core import DecisionCore
from l1_engine.threshold_compiler import ThresholdCompiler
from models.feature_snapshot import (
    FeatureSnapshot, MarketFeatures, PriceFeatures,
    OpenInterestFeatures, TakerImbalanceFeatures,
    VolumeFeatures, FundingFeatures,
    CoverageInfo, FeatureMetadata, FeatureVersion
)
from models.thresholds import Thresholds
from models.enums import Decision, MarketRegime, TradeQuality, ExecutionPermission
from models.reason_tags import ReasonTag


# ============================================
# Helper函数
# ============================================

def create_test_features(**kwargs) -> FeatureSnapshot:
    """
    创建测试用的FeatureSnapshot
    
    Args:
        **kwargs: 覆盖默认值的字段
    
    Returns:
        FeatureSnapshot
    """
    # 默认值（正常市场）
    defaults = {
        'current_price': 50000.0,
        'price_change_1h': 0.01,
        'price_change_6h': 0.02,
        'price_change_15m': 0.005,
        'oi_change_1h': 0.15,
        'oi_change_6h': 0.25,
        'oi_change_15m': 0.08,
        'taker_imbalance_1h': 0.3,
        'taker_imbalance_15m': 0.2,
        'volume_1h': 10000,
        'volume_24h': 200000,
        'volume_ratio_15m': 1.0,
        'funding_rate': 0.0001,
        'funding_rate_prev': 0.0001
    }
    
    # 覆盖用户提供的值
    defaults.update(kwargs)
    
    # 构建FeatureSnapshot
    features = FeatureSnapshot(
        features=MarketFeatures(
            price=PriceFeatures(
                price_change_1h=defaults['price_change_1h'],
                price_change_6h=defaults['price_change_6h'],
                price_change_15m=defaults.get('price_change_15m'),
                current_price=defaults['current_price']
            ),
            open_interest=OpenInterestFeatures(
                oi_change_1h=defaults['oi_change_1h'],
                oi_change_6h=defaults['oi_change_6h'],
                oi_change_15m=defaults.get('oi_change_15m')
            ),
            taker_imbalance=TakerImbalanceFeatures(
                taker_imbalance_1h=defaults['taker_imbalance_1h'],
                taker_imbalance_15m=defaults.get('taker_imbalance_15m')
            ),
            volume=VolumeFeatures(
                volume_1h=defaults['volume_1h'],
                volume_24h=defaults['volume_24h'],
                volume_ratio_15m=defaults.get('volume_ratio_15m')
            ),
            funding=FundingFeatures(
                funding_rate=defaults['funding_rate'],
                funding_rate_prev=defaults['funding_rate_prev']
            )
        ),
        coverage=CoverageInfo(
            short_evaluable=True,
            medium_evaluable=True
        ),
        metadata=FeatureMetadata(
            symbol="BTC",
            feature_version=FeatureVersion.V3_ARCH01,
            generated_at=datetime.now()
        )
    )
    
    return features


def load_test_thresholds() -> Thresholds:
    """
    加载测试用的Thresholds配置
    
    Returns:
        Thresholds
    """
    compiler = ThresholdCompiler()
    # 使用实际配置文件
    config_path = 'config/l1_thresholds.yaml'
    return compiler.compile(config_path)


# ============================================
# Test 1: 确定性基础测试
# ============================================

def test_decision_core_deterministic():
    """
    测试DecisionCore的确定性
    
    相同输入应该产生相同输出（纯函数特性）
    """
    # 构造固定输入
    features = create_test_features(
        price_change_1h=0.02,
        price_change_6h=0.03,
        taker_imbalance_1h=0.7,
        oi_change_1h=0.35
    )
    thresholds = load_test_thresholds()
    
    # 多次调用
    results = [
        DecisionCore.evaluate_single(features, thresholds, "BTC")
        for _ in range(10)
    ]
    
    # 断言：所有结果的核心字段完全相同
    for i in range(1, len(results)):
        assert results[i].decision == results[0].decision, \
            f"Decision不一致: {results[i].decision} vs {results[0].decision}"
        assert results[i].confidence == results[0].confidence, \
            f"Confidence不一致: {results[i].confidence} vs {results[0].confidence}"
        assert results[i].market_regime == results[0].market_regime, \
            f"MarketRegime不一致: {results[i].market_regime} vs {results[0].market_regime}"
        assert results[i].trade_quality == results[0].trade_quality, \
            f"TradeQuality不一致: {results[i].trade_quality} vs {results[0].trade_quality}"
        
        # reason_tags可能顺序不同，但集合应该相同
        assert set(results[i].reason_tags) == set(results[0].reason_tags), \
            f"ReasonTags不一致"
    
    print(f"✅ 确定性测试通过：10次调用结果完全一致")
    print(f"   Decision: {results[0].decision.value}")
    print(f"   Confidence: {results[0].confidence.value}")
    print(f"   MarketRegime: {results[0].market_regime.value}")


# ============================================
# Test 2: 市场环境识别测试
# ============================================

def test_market_regime_detection():
    """测试市场环境识别"""
    thresholds = load_test_thresholds()
    
    # EXTREME: price_change_1h = 0.08 (> 0.07)
    features_extreme = create_test_features(price_change_1h=0.08)
    regime, tags = DecisionCore._detect_market_regime(features_extreme, thresholds)
    assert regime == MarketRegime.EXTREME, f"Expected EXTREME, got {regime}"
    print(f"✅ EXTREME环境识别正确")
    
    # TREND: price_change_6h = 0.03 (> 0.02)
    features_trend = create_test_features(price_change_6h=0.03)
    regime, tags = DecisionCore._detect_market_regime(features_trend, thresholds)
    assert regime == MarketRegime.TREND, f"Expected TREND, got {regime}"
    print(f"✅ TREND环境识别正确")
    
    # RANGE: 默认
    features_range = create_test_features(price_change_1h=0.01, price_change_6h=0.02)
    regime, tags = DecisionCore._detect_market_regime(features_range, thresholds)
    assert regime == MarketRegime.RANGE, f"Expected RANGE, got {regime}"
    print(f"✅ RANGE环境识别正确")


# ============================================
# Test 3: 风险准入评估测试
# ============================================

def test_risk_exposure_evaluation():
    """测试风险准入评估"""
    thresholds = load_test_thresholds()
    
    # EXTREME regime应该DENY
    features = create_test_features()
    risk_ok, tags = DecisionCore._eval_risk_exposure(
        features, MarketRegime.EXTREME, thresholds
    )
    assert risk_ok == False, "EXTREME应该拒绝"
    assert ReasonTag.EXTREME_REGIME in tags
    print(f"✅ EXTREME环境风险拒绝正确")
    
    # 清算阶段应该DENY（急跌 + OI急降）
    features_liquidation = create_test_features(
        price_change_1h=-0.08,  # 急跌（触发EXTREME）
        oi_change_1h=-0.35       # OI急降
    )
    risk_ok, tags = DecisionCore._eval_risk_exposure(
        features_liquidation, MarketRegime.RANGE, thresholds
    )
    assert risk_ok == False, "清算阶段应该拒绝"
    assert ReasonTag.LIQUIDATION_PHASE in tags
    print(f"✅ 清算阶段风险拒绝正确")
    
    # 拥挤风险应该DENY（极端费率 + 高OI增长）
    features_crowding = create_test_features(
        funding_rate=0.0015,     # 极端费率
        oi_change_6h=0.60        # 高OI增长
    )
    risk_ok, tags = DecisionCore._eval_risk_exposure(
        features_crowding, MarketRegime.RANGE, thresholds
    )
    assert risk_ok == False, "拥挤风险应该拒绝"
    assert ReasonTag.CROWDING_RISK in tags
    print(f"✅ 拥挤风险拒绝正确")
    
    # 正常情况应该允许
    features_normal = create_test_features()
    risk_ok, tags = DecisionCore._eval_risk_exposure(
        features_normal, MarketRegime.RANGE, thresholds
    )
    assert risk_ok == True, "正常情况应该允许"
    print(f"✅ 正常情况风险允许正确")


# ============================================
# Test 4: 交易质量评估测试
# ============================================

def test_trade_quality_evaluation():
    """测试交易质量评估"""
    thresholds = load_test_thresholds()
    
    # 吸纳风险应该POOR（高失衡 + 低成交量）
    features_absorption = create_test_features(
        taker_imbalance_1h=0.8,  # 高失衡
        volume_1h=1000,          # 低成交量
        volume_24h=50000         # 24h平均高
    )
    quality, tags = DecisionCore._eval_trade_quality(
        features_absorption, MarketRegime.RANGE, thresholds, "BTC"
    )
    assert quality == TradeQuality.POOR, f"吸纳风险应该POOR，got {quality}"
    assert ReasonTag.ABSORPTION_RISK in tags
    print(f"✅ 吸纳风险质量评估正确")
    
    # 噪音市应该UNCERTAIN（费率波动大 + 当前费率低）
    features_noise = create_test_features(
        funding_rate=0.00005,     # 当前费率低（< 0.0001）
        funding_rate_prev=0.00080  # 前值高（波动0.00075 > 0.0005）
    )
    quality, tags = DecisionCore._eval_trade_quality(
        features_noise, MarketRegime.RANGE, thresholds, "BTC"
    )
    assert quality == TradeQuality.UNCERTAIN, f"噪音市应该UNCERTAIN，got {quality}"
    assert ReasonTag.NOISY_MARKET in tags
    print(f"✅ 噪音市质量评估正确")
    
    # 正常情况应该GOOD
    features_good = create_test_features()
    quality, tags = DecisionCore._eval_trade_quality(
        features_good, MarketRegime.TREND, thresholds, "BTC"
    )
    assert quality == TradeQuality.GOOD, f"正常情况应该GOOD，got {quality}"
    print(f"✅ 正常情况质量评估正确")


# ============================================
# Test 5: 方向评估测试
# ============================================

def test_direction_evaluation():
    """测试方向评估"""
    thresholds = load_test_thresholds()
    
    # LONG条件（TREND：高失衡 + 高OI + 上涨）
    features_long_trend = create_test_features(
        taker_imbalance_1h=0.7,  # > 0.6
        oi_change_1h=0.35,       # > 0.3
        price_change_1h=0.025    # > 0.02
    )
    allow_long, tags = DecisionCore._eval_long_direction(
        features_long_trend, MarketRegime.TREND, thresholds
    )
    assert allow_long == True, "TREND LONG条件应该允许"
    print(f"✅ TREND LONG方向评估正确")
    
    # SHORT条件（TREND：低失衡 + 高OI + 下跌）
    features_short_trend = create_test_features(
        taker_imbalance_1h=-0.7,  # < -0.6
        oi_change_1h=0.35,        # > 0.3
        price_change_1h=-0.025    # < -0.02
    )
    allow_short, tags = DecisionCore._eval_short_direction(
        features_short_trend, MarketRegime.TREND, thresholds
    )
    assert allow_short == True, "TREND SHORT条件应该允许"
    print(f"✅ TREND SHORT方向评估正确")
    
    # 条件不满足应该拒绝
    features_no_direction = create_test_features(
        taker_imbalance_1h=0.3,  # 失衡度不够
        oi_change_1h=0.15,       # OI变化不够
        price_change_1h=0.01     # 价格变化不够
    )
    allow_long_weak, _ = DecisionCore._eval_long_direction(
        features_no_direction, MarketRegime.TREND, thresholds
    )
    assert allow_long_weak == False, "弱条件应该拒绝LONG"
    print(f"✅ 弱条件方向评估正确")


# ============================================
# Test 6: None-safe行为测试
# ============================================

def test_none_safe_behavior():
    """测试None-safe行为"""
    thresholds = load_test_thresholds()
    
    # 缺失关键字段时，应该返回NO_TRADE（不崩溃）
    features_missing = create_test_features(
        price_change_1h=None,  # 缺失
        oi_change_1h=None      # 缺失
    )
    
    try:
        draft = DecisionCore.evaluate_single(features_missing, thresholds, "BTC")
        
        # 应该返回NO_TRADE，不应该抛异常
        assert draft.decision == Decision.NO_TRADE, \
            f"缺失关键字段应该返回NO_TRADE，got {draft.decision}"
        
        # 应该有相关标签（可能是DATA相关或其他）
        print(f"✅ None-safe测试通过：返回NO_TRADE，reason_tags={[t.value for t in draft.reason_tags]}")
        
    except Exception as e:
        raise AssertionError(f"None-safe测试失败：抛出异常 {e}")


# ============================================
# 运行所有测试
# ============================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("PR-ARCH-02 M6: DecisionCore确定性单测")
    print("="*80 + "\n")
    
    try:
        print("Test 1: 确定性基础测试")
        print("-" * 80)
        test_decision_core_deterministic()
        print()
        
        print("Test 2: 市场环境识别测试")
        print("-" * 80)
        test_market_regime_detection()
        print()
        
        print("Test 3: 风险准入评估测试")
        print("-" * 80)
        test_risk_exposure_evaluation()
        print()
        
        print("Test 4: 交易质量评估测试")
        print("-" * 80)
        test_trade_quality_evaluation()
        print()
        
        print("Test 5: 方向评估测试")
        print("-" * 80)
        test_direction_evaluation()
        print()
        
        print("Test 6: None-safe行为测试")
        print("-" * 80)
        test_none_safe_behavior()
        print()
        
        print("="*80)
        print("✅ 所有测试通过！")
        print("="*80)
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        raise
    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        raise
