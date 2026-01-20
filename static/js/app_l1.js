/**
 * L1 Advisory Layer - Frontend Logic
 * 
 * 负责：
 * 1. 调用L1 API获取决策
 * 2. 更新决策信号面板
 * 3. 更新安全闸门状态
 * 4. 显示决策追溯（reason tags）
 * 5. 历史决策时间轴
 * 6. 市场数据展示
 */

// ==========================================
// 全局变量
// ==========================================

let currentSymbol = 'BTC';
let currentMarketType = 'futures'; // 固定为合约市场
let autoRefreshInterval = null;
let refreshCountdown = 60;
let reasonTagExplanations = {};
let historyExpanded = false; // 历史记录是否展开
const MAX_VISIBLE_HISTORY = 30; // 默认显示的历史记录数

// ==========================================
// 初始化
// ==========================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('L1 Advisory Layer - Frontend initialized');
    
    // 加载reason tag解释
    loadReasonTagExplanations();
    
    // 加载可用市场
    loadAvailableMarkets();
    
    // 启动自动刷新
    startAutoRefresh();
});

// ==========================================
// API调用
// ==========================================

/**
 * 获取L1决策
 */
async function fetchAdvisory(symbol) {
    try {
        const response = await fetch(`/api/l1/advisory/${symbol}`);
        const result = await response.json();
        
        if (result.success && result.data) {
            return result.data;
        } else {
            console.error('Failed to fetch advisory:', result.message);
            return null;
        }
    } catch (error) {
        console.error('Error fetching advisory:', error);
        return null;
    }
}

/**
 * 获取历史决策（24小时）
 */
async function fetchHistory(symbol, hours = 24, limit = 1500) {
    try {
        const response = await fetch(`/api/l1/history/${symbol}?hours=${hours}&limit=${limit}`);
        const result = await response.json();
        
        if (result.success && result.data) {
            return result.data;
        } else {
            console.error('Failed to fetch history:', result.message);
            return [];
        }
    } catch (error) {
        console.error('Error fetching history:', error);
        return [];
    }
}

/**
 * 获取reason tag解释
 */
async function loadReasonTagExplanations() {
    try {
        const response = await fetch('/api/l1/reason-tags/explain');
        const result = await response.json();
        
        if (result.success && result.data) {
            reasonTagExplanations = result.data;
            console.log('Loaded reason tag explanations:', Object.keys(reasonTagExplanations).length);
        }
    } catch (error) {
        console.error('Error loading reason tag explanations:', error);
    }
}

/**
 * 获取可用市场
 */
async function loadAvailableMarkets() {
    try {
        const response = await fetch('/api/markets');
        const result = await response.json();
        
        if (result.success && result.data) {
            // 使用default_symbol作为初始币种
            if (result.data.default_symbol) {
                currentSymbol = result.data.default_symbol;
            }
            createSymbolButtons(result.data.markets);
        }
    } catch (error) {
        console.error('Error loading markets:', error);
    }
}

// ==========================================
// UI 更新
// ==========================================

/**
 * 刷新所有数据
 */
async function refreshAdvisory() {
    console.log(`Refreshing advisory for ${currentSymbol}...`);
    
    // 显示加载状态
    showLoading();
    
    // 获取决策
    const advisory = await fetchAdvisory(currentSymbol);
    
    if (advisory) {
        // 更新决策信号面板
        updateDecisionPanel(advisory);
        
        // 更新安全闸门
        updateSafetyGates(advisory);
        
        // 更新决策追溯
        updateReasonTags(advisory);
        
        // 更新最后更新时间
        updateLastUpdateTime();
    }
    
    // 加载历史
    const history = await fetchHistory(currentSymbol);
    updateHistoryTimeline(history);
    
    // 更新决策管道可视化
    await updatePipelineVisualization(currentSymbol);
    
    // 重置倒计时
    refreshCountdown = 60;
}

/**
 * 更新决策信号面板
 */
function updateDecisionPanel(advisory) {
    const { decision, confidence, timestamp, executable } = advisory;
    
    // 更新币种标识
    document.getElementById('currentSymbolBadge').textContent = `${currentSymbol}/USDT`;
    
    // 获取元素
    const decisionSignal = document.getElementById('decisionSignal');
    const signalIcon = document.getElementById('signalIcon');
    const signalText = document.getElementById('signalText');
    const confidenceValue = document.getElementById('confidenceValue');
    const confidenceFill = document.getElementById('confidenceFill');
    const decisionTimestamp = document.getElementById('decisionTimestamp');
    const decisionConfidence = document.getElementById('decisionConfidence');
    
    // 移除所有状态类
    decisionSignal.className = 'decision-signal';
    decisionConfidence.className = 'decision-confidence';
    
    // 根据决策设置样式
    if (decision === 'long') {
        decisionSignal.classList.add('long');
        signalIcon.textContent = '🟢';
        signalText.textContent = 'LONG';
    } else if (decision === 'short') {
        decisionSignal.classList.add('short');
        signalIcon.textContent = '🔴';
        signalText.textContent = 'SHORT';
    } else {
        decisionSignal.classList.add('notrade');
        signalIcon.textContent = '⚪';
        signalText.textContent = 'NO_TRADE';
    }
    
    // 更新置信度
    confidenceValue.textContent = confidence.toUpperCase();
    
    // 置信度百分比和颜色
    let confidencePercent = 0;
    if (confidence === 'high') {
        confidencePercent = 85;
        decisionConfidence.classList.add('confidence-high');
    } else if (confidence === 'medium') {
        confidencePercent = 60;
        decisionConfidence.classList.add('confidence-medium');
    } else {
        confidencePercent = 30;
        decisionConfidence.classList.add('confidence-low');
    }
    
    confidenceFill.style.width = confidencePercent + '%';
    
    // 更新时间戳
    const dt = new Date(timestamp);
    decisionTimestamp.textContent = `决策时间: ${dt.toLocaleString('zh-CN')}`;
    
    // 添加淡入动画
    decisionSignal.classList.add('fade-in');
}

/**
 * 更新安全闸门
 */
function updateSafetyGates(advisory) {
    const { risk_exposure_allowed, trade_quality, market_regime, system_state, execution_permission, executable } = advisory;
    
    // 风险准入
    updateGateCard('riskGateCard', 'riskGateIcon', 'riskGateValue', 
        risk_exposure_allowed ? '✅ Allowed' : '❌ Denied',
        risk_exposure_allowed ? 'success' : 'danger');
    
    // 交易质量（P2修复：支持三态 GOOD/UNCERTAIN/POOR）
    let qualityValue, qualityClass;
    if (trade_quality === 'good') {
        qualityValue = '✅ GOOD';
        qualityClass = 'success';
    } else if (trade_quality === 'uncertain') {
        qualityValue = '⚠️ UNCERTAIN';
        qualityClass = 'warning';
    } else {
        qualityValue = '❌ POOR';
        qualityClass = 'danger';
    }
    updateGateCard('qualityGateCard', 'qualityGateIcon', 'qualityGateValue',
        qualityValue, qualityClass);
    
    // 市场环境
    let regimeIcon = '📊';
    let regimeText = market_regime.toUpperCase();
    let regimeClass = 'success';
    if (market_regime === 'trend') {
        regimeIcon = '📈';
        regimeClass = 'success';
    } else if (market_regime === 'extreme') {
        regimeIcon = '⚡';
        regimeClass = 'danger';
    }
    updateGateCard('regimeCard', 'regimeIcon', 'regimeValue',
        regimeText, regimeClass, regimeIcon);
    
    // 系统状态
    let stateIcon = '⏳';
    let stateText = system_state.toUpperCase().replace('_', ' ');
    let stateClass = 'success';
    if (system_state.includes('active')) {
        stateIcon = '🟢';
        stateClass = 'success';
    } else if (system_state === 'cool_down') {
        stateIcon = '⏸️';
        stateClass = 'warning';
    }
    updateGateCard('stateCard', 'stateIcon', 'stateValue',
        stateText, stateClass, stateIcon);
    
    // 执行许可级别 (方案D新增)
    let permIcon, permText, permClass;
    if (execution_permission === 'allow') {
        permIcon = '✅';
        permText = '✅ ALLOW';
        permClass = 'success';
    } else if (execution_permission === 'allow_reduced') {
        permIcon = '⚠️';
        permText = '⚠️ ALLOW_REDUCED';
        permClass = 'warning';
    } else {
        permIcon = '⛔';
        permText = '⛔ DENY';
        permClass = 'danger';
    }
    updateGateCard('executionPermCard', 'executionPermIcon', 'executionPermValue',
        permText, permClass, permIcon);
    
    // L3执行判定 (方案D双门槛)
    const executableValue = executable ? '✅ Executable' : '⛔ Not Executable';
    const executableClass = executable ? 'success' : 'danger';
    const executableIcon = executable ? '✅' : '⛔';
    updateGateCard('executableCard', 'executableIcon', 'executableValue',
        executableValue, executableClass, executableIcon);
}

/**
 * 更新单个闸门卡片
 */
function updateGateCard(cardId, iconId, valueId, valueText, statusClass, customIcon = null) {
    const card = document.getElementById(cardId);
    const icon = document.getElementById(iconId);
    const value = document.getElementById(valueId);
    
    // 移除所有状态类
    card.className = 'gate-card';
    card.classList.add(statusClass);
    
    // 更新内容
    if (customIcon) {
        icon.textContent = customIcon;
    }
    value.textContent = valueText;
}

/**
 * 更新决策追溯（Reason Tags）
 */
function updateReasonTags(advisory) {
    const { reason_tags } = advisory;
    const container = document.getElementById('reasonTagsContainer');
    
    if (!reason_tags || reason_tags.length === 0) {
        container.innerHTML = '<div class="reason-tags-placeholder">无附加决策依据</div>';
        return;
    }
    
    container.innerHTML = '';
    
    reason_tags.forEach(tagValue => {
        const tagData = reasonTagExplanations[tagValue];
        const explanation = tagData ? tagData.explanation : tagValue;
        const category = tagData ? tagData.category : 'info';
        
        const tag = document.createElement('div');
        tag.className = `reason-tag ${category}`;
        tag.textContent = explanation;
        tag.title = `Tag: ${tagValue}`;
        
        container.appendChild(tag);
    });
}

/**
 * 更新历史决策时间轴（最多显示30个，剩余可展开）
 */
function updateHistoryTimeline(history) {
    const timeline = document.getElementById('historyTimeline');
    const toggleDiv = document.getElementById('historyToggle');
    const toggleBtn = document.getElementById('historyToggleBtn');
    const hiddenCountSpan = document.getElementById('hiddenCount');
    
    if (!history || history.length === 0) {
        timeline.innerHTML = '<div class="timeline-loading">暂无历史记录</div>';
        toggleDiv.style.display = 'none';
        return;
    }
    
    timeline.innerHTML = '';
    
    // 判断是否需要折叠
    const needCollapse = history.length > MAX_VISIBLE_HISTORY;
    const displayCount = historyExpanded ? history.length : Math.min(history.length, MAX_VISIBLE_HISTORY);
    
    // 显示历史记录
    for (let i = 0; i < displayCount; i++) {
        const item = history[i];
        const timelineItem = document.createElement('div');
        const decision = item.decision;
        timelineItem.className = `timeline-item ${decision}`;
        
        // 时间
        const dt = new Date(item.timestamp);
        const timeStr = dt.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
        
        // 图标
        let icon = '⚪';
        let label = 'NO_TRADE';
        if (decision === 'long') {
            icon = '🟢';
            label = 'LONG';
        } else if (decision === 'short') {
            icon = '🔴';
            label = 'SHORT';
        }
        
        timelineItem.innerHTML = `
            <div class="item-time">${timeStr}</div>
            <div class="item-decision">${icon}</div>
            <div class="item-label">${label}</div>
        `;
        
        // 点击显示详情
        timelineItem.onclick = () => showHistoryDetail(item);
        
        timeline.appendChild(timelineItem);
    }
    
    // 更新折叠按钮
    if (needCollapse) {
        toggleDiv.style.display = 'block';
        const hiddenCount = history.length - MAX_VISIBLE_HISTORY;
        hiddenCountSpan.textContent = hiddenCount;
        toggleBtn.textContent = historyExpanded 
            ? '收起历史记录' 
            : `展开更多历史记录 (${hiddenCount})`;
    } else {
        toggleDiv.style.display = 'none';
    }
}

/**
 * 切换历史记录展开/收起
 */
function toggleHistoryExpand() {
    historyExpanded = !historyExpanded;
    // 重新获取历史数据并更新显示
    fetchHistory(currentSymbol).then(history => {
        updateHistoryTimeline(history);
    });
}

/**
 * 显示历史决策详情（简单弹窗）
 */
function showHistoryDetail(item) {
    const tags = item.reason_tags.map(tag => {
        const tagData = reasonTagExplanations[tag];
        return tagData ? tagData.explanation : tag;
    }).join(', ');
    
    const detail = `
决策: ${item.decision.toUpperCase()}
置信度: ${item.confidence.toUpperCase()}
市场环境: ${item.market_regime.toUpperCase()}
决策依据: ${tags || '无'}
时间: ${new Date(item.timestamp).toLocaleString('zh-CN')}
    `;
    
    alert(detail);
}

/**
 * 更新最后更新时间
 */
function updateLastUpdateTime() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
    document.getElementById('lastUpdate').textContent = timeStr;
}

/**
 * 显示加载状态
 */
function showLoading() {
    // 可以添加loading动画
    console.log('Loading...');
}

// ==========================================
// 币种和市场类型切换
// ==========================================

/**
 * 创建币种按钮
 */
function createSymbolButtons(markets) {
    const container = document.getElementById('symbolButtons');
    container.innerHTML = '';
    
    for (let symbol in markets) {
        const market = markets[symbol];
        const hasAnyMarket = market.spot || market.futures;
        
        const button = document.createElement('button');
        button.textContent = `${symbol}/USDT`;
        button.dataset.symbol = symbol;
        
        if (!hasAnyMarket) {
            button.className = 'disabled';
            button.title = '该币种暂无可用市场';
        } else {
            button.onclick = () => selectSymbol(symbol);
        }
        
        if (symbol === currentSymbol) {
            button.classList.add('active');
        }
        
        container.appendChild(button);
    }
}

/**
 * 选择币种
 */
function selectSymbol(symbol) {
    currentSymbol = symbol;
    
    // 更新按钮状态
    document.querySelectorAll('#symbolButtons button').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.symbol === symbol) {
            btn.classList.add('active');
        }
    });
    
    // 刷新数据
    refreshAdvisory();
}

/**
 * 切换市场类型（已禁用，固定为合约）
 */
function switchMarketType(type) {
    // 固定为合约市场，不再支持切换
    currentMarketType = 'futures';
    console.log('Market type is fixed to futures');
}

// ==========================================
// 市场数据概览（可折叠）
// ==========================================

// ==========================================
// 自动刷新
// ==========================================

/**
 * 启动自动刷新（1分钟一次）
 */
function startAutoRefresh() {
    // 立即刷新一次
    refreshAdvisory();
    
    // 每60秒刷新一次
    autoRefreshInterval = setInterval(() => {
        refreshAdvisory();
    }, 60000);
    
    // 倒计时显示
    setInterval(() => {
        refreshCountdown--;
        if (refreshCountdown <= 0) {
            refreshCountdown = 60;
        }
        // 可以在UI上显示倒计时
    }, 1000);
}

/**
 * 停止自动刷新
 */
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// ==========================================
// 页面卸载清理
// ==========================================

window.addEventListener('beforeunload', function() {
    stopAutoRefresh();
});

// ==========================================
// 工具函数
// ==========================================

/**
 * 格式化数字
 */
function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined || isNaN(num)) return '--';
    return num.toLocaleString('zh-CN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

/**
 * 格式化大数字
 */
function formatLargeNumber(num) {
    if (num === null || num === undefined || isNaN(num)) return '--';
    if (num >= 1e9) {
        return formatNumber(num / 1e9, 2) + 'B';
    } else if (num >= 1e6) {
        return formatNumber(num / 1e6, 2) + 'M';
    } else if (num >= 1e3) {
        return formatNumber(num / 1e3, 2) + 'K';
    }
    return formatNumber(num, 2);
}

// ==========================================
// 决策管道可视化
// ==========================================

/**
 * 更新决策管道可视化
 */
async function updatePipelineVisualization(symbol) {
    try {
        const response = await fetch(`/api/l1/pipeline/${symbol}`);
        const result = await response.json();
        
        if (result.success && result.data && result.data.steps && result.data.steps.length > 0) {
            const steps = result.data.steps;
            
            // 遍历每个步骤，更新UI
            steps.forEach(step => {
                const stepElement = document.querySelector(`.pipeline-step[data-step="${step.step}"]`);
                if (stepElement) {
                    // 移除所有状态类
                    stepElement.classList.remove('success', 'warning', 'failed', 'pending');
                    
                    // 添加当前状态类
                    stepElement.classList.add(step.status);
                    
                    // 更新状态图标
                    const iconSpan = stepElement.querySelector('.step-status');
                    if (iconSpan) {
                        if (step.status === 'success') {
                            iconSpan.textContent = '✅';
                        } else if (step.status === 'failed') {
                            iconSpan.textContent = '❌';
                        } else if (step.status === 'warning') {
                            iconSpan.textContent = '⚠️';
                        } else {
                            iconSpan.textContent = '⏳';
                        }
                    }
                    
                    // 更新结果文本
                    const resultSpan = stepElement.querySelector('.step-result');
                    if (resultSpan && step.result) {
                        if (Array.isArray(step.result)) {
                            resultSpan.textContent = ` → ${step.result.join(', ')}`;
                        } else {
                            resultSpan.textContent = ` → ${step.result}`;
                        }
                    }
                    
                    // 设置tooltip
                    stepElement.title = step.message || '';
                }
            });
            
            console.log(`Pipeline visualization updated with ${steps.length} steps`);
        } else if (result.data && result.data.message) {
            console.log(result.data.message);
        }
    } catch (error) {
        console.error('Error updating pipeline visualization:', error);
    }
}
