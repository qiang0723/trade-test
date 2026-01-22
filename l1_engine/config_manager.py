"""
L1 配置管理器

负责：
- 加载YAML配置
- 配置校验（口径、门槛一致性、拼写检查）
- 配置扁平化
- 默认配置
"""

import yaml
import os
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认为 config/l1_thresholds.yaml
        """
        if config_path is None:
            config_path = os.path.join('config', 'l1_thresholds.yaml')
        
        self.config = self._load_config(config_path)
        
        # 启动时校验（fail-fast）
        self._validate_decimal_calibration(self.config)
        self._validate_threshold_consistency(self.config)
        self._validate_reason_tag_spelling(self.config)
        self._validate_confidence_values(self.config)
        
        # 扁平化阈值
        self.thresholds = self._flatten_thresholds(self.config)
    
    def _load_config(self, config_path: str) -> dict:
        """
        加载YAML配置文件
        
        Args:
            config_path: 配置文件路径
        
        Returns:
            dict: 配置字典
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded config from {config_path}")
            return config
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}, using defaults")
            return self._get_default_config()
    
    def _validate_decimal_calibration(self, config: dict):
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
                # 配置项不存在，跳过
                pass
        
        # 检查方向评估阈值（嵌套结构）
        direction_config = config.get('direction', {})
        for regime in ['trend', 'range']:
            for side in ['long', 'short']:
                side_config = direction_config.get(regime, {}).get(side, {})
                
                # oi_change 应 < 1.0
                oi_change = side_config.get('oi_change')
                if oi_change is not None and abs(oi_change) >= 1.0:
                    errors.append(
                        f"❌ direction.{regime}.{side}.oi_change = {oi_change} "
                        f"(疑似百分点格式，应使用小数格式，如 0.05 表示 5%)"
                    )
                
                # price_change 应 < 1.0
                price_change = side_config.get('price_change')
                if price_change is not None and abs(price_change) >= 1.0:
                    errors.append(
                        f"❌ direction.{regime}.{side}.price_change = {price_change} "
                        f"(疑似百分点格式，应使用小数格式，如 0.01 表示 1%)"
                    )
        
        # 如果发现错误，拒绝启动
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
    
    def _validate_threshold_consistency(self, config: dict):
        """
        启动时校验：门槛一致性检查（P1-3）
        
        目标：防止"允许降级但永远达不到门槛"的逻辑矛盾
        
        检查项：
        1. min_confidence_reduced <= uncertain_quality_max
           - reduced门槛不能高于UNCERTAIN的cap
           - 否则UNCERTAIN质量永远达不到reduced门槛
        
        2. min_confidence_reduced <= tag_caps (for reduce_tags)
           - reduced门槛不能高于降级标签的cap
           - 否则有降级标签时永远达不到reduced门槛
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 如果发现门槛一致性问题
        """
        from models.enums import Confidence
        
        errors = []
        
        # 获取配置
        exec_config = config.get('executable_control', {})
        min_reduced_str = exec_config.get('min_confidence_reduced', 'MEDIUM')
        
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        uncertain_max_str = caps_config.get('uncertain_quality_max', 'MEDIUM')
        tag_caps = caps_config.get('tag_caps', {})
        
        tag_rules = config.get('reason_tag_rules', {})
        reduce_tags = tag_rules.get('reduce_tags', [])
        
        # 置信度顺序映射
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
                "  3. 推荐配置（方案D）:\n"
                "     - min_confidence_reduced: MEDIUM\n"
                "     - uncertain_quality_max: HIGH\n"
                "     - tag_caps: {noisy_market: HIGH, weak_signal_in_range: HIGH}\n"
                "     - 确保 MEDIUM <= HIGH 的一致性\n\n"
                "设计原理：\n"
                "  ALLOW_REDUCED场景需要 cap >= reduced门槛，否则降级执行永远失效\n"
                "="*80 + "\n"
            )
            raise ValueError(error_message)
        
        logger.info("✅ 门槛一致性校验通过：reduced门槛 <= caps，降级执行逻辑正确")
    
    def _validate_reason_tag_spelling(self, config: dict):
        """
        启动时校验：ReasonTag拼写有效性检查（P1-3）
        
        目标：防止配置中的标签名拼写错误，fail-fast
        
        检查范围：
        1. reason_tag_rules.reduce_tags
        2. reason_tag_rules.deny_tags
        3. confidence_scoring.caps.tag_caps (keys)
        4. confidence_scoring.strong_signal_boost.required_tags
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 如果发现无效的ReasonTag名称
        """
        from models.reason_tags import ReasonTag
        
        # 获取所有有效的ReasonTag值
        valid_tags = {tag.value for tag in ReasonTag}
        
        errors = []
        
        # 检查 reduce_tags
        tag_rules = config.get('reason_tag_rules', {})
        reduce_tags = tag_rules.get('reduce_tags', [])
        for tag_name in reduce_tags:
            if tag_name not in valid_tags:
                errors.append(
                    f"reason_tag_rules.reduce_tags: '{tag_name}' 不是有效的ReasonTag\n"
                    f"  → 可能是拼写错误，请检查 models/reason_tags.py 中的定义"
                )
        
        # 检查 deny_tags
        deny_tags = tag_rules.get('deny_tags', [])
        for tag_name in deny_tags:
            if tag_name not in valid_tags:
                errors.append(
                    f"reason_tag_rules.deny_tags: '{tag_name}' 不是有效的ReasonTag\n"
                    f"  → 可能是拼写错误，请检查 models/reason_tags.py 中的定义"
                )
        
        # 检查 tag_caps (keys)
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        tag_caps = caps_config.get('tag_caps', {})
        for tag_name in tag_caps.keys():
            if tag_name not in valid_tags:
                errors.append(
                    f"confidence_scoring.caps.tag_caps: '{tag_name}' 不是有效的ReasonTag\n"
                    f"  → 可能是拼写错误，请检查 models/reason_tags.py 中的定义"
                )
        
        # 检查 required_tags
        boost_config = scoring_config.get('strong_signal_boost', {})
        required_tags = boost_config.get('required_tags', [])
        for tag_name in required_tags:
            if tag_name not in valid_tags:
                errors.append(
                    f"confidence_scoring.strong_signal_boost.required_tags: '{tag_name}' 不是有效的ReasonTag\n"
                    f"  → 可能是拼写错误，请检查 models/reason_tags.py 中的定义"
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
                "修复方法：\n"
                "  1. 检查配置文件: config/l1_thresholds.yaml\n"
                "  2. 修正拼写错误的标签名\n"
                "  3. 参考 models/reason_tags.py 中的 ReasonTag 枚举定义\n"
                "  4. 标签名必须使用下划线小写格式（如 strong_buy_pressure）\n\n"
                "设计原理：\n"
                "  配置中的标签拼写错误会导致运行时逻辑失效，fail-fast机制确保启动前发现\n"
                "="*80 + "\n"
            )
            raise ValueError(error_message)
        
        logger.info("✅ ReasonTag拼写校验通过：所有标签名有效")
    
    def _validate_confidence_values(self, config: dict):
        """
        启动时校验：Confidence值拼写有效性检查（PR-H）
        
        目标：所有 Confidence 字符串配置必须是合法枚举；拼写错误直接拒绝启动，
             而不是运行中降级为 LOW
        
        检查范围：
        1. execution.min_confidence_normal
        2. execution.min_confidence_reduced
        3. confidence_scoring.caps.uncertain_quality_max
        4. confidence_scoring.caps.tag_caps.* (所有值)
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 如果发现无效的Confidence值
        """
        # 有效的Confidence值（大小写不敏感）
        valid_confidence_values = {'LOW', 'MEDIUM', 'HIGH', 'ULTRA'}
        
        errors = []
        
        # 检查 executable_control.min_confidence_normal
        exec_config = config.get('executable_control', {})
        min_conf_normal = exec_config.get('min_confidence_normal', 'HIGH')
        if min_conf_normal.upper() not in valid_confidence_values:
            errors.append(
                f"executable_control.min_confidence_normal: '{min_conf_normal}' 不是有效的Confidence值\n"
                f"  → 有效值: LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）"
            )
        
        # 检查 executable_control.min_confidence_reduced
        min_conf_reduced = exec_config.get('min_confidence_reduced', 'MEDIUM')
        if min_conf_reduced.upper() not in valid_confidence_values:
            errors.append(
                f"executable_control.min_confidence_reduced: '{min_conf_reduced}' 不是有效的Confidence值\n"
                f"  → 有效值: LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）"
            )
        
        # 检查 confidence_scoring.caps.uncertain_quality_max
        scoring_config = config.get('confidence_scoring', {})
        caps_config = scoring_config.get('caps', {})
        uncertain_max = caps_config.get('uncertain_quality_max', 'MEDIUM')
        if uncertain_max.upper() not in valid_confidence_values:
            errors.append(
                f"confidence_scoring.caps.uncertain_quality_max: '{uncertain_max}' 不是有效的Confidence值\n"
                f"  → 有效值: LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）"
            )
        
        # 检查 confidence_scoring.caps.tag_caps.* (所有值)
        tag_caps = caps_config.get('tag_caps', {})
        for tag_name, cap_value in tag_caps.items():
            if cap_value.upper() not in valid_confidence_values:
                errors.append(
                    f"confidence_scoring.caps.tag_caps.{tag_name}: '{cap_value}' 不是有效的Confidence值\n"
                    f"  → 有效值: LOW, MEDIUM, HIGH, ULTRA（大小写不敏感）"
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
                "修复方法：\n"
                "  1. 检查配置文件: config/l1_thresholds.yaml\n"
                "  2. 修正拼写错误的Confidence值\n"
                "  3. 常见错误: HGIH → HIGH, MEDUIM → MEDIUM\n"
                "  4. 确保所有置信度配置使用正确的枚举值\n\n"
                "设计原理（PR-H）：\n"
                "  - 采用fail-fast原则，配置错误直接拒绝启动\n"
                "  - 避免运行时静默回退到LOW导致意外行为\n"
                "  - 保持与ReasonTag拼写校验的一致性\n"
                "="*80 + "\n"
            )
            raise ValueError(error_message)
        
        logger.info("✅ Confidence值拼写校验通过：所有置信度配置有效")
    
    def _flatten_thresholds(self, config: dict) -> dict:
        """
        将嵌套配置扁平化为易于访问的字典
        
        Args:
            config: 嵌套配置字典
        
        Returns:
            dict: 扁平化后的阈值字典
        """
        flat = {}
        
        # 数据质量（PR-002）
        dq = config.get('data_quality', {})
        flat['data_max_staleness_seconds'] = dq.get('max_staleness_seconds', 120)
        
        # 市场环境
        mr = config.get('market_regime', {})
        flat['extreme_price_change_1h'] = mr.get('extreme_price_change_1h', 0.05)
        flat['trend_price_change_6h'] = mr.get('trend_price_change_6h', 0.03)
        
        # 风险准入
        re = config.get('risk_exposure', {})
        flat['liquidation_price_change'] = re.get('liquidation', {}).get('price_change', 0.05)
        flat['liquidation_oi_drop'] = re.get('liquidation', {}).get('oi_drop', -0.15)
        flat['crowding_funding_abs'] = re.get('crowding', {}).get('funding_abs', 0.001)
        flat['crowding_oi_growth'] = re.get('crowding', {}).get('oi_growth', 0.30)
        flat['extreme_volume_multiplier'] = re.get('extreme_volume', {}).get('multiplier', 10.0)
        
        # 交易质量
        tq = config.get('trade_quality', {})
        flat['absorption_imbalance'] = tq.get('absorption', {}).get('imbalance', 0.7)
        flat['absorption_volume_ratio'] = tq.get('absorption', {}).get('volume_ratio', 0.5)
        flat['noisy_funding_volatility'] = tq.get('noise', {}).get('funding_volatility', 0.0005)
        flat['noisy_funding_abs'] = tq.get('noise', {}).get('funding_abs', 0.0001)
        flat['rotation_price_threshold'] = tq.get('rotation', {}).get('price_threshold', 0.02)
        flat['rotation_oi_threshold'] = tq.get('rotation', {}).get('oi_threshold', 0.05)
        flat['range_weak_imbalance'] = tq.get('range_weak', {}).get('imbalance', 0.6)
        flat['range_weak_oi'] = tq.get('range_weak', {}).get('oi', 0.10)
        
        # 方向评估
        d = config.get('direction', {})
        flat['long_imbalance_trend'] = d.get('trend', {}).get('long', {}).get('imbalance', 0.6)
        flat['long_oi_change_trend'] = d.get('trend', {}).get('long', {}).get('oi_change', 0.05)
        flat['long_price_change_trend'] = d.get('trend', {}).get('long', {}).get('price_change', 0.01)
        flat['short_imbalance_trend'] = d.get('trend', {}).get('short', {}).get('imbalance', 0.6)
        flat['short_oi_change_trend'] = d.get('trend', {}).get('short', {}).get('oi_change', 0.05)
        flat['short_price_change_trend'] = d.get('trend', {}).get('short', {}).get('price_change', 0.01)
        flat['long_imbalance_range'] = d.get('range', {}).get('long', {}).get('imbalance', 0.7)
        flat['long_oi_change_range'] = d.get('range', {}).get('long', {}).get('oi_change', 0.10)
        flat['short_imbalance_range'] = d.get('range', {}).get('short', {}).get('imbalance', 0.7)
        flat['short_oi_change_range'] = d.get('range', {}).get('short', {}).get('oi_change', 0.10)
        
        # 辅助标签阈值（P0-3）
        aux = config.get('auxiliary_tags', {})
        flat['aux_oi_growing_threshold'] = aux.get('oi_growing_threshold', 0.05)
        flat['aux_oi_declining_threshold'] = aux.get('oi_declining_threshold', -0.05)
        flat['aux_funding_rate_threshold'] = aux.get('funding_rate_threshold', 0.0005)
        
        return flat
    
    def _get_default_config(self) -> dict:
        """
        获取默认配置（当配置文件不存在时）
        
        Returns:
            dict: 默认配置字典
        """
        return {
            'symbol_universe': {
                'enabled_symbols': ['BTC', 'ETH', 'BNB', 'SOL', 'XRP'],
                'default_symbol': 'BTC'
            },
            'data_quality': {
                'max_staleness_seconds': 120
            },
            'market_regime': {
                'extreme_price_change_1h': 0.05,
                'trend_price_change_6h': 0.03
            },
            'risk_exposure': {
                'liquidation': {'price_change': 0.05, 'oi_drop': -0.15},
                'crowding': {'funding_abs': 0.001, 'oi_growth': 0.30},
                'extreme_volume': {'multiplier': 10.0}
            },
            'trade_quality': {
                'absorption': {'imbalance': 0.7, 'volume_ratio': 0.5},
                'noise': {'funding_volatility': 0.0005, 'funding_abs': 0.0001},
                'rotation': {'price_threshold': 0.02, 'oi_threshold': 0.05},
                'range_weak': {'imbalance': 0.6, 'oi': 0.10}
            },
            'direction': {
                'trend': {
                    'long': {'imbalance': 0.6, 'oi_change': 0.05, 'price_change': 0.01},
                    'short': {'imbalance': 0.6, 'oi_change': 0.05, 'price_change': 0.01}
                },
                'range': {
                    'long': {'imbalance': 0.7, 'oi_change': 0.10},
                    'short': {'imbalance': 0.7, 'oi_change': 0.10}
                }
            },
            'decision_control': {
                'min_decision_interval_seconds': 300,
                'flip_cooldown_seconds': 600,
                'enable_min_interval': True,
                'enable_flip_cooldown': True
            }
        }
    
    def update_thresholds(self, new_thresholds: dict):
        """
        热更新阈值配置
        
        Args:
            new_thresholds: 新的阈值字典
        """
        self.thresholds.update(new_thresholds)
        logger.info(f"Thresholds updated: {len(new_thresholds)} items")
    
    def get_config(self) -> dict:
        """获取完整配置"""
        return self.config
    
    def get_thresholds(self) -> dict:
        """获取扁平化的阈值"""
        return self.thresholds
