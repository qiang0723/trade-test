/**
 * Constants - 常量定义
 * 
 * 职责：
 * 定义全局常量和配置
 */

export const Constants = {
    // 刷新间隔（毫秒）
    AUTO_REFRESH_INTERVAL: 60000,  // 1分钟
    
    // 分页
    DEFAULT_PAGE_SIZE: 20,
    PAGE_SIZE_OPTIONS: [10, 20, 50, 100],
    
    // 历史记录查询
    DEFAULT_HISTORY_HOURS: 24,
    MAX_HISTORY_LIMIT: 2000,
    
    // 通知
    POPUP_AUTO_CLOSE_DELAY: 10000,  // 10秒
    NOTIFICATION_STAGGER_DELAY: 500,  // 每个通知间隔500ms
    
    // 决策类型
    DECISION_TYPES: {
        LONG: 'long',
        SHORT: 'short',
        NO_TRADE: 'no_trade'
    },
    
    // 置信度级别
    CONFIDENCE_LEVELS: {
        ULTRA: 'ultra',
        HIGH: 'high',
        MEDIUM: 'medium',
        LOW: 'low'
    },
    
    // 周期标识
    TIMEFRAMES: {
        SHORT_TERM: 'short_term',
        MEDIUM_TERM: 'medium_term'
    },
    
    // 一致性类型
    ALIGNMENT_TYPES: {
        BOTH_LONG: 'both_long',
        BOTH_SHORT: 'both_short',
        BOTH_NO_TRADE: 'both_no_trade',
        CONFLICT: 'conflict',
        PARTIAL_LONG: 'partial_long',
        PARTIAL_SHORT: 'partial_short'
    }
};
