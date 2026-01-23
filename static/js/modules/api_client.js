/**
 * API Client Module - API调用封装
 * 
 * 职责：
 * 1. 封装所有API调用
 * 2. 统一错误处理
 * 3. 请求/响应拦截
 */

export class APIClient {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
    }
    
    /**
     * 获取双周期决策
     */
    async fetchDualAdvisory(symbol) {
        try {
            const response = await fetch(`${this.baseURL}/api/l1/advisory-dual/${symbol}`);
            const result = await response.json();
            
            if (result.success && result.data) {
                return result.data;
            } else {
                console.error(`Failed to fetch dual advisory for ${symbol}:`, result.message);
                return null;
            }
        } catch (error) {
            console.error(`Error fetching dual advisory for ${symbol}:`, error);
            return null;
        }
    }
    
    /**
     * 获取双周期历史记录
     */
    async fetchDualHistory(symbol, hours = 24, limit = 1500) {
        try {
            const response = await fetch(`${this.baseURL}/api/l1/history-dual/${symbol}?hours=${hours}&limit=${limit}`);
            const result = await response.json();
            
            if (result.success && result.data) {
                return result.data;
            } else {
                console.error(`Failed to fetch dual history for ${symbol}:`, result.message);
                return [];
            }
        } catch (error) {
            console.error(`Error fetching dual history for ${symbol}:`, error);
            return [];
        }
    }
    
    /**
     * 获取reason tag解释
     */
    async loadReasonTagExplanations() {
        try {
            const response = await fetch(`${this.baseURL}/api/l1/reason-tags/explain`);
            const result = await response.json();
            
            if (result.success && result.data) {
                return result.data;
            }
            return {};
        } catch (error) {
            console.error('Error loading reason tag explanations:', error);
            return {};
        }
    }
    
    /**
     * 获取可用市场列表
     */
    async loadAvailableMarkets() {
        try {
            const response = await fetch(`${this.baseURL}/api/markets`);
            const result = await response.json();
            
            if (result.success && result.data) {
                return result.data;
            }
            return { symbols: [], default_symbol: 'BTC', markets: {} };
        } catch (error) {
            console.error('Error loading markets:', error);
            return { symbols: [], default_symbol: 'BTC', markets: {} };
        }
    }
    
    /**
     * 获取管道状态
     */
    async loadPipeline(symbol) {
        try {
            const response = await fetch(`${this.baseURL}/api/l1/pipeline/${symbol}`);
            const result = await response.json();
            
            if (result.success && result.data) {
                return result.data;
            }
            return { steps: [], message: '暂无管道数据' };
        } catch (error) {
            console.error(`Error loading pipeline for ${symbol}:`, error);
            return { steps: [], message: '加载失败' };
        }
    }
}

// 导出默认实例
export const apiClient = new APIClient();
