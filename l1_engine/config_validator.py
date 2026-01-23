"""
L1 Advisory Engine - 配置验证模块

职责：
1. 启动时校验配置有效性（fail-fast）
2. 口径校验、门槛一致性、拼写检查
"""

from typing import Dict
from models.reason_tags import ReasonTag
import logging

logger = logging.getLogger(__name__)


class ConfigValidator:
    """配置验证器"""
    
    @staticmethod
    def validate_decimal_calibration(config: Dict):
        """
        启动时校验：检查配置口径是否为小数格式（防回归）
        
        目标：所有百分比阈值必须使用小数格式（0.05=5%），不允许百分点格式（5.0）
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 如果发现疑似百分点格式的阈值
        """
        errors = []
        
        # 定义需要检查的百分比阈值路径（值应 < 1.0）
        percentage_thresholds = [
            ('market_regime', 'extreme_price_change_1h', 'EXTREME价格变化阈值'),
            ('market_regime', 'trend_price_change_6h', 'TREND价格变化阈值'),
            ('risk_exposure', 'liquidation', 'price_change', '清算价格变化阈值'),
            ('risk_exposure', 'liquidation', 'oi_drop', '清算OI下降阈值'),
            ('risk_exposure', 'crowding', 'oi_growth', '拥挤OI增长阈值'),
            ('trade_quality', 'rotation', 'price_threshold', '轮动价格阈值'),
            ('trade_quality', 'rotation', 'oi_threshold', '轮动OI阈值'),
            ('trade_quality', 'range_weak', 'oi', '震荡弱信号OI阈值'),
        ]
        
        # 检查基础百分比阈值
        for path_parts in percentage_thresholds:
            *path, last_key, name = path_parts
            value = config
            try:
                for key in path:
                    value = value[key]
                threshold_value = value[last_key]
                
                # 检查：百分比阈值的绝对值应该 < 1.0（允许负数，如-0.15）
                if abs(threshold_value) >= 1.0:
                    config_path = '.'.join(path) + '.' + last_key if path else last_key
                    errors.append(
                        f"❌ {config_path} = {threshold_value} ({name}，疑似百分点格式，应使用小数格式，如 0.05 表示 5%)"
                    )
            except (KeyError, TypeError):
                pass
        
        # 检查方向评估阈值（嵌套结构）
        direction_config = config.get('direction', {})
        for regime in ['trend', 'range']:
            for side in ['long', 'short']:
                side_config = direction_config.get(regime, {}).get(side, {})
                
                oi_change = side_config.get('oi_change')
                if oi_change is not None and abs(oi_change) >= 1.0:
                    errors.append(
                        f"❌ direction.{regime}.{side}.oi_change = {oi_change} "
                        f"(疑似百分点格式，应使用小数格式，如 0.05 表示 5%)"
                    )
                
                price_change = side_config.get('price_change')
                if price_change is not None and abs(price_change) >= 1.0:
                    errors.append(
                        f"❌ direction.{regime}.{side}.price_change = {price_change} "
                        f"(疑似百分点格式，应使用小数格式，如 0.01 表示 1%)"
                    )
        
        if errors:
            error_message = (
                "\n" + "="*80 + "\n"
                "⚠️  配置口径错误检测（Decimal Calibration Validation Failed）\n"
                "="*80 + "\n"
                "发现疑似使用百分点格式的阈值配置，系统拒绝启动！\n\n"
                "错误项：\n" + "\n".join(f"  {err}" for err in errors) + "\n\n"
                "修复方法：\n"
                "  1. 打开配置文件: config/l1_thresholds.yaml\n"
                "  2. 将所有百分比阈值改为小数格式:\n"
                "     - 错误: 5.0 (百分点)\n"
                "     - 正确: 0.05 (小数，表示5%)\n"
                "  3. 参考文档: doc/平台详解3.0.md 第4章（口径规范）\n"
                "="*80
            )
            logger.error(error_message)
            raise ValueError(error_message)
        
        logger.info("✅ 配置口径校验通过：所有百分比阈值使用小数格式")
    
    @staticmethod
    def validate_threshold_consistency(config: Dict):
        """启动时校验：门槛一致性检查"""
        errors = []
        
        exec_config = config.get('executable_control', {})
        min_reduced_str = exec_config.get('min_confidence_reduced', 'MEDIUM')
        
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        uncertain_max_str = caps_config.get('uncertain_quality_max', 'MEDIUM')
        tag_caps = caps_config.get('tag_caps', {})
        
        tag_rules = config.get('reason_tag_rules', {})
        reduce_tags = tag_rules.get('reduce_tags', [])
        
        confidence_order = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2, 'ULTRA': 3}
        
        min_reduced_level = confidence_order.get(min_reduced_str.upper(), 1)
        uncertain_max_level = confidence_order.get(uncertain_max_str.upper(), 1)
        
        # 检查1: min_confidence_reduced <= uncertain_quality_max
        if min_reduced_level > uncertain_max_level:
            errors.append(
                f"min_confidence_reduced ({min_reduced_str}) > uncertain_quality_max ({uncertain_max_str})\n"
                f"  → UNCERTAIN质量被cap到 {uncertain_max_str}，但reduced门槛要求 {min_reduced_str}\n"
                f"  → 逻辑矛盾：UNCERTAIN永远达不到reduced门槛，降级执行失效"
            )
        
        # 检查2: min_confidence_reduced <= tag_caps (for reduce_tags)
        for tag_name in reduce_tags:
            if tag_name in tag_caps:
                tag_cap_str = tag_caps[tag_name]
                tag_cap_level = confidence_order.get(tag_cap_str.upper(), 1)
                
                if min_reduced_level > tag_cap_level:
                    errors.append(
                        f"min_confidence_reduced ({min_reduced_str}) > tag_caps['{tag_name}'] ({tag_cap_str})\n"
                        f"  → {tag_name} 被cap到 {tag_cap_str}，但reduced门槛要求 {min_reduced_str}\n"
                        f"  → 逻辑矛盾：有{tag_name}时永远达不到reduced门槛"
                    )
        
        if errors:
            error_message = (
                "\n" + "="*80 + "\n"
                "⚠️  门槛一致性错误检测（Threshold Consistency Validation Failed）\n"
                "="*80 + "\n"
                "发现门槛配置不一致，会导致'允许降级但永远达不到门槛'的逻辑矛盾！\n\n"
                "错误项：\n" + "\n".join(f"  {i+1}. {err}\n" for i, err in enumerate(errors)) + "\n"
                "修复方法：\n"
                "  1. 确保 min_confidence_reduced <= uncertain_quality_max\n"
                "  2. 确保 min_confidence_reduced <= tag_caps (for all reduce_tags)\n"
                "="*80 + "\n"
            )
            raise ValueError(error_message)
        
        logger.info("✅ 门槛一致性校验通过：reduced门槛 <= caps，降级执行逻辑正确")
    
    @staticmethod
    def validate_reason_tag_spelling(config: Dict):
        """启动时校验：ReasonTag拼写有效性检查"""
        valid_tags = {tag.value for tag in ReasonTag}
        errors = []
        
        # 检查 reduce_tags
        tag_rules = config.get('reason_tag_rules', {})
        reduce_tags = tag_rules.get('reduce_tags', [])
        for tag_name in reduce_tags:
            if tag_name not in valid_tags:
                errors.append(
                    f"reason_tag_rules.reduce_tags: '{tag_name}' 不是有效的ReasonTag"
                )
        
        # 检查 deny_tags
        deny_tags = tag_rules.get('deny_tags', [])
        for tag_name in deny_tags:
            if tag_name not in valid_tags:
                errors.append(
                    f"reason_tag_rules.deny_tags: '{tag_name}' 不是有效的ReasonTag"
                )
        
        # 检查 tag_caps (keys)
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        tag_caps = caps_config.get('tag_caps', {})
        for tag_name in tag_caps.keys():
            if tag_name not in valid_tags:
                errors.append(
                    f"confidence_scoring.caps.tag_caps: '{tag_name}' 不是有效的ReasonTag"
                )
        
        # 检查 required_tags
        boost_config = scoring_config.get('strong_signal_boost', {})
        required_tags = boost_config.get('required_tags', [])
        for tag_name in required_tags:
            if tag_name not in valid_tags:
                errors.append(
                    f"confidence_scoring.strong_signal_boost.required_tags: '{tag_name}' 不是有效的ReasonTag"
                )
        
        if errors:
            error_message = (
                "\n" + "="*80 + "\n"
                "⚠️  ReasonTag拼写错误检测（ReasonTag Spelling Validation Failed）\n"
                "="*80 + "\n"
                "发现无效的ReasonTag名称，系统拒绝启动（fail-fast）！\n\n"
                "错误项：\n" + "\n".join(f"  {i+1}. {err}\n" for i, err in enumerate(errors)) + "\n"
                "有效的ReasonTag列表：\n"
                "  " + ", ".join(sorted(valid_tags)) + "\n\n"
                "="*80 + "\n"
            )
            raise ValueError(error_message)
        
        logger.info("✅ ReasonTag拼写校验通过：所有标签名有效")
    
    @staticmethod
    def validate_confidence_values(config: Dict):
        """启动时校验：Confidence值拼写有效性检查"""
        valid_confidence_values = {'LOW', 'MEDIUM', 'HIGH', 'ULTRA'}
        errors = []
        
        exec_config = config.get('executable_control', {})
        min_conf_normal = exec_config.get('min_confidence_normal', 'HIGH')
        if min_conf_normal.upper() not in valid_confidence_values:
            errors.append(
                f"executable_control.min_confidence_normal: '{min_conf_normal}' 不是有效的Confidence值"
            )
        
        min_conf_reduced = exec_config.get('min_confidence_reduced', 'MEDIUM')
        if min_conf_reduced.upper() not in valid_confidence_values:
            errors.append(
                f"executable_control.min_confidence_reduced: '{min_conf_reduced}' 不是有效的Confidence值"
            )
        
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        uncertain_max = caps_config.get('uncertain_quality_max', 'MEDIUM')
        if uncertain_max.upper() not in valid_confidence_values:
            errors.append(
                f"confidence_scoring.caps.uncertain_quality_max: '{uncertain_max}' 不是有效的Confidence值"
            )
        
        tag_caps = caps_config.get('tag_caps', {})
        for tag_name, cap_value in tag_caps.items():
            if cap_value.upper() not in valid_confidence_values:
                errors.append(
                    f"confidence_scoring.caps.tag_caps.{tag_name}: '{cap_value}' 不是有效的Confidence值"
                )
        
        if errors:
            error_message = (
                "\n" + "="*80 + "\n"
                "⚠️  Confidence值拼写错误检测（Confidence Value Validation Failed）\n"
                "="*80 + "\n"
                "发现无效的Confidence配置值，系统拒绝启动（fail-fast）！\n\n"
                "错误项：\n" + "\n".join(f"  {i+1}. {err}\n" for i, err in enumerate(errors)) + "\n"
                "有效的Confidence值：\n"
                "  LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）\n\n"
                "="*80 + "\n"
            )
            raise ValueError(error_message)
        
        logger.info("✅ Confidence值拼写校验通过：所有置信度配置有效")
