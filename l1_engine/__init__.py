"""
L1 Advisory Engine - 模块化引擎

本模块提供模块化的L1决策引擎实现，将原3486行的巨型文件拆分为清晰的模块：

核心模块：
- data_validator: 数据验证
- regime_detector: 市场环境识别
- risk_gates: 风险准入+交易质量
- signal_generator: 信号生成（方向评估）
- confidence_calculator: 置信度+执行许可计算
- frequency_controller: 频率控制
- memory: 决策记忆管理
- config_validator: 配置验证
- helper_utils: 辅助工具

向后兼容：
- 原始的L1AdvisoryEngine仍然从market_state_machine_l1.py导出
- 新的模块化版本可以通过单独导入各模块使用
"""

# 导入核心模块
from .data_validator import DataValidator
from .regime_detector import RegimeDetector
from .risk_gates import RiskGates
from .signal_generator import SignalGenerator
from .confidence_calculator import ConfidenceCalculator
from .frequency_controller import FrequencyController
from .memory import DecisionMemory, DualDecisionMemory
from .config_validator import ConfigValidator
from .helper_utils import HelperUtils

# 为了向后兼容，保留原始L1AdvisoryEngine的导入路径
# 用户可以继续使用：from market_state_machine_l1 import L1AdvisoryEngine
# 或者使用新的模块化导入

__all__ = [
    # 核心验证器和检测器
    'DataValidator',
    'RegimeDetector',
    'RiskGates',
    'SignalGenerator',
    'ConfidenceCalculator',
    'FrequencyController',
    
    # 记忆管理
    'DecisionMemory',
    'DualDecisionMemory',
    
    # 配置和工具
    'ConfigValidator',
    'HelperUtils',
]


# 提供便利函数用于创建完整的引擎实例（未来扩展）
def create_l1_engine(config_path: str = None):
    """
    创建L1引擎实例（模块化版本）
    
    注意：当前仍推荐使用原始的L1AdvisoryEngine
    未来版本将提供完全模块化的引擎实现
    
    Args:
        config_path: 配置文件路径
    
    Returns:
        L1AdvisoryEngine实例
    """
    # 为了向后兼容，暂时导入原始引擎
    from market_state_machine_l1 import L1AdvisoryEngine
    return L1AdvisoryEngine(config_path)
