"""
P1-07: ThresholdCompiler - 配置强化校验

功能：
1. 类型校验：caps/tag_caps值必须是Confidence enum
2. 范围校验：min_volume_ratio>0, required_confirmed>=required_partial
3. 依赖校验：deny/reduce tags必须是已注册ReasonTag
4. 输出thresholds_version_hash

设计原则：
- 配置错误fail-fast（启动/加载失败），不允许静默运行
- 所有校验规则可扩展
"""

import hashlib
import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

# yaml是可选依赖，用于加载配置文件
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """校验级别"""
    ERROR = "error"      # 必须修复，否则启动失败
    WARNING = "warning"  # 应该修复，但允许启动


@dataclass
class ValidationResult:
    """校验结果"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    version_hash: str
    
    def to_dict(self) -> Dict:
        return {
            'is_valid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'version_hash': self.version_hash
        }


class ThresholdCompiler:
    """
    配置编译器 - 强化校验
    
    校验规则：
    1. 类型约束：caps必须是Confidence enum名称
    2. 范围约束：min_volume_ratio>0, 百分比在合理范围
    3. 逻辑约束：required_confirmed >= required_partial
    4. 依赖约束：deny/reduce tags必须是已注册ReasonTag
    """
    
    # 有效的Confidence级别
    VALID_CONFIDENCE_LEVELS = {'ULTRA', 'HIGH', 'MEDIUM', 'LOW'}
    
    def __init__(self):
        self._registered_reason_tags: Optional[set] = None
    
    def _get_registered_reason_tags(self) -> set:
        """获取已注册的ReasonTag值"""
        if self._registered_reason_tags is None:
            try:
                from models.reason_tags import ReasonTag
                self._registered_reason_tags = {tag.value for tag in ReasonTag}
            except ImportError:
                logger.warning("Cannot import ReasonTag, skip tag validation")
                self._registered_reason_tags = set()
        return self._registered_reason_tags
    
    def compile(self, config: Dict) -> ValidationResult:
        """
        编译并校验配置
        
        Args:
            config: 配置字典
        
        Returns:
            ValidationResult: 校验结果
        """
        errors = []
        warnings = []
        
        # 1. 类型校验
        type_errors, type_warnings = self._validate_types(config)
        errors.extend(type_errors)
        warnings.extend(type_warnings)
        
        # 2. 范围校验
        range_errors, range_warnings = self._validate_ranges(config)
        errors.extend(range_errors)
        warnings.extend(range_warnings)
        
        # 3. 逻辑约束校验
        logic_errors, logic_warnings = self._validate_logic_constraints(config)
        errors.extend(logic_errors)
        warnings.extend(logic_warnings)
        
        # 4. 依赖校验
        dep_errors, dep_warnings = self._validate_dependencies(config)
        errors.extend(dep_errors)
        warnings.extend(dep_warnings)
        
        # 5. 计算版本哈希
        version_hash = self._compute_version_hash(config)
        
        is_valid = len(errors) == 0
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            version_hash=version_hash
        )
    
    def _validate_types(self, config: Dict) -> Tuple[List[str], List[str]]:
        """类型校验"""
        errors = []
        warnings = []
        
        # 校验confidence_scoring.caps.tag_caps
        caps = config.get('confidence_scoring', {}).get('caps', {})
        tag_caps = caps.get('tag_caps', {})
        
        for tag_key, cap_value in tag_caps.items():
            cap_upper = cap_value.upper() if isinstance(cap_value, str) else str(cap_value).upper()
            if cap_upper not in self.VALID_CONFIDENCE_LEVELS:
                errors.append(
                    f"[TYPE] tag_caps['{tag_key}'] = '{cap_value}' is not a valid Confidence level. "
                    f"Valid values: {self.VALID_CONFIDENCE_LEVELS}"
                )
        
        # 校验caps.uncertain_quality_max
        uncertain_max = caps.get('uncertain_quality_max')
        if uncertain_max:
            cap_upper = uncertain_max.upper() if isinstance(uncertain_max, str) else str(uncertain_max).upper()
            if cap_upper not in self.VALID_CONFIDENCE_LEVELS:
                errors.append(
                    f"[TYPE] caps.uncertain_quality_max = '{uncertain_max}' is not a valid Confidence level"
                )
        
        # 校验caps.reduce_default_max
        reduce_max = caps.get('reduce_default_max')
        if reduce_max:
            cap_upper = reduce_max.upper() if isinstance(reduce_max, str) else str(reduce_max).upper()
            if cap_upper not in self.VALID_CONFIDENCE_LEVELS:
                errors.append(
                    f"[TYPE] caps.reduce_default_max = '{reduce_max}' is not a valid Confidence level"
                )
        
        # 校验executable_control的confidence值
        exec_control = config.get('executable_control', {})
        for key in ['min_confidence_normal', 'min_confidence_reduced']:
            value = exec_control.get(key)
            if value:
                val_upper = value.upper() if isinstance(value, str) else str(value).upper()
                if val_upper not in self.VALID_CONFIDENCE_LEVELS:
                    errors.append(
                        f"[TYPE] executable_control.{key} = '{value}' is not a valid Confidence level"
                    )
        
        return errors, warnings
    
    def _validate_ranges(self, config: Dict) -> Tuple[List[str], List[str]]:
        """范围校验"""
        errors = []
        warnings = []
        
        # 校验multi_tf中的volume_ratio > 0
        multi_tf = config.get('multi_tf', {})
        for layer in ['confirm_15m', 'trigger_5m']:
            layer_config = multi_tf.get(layer, {})
            for direction in ['long', 'short']:
                dir_config = layer_config.get(direction, {})
                volume_ratio = dir_config.get('min_volume_ratio')
                if volume_ratio is not None and volume_ratio <= 0:
                    errors.append(
                        f"[RANGE] multi_tf.{layer}.{direction}.min_volume_ratio = {volume_ratio} must be > 0"
                    )
        
        # 校验confidence_scoring.thresholds递减
        scoring = config.get('confidence_scoring', {})
        thresholds = scoring.get('thresholds', {})
        ultra = thresholds.get('ultra', 90)
        high = thresholds.get('high', 65)
        medium = thresholds.get('medium', 45)
        
        if not (ultra > high > medium > 0):
            errors.append(
                f"[RANGE] confidence thresholds must be ultra({ultra}) > high({high}) > medium({medium}) > 0"
            )
        
        # 校验百分比阈值在合理范围
        direction = config.get('direction', {})
        for regime in ['trend', 'range']:
            regime_config = direction.get(regime, {})
            for dir_key in ['long', 'short']:
                dir_config = regime_config.get(dir_key, {})
                # 检查imbalance范围
                imbalance = dir_config.get('imbalance')
                if imbalance is not None and abs(imbalance) > 1.0:
                    warnings.append(
                        f"[RANGE] direction.{regime}.{dir_key}.imbalance = {imbalance} seems unusual (>100%)"
                    )
        
        # 校验risk_exposure阈值
        risk = config.get('risk_exposure', {})
        liquidation = risk.get('liquidation', {})
        price_change = liquidation.get('price_change')
        if price_change is not None and price_change > 0.5:
            warnings.append(
                f"[RANGE] risk_exposure.liquidation.price_change = {price_change} (>{0.5}=50%) seems too high"
            )
        
        return errors, warnings
    
    def _validate_logic_constraints(self, config: Dict) -> Tuple[List[str], List[str]]:
        """逻辑约束校验"""
        errors = []
        warnings = []
        
        # 校验required_confirmed >= required_partial
        multi_tf = config.get('multi_tf', {})
        confirm_15m = multi_tf.get('confirm_15m', {})
        
        for direction in ['long', 'short']:
            dir_config = confirm_15m.get(direction, {})
            required_confirmed = dir_config.get('required_confirmed', 2)
            required_partial = dir_config.get('required_partial', 1)
            
            if required_confirmed < required_partial:
                errors.append(
                    f"[LOGIC] multi_tf.confirm_15m.{direction}: "
                    f"required_confirmed({required_confirmed}) must be >= required_partial({required_partial})"
                )
        
        # 校验min_confidence_reduced <= caps.reduce_default_max
        exec_control = config.get('executable_control', {})
        caps = config.get('confidence_scoring', {}).get('caps', {})
        
        min_reduced = exec_control.get('min_confidence_reduced', 'MEDIUM')
        reduce_max = caps.get('reduce_default_max', 'MEDIUM')
        
        # 比较逻辑
        conf_order = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3, 'ULTRA': 4}
        min_reduced_order = conf_order.get(min_reduced.upper(), 0)
        reduce_max_order = conf_order.get(reduce_max.upper(), 0)
        
        if min_reduced_order > reduce_max_order:
            errors.append(
                f"[LOGIC] min_confidence_reduced({min_reduced}) cannot be higher than "
                f"caps.reduce_default_max({reduce_max})"
            )
        
        # 校验tag_caps值 >= min_confidence_reduced
        tag_caps = caps.get('tag_caps', {})
        for tag_key, cap_value in tag_caps.items():
            cap_order = conf_order.get(cap_value.upper() if isinstance(cap_value, str) else str(cap_value).upper(), 0)
            if cap_order < min_reduced_order:
                warnings.append(
                    f"[LOGIC] tag_caps['{tag_key}'] = '{cap_value}' is lower than "
                    f"min_confidence_reduced({min_reduced}), signal will never be executable"
                )
        
        return errors, warnings
    
    def _validate_dependencies(self, config: Dict) -> Tuple[List[str], List[str]]:
        """依赖校验 - deny/reduce tags必须是已注册ReasonTag"""
        errors = []
        warnings = []
        
        registered_tags = self._get_registered_reason_tags()
        if not registered_tags:
            warnings.append("[DEP] Cannot validate ReasonTag dependencies (import failed)")
            return errors, warnings
        
        # 校验reason_tag_rules
        tag_rules = config.get('reason_tag_rules', {})
        
        # 检查reduce_tags
        reduce_tags = tag_rules.get('reduce_tags', [])
        for tag in reduce_tags:
            if tag not in registered_tags:
                errors.append(
                    f"[DEP] reason_tag_rules.reduce_tags contains unregistered tag: '{tag}'"
                )
        
        # 检查deny_tags
        deny_tags = tag_rules.get('deny_tags', [])
        for tag in deny_tags:
            if tag not in registered_tags:
                errors.append(
                    f"[DEP] reason_tag_rules.deny_tags contains unregistered tag: '{tag}'"
                )
        
        # 检查tag_caps中的tag是否存在
        caps = config.get('confidence_scoring', {}).get('caps', {})
        tag_caps = caps.get('tag_caps', {})
        for tag_key in tag_caps.keys():
            if tag_key not in registered_tags:
                warnings.append(
                    f"[DEP] tag_caps['{tag_key}'] references unregistered ReasonTag"
                )
        
        return errors, warnings
    
    def _compute_version_hash(self, config: Dict) -> str:
        """计算配置版本哈希"""
        # 序列化配置为字符串（使用json以确保跨平台一致性）
        config_str = json.dumps(config, sort_keys=True, default=str)
        # 计算SHA256哈希，取前8位
        hash_full = hashlib.sha256(config_str.encode()).hexdigest()
        return hash_full[:8]


def load_and_validate_thresholds(config_path: str = None) -> Tuple[Dict, ValidationResult]:
    """
    加载并校验配置（便捷函数）
    
    Args:
        config_path: 配置文件路径，默认为config/l1_thresholds.yaml
    
    Returns:
        (config, validation_result): 配置字典和校验结果
    
    Raises:
        ValueError: 如果校验失败（有ERROR级别错误）
        ImportError: 如果yaml模块不可用
    """
    if not HAS_YAML:
        raise ImportError("PyYAML is required for loading config files. Install with: pip install pyyaml")
    
    if config_path is None:
        # 默认路径
        config_path = Path(__file__).parent / 'l1_thresholds.yaml'
    else:
        config_path = Path(config_path)
    
    # 加载配置
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 校验配置
    compiler = ThresholdCompiler()
    result = compiler.compile(config)
    
    # 输出结果
    if result.errors:
        logger.error(f"Threshold validation FAILED with {len(result.errors)} errors:")
        for err in result.errors:
            logger.error(f"  - {err}")
    
    if result.warnings:
        logger.warning(f"Threshold validation completed with {len(result.warnings)} warnings:")
        for warn in result.warnings:
            logger.warning(f"  - {warn}")
    
    logger.info(f"Threshold version hash: {result.version_hash}")
    
    # fail-fast：有错误则抛出异常
    if not result.is_valid:
        raise ValueError(
            f"Threshold configuration validation failed with {len(result.errors)} errors. "
            f"Fix the errors and restart."
        )
    
    return config, result


# 单例缓存
_cached_config: Optional[Dict] = None
_cached_result: Optional[ValidationResult] = None


def get_validated_thresholds() -> Tuple[Dict, ValidationResult]:
    """
    获取已校验的配置（带缓存）
    
    Returns:
        (config, validation_result)
    """
    global _cached_config, _cached_result
    
    if _cached_config is None:
        _cached_config, _cached_result = load_and_validate_thresholds()
    
    return _cached_config, _cached_result


def clear_threshold_cache():
    """清除配置缓存（用于测试）"""
    global _cached_config, _cached_result
    _cached_config = None
    _cached_result = None
