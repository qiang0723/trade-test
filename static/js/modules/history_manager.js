/**
 * History Manager Module - 历史记录管理模块
 * 
 * 职责：
 * 1. 加载和过滤历史记录
 * 2. 分页管理
 * 3. 统计数据计算
 */

export class HistoryManager {
    constructor() {
        this.allHistoryData = [];
        this.filteredHistoryData = [];
        this.currentPage = 1;
        this.pageSize = 20;
        this.totalPages = 1;
    }
    
    /**
     * 加载历史记录列表
     */
    async loadHistoryList(apiClient, availableSymbols) {
        try {
            const hours = parseInt(document.getElementById('filterHours').value) || 24;
            const filterSymbol = document.getElementById('filterSymbol').value;
            
            if (filterSymbol === 'all') {
                this.allHistoryData = [];
                
                const promises = availableSymbols.map(symbol => 
                    apiClient.fetchDualHistory(symbol, hours, 2000).then(history => {
                        return history.map(item => ({...item, symbol: symbol}));
                    }).catch(err => {
                        console.error(`Failed to fetch dual history for ${symbol}:`, err);
                        return [];
                    })
                );
                
                const results = await Promise.all(promises);
                
                results.forEach(symbolHistory => {
                    this.allHistoryData = this.allHistoryData.concat(symbolHistory);
                });
                
                this.allHistoryData.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
                
            } else {
                const history = await apiClient.fetchDualHistory(filterSymbol, hours, 2000);
                this.allHistoryData = history.map(item => ({...item, symbol: filterSymbol}));
            }
            
            if (this.allHistoryData && this.allHistoryData.length > 0) {
                this.applyFilters();
            } else {
                this.allHistoryData = [];
                this.filteredHistoryData = [];
            }
        } catch (error) {
            console.error('Error loading history list:', error);
        }
    }
    
    /**
     * 应用过滤条件
     */
    applyFilters() {
        const symbol = document.getElementById('filterSymbol').value;
        const timeframe = document.getElementById('filterTimeframe')?.value || 'all';
        const decision = document.getElementById('filterDecision').value;
        
        // 扁平化双周期历史数据为单行
        let flattenedData = [];
        this.allHistoryData.forEach(item => {
            // 短期记录
            if (item.short_term) {
                flattenedData.push({
                    ...item.short_term,
                    symbol: item.symbol,
                    timeframe: 'short',
                    timeframe_label: '短期(5m/15m)',
                    timestamp: item.timestamp,
                    price: item.price,
                    alignment_type: item.alignment?.alignment_type
                });
            }
            // 中长期记录
            if (item.medium_term) {
                flattenedData.push({
                    ...item.medium_term,
                    symbol: item.symbol,
                    timeframe: 'medium',
                    timeframe_label: '中长(1h/6h)',
                    timestamp: item.timestamp,
                    price: item.price,
                    alignment_type: item.alignment?.alignment_type
                });
            }
        });
        
        // 应用筛选
        this.filteredHistoryData = flattenedData.filter(item => {
            if (item.decision === 'no_trade') return false;
            if (symbol !== 'all' && item.symbol !== symbol) return false;
            if (timeframe !== 'all' && item.timeframe !== timeframe) return false;
            if (decision !== 'all' && item.decision !== decision) return false;
            return true;
        });
        
        this.currentPage = 1;
        this.totalPages = Math.ceil(this.filteredHistoryData.length / this.pageSize);
    }
    
    /**
     * 渲染当前页
     */
    renderCurrentPage(renderer) {
        const startIndex = (this.currentPage - 1) * this.pageSize;
        const endIndex = Math.min(startIndex + this.pageSize, this.filteredHistoryData.length);
        const pageData = this.filteredHistoryData.slice(startIndex, endIndex);
        
        renderer.renderHistoryTable(pageData);
        this.updatePaginationControls();
    }
    
    /**
     * 更新分页控件
     */
    updatePaginationControls() {
        const totalItems = this.filteredHistoryData.length;
        const startIndex = (this.currentPage - 1) * this.pageSize + 1;
        const endIndex = Math.min(this.currentPage * this.pageSize, totalItems);
        
        document.getElementById('pageStart').textContent = totalItems > 0 ? startIndex : 0;
        document.getElementById('pageEnd').textContent = endIndex;
        document.getElementById('pageTotal').textContent = totalItems;
        document.getElementById('currentPageInput').value = this.currentPage;
        document.getElementById('totalPages').textContent = this.totalPages;
        
        document.getElementById('btnFirstPage').disabled = this.currentPage === 1;
        document.getElementById('btnPrevPage').disabled = this.currentPage === 1;
        document.getElementById('btnNextPage').disabled = this.currentPage === this.totalPages;
        document.getElementById('btnLastPage').disabled = this.currentPage === this.totalPages;
    }
    
    /**
     * 跳转到指定页
     */
    goToPage(page, renderer) {
        if (page < 1 || page > this.totalPages) return;
        this.currentPage = page;
        this.renderCurrentPage(renderer);
    }
    
    /**
     * 上一页
     */
    previousPage(renderer) {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.renderCurrentPage(renderer);
        }
    }
    
    /**
     * 下一页
     */
    nextPage(renderer) {
        if (this.currentPage < this.totalPages) {
            this.currentPage++;
            this.renderCurrentPage(renderer);
        }
    }
    
    /**
     * 最后一页
     */
    lastPage(renderer) {
        this.currentPage = this.totalPages;
        this.renderCurrentPage(renderer);
    }
    
    /**
     * 更改每页条数
     */
    changePageSize(newSize, renderer) {
        this.pageSize = newSize;
        this.currentPage = 1;
        this.totalPages = Math.ceil(this.filteredHistoryData.length / this.pageSize);
        this.renderCurrentPage(renderer);
    }
}

// 导出默认实例
export const historyManager = new HistoryManager();
