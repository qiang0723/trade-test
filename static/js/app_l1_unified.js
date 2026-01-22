/**
 * L1 Advisory Layer - Unified Dual Timeframe Frontend
 * 
 * 双周期统一界面：
 * 1. 在币种卡片中同时显示短期和中长期决策
 * 2. 点击卡片显示完整的双周期详情
 * 3. 信号通知和历史记录支持
 */

// ==========================================
// 全局变量
// ==========================================

let availableSymbols = [];
let allDualDecisions = {};  // 所有币种的双周期决策缓存
let previousDecisions = {};  // 上一次的决策状态（用于信号检测）
let signalNotificationEnabled = true;
let soundEnabled = true;
let reasonTagExplanations = {};

// 历史记录分页
let allHistoryData = [];
let filteredHistoryData = [];
let currentPage = 1;
let pageSize = 20;
let totalPages = 1;

// ==========================================
// 初始化
// ==========================================

document.addEventListener('DOMContentLoaded', function() {
    console.log('L1 Unified Dual Timeframe Frontend initialized');
    
    // 加载用户设置
    loadUserSettings();
    
    // 加载reason tag解释
    loadReasonTagExplanations();
    
    // 加载可用市场
    loadAvailableMarkets();
    
    // 启动自动刷新
    startAutoRefresh();
    
    // 请求浏览器通知权限
    requestNotificationPermission();
});

function loadUserSettings() {
    const savedNotification = localStorage.getItem('signalNotificationEnabled');
    if (savedNotification !== null) {
        signalNotificationEnabled = savedNotification === 'true';
        updateNotificationButton();
    }
    
    const savedSound = localStorage.getItem('soundEnabled');
    if (savedSound !== null) {
        soundEnabled = savedSound === 'true';
        updateSoundButton();
    }
}

function requestNotificationPermission() {
    if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
    }
}

// ==========================================
// API调用
// ==========================================

async function fetchDualAdvisory(symbol) {
    try {
        const response = await fetch(`/api/l1/advisory-dual/${symbol}`);
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

async function fetchDualHistory(symbol, hours = 24, limit = 1500) {
    try {
        const response = await fetch(`/api/l1/history-dual/${symbol}?hours=${hours}&limit=${limit}`);
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

async function loadAvailableMarkets() {
    try {
        const response = await fetch('/api/markets');
        const result = await response.json();
        
        if (result.success && result.data) {
            availableSymbols = result.data.symbols || [];
            console.log('Available symbols:', availableSymbols);
            
            // 初始化历史记录的币种筛选下拉框
            initHistorySymbolFilter(availableSymbols);
            
            // 立即刷新所有币种决策
            refreshAdvisory();
        }
    } catch (error) {
        console.error('Error loading markets:', error);
    }
}

// ==========================================
// 主刷新逻辑
// ==========================================

async function refreshAdvisory() {
    console.log('Refreshing dual advisory for all symbols...');
    
    showLoading();
    
    if (!availableSymbols || availableSymbols.length === 0) {
        console.error('No available symbols');
        return;
    }
    
    // 并行获取所有币种的双周期决策
    const promises = availableSymbols.map(symbol => 
        fetchDualAdvisory(symbol).then(dualAdvisory => ({
            symbol: symbol,
            dualAdvisory: dualAdvisory
        })).catch(err => {
            console.error(`Failed to fetch dual advisory for ${symbol}:`, err);
            return { symbol: symbol, dualAdvisory: null };
        })
    );
    
    const results = await Promise.all(promises);
    
    // 检测交易信号变化（在更新缓存前）
    const newDecisions = {};
    results.forEach(({symbol, dualAdvisory}) => {
        if (dualAdvisory) {
            newDecisions[symbol] = dualAdvisory;
        }
    });
    
    checkForNewDualSignals(newDecisions);
    
    // 更新决策缓存
    allDualDecisions = newDecisions;
    
    // 更新所有币种的决策面板
    updateAllDualDecisionsPanel(allDualDecisions);
    
    // 加载历史决策列表
    await loadHistoryList();
    
    // 更新最后更新时间
    updateLastUpdateTime();
}

// ==========================================
// UI 更新
// ==========================================

function updateAllDualDecisionsPanel(decisions) {
    const grid = document.getElementById('decisionsGrid');
    grid.innerHTML = '';
    
    if (!decisions || Object.keys(decisions).length === 0) {
        grid.innerHTML = '<div class="loading-placeholder">暂无决策数据</div>';
        return;
    }
    
    // 为每个币种创建双周期决策卡片
    for (const symbol of availableSymbols) {
        const dualData = decisions[symbol];
        if (!dualData) continue;
        
        const card = createDualDecisionCard(symbol, dualData);
        grid.appendChild(card);
    }
}

function createDualDecisionCard(symbol, dualData) {
    const card = document.createElement('div');
    card.className = 'decision-card';
    card.id = `card-${symbol}`;
    
    const { short_term, medium_term, alignment } = dualData;
    
    // 计算执行状态
    let execStatus, execClass;
    if (short_term.executable && medium_term.executable) {
        execStatus = '双可执行';
        execClass = 'both-exec';
    } else if (short_term.executable || medium_term.executable) {
        execStatus = '部分可执行';
        execClass = 'partial-exec';
    } else {
        execStatus = '不可执行';
        execClass = 'no-exec';
    }
    
    // 一致性标签文本
    const alignmentText = {
        'both_long': '✅ 双向做多',
        'both_short': '❌ 双向做空',
        'both_no_trade': '⏸ 双向观望',
        'short_confirm_long': '⚠️ 短期确认中',
        'long_confirm_short': '⚠️ 长期确认中',
        'conflict': '⚡ 周期冲突'
    }[alignment.alignment_type] || alignment.alignment_type;
    
    const alignmentClass = alignment.alignment_type;
    
    card.innerHTML = `
        <div class="decision-card-header">
            <span class="symbol-name">${symbol}</span>
            <span class="exec-status ${execClass}">${execStatus}</span>
        </div>
        
        <!-- 短期决策 -->
        <div class="timeframe-row short-term">
            <span class="timeframe-label">短期 5m/15m</span>
            <div class="timeframe-decision">
                <span class="decision-icon-mini">${getDecisionIcon(short_term.decision)}</span>
                <span class="decision-text ${short_term.decision}">${getDecisionLabel(short_term.decision)}</span>
                <span class="confidence-mini ${short_term.confidence}">${short_term.confidence.toUpperCase()}</span>
            </div>
        </div>
        
        <!-- 中长期决策 -->
        <div class="timeframe-row medium-term">
            <span class="timeframe-label">中长 1h/6h</span>
            <div class="timeframe-decision">
                <span class="decision-icon-mini">${getDecisionIcon(medium_term.decision)}</span>
                <span class="decision-text ${medium_term.decision}">${getDecisionLabel(medium_term.decision)}</span>
                <span class="confidence-mini ${medium_term.confidence}">${medium_term.confidence.toUpperCase()}</span>
            </div>
        </div>
        
        <!-- 一致性标签 -->
        <div class="alignment-badge ${alignmentClass}">
            ${alignmentText}
        </div>
    `;
    
    // 点击显示详情
    card.onclick = () => showDualDetailModal(symbol, dualData);
    
    return card;
}

function getDecisionIcon(decision) {
    const icons = {
        'long': '🟢',
        'short': '🔴',
        'no_trade': '⚪'
    };
    return icons[decision] || '⚪';
}

function getDecisionLabel(decision) {
    const labels = {
        'long': 'LONG',
        'short': 'SHORT',
        'no_trade': 'NO_TRADE'
    };
    return labels[decision] || decision;
}

// ==========================================
// 详情弹窗
// ==========================================

function showDualDetailModal(symbol, dualData) {
    const modal = document.getElementById('detailModal');
    const content = document.getElementById('detailContent');
    
    content.innerHTML = createDualDetailHTML(symbol, dualData);
    
    modal.style.display = 'flex';
    
    // 加载管道数据
    loadPipelineForSymbol(symbol);
}

function closeDetailModal() {
    const modal = document.getElementById('detailModal');
    modal.style.display = 'none';
}

function createDualDetailHTML(symbol, dualData) {
    const { short_term, medium_term, alignment, risk_exposure_allowed, global_risk_tags, timestamp } = dualData;
    
    // 格式化短期决策
    const shortTermHTML = createTimeframeDetailHTML(short_term, 'short-term', '短期决策 (5m/15m)');
    
    // 格式化中长期决策
    const mediumTermHTML = createTimeframeDetailHTML(medium_term, 'medium-term', '中长期决策 (1h/6h)');
    
    // 一致性分析
    const alignmentHTML = createAlignmentDetailHTML(alignment);
    
    // 全局风险
    const riskHTML = createGlobalRiskHTML(risk_exposure_allowed, global_risk_tags);
    
    return `
        <div class="detail-header">
            <h3>📊 ${symbol} - 双周期决策详情</h3>
            <button class="detail-close" onclick="closeDetailModal()">✕ 关闭</button>
        </div>
        
        <div class="detail-body">
            <!-- 双周期决策 -->
            <div class="detail-section">
                <h4>🎯 双周期独立决策</h4>
                <div class="dual-timeframe-detail">
                    ${shortTermHTML}
                    ${mediumTermHTML}
                    ${alignmentHTML}
                </div>
            </div>
            
            <!-- 全局风险 -->
            <div class="detail-section">
                ${riskHTML}
            </div>
            
            <!-- 决策管道 -->
            <div class="detail-section">
                <h4>🔍 决策管道（10步）</h4>
                <div class="pipeline-mini" id="pipeline-${symbol}">
                    <div class="pipeline-loading">正在加载...</div>
                </div>
            </div>
            
            <div class="detail-timestamp">
                决策时间: ${new Date(timestamp).toLocaleString('zh-CN')}
            </div>
        </div>
    `;
}

function createTimeframeDetailHTML(tf, cssClass, title) {
    const decisionIcon = getDecisionIcon(tf.decision);
    const decisionText = getDecisionLabel(tf.decision);
    const execText = tf.executable ? '✓ 可执行' : '✗ 不可执行';
    
    // 关键指标
    const metricsHTML = Object.entries(tf.key_metrics || {}).slice(0, 6).map(([key, value]) => `
        <div class="metric-item">
            <div class="metric-label">${key}</div>
            <div class="metric-value">${formatMetricValue(value)}</div>
        </div>
    `).join('');
    
    // 原因标签
    const tagsHTML = (tf.reason_tags || []).slice(0, 4).map(tag => {
        const tagData = reasonTagExplanations[tag];
        const explanation = tagData ? tagData.explanation : tag;
        const category = tagData ? tagData.category : 'info';
        return `<span class="reason-tag ${category}" title="${tag}">${explanation}</span>`;
    }).join('');
    
    return `
        <div class="timeframe-detail-panel ${cssClass}">
            <div class="timeframe-detail-header">${title}</div>
            
            <div class="detail-row">
                <span class="detail-label">决策方向</span>
                <span class="detail-value">${decisionIcon} ${decisionText}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">置信度</span>
                <span class="detail-value">${tf.confidence.toUpperCase()}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">可执行性</span>
                <span class="detail-value">${execText}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">市场环境</span>
                <span class="detail-value">${tf.market_regime.toUpperCase()}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">交易质量</span>
                <span class="detail-value">${tf.trade_quality.toUpperCase()}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">执行许可</span>
                <span class="detail-value">${tf.execution_permission.toUpperCase()}</span>
            </div>
            
            <div style="margin-top: 12px;">
                <div class="detail-label" style="margin-bottom: 8px;">关键指标</div>
                <div class="key-metrics-grid">
                    ${metricsHTML}
                </div>
            </div>
            
            <div style="margin-top: 12px;">
                <div class="detail-label" style="margin-bottom: 8px;">决策依据</div>
                <div class="reason-tags-mini">
                    ${tagsHTML || '<span style="color: #9ca3af;">无</span>'}
                </div>
            </div>
        </div>
    `;
}

function createAlignmentDetailHTML(alignment) {
    const statusText = alignment.is_aligned ? '✅ 一致' : (alignment.has_conflict ? '⚡ 冲突' : '⚠️ 部分确认');
    
    return `
        <div class="alignment-detail">
            <div class="alignment-detail-header">
                🎯 一致性分析 - ${statusText}
            </div>
            
            <div class="detail-row">
                <span class="detail-label">一致性类型</span>
                <span class="detail-value">${alignment.alignment_type}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">综合建议</span>
                <span class="detail-value">${getDecisionIcon(alignment.recommended_action)} ${alignment.recommended_action.toUpperCase()}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">建议置信度</span>
                <span class="detail-value">${alignment.recommended_confidence.toUpperCase()}</span>
            </div>
            
            ${alignment.has_conflict ? `
                <div class="detail-row">
                    <span class="detail-label">冲突处理</span>
                    <span class="detail-value">${alignment.conflict_resolution}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">处理原因</span>
                    <span class="detail-value">${alignment.resolution_reason}</span>
                </div>
            ` : ''}
            
            <div class="alignment-notes">
                ${alignment.recommendation_notes}
            </div>
        </div>
    `;
}

function createGlobalRiskHTML(risk_allowed, risk_tags) {
    const riskStatus = risk_allowed ? '✅ 通过' : '❌ 拒绝';
    const riskClass = risk_allowed ? 'success' : 'danger';
    
    let tagsHTML = '';
    if (risk_tags && risk_tags.length > 0) {
        tagsHTML = `
            <div style="margin-top: 12px; padding: 12px; background: #fff3cd; border-radius: 8px; border-left: 3px solid #f59e0b;">
                <strong>⚠️ 全局风险标签:</strong><br>
                ${risk_tags.join(', ')}
            </div>
        `;
    }
    
    return `
        <h4>🛡️ 全局风险状态</h4>
        <div class="gate-mini ${riskClass}" style="max-width: 300px;">
            <span class="gate-label">风险准入</span>
            <span class="gate-value">${riskStatus}</span>
        </div>
        ${tagsHTML}
    `;
}

async function loadPipelineForSymbol(symbol) {
    try {
        const response = await fetch(`/api/l1/pipeline/${symbol}`);
        const result = await response.json();
        
        const pipelineContainer = document.getElementById(`pipeline-${symbol}`);
        if (!pipelineContainer) return;
        
        if (result.success && result.data && result.data.steps && result.data.steps.length > 0) {
            pipelineContainer.innerHTML = result.data.steps.map(step => {
                const statusIcon = step.status === 'success' ? '✓' : 
                                  step.status === 'failed' ? '✗' : '⏳';
                const statusClass = step.status === 'success' ? 'success' : 
                                   step.status === 'failed' ? 'failed' : 'pending';
                
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
            pipelineContainer.innerHTML = '<div style="color: #9ca3af;">暂无管道数据</div>';
        }
    } catch (error) {
        console.error(`Error loading pipeline for ${symbol}:`, error);
    }
}

function formatMetricValue(value) {
    if (typeof value === 'number') {
        if (Math.abs(value) < 0.01) {
            return (value * 100).toFixed(3) + '%';
        } else {
            return (value * 100).toFixed(2) + '%';
        }
    }
    return value;
}

// ==========================================
// 信号检测和通知
// ==========================================

function checkForNewDualSignals(newDecisions) {
    if (!signalNotificationEnabled) return;
    
    const newSignals = [];
    
    for (const symbol in newDecisions) {
        const newDual = newDecisions[symbol];
        const oldDual = previousDecisions[symbol];
        
        // 检查短期信号
        if (newDual.short_term.decision !== 'no_trade') {
            if (!oldDual || oldDual.short_term.decision === 'no_trade' || 
                oldDual.short_term.decision !== newDual.short_term.decision) {
                newSignals.push({
                    symbol: symbol,
                    timeframe: 'short_term',
                    decision: newDual.short_term.decision,
                    confidence: newDual.short_term.confidence,
                    executable: newDual.short_term.executable,
                    price: newDual.price,
                    isReversal: oldDual && oldDual.short_term.decision !== 'no_trade' && 
                               oldDual.short_term.decision !== newDual.short_term.decision
                });
            }
        }
        
        // 检查中长期信号
        if (newDual.medium_term.decision !== 'no_trade') {
            if (!oldDual || oldDual.medium_term.decision === 'no_trade' || 
                oldDual.medium_term.decision !== newDual.medium_term.decision) {
                newSignals.push({
                    symbol: symbol,
                    timeframe: 'medium_term',
                    decision: newDual.medium_term.decision,
                    confidence: newDual.medium_term.confidence,
                    executable: newDual.medium_term.executable,
                    price: newDual.price,
                    isReversal: oldDual && oldDual.medium_term.decision !== 'no_trade' && 
                               oldDual.medium_term.decision !== newDual.medium_term.decision
                });
            }
        }
    }
    
    // 更新历史记录
    previousDecisions = { ...newDecisions };
    
    // 显示信号提示
    if (newSignals.length > 0) {
        showSignalNotifications(newSignals);
    }
}

function showSignalNotifications(signals) {
    signals.forEach((signal, index) => {
        setTimeout(() => {
            showSignalPopup(signal);
            
            if (soundEnabled) {
                playNotificationSound(signal.decision);
            }
            
            showBrowserNotification(signal);
        }, index * 500);
    });
}

function showSignalPopup(signal) {
    const { symbol, timeframe, decision, confidence, executable, price, isReversal } = signal;
    
    const popup = document.createElement('div');
    popup.className = 'signal-popup';
    popup.classList.add(decision === 'long' ? 'signal-long' : 'signal-short');
    
    const icon = decision === 'long' ? '🟢' : '🔴';
    const decisionLabel = decision === 'long' ? '做多信号' : '做空信号';
    const timeframeLabel = timeframe === 'short_term' ? '短期(5m/15m)' : '中长期(1h/6h)';
    const reversalLabel = isReversal ? ' (方向反转)' : '';
    const priceInfo = price ? `<div class="signal-price">💰 价格: $${price.toLocaleString()}</div>` : '';
    
    const confidenceLabel = {
        'ultra': '极高',
        'high': '高',
        'medium': '中',
        'low': '低'
    }[confidence] || confidence;
    
    const execLabel = executable ? '✓ 可执行' : '✗ 不可执行';
    const execClass = executable ? 'exec-yes' : 'exec-no';
    
    popup.innerHTML = `
        <div class="signal-popup-header">
            <span class="signal-icon">${icon}</span>
            <span class="signal-title">${timeframeLabel} ${decisionLabel}${reversalLabel}</span>
            <button class="signal-close" onclick="closeSignalPopup(this)">×</button>
        </div>
        <div class="signal-popup-body">
            <div class="signal-info">
                <div class="signal-symbol">${symbol}</div>
                ${priceInfo}
                <div class="signal-details">
                    <span class="signal-confidence">置信度: ${confidenceLabel}</span>
                    <span class="signal-exec ${execClass}">${execLabel}</span>
                </div>
            </div>
            <div class="signal-actions">
                <button class="signal-btn signal-btn-detail" onclick="showDetailFromPopup('${symbol}')">
                    查看详情
                </button>
                <button class="signal-btn signal-btn-close" onclick="closeSignalPopup(this)">
                    关闭
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(popup);
    
    setTimeout(() => popup.classList.add('show'), 10);
    
    setTimeout(() => {
        if (popup.parentNode) {
            closeSignalPopup(popup.querySelector('.signal-close'));
        }
    }, 10000);
}

function closeSignalPopup(button) {
    const popup = button.closest('.signal-popup');
    if (popup) {
        popup.classList.remove('show');
        setTimeout(() => {
            if (popup.parentNode) {
                popup.parentNode.removeChild(popup);
            }
        }, 300);
    }
}

function showDetailFromPopup(symbol) {
    const dualData = allDualDecisions[symbol];
    if (dualData) {
        showDualDetailModal(symbol, dualData);
    }
}

function playNotificationSound(decision) {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.value = decision === 'long' ? 800 : 600;
        oscillator.type = 'sine';
        
        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.3);
    } catch (error) {
        console.error('Failed to play notification sound:', error);
    }
}

function showBrowserNotification(signal) {
    if (!("Notification" in window)) {
        return;
    }
    
    if (Notification.permission === "granted") {
        createNotification(signal);
    } else if (Notification.permission !== "denied") {
        Notification.requestPermission().then(permission => {
            if (permission === "granted") {
                createNotification(signal);
            }
        });
    }
}

function createNotification(signal) {
    const { symbol, timeframe, decision, confidence, executable, price } = signal;
    
    const timeframeLabel = timeframe === 'short_term' ? '短期' : '中长期';
    const title = `${symbol} - ${timeframeLabel}${decision === 'long' ? '做多' : '做空'}信号`;
    const priceText = price ? `\n💰 价格: $${price.toLocaleString()}` : '';
    const body = `置信度: ${confidence}${priceText}\n${executable ? '✓ 可执行' : '✗ 不可执行'}`;
    
    const notification = new Notification(title, {
        body: body,
        tag: `dual-signal-${symbol}-${timeframe}`,
        requireInteraction: false
    });
    
    notification.onclick = function() {
        window.focus();
        notification.close();
        
        const dualData = allDualDecisions[symbol];
        if (dualData) {
            showDualDetailModal(symbol, dualData);
        }
    };
    
    setTimeout(() => notification.close(), 3000);
}

function toggleSignalNotification() {
    signalNotificationEnabled = !signalNotificationEnabled;
    updateNotificationButton();
    localStorage.setItem('signalNotificationEnabled', signalNotificationEnabled);
}

function toggleSound() {
    soundEnabled = !soundEnabled;
    updateSoundButton();
    localStorage.setItem('soundEnabled', soundEnabled);
}

function updateNotificationButton() {
    const button = document.getElementById('toggleNotificationBtn');
    if (button) {
        button.textContent = signalNotificationEnabled ? '🔔 通知已开启' : '🔕 通知已关闭';
        button.classList.toggle('disabled', !signalNotificationEnabled);
    }
}

function updateSoundButton() {
    const button = document.getElementById('toggleSoundBtn');
    if (button) {
        button.textContent = soundEnabled ? '🔊 声音已开启' : '🔇 声音已关闭';
        button.classList.toggle('disabled', !soundEnabled);
    }
}

// ==========================================
// 历史记录（使用双周期历史API）
// ==========================================

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

async function loadHistoryList() {
    try {
        const hours = parseInt(document.getElementById('filterHours').value) || 24;
        const filterSymbol = document.getElementById('filterSymbol').value;
        
        if (filterSymbol === 'all') {
            allHistoryData = [];
            
            const promises = availableSymbols.map(symbol => 
                fetchDualHistory(symbol, hours, 2000).then(history => {
                    return history.map(item => ({...item, symbol: symbol}));
                }).catch(err => {
                    console.error(`Failed to fetch dual history for ${symbol}:`, err);
                    return [];
                })
            );
            
            const results = await Promise.all(promises);
            
            results.forEach(symbolHistory => {
                allHistoryData = allHistoryData.concat(symbolHistory);
            });
            
            allHistoryData.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            
        } else {
            const history = await fetchDualHistory(filterSymbol, hours, 2000);
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

function applyHistoryFilters() {
    const symbol = document.getElementById('filterSymbol').value;
    const timeframe = document.getElementById('filterTimeframe')?.value || 'all';
    const decision = document.getElementById('filterDecision').value;
    const hours = parseInt(document.getElementById('filterHours').value);
    
    const prevHours = parseInt(document.getElementById('filterHours').dataset.prevValue || '24');
    const prevSymbol = document.getElementById('filterSymbol').dataset.prevValue || 'all';
    
    if (hours !== prevHours || symbol !== prevSymbol) {
        document.getElementById('filterHours').dataset.prevValue = hours;
        document.getElementById('filterSymbol').dataset.prevValue = symbol;
        loadHistoryList();
        return;
    }
    
    // 扁平化双周期历史数据为单行
    let flattenedData = [];
    allHistoryData.forEach(item => {
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
    filteredHistoryData = flattenedData.filter(item => {
        // 过滤掉NO_TRADE观望信号
        if (item.decision === 'no_trade') return false;
        
        if (symbol !== 'all' && item.symbol !== symbol) return false;
        if (timeframe !== 'all' && item.timeframe !== timeframe) return false;
        if (decision !== 'all' && item.decision !== decision) return false;
        return true;
    });
    
    currentPage = 1;
    totalPages = Math.ceil(filteredHistoryData.length / pageSize);
    
    renderCurrentPage();
    updateHistoryStats(filteredHistoryData);
}

function resetHistoryFilters() {
    document.getElementById('filterSymbol').value = 'all';
    if (document.getElementById('filterTimeframe')) {
        document.getElementById('filterTimeframe').value = 'all';
    }
    document.getElementById('filterDecision').value = 'all';
    document.getElementById('filterHours').value = '24';
    document.getElementById('filterSymbol').dataset.prevValue = 'all';
    document.getElementById('filterHours').dataset.prevValue = '24';
    loadHistoryList();
}

function renderCurrentPage() {
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, filteredHistoryData.length);
    const pageData = filteredHistoryData.slice(startIndex, endIndex);
    
    renderHistoryTable(pageData);
    updatePaginationControls();
}

function renderHistoryTable(data) {
    const tbody = document.getElementById('historyTableBody');
    
    if (!data || data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="table-empty">暂无符合条件的历史记录</td></tr>';
        return;
    }
    
    tbody.innerHTML = '';
    
    data.forEach(item => {
        const row = document.createElement('tr');
        row.className = `history-row ${item.decision}`;
        
        const dt = new Date(item.timestamp);
        const timeStr = dt.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        
        const decisionIcon = getDecisionIcon(item.decision);
        const decisionLabel = getDecisionLabel(item.decision);
        
        const confidenceLabel = {
            'high': '高',
            'medium': '中',
            'low': '低',
            'ultra': '极高'
        }[item.confidence] || item.confidence;
        
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
        
        // 添加点击事件显示详情
        row.onclick = () => showHistoryDetailModal(item);
        row.style.cursor = 'pointer';
        
        tbody.appendChild(row);
    });
}

/**
 * 显示历史记录详情（模态框）
 */
function showHistoryDetailModal(item) {
    const allTags = (item.reason_tags || []).map(tag => {
        const tagData = reasonTagExplanations[tag];
        return tagData ? `• ${tagData.explanation} (${tag})` : `• ${tag}`;
    }).join('\n');
    
    const priceInfo = item.price ? `\n💰 价格: $${item.price.toLocaleString()}` : '';
    
    const detail = `
📊 决策详情

交易对: ${item.symbol}
周期: ${item.timeframe_label || 'N/A'}
时间: ${new Date(item.timestamp).toLocaleString('zh-CN')}${priceInfo}

【核心决策】
决策: ${item.decision.toUpperCase()}
置信度: ${item.confidence.toUpperCase()}
可执行: ${item.executable ? '是' : '否'}

【决策依据】
${allTags || '无'}
    `.trim();
    
    alert(detail);
}

function updateHistoryStats(data) {
    const stats = {
        total: data.length,
        long: 0,
        short: 0,
        no_trade: 0
    };
    
    data.forEach(item => {
        if (item.decision === 'long') stats.long++;
        else if (item.decision === 'short') stats.short++;
        else stats.no_trade++;
    });
    
    document.getElementById('statTotal').textContent = stats.total;
    document.getElementById('statLong').textContent = stats.long;
    document.getElementById('statShort').textContent = stats.short;
    document.getElementById('statNoTrade').textContent = stats.no_trade;
}

// ==========================================
// 分页控制
// ==========================================

function updatePaginationControls() {
    const totalItems = filteredHistoryData.length;
    const startIndex = (currentPage - 1) * pageSize + 1;
    const endIndex = Math.min(currentPage * pageSize, totalItems);
    
    document.getElementById('pageStart').textContent = totalItems > 0 ? startIndex : 0;
    document.getElementById('pageEnd').textContent = endIndex;
    document.getElementById('pageTotal').textContent = totalItems;
    document.getElementById('currentPageInput').value = currentPage;
    document.getElementById('totalPages').textContent = totalPages;
    
    document.getElementById('btnFirstPage').disabled = currentPage === 1;
    document.getElementById('btnPrevPage').disabled = currentPage === 1;
    document.getElementById('btnNextPage').disabled = currentPage === totalPages;
    document.getElementById('btnLastPage').disabled = currentPage === totalPages;
}

function goToPage(page) {
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    renderCurrentPage();
}

function previousPage() {
    if (currentPage > 1) {
        currentPage--;
        renderCurrentPage();
    }
}

function nextPage() {
    if (currentPage < totalPages) {
        currentPage++;
        renderCurrentPage();
    }
}

function goToLastPage() {
    currentPage = totalPages;
    renderCurrentPage();
}

function goToPageInput() {
    const input = document.getElementById('currentPageInput');
    const page = parseInt(input.value);
    
    if (isNaN(page) || page < 1 || page > totalPages) {
        input.value = currentPage;
        return;
    }
    
    goToPage(page);
}

function changePageSize() {
    pageSize = parseInt(document.getElementById('pageSizeSelect').value) || 20;
    currentPage = 1;
    totalPages = Math.ceil(filteredHistoryData.length / pageSize);
    renderCurrentPage();
}

// ==========================================
// 自动刷新
// ==========================================

function startAutoRefresh() {
    refreshAdvisory();
    
    setInterval(() => {
        refreshAdvisory();
    }, 60000);
}

function updateLastUpdateTime() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
    document.getElementById('lastUpdate').textContent = timeStr;
}

function showLoading() {
    console.log('Loading...');
}
