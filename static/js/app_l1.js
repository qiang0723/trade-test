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

let currentMarketType = 'futures'; // 固定为合约市场
let autoRefreshInterval = null;
let refreshCountdown = 60;
let reasonTagExplanations = {};
let availableSymbols = []; // 可用币种列表
let allDecisions = {};  // 所有币种的决策缓存

// 历史记录列表分页状态
let allHistoryData = []; // 所有历史数据
let filteredHistoryData = []; // 筛选后的数据
let currentPage = 1;
let pageSize = 20;
let totalPages = 1;

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
            // 保存可用币种列表
            availableSymbols = result.data.symbols || [];
            
            // 使用default_symbol作为初始币种
            if (result.data.default_symbol) {
                currentSymbol = result.data.default_symbol;
            }
            
            // 创建币种按钮
            createSymbolButtons(result.data.markets);
            
            // 初始化历史记录的币种筛选下拉框
            initHistorySymbolFilter(availableSymbols);
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
    
    // 加载历史决策列表
    await loadHistoryList();
    
    // 更新决策管道可视化
    await updatePipelineVisualization(currentSymbol);
    
    // 更新最后更新时间
    updateLastUpdateTime();
    
    // 重置倒计时
    refreshCountdown = 60;
}

/**
 * 更新所有币种决策面板（并排显示）
 */
function updateAllDecisionsPanel(decisions) {
    const grid = document.getElementById('decisionsGrid');
    grid.innerHTML = '';
    
    if (!decisions || Object.keys(decisions).length === 0) {
        grid.innerHTML = '<div class="loading-placeholder">暂无决策数据</div>';
        return;
    }
    
    // 为每个币种创建决策卡片
    for (const symbol of availableSymbols) {
        const advisory = decisions[symbol];
        if (!advisory) continue;
        
        const card = document.createElement('div');
        card.className = 'decision-card';
        
        const { decision, confidence, executable } = advisory;
        
        // 决策图标和颜色
        let icon = '⚪';
        let decisionClass = 'notrade';
        let decisionLabel = 'NO_TRADE';
        
        if (decision === 'long') {
            icon = '🟢';
            decisionClass = 'long';
            decisionLabel = 'LONG';
        } else if (decision === 'short') {
            icon = '🔴';
            decisionClass = 'short';
            decisionLabel = 'SHORT';
        }
        
        // 置信度标签
        const confidenceLabel = {
            'ultra': '极高',
            'high': '高',
            'medium': '中',
            'low': '低'
        }[confidence] || confidence;
        
        // 可执行标识
        const execBadge = executable 
            ? '<span class="exec-badge exec-yes">✓</span>'
            : '<span class="exec-badge exec-no">✗</span>';
        
        card.innerHTML = `
            <div class="decision-card-header ${decisionClass}">
                <span class="symbol-name">${symbol}</span>
                ${execBadge}
            </div>
            <div class="decision-card-body">
                <div class="decision-icon ${decisionClass}">${icon}</div>
                <div class="decision-label ${decisionClass}">${decisionLabel}</div>
                <div class="confidence-mini confidence-${confidence}">${confidenceLabel}</div>
            </div>
        `;
        
        // 点击查看详情
        card.onclick = () => showSymbolDetail(symbol, advisory);
        
        grid.appendChild(card);
    }
}

/**
 * 显示币种决策详情
 */
function showSymbolDetail(symbol, advisory) {
    const tags = advisory.reason_tags.map(tag => {
        const tagData = reasonTagExplanations[tag];
        return tagData ? tagData.explanation : tag;
    }).join('\n• ');
    
    const execPermLabel = {
        'allow': '正常执行',
        'allow_reduced': '降级执行',
        'deny': '拒绝执行'
    }[advisory.execution_permission] || advisory.execution_permission;
    
    alert(`
📊 ${symbol} 决策详情

【核心决策】
决策: ${advisory.decision.toUpperCase()}
置信度: ${advisory.confidence.toUpperCase()}
可执行: ${advisory.executable ? '是' : '否'}
执行许可: ${execPermLabel}

【市场状态】
市场环境: ${advisory.market_regime.toUpperCase()}
系统状态: ${advisory.system_state || 'N/A'}
风险准入: ${advisory.risk_exposure_allowed ? '通过' : '拒绝'}
交易质量: ${advisory.trade_quality.toUpperCase()}

【决策依据】
• ${tags || '无'}

时间: ${new Date(advisory.timestamp).toLocaleString('zh-CN')}
    `.trim());
}

/**
 * 旧的更新决策信号面板（保留兼容）
 */
function updateDecisionPanel(advisory) {
    const { decision, confidence, timestamp, executable } = advisory;
    
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

// ==========================================
// 历史记录列表 - 查询、筛选、分页
// ==========================================

/**
 * 初始化历史记录的币种筛选下拉框
 */
function initHistorySymbolFilter(symbols) {
    const filterSymbol = document.getElementById('filterSymbol');
    
    if (!filterSymbol) {
        console.error('filterSymbol element not found');
        return;
    }
    
    // 清空现有选项（保留"全部币种"）
    filterSymbol.innerHTML = '<option value="all">全部币种</option>';
    
    // 添加每个币种选项
    symbols.forEach(symbol => {
        const option = document.createElement('option');
        option.value = symbol;
        option.textContent = symbol;
        filterSymbol.appendChild(option);
    });
    
    console.log(`Initialized symbol filter with ${symbols.length} symbols`);
}

/**
 * 加载历史记录（列表模式）
 * 
 * 修复：不依赖currentSymbol，完全根据筛选条件独立工作
 */
async function loadHistoryList() {
    try {
        const hours = parseInt(document.getElementById('filterHours').value) || 24;
        const filterSymbol = document.getElementById('filterSymbol').value;
        
        // 如果选择"全部币种"，需要查询所有币种的历史
        if (filterSymbol === 'all') {
            allHistoryData = [];
            
            // 并行查询所有币种的历史数据
            const promises = availableSymbols.map(symbol => 
                fetchHistory(symbol, hours, 2000).then(history => {
                    // 为每条记录添加币种字段
                    return history.map(item => ({...item, symbol: symbol}));
                }).catch(err => {
                    console.error(`Failed to fetch history for ${symbol}:`, err);
                    return [];  // 失败时返回空数组
                })
            );
            
            const results = await Promise.all(promises);
            
            // 合并所有币种的历史数据
            results.forEach(symbolHistory => {
                allHistoryData = allHistoryData.concat(symbolHistory);
            });
            
            // 按时间倒序排序
            allHistoryData.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            
        } else {
            // 查询单一币种
            const history = await fetchHistory(filterSymbol, hours, 2000);
            allHistoryData = history.map(item => ({...item, symbol: filterSymbol}));
        }
        
        if (allHistoryData && allHistoryData.length > 0) {
            applyHistoryFilters();
        } else {
            allHistoryData = [];
            filteredHistoryData = [];
            renderHistoryTable([]);
            updateHistoryStats([]);
        }
    } catch (error) {
        console.error('Error loading history list:', error);
    }
}

/**
 * 应用筛选条件
 */
function applyHistoryFilters() {
    const symbol = document.getElementById('filterSymbol').value;
    const decision = document.getElementById('filterDecision').value;
    const confidence = document.getElementById('filterConfidence').value;
    const executable = document.getElementById('filterExecutable').value;
    const hours = parseInt(document.getElementById('filterHours').value);
    
    // 如果时间范围或币种改变，需要重新加载数据
    const prevHours = parseInt(document.getElementById('filterHours').dataset.prevValue || '24');
    const prevSymbol = document.getElementById('filterSymbol').dataset.prevValue || 'all';
    
    if (hours !== prevHours || symbol !== prevSymbol) {
        document.getElementById('filterHours').dataset.prevValue = hours;
        document.getElementById('filterSymbol').dataset.prevValue = symbol;
        loadHistoryList();
        return;
    }
    
    // 筛选数据（不需要重新加载）
    filteredHistoryData = allHistoryData.filter(item => {
        // 币种筛选（如果已在loadHistoryList中处理，这里可以跳过，但为了一致性保留）
        if (symbol !== 'all' && item.symbol !== symbol) return false;
        if (decision !== 'all' && item.decision !== decision) return false;
        if (confidence !== 'all' && item.confidence !== confidence) return false;
        if (executable !== 'all') {
            const isExecutable = item.executable === true || item.executable === 'true';
            if (executable === 'true' && !isExecutable) return false;
            if (executable === 'false' && isExecutable) return false;
        }
        return true;
    });
    
    // 重置到第一页
    currentPage = 1;
    totalPages = Math.ceil(filteredHistoryData.length / pageSize);
    
    // 更新显示
    renderCurrentPage();
    updateHistoryStats(filteredHistoryData);
}

/**
 * 重置筛选条件
 */
function resetHistoryFilters() {
    document.getElementById('filterSymbol').value = 'all';
    document.getElementById('filterDecision').value = 'all';
    document.getElementById('filterConfidence').value = 'all';
    document.getElementById('filterExecutable').value = 'all';
    document.getElementById('filterHours').value = '24';
    document.getElementById('filterSymbol').dataset.prevValue = 'all';
    document.getElementById('filterHours').dataset.prevValue = '24';
    loadHistoryList();
}

/**
 * 渲染当前页数据
 */
function renderCurrentPage() {
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, filteredHistoryData.length);
    const pageData = filteredHistoryData.slice(startIndex, endIndex);
    
    renderHistoryTable(pageData);
    updatePaginationControls();
}

/**
 * 渲染历史记录表格
 */
function renderHistoryTable(data) {
    const tbody = document.getElementById('historyTableBody');
    
    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="table-empty">暂无符合条件的历史记录</td></tr>';
        return;
    }
    
    tbody.innerHTML = '';
    
    data.forEach(item => {
        const row = document.createElement('tr');
        row.className = `history-row ${item.decision}`;
        
        // 时间
        const dt = new Date(item.timestamp);
        const timeStr = dt.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        
        // 决策标签
        let decisionIcon = '⚪';
        let decisionLabel = 'NO_TRADE';
        let decisionClass = 'notrade';
        if (item.decision === 'long') {
            decisionIcon = '🟢';
            decisionLabel = 'LONG';
            decisionClass = 'long';
        } else if (item.decision === 'short') {
            decisionIcon = '🔴';
            decisionLabel = 'SHORT';
            decisionClass = 'short';
        }
        
        // 置信度
        const confidenceLabel = {
            'high': '高',
            'medium': '中',
            'low': '低',
            'ultra': '极高'
        }[item.confidence] || item.confidence;
        
        // 可执行
        const executableBadge = item.executable 
            ? '<span class="badge badge-success">✓ 可执行</span>'
            : '<span class="badge badge-danger">✗ 不可执行</span>';
        
        // 市场环境
        const regimeLabel = {
            'trend': '趋势市',
            'range': '震荡市',
            'extreme': '极端市'
        }[item.market_regime] || item.market_regime;
        
        // 交易质量
        const qualityLabel = {
            'good': '优',
            'uncertain': '中',
            'poor': '差'
        }[item.trade_quality] || item.trade_quality;
        
        const qualityClass = {
            'good': 'quality-good',
            'uncertain': 'quality-uncertain',
            'poor': 'quality-poor'
        }[item.trade_quality] || '';
        
        // 决策说明（reason tags）
        const reasonText = formatReasonTags(item.reason_tags);
        
        row.innerHTML = `
            <td class="col-symbol">
                <span class="symbol-badge">${item.symbol || currentSymbol}</span>
            </td>
            <td class="col-time">${timeStr}</td>
            <td class="col-decision">
                <span class="decision-badge ${decisionClass}">${decisionIcon} ${decisionLabel}</span>
            </td>
            <td class="col-confidence">
                <span class="confidence-badge confidence-${item.confidence}">${confidenceLabel}</span>
            </td>
            <td class="col-executable">${executableBadge}</td>
            <td class="col-regime">${regimeLabel}</td>
            <td class="col-quality">
                <span class="quality-badge ${qualityClass}">${qualityLabel}</span>
            </td>
            <td class="col-reason">${reasonText}</td>
        `;
        
        // 点击行显示详情
        row.onclick = () => showHistoryDetailModal(item);
        row.style.cursor = 'pointer';
        
        tbody.appendChild(row);
    });
}

/**
 * 格式化reason tags为可读文本
 */
function formatReasonTags(tags) {
    if (!tags || tags.length === 0) {
        return '<span class="text-muted">无</span>';
    }
    
    const tagTexts = tags.slice(0, 3).map(tag => {
        const tagData = reasonTagExplanations[tag];
        if (tagData) {
            return `<span class="reason-badge reason-${tagData.category}" title="${tag}">${tagData.explanation}</span>`;
        }
        return `<span class="reason-badge" title="${tag}">${tag}</span>`;
    });
    
    if (tags.length > 3) {
        tagTexts.push(`<span class="text-muted">+${tags.length - 3}个</span>`);
    }
    
    return tagTexts.join(' ');
}

/**
 * 显示历史记录详情（模态框）
 */
function showHistoryDetailModal(item) {
    const allTags = item.reason_tags.map(tag => {
        const tagData = reasonTagExplanations[tag];
        return tagData ? `• ${tagData.explanation} (${tag})` : `• ${tag}`;
    }).join('\n');
    
    const execPermission = {
        'allow': '正常执行',
        'allow_reduced': '降级执行',
        'deny': '拒绝执行'
    }[item.execution_permission] || item.execution_permission;
    
    const detail = `
📊 决策详情

时间: ${new Date(item.timestamp).toLocaleString('zh-CN')}

【核心决策】
决策: ${item.decision.toUpperCase()}
置信度: ${item.confidence.toUpperCase()}
可执行: ${item.executable ? '是' : '否'}
执行许可: ${execPermission}

【市场状态】
市场环境: ${item.market_regime.toUpperCase()}
系统状态: ${item.system_state || 'N/A'}
风险准入: ${item.risk_exposure_allowed ? '通过' : '拒绝'}
交易质量: ${item.trade_quality.toUpperCase()}

【决策依据】
${allTags || '无'}
    `.trim();
    
    alert(detail);
}

/**
 * 更新统计信息
 */
function updateHistoryStats(data) {
    const stats = {
        total: data.length,
        long: 0,
        short: 0,
        no_trade: 0,
        executable: 0
    };
    
    data.forEach(item => {
        if (item.decision === 'long') stats.long++;
        else if (item.decision === 'short') stats.short++;
        else stats.no_trade++;
        
        if (item.executable) stats.executable++;
    });
    
    document.getElementById('statTotal').textContent = stats.total;
    document.getElementById('statLong').textContent = stats.long;
    document.getElementById('statShort').textContent = stats.short;
    document.getElementById('statNoTrade').textContent = stats.no_trade;
    document.getElementById('statExecutable').textContent = stats.executable;
}

// ==========================================
// 分页控制
// ==========================================

/**
 * 更新分页控件状态
 */
function updatePaginationControls() {
    const totalItems = filteredHistoryData.length;
    const startIndex = (currentPage - 1) * pageSize + 1;
    const endIndex = Math.min(currentPage * pageSize, totalItems);
    
    document.getElementById('pageStart').textContent = totalItems > 0 ? startIndex : 0;
    document.getElementById('pageEnd').textContent = endIndex;
    document.getElementById('pageTotal').textContent = totalItems;
    document.getElementById('currentPageInput').value = currentPage;
    document.getElementById('totalPages').textContent = totalPages;
    
    // 启用/禁用按钮
    document.getElementById('btnFirstPage').disabled = currentPage === 1;
    document.getElementById('btnPrevPage').disabled = currentPage === 1;
    document.getElementById('btnNextPage').disabled = currentPage === totalPages;
    document.getElementById('btnLastPage').disabled = currentPage === totalPages;
}

/**
 * 跳转到指定页
 */
function goToPage(page) {
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    renderCurrentPage();
}

/**
 * 上一页
 */
function previousPage() {
    if (currentPage > 1) {
        currentPage--;
        renderCurrentPage();
    }
}

/**
 * 下一页
 */
function nextPage() {
    if (currentPage < totalPages) {
        currentPage++;
        renderCurrentPage();
    }
}

/**
 * 跳转到末页
 */
function goToLastPage() {
    currentPage = totalPages;
    renderCurrentPage();
}

/**
 * 从输入框跳转
 */
function goToPageInput() {
    const input = document.getElementById('currentPageInput');
    const page = parseInt(input.value);
    
    if (isNaN(page) || page < 1 || page > totalPages) {
        input.value = currentPage;
        return;
    }
    
    goToPage(page);
}

/**
 * 改变每页显示数量
 */
function changePageSize() {
    pageSize = parseInt(document.getElementById('pageSizeSelect').value) || 20;
    currentPage = 1;
    totalPages = Math.ceil(filteredHistoryData.length / pageSize);
    renderCurrentPage();
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
