/**
 * Signal Notification Module - 信号通知模块
 * 
 * 职责：
 * 1. 检测新信号
 * 2. 显示弹窗通知
 * 3. 浏览器通知
 * 4. 声音提示
 */

export class SignalNotification {
    constructor() {
        this.previousDecisions = {};
        this.enabled = true;
        this.soundEnabled = true;
        
        // 加载用户设置
        this.loadSettings();
    }
    
    loadSettings() {
        const savedNotification = localStorage.getItem('signalNotificationEnabled');
        if (savedNotification !== null) {
            this.enabled = savedNotification === 'true';
        }
        
        const savedSound = localStorage.getItem('soundEnabled');
        if (savedSound !== null) {
            this.soundEnabled = savedSound === 'true';
        }
    }
    
    saveSettings() {
        localStorage.setItem('signalNotificationEnabled', this.enabled);
        localStorage.setItem('soundEnabled', this.soundEnabled);
    }
    
    toggleNotification() {
        this.enabled = !this.enabled;
        this.saveSettings();
        return this.enabled;
    }
    
    toggleSound() {
        this.soundEnabled = !this.soundEnabled;
        this.saveSettings();
        return this.soundEnabled;
    }
    
    /**
     * 请求浏览器通知权限
     */
    requestPermission() {
        if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission();
        }
    }
    
    /**
     * 检测新信号
     */
    checkForNewSignals(newDecisions) {
        if (!this.enabled) return;
        
        const newSignals = [];
        
        for (const symbol in newDecisions) {
            const newDual = newDecisions[symbol];
            const oldDual = this.previousDecisions[symbol];
            
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
        this.previousDecisions = { ...newDecisions };
        
        // 显示信号提示
        if (newSignals.length > 0) {
            this.showSignalNotifications(newSignals);
        }
    }
    
    /**
     * 显示信号通知
     */
    showSignalNotifications(signals) {
        signals.forEach((signal, index) => {
            setTimeout(() => {
                this.showSignalPopup(signal);
                
                if (this.soundEnabled) {
                    this.playNotificationSound(signal.decision);
                }
                
                this.showBrowserNotification(signal);
            }, index * 500);
        });
    }
    
    /**
     * 显示信号弹窗
     */
    showSignalPopup(signal) {
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
                <button class="signal-close" onclick="window.closeSignalPopup(this)">×</button>
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
                    <button class="signal-btn signal-btn-detail" onclick="window.showDetailFromPopup('${symbol}')">
                        查看详情
                    </button>
                    <button class="signal-btn signal-btn-close" onclick="window.closeSignalPopup(this)">
                        关闭
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(popup);
        
        setTimeout(() => popup.classList.add('show'), 10);
        
        // 10秒后自动关闭
        setTimeout(() => {
            if (popup.parentNode) {
                this.closePopup(popup);
            }
        }, 10000);
    }
    
    /**
     * 关闭弹窗
     */
    closePopup(popup) {
        popup.classList.remove('show');
        setTimeout(() => {
            if (popup.parentNode) {
                popup.parentNode.removeChild(popup);
            }
        }, 300);
    }
    
    /**
     * 播放通知声音
     */
    playNotificationSound(decision) {
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
    
    /**
     * 显示浏览器通知
     */
    showBrowserNotification(signal) {
        if (!("Notification" in window)) {
            return;
        }
        
        if (Notification.permission === "granted") {
            this.createNotification(signal);
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission().then(permission => {
                if (permission === "granted") {
                    this.createNotification(signal);
                }
            });
        }
    }
    
    /**
     * 创建浏览器通知
     */
    createNotification(signal) {
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
        };
        
        setTimeout(() => notification.close(), 3000);
    }
}

// 导出默认实例
export const signalNotification = new SignalNotification();
