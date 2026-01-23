/**
 * Formatters - 数据格式化工具
 * 
 * 职责：
 * 提供统一的数据格式化函数
 */

export class Formatters {
    /**
     * 格式化时间
     */
    static formatTime(timestamp) {
        const dt = new Date(timestamp);
        return dt.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }
    
    /**
     * 格式化指标值
     */
    static formatMetricValue(value) {
        if (typeof value === 'number') {
            if (Math.abs(value) < 0.01) {
                return (value * 100).toFixed(3) + '%';
            } else {
                return (value * 100).toFixed(2) + '%';
            }
        }
        return value;
    }
    
    /**
     * 格式化价格
     */
    static formatPrice(price) {
        if (price === null || price === undefined) return 'N/A';
        return '$' + price.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }
    
    /**
     * 格式化置信度标签
     */
    static formatConfidenceLabel(confidence) {
        const labels = {
            'ultra': '极高',
            'high': '高',
            'medium': '中',
            'low': '低'
        };
        return labels[confidence] || confidence;
    }
    
    /**
     * 格式化决策标签
     */
    static formatDecisionLabel(decision) {
        const labels = {
            'long': 'LONG',
            'short': 'SHORT',
            'no_trade': 'NO_TRADE'
        };
        return labels[decision] || decision;
    }
    
    /**
     * 获取决策图标
     */
    static getDecisionIcon(decision) {
        const icons = {
            'long': '🟢',
            'short': '🔴',
            'no_trade': '⚪'
        };
        return icons[decision] || '⚪';
    }
}
