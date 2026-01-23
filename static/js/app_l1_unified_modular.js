/**
 * L1 Advisory Layer - Unified Dual Timeframe Frontend (模块化版本)
 * 
 * 这是重构后的精简版本，将功能拆分到独立模块：
 * - modules/api_client.js: API调用封装
 * - modules/dual_decision.js: 双周期决策渲染
 * - modules/signal_notification.js: 信号通知
 * - modules/history_manager.js: 历史记录管理
 * - utils/formatters.js: 数据格式化
 * - utils/constants.js: 常量定义
 * 
 * 原始版本 app_l1_unified.js 保持不变，确保向后兼容。
 */

import { apiClient } from './modules/api_client.js';
import { signalNotification } from './modules/signal_notification.js';
import { dualDecisionRenderer } from './modules/dual_decision.js';
import { historyManager } from './modules/history_manager.js';
import { Formatters } from './utils/formatters.js';
import { Constants } from './utils/constants.js';

// ==========================================
// 全局状态
// ==========================================

let availableSymbols = [];
let allDualDecisions = {};
let reasonTagExplanations = {};

// ==========================================
// 初始化
// ==========================================

document.addEventListener('DOMContentLoaded', async function() {
    console.log('L1 Unified Dual Timeframe Frontend (Modular) initialized');
    
    // 请求浏览器通知权限
    signalNotification.requestPermission();
    
    // 加载reason tag解释
    reasonTagExplanations = await apiClient.loadReasonTagExplanations();
    dualDecisionRenderer.reasonTagExplanations = reasonTagExplanations;
    
    // 加载可用市场
    const marketData = await apiClient.loadAvailableMarkets();
    availableSymbols = marketData.symbols || [];
    
    // 初始化历史记录的币种筛选下拉框
    initHistorySymbolFilter(availableSymbols);
    
    // 启动自动刷新
    startAutoRefresh();
    
    // 更新按钮状态
    updateNotificationButton();
    updateSoundButton();
});

function initHistorySymbolFilter(symbols) {
    const filterSymbol = document.getElementById('filterSymbol');
    if (!filterSymbol) return;
    
    filterSymbol.innerHTML = '<option value="all">全部币种</option>';
    symbols.forEach(symbol => {
        const option = document.createElement('option');
        option.value = symbol;
        option.textContent = symbol;
        filterSymbol.appendChild(option);
    });
}

// ==========================================
// 主刷新逻辑
// ==========================================

async function refreshAdvisory() {
    console.log('Refreshing dual advisory for all symbols...');
    
    if (!availableSymbols || availableSymbols.length === 0) {
        console.error('No available symbols');
        return;
    }
    
    // 并行获取所有币种的双周期决策
    const promises = availableSymbols.map(symbol => 
        apiClient.fetchDualAdvisory(symbol).then(dualAdvisory => ({
            symbol: symbol,
            dualAdvisory: dualAdvisory
        })).catch(err => {
            console.error(`Failed to fetch dual advisory for ${symbol}:`, err);
            return { symbol: symbol, dualAdvisory: null };
        })
    );
    
    const results = await Promise.all(promises);
    
    // 检测交易信号变化
    const newDecisions = {};
    results.forEach(({symbol, dualAdvisory}) => {
        if (dualAdvisory) {
            newDecisions[symbol] = dualAdvisory;
        }
    });
    
    signalNotification.checkForNewSignals(newDecisions);
    
    // 更新决策缓存
    allDualDecisions = newDecisions;
    
    // 更新所有币种的决策面板
    dualDecisionRenderer.updateAllDecisionsPanel(allDualDecisions, availableSymbols);
    
    // 加载历史决策列表
    await historyManager.loadHistoryList(apiClient, availableSymbols);
    historyManager.renderCurrentPage(createHistoryRenderer());
    
    // 更新最后更新时间
    updateLastUpdateTime();
}

function createHistoryRenderer() {
    return {
        renderHistoryTable: (data) => {
            const tbody = document.getElementById('historyTableBody');
            
            if (!data || data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" class="table-empty">暂无符合条件的历史记录</td></tr>';
                return;
            }
            
            tbody.innerHTML = '';
            
            data.forEach(item => {
                const row = document.createElement('tr');
                row.className = `history-row ${item.decision}`;
                
                const timeStr = Formatters.formatTime(item.timestamp);
                const decisionIcon = Formatters.getDecisionIcon(item.decision);
                const decisionLabel = Formatters.formatDecisionLabel(item.decision);
                const confidenceLabel = Formatters.formatConfidenceLabel(item.confidence);
                
                const executableBadge = item.executable 
                    ? '<span class="badge badge-success">✓</span>'
                    : '<span class="badge badge-danger">✗</span>';
                
                const reasonText = (item.reason_tags || []).slice(0, 3).map(tag => {
                    const tagData = reasonTagExplanations[tag];
                    return tagData ? tagData.explanation : tag;
                }).join(', ');
                
                row.innerHTML = `
                    <td class="col-symbol"><span class="symbol-badge">${item.symbol || 'N/A'}</span></td>
                    <td class="col-timeframe">${item.timeframe_label || 'N/A'}</td>
                    <td class="col-time">${timeStr}</td>
                    <td class="col-decision">
                        <span class="decision-badge ${item.decision}">${decisionIcon} ${decisionLabel}</span>
                    </td>
                    <td class="col-confidence">
                        <span class="confidence-badge confidence-${item.confidence}">${confidenceLabel}</span>
                    </td>
                    <td class="col-executable">${executableBadge}</td>
                    <td class="col-reason">${reasonText || '无'}</td>
                `;
                
                row.onclick = () => showHistoryDetailModal(item);
                row.style.cursor = 'pointer';
                
                tbody.appendChild(row);
            });
            
            // 更新统计
            updateHistoryStats(data);
        }
    };
}

function updateHistoryStats(data) {
    const stats = {
        total: data.length,
        long: data.filter(item => item.decision === 'long').length,
        short: data.filter(item => item.decision === 'short').length,
        no_trade: data.filter(item => item.decision === 'no_trade').length
    };
    
    document.getElementById('statTotal').textContent = stats.total;
    document.getElementById('statLong').textContent = stats.long;
    document.getElementById('statShort').textContent = stats.short;
    document.getElementById('statNoTrade').textContent = stats.no_trade;
}

function showHistoryDetailModal(item) {
    const allTags = (item.reason_tags || []).map(tag => {
        const tagData = reasonTagExplanations[tag];
        return tagData ? `• ${tagData.explanation} (${tag})` : `• ${tag}`;
    }).join('\n');
    
    const priceInfo = item.price ? `\n💰 价格: ${Formatters.formatPrice(item.price)}` : '';
    
    const detail = `
📊 决策详情

交易对: ${item.symbol}
周期: ${item.timeframe_label || 'N/A'}
时间: ${Formatters.formatTime(item.timestamp)}${priceInfo}

【核心决策】
决策: ${item.decision.toUpperCase()}
置信度: ${item.confidence.toUpperCase()}
可执行: ${item.executable ? '是' : '否'}

【决策依据】
${allTags || '无'}
    `.trim();
    
    alert(detail);
}

// ==========================================
// 自动刷新
// ==========================================

function startAutoRefresh() {
    refreshAdvisory();
    
    setInterval(() => {
        refreshAdvisory();
    }, Constants.AUTO_REFRESH_INTERVAL);
}

function updateLastUpdateTime() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
    document.getElementById('lastUpdate').textContent = timeStr;
}

// ==========================================
// 按钮更新
// ==========================================

function updateNotificationButton() {
    const button = document.getElementById('toggleNotificationBtn');
    if (button) {
        button.textContent = signalNotification.enabled ? '🔔 通知已开启' : '🔕 通知已关闭';
        button.classList.toggle('disabled', !signalNotification.enabled);
    }
}

function updateSoundButton() {
    const button = document.getElementById('toggleSoundBtn');
    if (button) {
        button.textContent = signalNotification.soundEnabled ? '🔊 声音已开启' : '🔇 声音已关闭';
        button.classList.toggle('disabled', !signalNotification.soundEnabled);
    }
}

// ==========================================
// 全局函数导出（供HTML直接调用）
// ==========================================

window.refreshAdvisory = refreshAdvisory;
window.toggleSignalNotification = () => {
    signalNotification.toggleNotification();
    updateNotificationButton();
};
window.toggleSound = () => {
    signalNotification.toggleSound();
    updateSoundButton();
};
window.applyHistoryFilters = () => {
    historyManager.applyFilters();
    historyManager.renderCurrentPage(createHistoryRenderer());
};
window.resetHistoryFilters = () => {
    document.getElementById('filterSymbol').value = 'all';
    if (document.getElementById('filterTimeframe')) {
        document.getElementById('filterTimeframe').value = 'all';
    }
    document.getElementById('filterDecision').value = 'all';
    document.getElementById('filterHours').value = '24';
    historyManager.loadHistoryList(apiClient, availableSymbols).then(() => {
        historyManager.renderCurrentPage(createHistoryRenderer());
    });
};
window.goToPage = (page) => historyManager.goToPage(page, createHistoryRenderer());
window.previousPage = () => historyManager.previousPage(createHistoryRenderer());
window.nextPage = () => historyManager.nextPage(createHistoryRenderer());
window.goToLastPage = () => historyManager.lastPage(createHistoryRenderer());
window.goToPageInput = () => {
    const input = document.getElementById('currentPageInput');
    const page = parseInt(input.value);
    
    if (!isNaN(page) && page >= 1 && page <= historyManager.totalPages) {
        historyManager.goToPage(page, createHistoryRenderer());
    } else {
        input.value = historyManager.currentPage;
    }
};
window.changePageSize = () => {
    const newSize = parseInt(document.getElementById('pageSizeSelect').value) || 20;
    historyManager.changePageSize(newSize, createHistoryRenderer());
};

// 详情弹窗相关
window.showDualDetailModal = (symbol, dualData) => {
    const modal = document.getElementById('detailModal');
    const content = document.getElementById('detailContent');
    
    content.innerHTML = dualDecisionRenderer.createDetailHTML(symbol, dualData);
    modal.style.display = 'flex';
    
    // 加载管道数据
    apiClient.loadPipeline(symbol).then(pipelineData => {
        const container = document.getElementById(`pipeline-${symbol}`);
        if (container && pipelineData.steps && pipelineData.steps.length > 0) {
            container.innerHTML = pipelineData.steps.map(step => {
                const statusIcon = step.status === 'success' ? '✓' : 
                                  step.status === 'failed' ? '✗' : '⏳';
                const statusClass = step.status;
                
                return `
                    <div class="pipeline-step-mini ${statusClass}">
                        <span class="step-num">Step${step.step}</span>
                        <span class="step-name">${step.name}</span>
                        <span class="step-icon">${statusIcon}</span>
                        <span class="step-message">${step.message || ''}</span>
                    </div>
                `;
            }).join('');
        } else {
            container.innerHTML = '<div style="color: #9ca3af;">暂无管道数据</div>';
        }
    });
};
window.closeDetailModal = () => {
    const modal = document.getElementById('detailModal');
    modal.style.display = 'none';
};
window.closeSignalPopup = (button) => {
    const popup = button.closest('.signal-popup');
    if (popup) {
        signalNotification.closePopup(popup);
    }
};
window.showDetailFromPopup = (symbol) => {
    const dualData = allDualDecisions[symbol];
    if (dualData) {
        window.showDualDetailModal(symbol, dualData);
    }
};
