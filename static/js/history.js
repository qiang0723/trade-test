// 历史信号数据管理
let allSignals = [];
let filteredSignals = [];
let currentPage = 1;
const pageSize = 10;

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
    loadSignals();
    setupEventListeners();
    // 每60秒自动刷新
    setInterval(loadSignals, 60000);
});

// 设置事件监听器
function setupEventListeners() {
    document.getElementById('refreshBtn').addEventListener('click', loadSignals);
    document.getElementById('cleanupBtn').addEventListener('click', cleanupOldSignals);
    document.getElementById('symbolFilter').addEventListener('change', applyFilters);
    document.getElementById('actionFilter').addEventListener('change', applyFilters);
}

// 加载信号数据
async function loadSignals() {
    try {
        showLoading();
        
        // 并行加载信号和统计数据
        const [signalsRes, accuracyRes] = await Promise.all([
            fetch('/api/signals-48h'),
            fetch('/api/signal-accuracy')
        ]);
        
        const signalsData = await signalsRes.json();
        const accuracyData = await accuracyRes.json();
        
        if (signalsData.success) {
            allSignals = signalsData.signals;
            applyFilters();
        } else {
            showError('加载信号失败: ' + signalsData.error);
        }
        
        if (accuracyData.success) {
            updateStatistics(accuracyData.analysis);
        }
        
    } catch (error) {
        showError('加载数据失败: ' + error.message);
    }
}

// 更新统计数据
function updateStatistics(analysis) {
    document.getElementById('totalSignals').textContent = analysis.total_signals || 0;
    document.getElementById('longSignals').textContent = analysis.long_count || 0;
    document.getElementById('shortSignals').textContent = analysis.short_count || 0;
    document.getElementById('noTradeSignals').textContent = analysis.no_trade_count || 0;
    
    document.getElementById('longPercentage').textContent = `${analysis.long_percentage || 0}%`;
    document.getElementById('shortPercentage').textContent = `${analysis.short_percentage || 0}%`;
    document.getElementById('noTradePercentage').textContent = `${analysis.no_trade_percentage || 0}%`;
    
    // 更新时间范围
    if (analysis.oldest_signal && analysis.newest_signal) {
        const oldest = new Date(analysis.oldest_signal).toLocaleString('zh-CN');
        const newest = new Date(analysis.newest_signal).toLocaleString('zh-CN');
        document.getElementById('timeRange').textContent = `时间范围: ${oldest} ~ ${newest}`;
    } else {
        document.getElementById('timeRange').textContent = '时间范围: 暂无数据';
    }
}

// 应用筛选器
function applyFilters() {
    const symbolFilter = document.getElementById('symbolFilter').value;
    const actionFilter = document.getElementById('actionFilter').value;
    
    filteredSignals = allSignals.filter(signal => {
        let match = true;
        
        if (symbolFilter && signal.symbol !== symbolFilter) {
            match = false;
        }
        
        if (actionFilter && signal.trade_action !== actionFilter) {
            match = false;
        }
        
        return match;
    });
    
    currentPage = 1;
    renderSignals();
}

// 渲染信号列表
function renderSignals() {
    const container = document.getElementById('historyContainer');
    
    if (filteredSignals.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <div class="empty-state-text">暂无符合条件的历史记录</div>
            </div>
        `;
        return;
    }
    
    // 分页
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    const pageSignals = filteredSignals.slice(start, end);
    
    let html = '';
    pageSignals.forEach(signal => {
        html += renderSignalCard(signal);
    });
    
    // 添加分页控件
    html += renderPagination();
    
    container.innerHTML = html;
    
    // 绑定展开/收起事件
    document.querySelectorAll('.signal-item').forEach(item => {
        item.addEventListener('click', function() {
            this.classList.toggle('expanded');
        });
    });
}

// 渲染单个信号卡片
function renderSignalCard(signal) {
    const actionClass = signal.trade_action.toLowerCase().replace('_', '-');
    const actionText = {
        'LONG': '做多',
        'SHORT': '做空',
        'NO_TRADE': '观望'
    }[signal.trade_action] || signal.trade_action;
    
    const time = new Date(signal.timestamp).toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    
    return `
        <div class="signal-item ${actionClass}">
            <div class="signal-header">
                <div class="signal-symbol">${signal.symbol}/USDT</div>
                <div class="signal-action ${actionClass}">${actionText}</div>
            </div>
            
            <div class="signal-time">⏰ ${time}</div>
            
            <div class="signal-data">
                <div class="signal-data-item">
                    <span class="signal-data-label">价格</span>
                    <span class="signal-data-value">$${formatNumber(signal.price, 4)}</span>
                </div>
                <div class="signal-data-item">
                    <span class="signal-data-label">24h涨跌</span>
                    <span class="signal-data-value ${signal.price_change_24h >= 0 ? 'positive' : 'negative'}">
                        ${formatPercent(signal.price_change_24h)}
                    </span>
                </div>
                <div class="signal-data-item">
                    <span class="signal-data-label">6h趋势</span>
                    <span class="signal-data-value ${signal.price_trend_6h >= 0 ? 'positive' : 'negative'}">
                        ${formatPercent(signal.price_trend_6h)}
                    </span>
                </div>
                <div class="signal-data-item">
                    <span class="signal-data-label">资金费率</span>
                    <span class="signal-data-value ${signal.funding_rate >= 0 ? 'positive' : 'negative'}">
                        ${formatPercent(signal.funding_rate, 4)}
                    </span>
                </div>
            </div>
            
            <div class="signal-details">
                <div class="signal-data">
                    <div class="signal-data-item">
                        <span class="signal-data-label">成交量变化</span>
                        <span class="signal-data-value ${signal.volume_change_6h >= 0 ? 'positive' : 'negative'}">
                            ${formatPercent(signal.volume_change_6h)}
                        </span>
                    </div>
                    <div class="signal-data-item">
                        <span class="signal-data-label">持仓量变化</span>
                        <span class="signal-data-value ${signal.oi_change_6h >= 0 ? 'positive' : 'negative'}">
                            ${formatPercent(signal.oi_change_6h)}
                        </span>
                    </div>
                    <div class="signal-data-item">
                        <span class="signal-data-label">1h买单占比</span>
                        <span class="signal-data-value">${formatPercent(signal.buy_ratio_1h)}</span>
                    </div>
                    <div class="signal-data-item">
                        <span class="signal-data-label">1h卖单占比</span>
                        <span class="signal-data-value">${formatPercent(signal.sell_ratio_1h)}</span>
                    </div>
                </div>
                
                ${signal.state_reason ? `
                    <div class="signal-reason">
                        <strong>决策原因：</strong>${signal.state_reason}
                    </div>
                ` : ''}
            </div>
            
            <div class="signal-expand-btn">点击展开/收起详情</div>
        </div>
    `;
}

// 渲染分页控件
function renderPagination() {
    const totalPages = Math.ceil(filteredSignals.length / pageSize);
    
    if (totalPages <= 1) return '';
    
    return `
        <div class="pagination">
            <button onclick="goToPage(${currentPage - 1})" ${currentPage === 1 ? 'disabled' : ''}>
                上一页
            </button>
            <span class="page-info">第 ${currentPage} / ${totalPages} 页</span>
            <button onclick="goToPage(${currentPage + 1})" ${currentPage === totalPages ? 'disabled' : ''}>
                下一页
            </button>
        </div>
    `;
}

// 跳转到指定页
function goToPage(page) {
    const totalPages = Math.ceil(filteredSignals.length / pageSize);
    if (page < 1 || page > totalPages) return;
    
    currentPage = page;
    renderSignals();
}

// 清理旧信号
async function cleanupOldSignals() {
    if (!confirm('确定要清理48小时前的旧数据吗？')) {
        return;
    }
    
    try {
        const response = await fetch('/api/cleanup-old-signals?hours=48');
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ ${data.message}`);
            loadSignals();
        } else {
            alert('❌ 清理失败: ' + data.error);
        }
    } catch (error) {
        alert('❌ 清理失败: ' + error.message);
    }
}

// 显示加载状态
function showLoading() {
    document.getElementById('historyContainer').innerHTML = `
        <div class="loading">正在加载历史数据...</div>
    `;
}

// 显示错误
function showError(message) {
    document.getElementById('historyContainer').innerHTML = `
        <div class="empty-state">
            <div class="empty-state-icon">❌</div>
            <div class="empty-state-text">${message}</div>
        </div>
    `;
}

// 格式化数字
function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined) return '-';
    return parseFloat(num).toFixed(decimals);
}

// 格式化百分比
function formatPercent(num, decimals = 2) {
    if (num === null || num === undefined) return '-';
    const value = parseFloat(num).toFixed(decimals);
    return value >= 0 ? `+${value}%` : `${value}%`;
}
