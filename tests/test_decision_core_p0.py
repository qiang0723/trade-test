"""
P0级单测：DecisionCore核心逻辑测试

测试DecisionCore的纯函数逻辑，确保核心决策流程正确。

测试覆盖：
1. 市场环境识别（_detect_market_regime）
2. 风险准入评估（_eval_risk_exposure）
3. 交易质量评估（_eval_trade_quality）
4. 方向评估（_eval_long_direction, _eval_short_direction）
5. 双周期独立性（evaluate_dual）
"""

import pytest
from datetime import datetime
from l1_engine.decision_core import DecisionCore
from models.feature_snapshot import FeatureSnapshot, MarketFeatures, CoverageInfo, FeatureMetadata
from models.feature_snapshot import PriceFeatures, OpenInterestFeatures, VolumeFeatures, FundingFeatures
from models.feature_snapshot import TakerImbalanceFeatures, FeatureVersion
from models.thresholds import Thresholds, MarketRegime as MarketRegimeThresholds
from models.thresholds import RiskExposure, LiquidationThreshold, CrowdingThreshold, ExtremeVolumeThreshold
from models.thresholds import TradeQuality as TradeQualityThresholds, AbsorptionThreshold, NoiseThreshold
from models.thresholds import RotationThreshold, RangeWeakSignalThreshold
from models.enums import MarketRegime, Decision, TradeQuality, Timeframe
from models.reason_tags import ReasonTag


# ============================================
# 测试辅助函数
# ============================================

def create_mock_thresholds() -> Thresholds:
    """创建模拟的阈值配置"""
    return Thresholds(
        symbol_universe=None,
        periodic_update=None,
        data_retention=None,
        error_handling=None,
        data_quality=None,
        decision_control=None,
        market_regime=MarketRegimeThresholds(
            extreme_price_change_1h=0.05,
            trend_price_change_6h=0.08,
            short_term_trend_1h=0.03
        ),
        risk_exposure=RiskExposure(
            liquidation=LiquidationThreshold(price_change=0.06, oi_drop=-0.15),
            crowding=CrowdingThreshold(funding_abs=0.002, oi_growth=0.5),
            extreme_volume=ExtremeVolumeThreshold(multiplier=3.0)
        ),
        trade_quality=TradeQualityThresholds(
            absorption=AbsorptionThreshold(imbalance=0.7, volume_ratio=0.5),
            noise=NoiseThreshold(funding_volatility=0.001, funding_abs=0.0005),
            rotation=RotationThreshold(price_threshold=0.02, oi_threshold=0.1),
            range_weak=RangeWeakSignalThreshold(imbalance=0.3, oi=0.05)
        ),
        confidence_scoring=None,
        dual_decision_control=None
    )


def create_mock_features(
    price=100000.0,
    price_change_1h=0.0,
    price_change_6h=0.0,
    price_change_15m=0.0,
    price_change_5m=0.0,
    oi_change_1h=0.0,
    oi_change_6h=0.0,
    volume_1h=1000000.0,
    volume_24h=24000000.0,
    funding_rate=0.0001,
    funding_rate_prev=0.0001,
    taker_imbalance_1h=0.0
) -> FeatureSnapshot:
    """创建模拟的特征快照"""
    features = MarketFeatures(
        price=PriceFeatures(
            current_price=price,
            price_change_1h=price_change_1h,
            price_change_6h=price_change_6h,
            price_change_15m=price_change_15m,
            price_change_5m=price_change_5m,
            price_change_24h=None
        ),
        open_interest=OpenInterestFeatures(
            current_oi=1000000000.0,
            oi_change_1h=oi_change_1h,
            oi_change_6h=oi_change_6h,
            oi_change_15m=None,
            oi_change_5m=None,
            oi_change_24h=None
        ),
        volume=VolumeFeatures(
            volume_1h=volume_1h,
            volume_24h=volume_24h,
            volume_ratio_1h=volume_1h / (volume_24h / 24),
            volume_ratio_15m=None,
            volume_ratio_5m=None
        ),
        funding=FundingFeatures(
            funding_rate=funding_rate,
            funding_rate_prev=funding_rate_prev
        ),
        taker_imbalance=TakerImbalanceFeatures(
            taker_imbalance_1h=taker_imbalance_1h,
            taker_imbalance_15m=None,
            taker_imbalance_5m=None
        )
    )
    
    coverage = CoverageInfo(
        short_evaluable=True,
        medium_evaluable=True,
        lookback_hours=6.0,
        gap_minutes=0.0,
        missing_windows=[]
    )
    
    metadata = FeatureMetadata(
        symbol="BTC",
        timestamp=datetime.now(),
        feature_version=FeatureVersion.V3
    )
    
    return FeatureSnapshot(
        features=features,
        coverage=coverage,
        metadata=metadata,
        trace=None
    )


# ============================================
# 测试1：市场环境识别
# ============================================

def test_detect_market_regime_extreme():
    """测试EXTREME环境识别"""
    features = create_mock_features(price_change_1h=0.08)
    thresholds = create_mock_thresholds()
    
    regime, tags = DecisionCore._detect_market_regime(features, thresholds, Timeframe.SHORT_TERM)
    
    assert regime == MarketRegime.EXTREME
    assert len(tags) == 0


def test_detect_market_regime_trend_6h():
    """测试TREND环境识别（基于6h）"""
    features = create_mock_features(price_change_6h=0.10)
    thresholds = create_mock_thresholds()
    
    regime, tags = DecisionCore._detect_market_regime(features, thresholds, Timeframe.MEDIUM_TERM)
    
    assert regime == MarketRegime.TREND
    assert len(tags) == 0


def test_detect_market_regime_trend_1h():
    """测试TREND环境识别（基于1h短期趋势）"""
    features = create_mock_features(price_change_1h=0.04)
    thresholds = create_mock_thresholds()
    
    regime, tags = DecisionCore._detect_market_regime(features, thresholds, Timeframe.SHORT_TERM)
    
    assert regime == MarketRegime.TREND
    assert ReasonTag.SHORT_TERM_TREND in tags


def test_detect_market_regime_range():
    """测试RANGE环境识别（默认）"""
    features = create_mock_features(price_change_1h=0.01, price_change_6h=0.02)
    thresholds = create_mock_thresholds()
    
    regime, tags = DecisionCore._detect_market_regime(features, thresholds, Timeframe.SHORT_TERM)
    
    assert regime == MarketRegime.RANGE
    assert len(tags) == 0


# ============================================
# 测试2：风险准入评估
# ============================================

def test_eval_risk_exposure_extreme_regime():
    """测试EXTREME环境被阻断"""
    features = create_mock_features()
    thresholds = create_mock_thresholds()
    
    risk_ok, tags = DecisionCore._eval_risk_exposure(features, MarketRegime.EXTREME, thresholds)
    
    assert risk_ok == False
    assert ReasonTag.EXTREME_REGIME in tags


def test_eval_risk_exposure_liquidation():
    """测试清算阶段被阻断"""
    features = create_mock_features(price_change_1h=0.07, oi_change_1h=-0.20)
    thresholds = create_mock_thresholds()
    
    risk_ok, tags = DecisionCore._eval_risk_exposure(features, MarketRegime.TREND, thresholds)
    
    assert risk_ok == False
    assert ReasonTag.LIQUIDATION_PHASE in tags


def test_eval_risk_exposure_crowding():
    """测试拥挤风险被阻断"""
    features = create_mock_features(funding_rate=0.0025, oi_change_6h=0.60)
    thresholds = create_mock_thresholds()
    
    risk_ok, tags = DecisionCore._eval_risk_exposure(features, MarketRegime.TREND, thresholds)
    
    assert risk_ok == False
    assert ReasonTag.CROWDING_RISK in tags


def test_eval_risk_exposure_extreme_volume():
    """测试极端成交量被阻断"""
    features = create_mock_features(volume_1h=4000000.0, volume_24h=24000000.0)
    thresholds = create_mock_thresholds()
    
    risk_ok, tags = DecisionCore._eval_risk_exposure(features, MarketRegime.TREND, thresholds)
    
    assert risk_ok == False
    assert ReasonTag.EXTREME_VOLUME in tags


def test_eval_risk_exposure_pass():
    """测试风险准入通过"""
    features = create_mock_features()
    thresholds = create_mock_thresholds()
    
    risk_ok, tags = DecisionCore._eval_risk_exposure(features, MarketRegime.TREND, thresholds)
    
    assert risk_ok == True
    assert len(tags) == 0


# ============================================
# 测试3：交易质量评估
# ============================================

def test_eval_trade_quality_absorption():
    """测试吸纳风险（POOR质量）"""
    features = create_mock_features(
        taker_imbalance_1h=0.8,
        volume_1h=400000.0,
        volume_24h=24000000.0
    )
    thresholds = create_mock_thresholds()
    
    quality, tags = DecisionCore._eval_trade_quality(features, MarketRegime.TREND, thresholds, "BTC")
    
    assert quality == TradeQuality.POOR
    assert ReasonTag.ABSORPTION_RISK in tags


def test_eval_trade_quality_noise():
    """测试噪音市场（UNCERTAIN质量）"""
    features = create_mock_features(
        funding_rate=0.0001,
        funding_rate_prev=0.0015
    )
    thresholds = create_mock_thresholds()
    
    quality, tags = DecisionCore._eval_trade_quality(features, MarketRegime.TREND, thresholds, "BTC")
    
    assert quality == TradeQuality.UNCERTAIN
    assert ReasonTag.NOISY_MARKET in tags


def test_eval_trade_quality_rotation():
    """测试轮动风险（POOR质量）"""
    features = create_mock_features(
        price_change_1h=0.03,
        oi_change_1h=-0.15
    )
    thresholds = create_mock_thresholds()
    
    quality, tags = DecisionCore._eval_trade_quality(features, MarketRegime.TREND, thresholds, "BTC")
    
    assert quality == TradeQuality.POOR
    assert ReasonTag.ROTATION_RISK in tags


def test_eval_trade_quality_good():
    """测试GOOD质量"""
    features = create_mock_features()
    thresholds = create_mock_thresholds()
    
    quality, tags = DecisionCore._eval_trade_quality(features, MarketRegime.TREND, thresholds, "BTC")
    
    assert quality == TradeQuality.GOOD
    assert len(tags) == 0


# ============================================
# 测试4：双周期独立性（P0-1修复验证）
# ============================================

def test_evaluate_dual_independence():
    """测试双周期决策独立性（P0-1修复验证）"""
    features = create_mock_features()
    thresholds = create_mock_thresholds()
    
    result = DecisionCore.evaluate_dual(features, thresholds, "BTC")
    
    # 确认返回的是DualTimeframeDecisionDraft
    assert result.short_term is not None
    assert result.medium_term is not None
    
    # 验证短期和中期都有决策结果
    assert result.short_term.decision is not None
    assert result.medium_term.decision is not None
    
    # 验证两个周期的决策可以不同（这是关键！）
    # 注意：这个测试用相同输入，但timeframe参数不同，
    # 未来可以通过不同的阈值配置让结果真正不同
    print(f"Short-term: {result.short_term.decision.value}")
    print(f"Medium-term: {result.medium_term.decision.value}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
