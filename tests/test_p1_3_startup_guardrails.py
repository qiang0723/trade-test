"""
P1-3修复验证：启动guardrail补齐（门槛一致性 + ReasonTag拼写）

问题背景:
- 当前只有decimal calibration校验
- 缺少门槛一致性校验：可能导致"允许降级但永远达不到门槛"
- 缺少ReasonTag拼写校验：拼写错误会导致运行时逻辑失效

补齐校验:
1. 门槛一致性校验:
   - min_confidence_reduced <= uncertain_quality_max
   - min_confidence_reduced <= tag_caps (for reduce_tags)
   - 否则会出现逻辑矛盾

2. ReasonTag拼写有效性校验:
   - reduce_tags / deny_tags / tag_caps / required_tags
   - 拼写错误应fail-fast

验证点:
1. 正常配置通过所有校验
2. 门槛不一致配置拒绝启动
3. ReasonTag拼写错误拒绝启动
4. 错误消息清晰指导修复
"""

import sys
import os
import yaml
import pytest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_state_machine_l1 import L1AdvisoryEngine

print("="*80)
print("P1-3修复验证：启动guardrail补齐")
print("="*80)

# ==================== 测试1：正常配置通过所有校验 ====================
print("\n【测试1】正常配置：通过所有启动校验")
print("-"*80)

try:
    engine = L1AdvisoryEngine()
    print("✅ 测试1通过: 正常配置通过所有启动校验")
    print("  - decimal calibration ✅")
    print("  - threshold consistency ✅")
    print("  - reason tag spelling ✅")
except Exception as e:
    print(f"❌ 测试1失败: 正常配置应该通过，但抛出异常: {e}")
    raise

# ==================== 测试2：门槛不一致 - reduced > uncertain_max ====================
print("\n" + "="*80)
print("【测试2】门槛不一致：min_confidence_reduced > uncertain_quality_max")
print("-"*80)

# 创建不一致的配置
inconsistent_config = yaml.safe_load("""
market_regime:
  trend_threshold: 0.05
  range_threshold: 0.03

risk_evaluation:
  extreme_threshold: 0.10
  liquidation_oi_threshold: -0.15
  liquidation_price_threshold: 0.08
  crowding_funding_threshold: 0.002
  crowding_oi_threshold: 0.30
  extreme_volume_ratio: 3.0

trade_quality:
  absorption_imbalance: 0.20
  absorption_volume_ratio: 0.5
  noisy_funding_volatility: 0.0003
  noisy_funding_abs: 0.0001
  rotation_price_threshold: 0.02
  rotation_oi_threshold: 0.05
  range_weak_imbalance: 0.10
  range_weak_oi: 0.05

direction:
  trend:
    long:
      imbalance: 0.6
      oi_change: 0.05
      price_change: 0.01
    short:
      imbalance: 0.6
      oi_change: 0.05
      price_change: 0.01
  range:
    long:
      imbalance: 0.7
      oi_change: 0.10
    short:
      imbalance: 0.7
      oi_change: 0.10

decision_control:
  min_decision_interval_seconds: 60
  flip_cooldown_seconds: 180

confidence_scoring:
  base_scores:
    regime_trend_score: 30
    regime_range_score: 10
    quality_good_score: 30
    quality_uncertain_score: 15
    quality_poor_score: 0
    strong_signal_bonus: 10
  thresholds:
    ultra: 90
    high: 65
    medium: 40
  caps:
    uncertain_quality_max: "MEDIUM"    # ⚠️ MEDIUM
    tag_caps:
      noisy_market: "HIGH"
      weak_signal_in_range: "HIGH"
  strong_signal_boost:
    enabled: true
    boost_levels: 1
    required_tags:
      - strong_buy_pressure
      - strong_sell_pressure

reason_tag_rules:
  reduce_tags:
    - noisy_market
    - weak_signal_in_range
  deny_tags:
    - liquidation_phase
    - crowding_risk
    - extreme_volume

executable_control:
  min_confidence_normal: "HIGH"
  min_confidence_reduced: "HIGH"      # ⚠️ HIGH > MEDIUM（不一致！）

auxiliary_tags:
  oi_growing_threshold: 0.05
  oi_declining_threshold: -0.05
  funding_rate_threshold: 0.0005
""")

inconsistent_path = '/tmp/test_inconsistent_threshold.yaml'
with open(inconsistent_path, 'w') as f:
    yaml.dump(inconsistent_config, f)

print("配置内容:")
print("  uncertain_quality_max: MEDIUM")
print("  min_confidence_reduced: HIGH")
print("  逻辑矛盾: HIGH > MEDIUM")
print("  影响: UNCERTAIN质量被cap到MEDIUM，但reduced门槛要求HIGH")
print("  结果: 降级执行永远失效")

try:
    engine_inconsistent = L1AdvisoryEngine(config_path=inconsistent_path)
    print("❌ 测试2失败: 应该拒绝启动，但没有抛出异常")
    assert False, "门槛不一致配置应该拒绝启动"
except ValueError as e:
    error_msg = str(e)
    print(f"\n✅ 测试2通过: 正确拒绝启动")
    print(f"  检测到: 门槛一致性错误")
    
    # 验证错误消息包含关键信息
    assert "门槛一致性错误" in error_msg or "Threshold Consistency" in error_msg, "错误消息应提及门槛一致性"
    assert "MEDIUM" in error_msg and "HIGH" in error_msg, "错误消息应包含具体的配置值"
    assert "逻辑矛盾" in error_msg or "达不到门槛" in error_msg, "错误消息应说明逻辑矛盾"
    
    print(f"  错误消息包含关键信息: ✅")
    print(f"    - 门槛一致性问题 ✅")
    print(f"    - 具体配置值 ✅")
    print(f"    - 逻辑矛盾说明 ✅")

# ==================== 测试3：门槛不一致 - reduced > tag_cap ====================
print("\n" + "="*80)
print("【测试3】门槛不一致：min_confidence_reduced > tag_caps (reduce_tags)")
print("-"*80)

inconsistent_tag_cap_config = inconsistent_config.copy()
inconsistent_tag_cap_config['confidence_scoring']['caps']['uncertain_quality_max'] = 'HIGH'
inconsistent_tag_cap_config['confidence_scoring']['caps']['tag_caps'] = {
    'noisy_market': 'LOW',            # ⚠️ LOW < HIGH（不一致！）
    'weak_signal_in_range': 'MEDIUM'  # ⚠️ MEDIUM < HIGH（不一致！）
}

inconsistent_tag_cap_path = '/tmp/test_inconsistent_tag_cap.yaml'
with open(inconsistent_tag_cap_path, 'w') as f:
    yaml.dump(inconsistent_tag_cap_config, f)

print("配置内容:")
print("  tag_caps.noisy_market: LOW")
print("  tag_caps.weak_signal_in_range: MEDIUM")
print("  min_confidence_reduced: HIGH")
print("  逻辑矛盾: HIGH > LOW, HIGH > MEDIUM")
print("  影响: 有降级标签时被cap到LOW/MEDIUM，但reduced门槛要求HIGH")
print("  结果: 降级执行永远失效")

try:
    engine_inconsistent_cap = L1AdvisoryEngine(config_path=inconsistent_tag_cap_path)
    print("❌ 测试3失败: 应该拒绝启动，但没有抛出异常")
    assert False, "tag_cap不一致配置应该拒绝启动"
except ValueError as e:
    error_msg = str(e)
    print(f"\n✅ 测试3通过: 正确拒绝启动")
    print(f"  检测到: 门槛一致性错误（tag_caps场景）")
    
    # 验证错误消息
    assert "门槛一致性错误" in error_msg or "Threshold Consistency" in error_msg
    assert "noisy_market" in error_msg or "weak_signal_in_range" in error_msg
    
    print(f"  错误消息包含tag名称: ✅")

# ==================== 测试4：ReasonTag拼写错误 - reduce_tags ====================
print("\n" + "="*80)
print("【测试4】ReasonTag拼写错误：reduce_tags中的无效标签")
print("-"*80)

spelling_error_config = inconsistent_config.copy()
spelling_error_config['confidence_scoring']['caps']['uncertain_quality_max'] = 'HIGH'
spelling_error_config['confidence_scoring']['caps']['tag_caps'] = {
    'noisy_market': 'HIGH',
    'weak_signal_in_range': 'HIGH'
}
spelling_error_config['executable_control']['min_confidence_reduced'] = 'MEDIUM'
spelling_error_config['reason_tag_rules']['reduce_tags'] = [
    'noisy_market',
    'weak_singal_in_range'  # ⚠️ 拼写错误：singal → signal
]

spelling_error_path = '/tmp/test_spelling_error.yaml'
with open(spelling_error_path, 'w') as f:
    yaml.dump(spelling_error_config, f)

print("配置内容:")
print("  reduce_tags:")
print("    - noisy_market          ✅ 正确")
print("    - weak_singal_in_range  ❌ 拼写错误（singal → signal）")

try:
    engine_spelling_error = L1AdvisoryEngine(config_path=spelling_error_path)
    print("❌ 测试4失败: 应该拒绝启动，但没有抛出异常")
    assert False, "拼写错误配置应该拒绝启动"
except ValueError as e:
    error_msg = str(e)
    print(f"\n✅ 测试4通过: 正确拒绝启动（fail-fast）")
    print(f"  检测到: ReasonTag拼写错误")
    
    # 验证错误消息
    assert "ReasonTag" in error_msg or "拼写" in error_msg, "错误消息应提及ReasonTag拼写"
    assert "weak_singal_in_range" in error_msg, "错误消息应包含具体的错误标签"
    assert "有效的ReasonTag" in error_msg or "valid" in error_msg.lower(), "错误消息应列出有效标签"
    
    print(f"  错误消息包含关键信息: ✅")
    print(f"    - ReasonTag拼写问题 ✅")
    print(f"    - 错误的标签名 ✅")
    print(f"    - 有效标签列表 ✅")

# ==================== 测试5：ReasonTag拼写错误 - required_tags ====================
print("\n" + "="*80)
print("【测试5】ReasonTag拼写错误：required_tags中的无效标签")
print("-"*80)

spelling_error_required_config = inconsistent_config.copy()
spelling_error_required_config['confidence_scoring']['caps']['uncertain_quality_max'] = 'HIGH'
spelling_error_required_config['confidence_scoring']['caps']['tag_caps'] = {
    'noisy_market': 'HIGH',
    'weak_signal_in_range': 'HIGH'
}
spelling_error_required_config['executable_control']['min_confidence_reduced'] = 'MEDIUM'
spelling_error_required_config['reason_tag_rules']['reduce_tags'] = [
    'noisy_market',
    'weak_signal_in_range'
]
spelling_error_required_config['confidence_scoring']['strong_signal_boost']['required_tags'] = [
    'strong_buy_presure',   # ⚠️ 拼写错误：presure → pressure
    'strong_sell_pressure'
]

spelling_error_required_path = '/tmp/test_spelling_error_required.yaml'
with open(spelling_error_required_path, 'w') as f:
    yaml.dump(spelling_error_required_config, f)

print("配置内容:")
print("  required_tags:")
print("    - strong_buy_presure   ❌ 拼写错误（presure → pressure）")
print("    - strong_sell_pressure ✅ 正确")

try:
    engine_spelling_required = L1AdvisoryEngine(config_path=spelling_error_required_path)
    print("❌ 测试5失败: 应该拒绝启动，但没有抛出异常")
    assert False, "required_tags拼写错误应该拒绝启动"
except ValueError as e:
    error_msg = str(e)
    print(f"\n✅ 测试5通过: 正确拒绝启动（fail-fast）")
    print(f"  检测到: required_tags拼写错误")
    
    assert "strong_buy_presure" in error_msg, "错误消息应包含错误的标签"
    print(f"  错误消息包含错误标签: ✅")

# ==================== 测试6：组合校验 - 多个错误 ====================
print("\n" + "="*80)
print("【测试6】组合校验：同时存在门槛不一致和拼写错误")
print("-"*80)

multi_error_config = inconsistent_config.copy()
multi_error_config['confidence_scoring']['caps']['uncertain_quality_max'] = 'MEDIUM'
multi_error_config['executable_control']['min_confidence_reduced'] = 'HIGH'  # 不一致
multi_error_config['reason_tag_rules']['reduce_tags'] = [
    'noisy_market',
    'weak_singal_in_range'  # 拼写错误
]

multi_error_path = '/tmp/test_multi_error.yaml'
with open(multi_error_path, 'w') as f:
    yaml.dump(multi_error_config, f)

print("配置问题:")
print("  1. 门槛不一致: HIGH > MEDIUM")
print("  2. 拼写错误: weak_singal_in_range")

try:
    engine_multi_error = L1AdvisoryEngine(config_path=multi_error_path)
    print("❌ 测试6失败: 应该拒绝启动")
    assert False
except ValueError as e:
    error_msg = str(e)
    print(f"\n✅ 测试6通过: 正确拒绝启动")
    print(f"  说明: 启动校验按顺序执行，发现第一个错误即fail-fast")
    
    # 应该在门槛一致性校验就失败（先于拼写校验）
    if "门槛一致性" in error_msg or "Threshold Consistency" in error_msg:
        print(f"  触发校验: 门槛一致性（优先）✅")
    elif "ReasonTag" in error_msg or "拼写" in error_msg:
        print(f"  触发校验: ReasonTag拼写 ✅")

# ==================== 总结 ====================
print("\n" + "="*80)
print("P1-3修复验证总结")
print("="*80)
print("✅ 测试1: 正常配置通过所有启动校验")
print("✅ 测试2: 门槛不一致（reduced > uncertain_max）拒绝启动")
print("✅ 测试3: 门槛不一致（reduced > tag_cap）拒绝启动")
print("✅ 测试4: ReasonTag拼写错误（reduce_tags）拒绝启动")
print("✅ 测试5: ReasonTag拼写错误（required_tags）拒绝启动")
print("✅ 测试6: 组合错误正确fail-fast")
print("\n关键成果:")
print("  - ✅ 补齐门槛一致性校验（防止逻辑矛盾）")
print("  - ✅ 补齐ReasonTag拼写校验（fail-fast机制）")
print("  - ✅ 错误消息清晰指导修复")
print("  - ✅ 启动guardrail机制完善")
print("\n启动校验清单:")
print("  1. decimal calibration ✅（PR-A防回归）")
print("  2. threshold consistency ✅（P1-3新增）")
print("  3. reason tag spelling ✅（P1-3新增）")
print("\n修复效果:")
print("  修复前: 只有口径校验，配置逻辑错误在运行时才发现 ❌")
print("  修复后: 三重校验，配置错误在启动时fail-fast ✅")
print("\n🎉 P1-3修复验证完全成功！")

# 清理临时文件
try:
    os.remove(inconsistent_path)
    os.remove(inconsistent_tag_cap_path)
    os.remove(spelling_error_path)
    os.remove(spelling_error_required_path)
    os.remove(multi_error_path)
except:
    pass
