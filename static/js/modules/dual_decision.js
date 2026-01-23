/**
 * Dual Decision Module - 双周期决策渲染模块
 * 
 * 职责：
 * 1. 渲染双周期决策卡片
 * 2. 创建详情弹窗
 * 3. 格式化显示数据
 */

export class DualDecisionRenderer {
    constructor(reasonTagExplanations = {}) {
        this.reasonTagExplanations = reasonTagExplanations;
    }
    
    /**
     * 更新所有决策面板
     */
    updateAllDecisionsPanel(decisions, availableSymbols) {
        const grid = document.getElementById('decisionsGrid');
        grid.innerHTML = '';
        
        if (!decisions || Object.keys(decisions).length === 0) {
            grid.innerHTML = '<div class="loading-placeholder">暂无决策数据</div>';
            return;
        }
        
        for (const symbol of availableSymbols) {
            const dualData = decisions[symbol];
            if (!dualData) continue;
            
            const card = this.createDecisionCard(symbol, dualData);
            grid.appendChild(card);
        }
    }
    
    /**
     * 创建双周期决策卡片
     */
    createDecisionCard(symbol, dualData) {
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
        
        // 一致性标签
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
                    <span class="decision-icon-mini">${this.getDecisionIcon(short_term.decision)}</span>
                    <span class="decision-text ${short_term.decision}">${this.getDecisionLabel(short_term.decision)}</span>
                    <span class="confidence-mini ${short_term.confidence}">${short_term.confidence.toUpperCase()}</span>
                </div>
            </div>
            
            <!-- 中长期决策 -->
            <div class="timeframe-row medium-term">
                <span class="timeframe-label">中长 1h/6h</span>
                <div class="timeframe-decision">
                    <span class="decision-icon-mini">${this.getDecisionIcon(medium_term.decision)}</span>
                    <span class="decision-text ${medium_term.decision}">${this.getDecisionLabel(medium_term.decision)}</span>
                    <span class="confidence-mini ${medium_term.confidence}">${medium_term.confidence.toUpperCase()}</span>
                </div>
            </div>
            
            <!-- 一致性标签 -->
            <div class="alignment-badge ${alignmentClass}">
                ${alignmentText}
            </div>
        `;
        
        return card;
    }
    
    getDecisionIcon(decision) {
        const icons = {
            'long': '🟢',
            'short': '🔴',
            'no_trade': '⚪'
        };
        return icons[decision] || '⚪';
    }
    
    getDecisionLabel(decision) {
        const labels = {
            'long': 'LONG',
            'short': 'SHORT',
            'no_trade': 'NO_TRADE'
        };
        return labels[decision] || decision;
    }
    
    /**
     * 创建详情HTML
     */
    createDetailHTML(symbol, dualData) {
        const { short_term, medium_term, alignment, risk_exposure_allowed, global_risk_tags, timestamp } = dualData;
        
        const shortTermHTML = this.createTimeframeDetailHTML(short_term, 'short-term', '短期决策 (5m/15m)');
        const mediumTermHTML = this.createTimeframeDetailHTML(medium_term, 'medium-term', '中长期决策 (1h/6h)');
        const alignmentHTML = this.createAlignmentDetailHTML(alignment);
        const riskHTML = this.createGlobalRiskHTML(risk_exposure_allowed, global_risk_tags);
        
        return `
            <div class="detail-header">
                <h3>📊 ${symbol} - 双周期决策详情</h3>
                <button class="detail-close" onclick="window.closeDetailModal()">✕ 关闭</button>
            </div>
            
            <div class="detail-body">
                <div class="detail-section">
                    <h4>🎯 双周期独立决策</h4>
                    <div class="dual-timeframe-detail">
                        ${shortTermHTML}
                        ${mediumTermHTML}
                        ${alignmentHTML}
                    </div>
                </div>
                
                <div class="detail-section">
                    ${riskHTML}
                </div>
                
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
    
    createTimeframeDetailHTML(tf, cssClass, title) {
        const decisionIcon = this.getDecisionIcon(tf.decision);
        const decisionText = this.getDecisionLabel(tf.decision);
        const execText = tf.executable ? '✓ 可执行' : '✗ 不可执行';
        
        // 关键指标
        const metricsHTML = Object.entries(tf.key_metrics || {}).slice(0, 6).map(([key, value]) => `
            <div class="metric-item">
                <div class="metric-label">${key}</div>
                <div class="metric-value">${this.formatMetricValue(value)}</div>
            </div>
        `).join('');
        
        // 原因标签
        const tagsHTML = (tf.reason_tags || []).slice(0, 4).map(tag => {
            const tagData = this.reasonTagExplanations[tag];
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
    
    createAlignmentDetailHTML(alignment) {
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
                    <span class="detail-value">${this.getDecisionIcon(alignment.recommended_action)} ${alignment.recommended_action.toUpperCase()}</span>
                </div>
                
                <div class="alignment-notes">
                    ${alignment.recommendation_notes}
                </div>
            </div>
        `;
    }
    
    createGlobalRiskHTML(risk_allowed, risk_tags) {
        const riskStatus = risk_allowed ? '✅ 通过' : '❌ 拒绝';
        const riskClass = risk_allowed ? 'success' : 'danger';
        
        let tagsHTML = '';
        if (risk_tags && risk_tags.length > 0) {
            tagsHTML = `
                <div style="margin-top: 12px; padding: 12px; background: #fff3cd; border-radius: 8px;">
                    <strong>⚠️ 全局风险标签:</strong><br>
                    ${risk_tags.join(', ')}
                </div>
            `;
        }
        
        return `
            <h4>🛡️ 全局风险状态</h4>
            <div class="gate-mini ${riskClass}">
                <span class="gate-label">风险准入</span>
                <span class="gate-value">${riskStatus}</span>
            </div>
            ${tagsHTML}
        `;
    }
    
    formatMetricValue(value) {
        if (typeof value === 'number') {
            if (Math.abs(value) < 0.01) {
                return (value * 100).toFixed(3) + '%';
            } else {
                return (value * 100).toFixed(2) + '%';
            }
        }
        return value;
    }
}

// 导出默认实例
export const dualDecisionRenderer = new DualDecisionRenderer();
