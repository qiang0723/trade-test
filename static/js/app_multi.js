// 全局变量
let klineChart = null;
let autoRefreshInterval = null;
let availableMarkets = {};
let currentSymbol = 'BTC';
let currentMarketType = 'spot';

// 格式化数字
function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined || isNaN(num)) return '--';
    return num.toLocaleString('zh-CN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

// 格式化大数字
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

// 更新最后更新时间
function updateLastUpdateTime() {
    const now = new Date();
    document.getElementById('lastUpdate').textContent = 
        now.toLocaleTimeString('zh-CN', { hour12: false });
}

// 加载可用市场信息
async function loadAvailableMarkets() {
    try {
        const response = await fetch('/api/markets');
        const result = await response.json();
        
        if (result.success) {
            availableMarkets = result.data;
            createSymbolButtons();
            
            // 自动选择第一个可用的币种
            for (let symbol in availableMarkets) {
                if (availableMarkets[symbol].spot || availableMarkets[symbol].futures) {
                    currentSymbol = symbol;
                    // 选择可用的市场类型
                    if (availableMarkets[symbol].spot) {
                        currentMarketType = 'spot';
                    } else if (availableMarkets[symbol].futures) {
                        currentMarketType = 'futures';
                    }
                    break;
                }
            }
            
            updateMarketTypeButtons();
        }
    } catch (error) {
        console.error('加载市场信息失败:', error);
    }
}

// 创建币种按钮
function createSymbolButtons() {
    const container = document.getElementById('symbolButtons');
    container.innerHTML = '';
    
    for (let symbol in availableMarkets) {
        const market = availableMarkets[symbol];
        const hasAnyMarket = market.spot || market.futures;
        
        const button = document.createElement('button');
        button.className = 'symbol-btn';
        button.textContent = `${symbol}/USDT`;
        button.dataset.symbol = symbol;
        
        if (!hasAnyMarket) {
            button.className += ' disabled';
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

// 选择币种
function selectSymbol(symbol) {
    const market = availableMarkets[symbol];
    if (!market || (!market.spot && !market.futures)) {
        alert('该币种暂无可用市场');
        return;
    }
    
    currentSymbol = symbol;
    
    // 如果当前市场类型不可用，切换到可用的
    if (currentMarketType === 'spot' && !market.spot) {
        currentMarketType = 'futures';
    } else if (currentMarketType === 'futures' && !market.futures) {
        currentMarketType = 'spot';
    }
    
    // 更新按钮状态
    document.querySelectorAll('.symbol-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.symbol === symbol) {
            btn.classList.add('active');
        }
    });
    
    updateMarketTypeButtons();
    refreshCurrentMarket();
}

// 切换市场类型
function switchMarketType(type) {
    const market = availableMarkets[currentSymbol];
    if (!market) return;
    
    if (type === 'spot' && !market.spot) {
        alert('该币种暂无现货市场');
        return;
    }
    
    if (type === 'futures' && !market.futures) {
        alert('该币种暂无合约市场');
        return;
    }
    
    currentMarketType = type;
    updateMarketTypeButtons();
    refreshCurrentMarket();
}

// 更新市场类型按钮
function updateMarketTypeButtons() {
    const market = availableMarkets[currentSymbol];
    if (!market) return;
    
    document.querySelectorAll('.market-btn').forEach(btn => {
        const type = btn.dataset.type;
        btn.classList.remove('active', 'disabled');
        
        if (type === 'spot' && !market.spot) {
            btn.classList.add('disabled');
        } else if (type === 'futures' && !market.futures) {
            btn.classList.add('disabled');
        }
        
        if (type === currentMarketType) {
            btn.classList.add('active');
        }
    });
}

// 刷新当前市场数据
function refreshCurrentMarket() {
    loadTicker();
    loadKlines();
    loadTrades();
    loadLargeOrders();
    loadMarketAnalysis();
}

// 加载市场分析（仅合约）
async function loadMarketAnalysis() {
    const analysisSection = document.getElementById('marketAnalysisSection');
    
    if (currentMarketType !== 'futures') {
        analysisSection.style.display = 'none';
        return;
    }
    
    analysisSection.style.display = 'block';
    
    try {
        // 显示加载状态
        document.getElementById('mainOperation').textContent = '🔄 正在获取最新数据并分析...';
        
        const response = await fetch(`/api/market-analysis/futures/${currentSymbol}`);
        const result = await response.json();
        
        if (result.success) {
            const analysis = result.analysis;
            
            // 更新标题
            document.getElementById('analysisSymbol').textContent = currentSymbol + '/USDT';
            
            // 更新分析时间
            const now = new Date();
            const timeStr = now.toLocaleString('zh-CN', { 
                month: '2-digit', 
                day: '2-digit', 
                hour: '2-digit', 
                minute: '2-digit', 
                second: '2-digit' 
            });
            document.getElementById('analysisUpdateTime').textContent = 
                `数据更新时间: ${timeStr} | 📊 数据来源: 币安实时行情`;
            
            // 更新三态交易信号（主信号）
            const tradeAction = analysis.trade_action || 'NO_TRADE';
            const tradeActionCard = document.getElementById('tradeActionCard');
            const actionIcon = document.getElementById('actionIcon');
            const actionText = document.getElementById('actionText');
            const actionDescription = document.getElementById('actionDescription');
            
            // 移除所有状态类
            tradeActionCard.classList.remove('action-long', 'action-short', 'action-notrade');
            
            // 根据交易信号设置样式和内容
            if (tradeAction === 'LONG') {
                tradeActionCard.classList.add('action-long');
                actionIcon.textContent = '🟢';
                actionText.textContent = 'LONG';
                actionDescription.textContent = '建议做多 - 符合做多条件，可考虑开多头仓位';
            } else if (tradeAction === 'SHORT') {
                tradeActionCard.classList.add('action-short');
                actionIcon.textContent = '🔴';
                actionText.textContent = 'SHORT';
                actionDescription.textContent = '建议做空 - 符合做空条件，可考虑开空头仓位';
            } else {
                tradeActionCard.classList.add('action-notrade');
                actionIcon.textContent = '⚪';
                actionText.textContent = 'NO_TRADE';
                actionDescription.textContent = '暂不交易 - 信号不明确或市场极端，建议观望';
            }
            
            // 更新做多模型评分和交易信号（辅助参考）
            const longScore = analysis.long_score || 0;
            const tradingSignal = analysis.trading_signal || '观望';
            const longModelCard = document.getElementById('longModelCard');
            
            // 更新做多评分显示
            document.getElementById('longScoreValue').textContent = longScore.toFixed(1);
            document.getElementById('tradingSignal').textContent = tradingSignal;
            
            // 根据做多评分设置评分圈颜色
            const longScoreCircle = document.getElementById('longScoreCircle');
            if (longScore >= 8) {
                longScoreCircle.style.borderColor = 'rgba(255, 255, 255, 0.9)';
                longScoreCircle.style.background = 'rgba(255, 255, 255, 0.25)';
            } else if (longScore >= 6) {
                longScoreCircle.style.borderColor = 'rgba(255, 255, 255, 0.7)';
                longScoreCircle.style.background = 'rgba(255, 255, 255, 0.2)';
            } else {
                longScoreCircle.style.borderColor = 'rgba(255, 255, 255, 0.4)';
                longScoreCircle.style.background = 'rgba(255, 255, 255, 0.15)';
            }
            
            // 更新做空模型评分和交易信号（辅助参考）
            const shortScore = analysis.short_score || 0;
            const shortSignal = analysis.short_signal || '观望';
            const shortModelCard = document.getElementById('shortModelCard');
            
            // 更新做空评分显示
            document.getElementById('shortScoreValue').textContent = shortScore.toFixed(1);
            document.getElementById('shortSignal').textContent = shortSignal;
            
            // 根据做空评分设置评分圈颜色
            const shortScoreCircle = document.getElementById('shortScoreCircle');
            if (shortScore >= 8) {
                shortScoreCircle.style.borderColor = 'rgba(255, 255, 255, 0.9)';
                shortScoreCircle.style.background = 'rgba(255, 255, 255, 0.25)';
            } else if (shortScore >= 6) {
                shortScoreCircle.style.borderColor = 'rgba(255, 255, 255, 0.7)';
                shortScoreCircle.style.background = 'rgba(255, 255, 255, 0.2)';
            } else {
                shortScoreCircle.style.borderColor = 'rgba(255, 255, 255, 0.4)';
                shortScoreCircle.style.background = 'rgba(255, 255, 255, 0.15)';
            }
            
            // 更新市场情绪
            const sentiment = analysis.market_sentiment;
            const sentimentElement = document.getElementById('marketSentiment');
            sentimentElement.textContent = sentiment;
            
            // 根据情绪设置颜色
            if (sentiment.includes('看涨') || sentiment.includes('转多')) {
                sentimentElement.style.color = '#10b981';
            } else if (sentiment.includes('看跌') || sentiment.includes('转空')) {
                sentimentElement.style.color = '#ef4444';
            } else {
                sentimentElement.style.color = '#6b7280';
            }
            
            // 更新风险等级
            const riskLevel = analysis.risk_level;
            const riskElement = document.getElementById('riskLevel');
            riskElement.textContent = riskLevel;
            
            // 根据风险等级设置颜色
            if (riskLevel === '高') {
                riskElement.style.color = '#ef4444';
            } else if (riskLevel === '中') {
                riskElement.style.color = '#f59e0b';
            } else {
                riskElement.style.color = '#10b981';
            }
            
            // 更新1小时买卖力量
            const buyRatio = analysis.data.buy_ratio_1h || 50;
            const sellRatio = analysis.data.sell_ratio_1h || 50;
            
            document.getElementById('miniPowerBuy').style.width = buyRatio + '%';
            document.getElementById('miniPowerSell').style.width = sellRatio + '%';
            document.getElementById('miniPowerBuyText').textContent = '🟢' + buyRatio.toFixed(1) + '%';
            document.getElementById('miniPowerSellText').textContent = '🔴' + sellRatio.toFixed(1) + '%';
            
            // 更新主要操作
            document.getElementById('mainOperation').textContent = analysis.main_operation;
            
            // 更新详细结论列表
            const conclusionsList = document.getElementById('conclusionsList');
            conclusionsList.innerHTML = '';
            
            // 在详细分析开头添加做多做空模型评分概览
            const modelScoresHeader = document.createElement('li');
            modelScoresHeader.style.fontWeight = '700';
            modelScoresHeader.style.fontSize = '1.05em';
            modelScoresHeader.style.color = '#1e293b';
            modelScoresHeader.style.marginBottom = '8px';
            modelScoresHeader.style.borderBottom = '2px solid #cbd5e1';
            modelScoresHeader.style.paddingBottom = '8px';
            modelScoresHeader.textContent = '📊 模型评分概览';
            conclusionsList.appendChild(modelScoresHeader);
            
            // 做多模型评分
            const longScoreInfo = document.createElement('li');
            longScoreInfo.style.color = '#10b981';
            longScoreInfo.style.fontWeight = '600';
            longScoreInfo.style.fontSize = '0.95em';
            longScoreInfo.innerHTML = `📈 做多模型：<span style="font-size: 1.1em; font-weight: 700;">${longScore.toFixed(1)}</span>/10.0 分 - ${tradingSignal}`;
            conclusionsList.appendChild(longScoreInfo);
            
            // 做空模型评分
            const shortScoreInfo = document.createElement('li');
            shortScoreInfo.style.color = '#ef4444';
            shortScoreInfo.style.fontWeight = '600';
            shortScoreInfo.style.fontSize = '0.95em';
            shortScoreInfo.innerHTML = `📉 做空模型：<span style="font-size: 1.1em; font-weight: 700;">${shortScore.toFixed(1)}</span>/10.0 分 - ${shortSignal}`;
            conclusionsList.appendChild(shortScoreInfo);
            
            // 添加分隔线
            const separator = document.createElement('li');
            separator.style.borderTop = '1px solid #e2e8f0';
            separator.style.marginTop = '10px';
            separator.style.marginBottom = '10px';
            separator.innerHTML = '&nbsp;';
            conclusionsList.appendChild(separator);
            
            // 原有的详细结论
            analysis.conclusions.forEach(conclusion => {
                const li = document.createElement('li');
                li.textContent = conclusion;
                conclusionsList.appendChild(li);
            });
            
            // 添加数据详情（可选显示原始数据）
            const dataInfo = document.createElement('li');
            dataInfo.style.color = '#64748b';
            dataInfo.style.fontSize = '0.85em';
            dataInfo.style.marginTop = '8px';
            dataInfo.textContent = `📈 价格24h: ${analysis.data.price_change_24h.toFixed(2)}% | ` +
                                    `持仓量: ${analysis.data.oi_change.toFixed(2)}% | ` +
                                    `成交量: ${analysis.data.volume_change.toFixed(2)}% | ` +
                                    `资金费率: ${analysis.data.funding_rate.toFixed(4)}%`;
            conclusionsList.appendChild(dataInfo);
        } else {
            // 如果分析失败，隐藏区域
            analysisSection.style.display = 'none';
        }
    } catch (error) {
        console.error('加载市场分析失败:', error);
        document.getElementById('mainOperation').textContent = '❌ 分析失败，请稍后重试';
    }
}

// 加载行情数据
async function loadTicker() {
    try {
        const response = await fetch('/api/all-tickers');
        const result = await response.json();
        
        // 找到当前币种的数据
        const marketData = result.markets.find(m => m.symbol === currentSymbol);
        if (!marketData) return;
        
        const data = currentMarketType === 'spot' ? marketData.spot : marketData.futures;
        if (!data || !data.success) return;
        
        const ticker = data.data;
        
        // 更新市场标识
        const marketBadge = document.getElementById('marketBadge');
        marketBadge.textContent = currentMarketType === 'spot' ? '现货' : '合约';
        
        // 更新当前价格
        document.getElementById('currentPrice').textContent = 
            '$' + formatNumber(ticker.last_price, 4);
        
        // 更新涨跌
        const change = ticker.price_change;
        const changePercent = ticker.price_change_percent;
        const changeElement = document.getElementById('priceChange');
        const changePercentElement = document.getElementById('priceChangePercent');
        
        const isUp = change >= 0;
        const arrow = isUp ? '📈' : '📉';
        const className = isUp ? 'price-up' : 'price-down';
        
        changeElement.textContent = (isUp ? '+' : '') + formatNumber(change, 4);
        changeElement.className = 'card-value ' + className;
        
        changePercentElement.textContent = arrow + ' ' + (isUp ? '+' : '') + 
            formatNumber(changePercent, 2) + '%';
        changePercentElement.className = 'card-subtitle ' + className;
        
        // 更新最高价
        document.getElementById('highPrice').textContent = 
            '$' + formatNumber(ticker.high_price, 4);
        
        // 更新最低价
        document.getElementById('lowPrice').textContent = 
            '$' + formatNumber(ticker.low_price, 4);
        
        // 更新成交量
        document.getElementById('volume').textContent = 
            formatLargeNumber(ticker.volume);
        document.getElementById('volumeSymbol').textContent = currentSymbol;
        
        // 更新成交量变化（6小时变化）
        const volumeChange = ticker.volume_change_percent || 0;
        const volumeChangeElement = document.getElementById('volumeChange');
        if (volumeChange !== 0) {
            const isVolumeUp = volumeChange >= 0;
            volumeChangeElement.textContent = (isVolumeUp ? '📈+' : '📉') + formatNumber(Math.abs(volumeChange), 1) + '%';
            volumeChangeElement.className = isVolumeUp ? 'price-up' : 'price-down';
            volumeChangeElement.title = '6小时变化';
        } else {
            volumeChangeElement.textContent = '';
        }
        
        // 更新成交额
        document.getElementById('quoteVolume').textContent = 
            '$' + formatLargeNumber(ticker.quote_volume);
        
        // 更新成交额变化（6小时变化）
        const quoteVolumeChange = ticker.quote_volume_change_percent || 0;
        const quoteVolumeChangeElement = document.getElementById('quoteVolumeChange');
        if (quoteVolumeChange !== 0) {
            const isQuoteVolumeUp = quoteVolumeChange >= 0;
            quoteVolumeChangeElement.textContent = (isQuoteVolumeUp ? '📈+' : '📉') + formatNumber(Math.abs(quoteVolumeChange), 1) + '%';
            quoteVolumeChangeElement.className = isQuoteVolumeUp ? 'price-up' : 'price-down';
            quoteVolumeChangeElement.title = '6小时变化';
        } else {
            quoteVolumeChangeElement.textContent = '';
        }
        
        // 显示/隐藏合约专属数据（资金费率和持仓量）
        const fundingRateCard = document.getElementById('fundingRateCard');
        const openInterestCard = document.getElementById('openInterestCard');
        
        if (currentMarketType === 'futures') {
            // 显示资金费率
            fundingRateCard.style.display = 'block';
            const fundingRate = ticker.funding_rate !== undefined ? ticker.funding_rate : 0;
            const fundingRatePercent = (fundingRate * 100).toFixed(4);
            const isFundingPositive = fundingRate >= 0;
            
            document.getElementById('fundingRate').textContent = 
                (isFundingPositive ? '+' : '') + fundingRatePercent + '%';
            document.getElementById('fundingRate').className = 
                'card-value ' + (isFundingPositive ? 'price-up' : 'price-down');
            
            // 显示下次结算时间和说明
            let subtitleText = '';
            if (ticker.next_funding_time) {
                const nextTime = new Date(ticker.next_funding_time);
                const hoursLeft = Math.floor((nextTime - new Date()) / (1000 * 60 * 60));
                const minutesLeft = Math.floor(((nextTime - new Date()) % (1000 * 60 * 60)) / (1000 * 60));
                subtitleText = `下次结算: ${hoursLeft}h ${minutesLeft}m | `;
            }
            
            // 添加资金费率说明
            if (fundingRate > 0) {
                subtitleText += '多头付费给空头';
            } else if (fundingRate < 0) {
                subtitleText += '空头付费给多头';
            } else {
                subtitleText += '多空平衡';
            }
            
            document.getElementById('fundingRatePercent').textContent = subtitleText;
            
            // 显示持仓量
            openInterestCard.style.display = 'block';
            const openInterest = ticker.open_interest || 0;
            document.getElementById('openInterest').textContent = 
                formatLargeNumber(openInterest);
            document.getElementById('openInterestSymbol').textContent = currentSymbol;
            
            // 更新持仓量变化（6小时变化）
            const openInterestChange = ticker.open_interest_change_percent || 0;
            const openInterestChangeElement = document.getElementById('openInterestChange');
            if (openInterestChange !== 0) {
                const isOiUp = openInterestChange >= 0;
                openInterestChangeElement.textContent = (isOiUp ? '📈+' : '📉') + formatNumber(Math.abs(openInterestChange), 1) + '%';
                openInterestChangeElement.className = isOiUp ? 'price-up' : 'price-down';
                openInterestChangeElement.title = '6小时变化';
            } else {
                openInterestChangeElement.textContent = '';
            }
        } else {
            // 现货模式下隐藏
            fundingRateCard.style.display = 'none';
            openInterestCard.style.display = 'none';
        }
        
        updateLastUpdateTime();
    } catch (error) {
        console.error('加载行情数据失败:', error);
    }
}
// 加载综合K线数据（价格+成交量+成交额+持仓量）
async function loadKlines() {
    try {
        const interval = document.getElementById('intervalSelect').value;
        const response = await fetch(`/api/klines/${currentMarketType}/${currentSymbol}?interval=${interval}&limit=50`);
        const result = await response.json();
        
        if (result.success) {
            const data = result.data;
            
            // 更新标题
            document.getElementById('chartSymbol').textContent = currentSymbol + '/USDT';
            document.getElementById('chartMarketType').textContent = 
                currentMarketType === 'spot' ? '现货' : '合约';
            
            // 准备基础数据
            const labels = data.map(k => k.time);
            const prices = data.map(k => k.close);
            const volumes = data.map(k => k.volume);
            const quoteVolumes = data.map(k => k.quote_volume);
            
            // 创建数据集数组
            const datasets = [
                {
                    label: '💰 价格 (USDT)',
                    data: prices,
                    borderColor: 'rgb(102, 126, 234)',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    yAxisID: 'yPrice',
                    type: 'line',
                    order: 1
                },
                {
                    label: `📊 成交量 (${currentSymbol})`,
                    data: volumes,
                    backgroundColor: 'rgba(16, 185, 129, 0.5)',
                    borderColor: 'rgb(16, 185, 129)',
                    borderWidth: 1,
                    yAxisID: 'yVolume',
                    type: 'bar',
                    order: 3
                },
                {
                    label: '💵 成交额 (USDT)',
                    data: quoteVolumes,
                    borderColor: 'rgb(245, 158, 11)',
                    backgroundColor: 'rgba(245, 158, 11, 0.3)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 5,
                    yAxisID: 'yQuoteVolume',
                    type: 'line',
                    order: 2
                }
            ];
            
            // 如果是合约，获取持仓量数据
            let openInterests = [];
            if (currentMarketType === 'futures') {
                document.getElementById('oiTitle').style.display = 'inline';
                try {
                    const oiResponse = await fetch(`/api/open-interest-history/${currentSymbol}?period=${interval}&limit=50`);
                    const oiResult = await oiResponse.json();
                    if (oiResult.success && oiResult.data.length > 0) {
                        // 对齐时间标签
                        openInterests = labels.map(label => {
                            const found = oiResult.data.find(item => item.time === label);
                            return found ? found.open_interest : null;
                        });
                        
                        datasets.push({
                            label: `📈 持仓量 (${currentSymbol})`,
                            data: openInterests,
                            borderColor: 'rgb(168, 85, 247)',
                            backgroundColor: 'rgba(168, 85, 247, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.4,
                            pointRadius: 0,
                            pointHoverRadius: 5,
                            yAxisID: 'yOI',
                            type: 'line',
                            order: 4
                        });
                    }
                } catch (error) {
                    console.log('持仓量数据获取失败:', error);
                }
            } else {
                document.getElementById('oiTitle').style.display = 'none';
            }
            
            // 销毁旧图表
            if (klineChart) {
                klineChart.destroy();
            }
            
            // 创建综合图表
            const ctx = document.getElementById('klineChart').getContext('2d');
            
            // 配置Y轴
            const scales = {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: '时间'
                    },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45
                    }
                },
                yPrice: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: '价格 (USDT)',
                        color: 'rgb(102, 126, 234)'
                    },
                    ticks: {
                        callback: function(value) {
                            return '$' + formatNumber(value, 2);
                        },
                        color: 'rgb(102, 126, 234)'
                    }
                },
                yVolume: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: `成交量 (${currentSymbol})`,
                        color: 'rgb(16, 185, 129)'
                    },
                    ticks: {
                        callback: function(value) {
                            return formatLargeNumber(value);
                        },
                        color: 'rgb(16, 185, 129)'
                    },
                    grid: {
                        drawOnChartArea: false
                    }
                },
                yQuoteVolume: {
                    type: 'linear',
                    display: false,
                    position: 'right'
                }
            };
            
            // 如果有持仓量数据，添加持仓量Y轴
            if (currentMarketType === 'futures' && openInterests.length > 0) {
                scales.yOI = {
                    type: 'linear',
                    display: false,
                    position: 'right'
                };
            }
            
            klineChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: {
                                usePointStyle: true,
                                padding: 15
                            }
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            callbacks: {
                                label: function(context) {
                                    const label = context.dataset.label || '';
                                    const value = context.parsed.y;
                                    if (label.includes('价格')) {
                                        return label + ': $' + formatNumber(value, 4);
                                    } else if (label.includes('成交额')) {
                                        return label + ': $' + formatLargeNumber(value);
                                    } else {
                                        return label + ': ' + formatLargeNumber(value);
                                    }
                                }
                            }
                        }
                    },
                    scales: scales,
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    }
                }
            });
        }
    } catch (error) {
        console.error('加载K线数据失败:', error);
    }
}

// 加载所有市场概览
async function loadAllMarketsOverview() {
    try {
        const response = await fetch('/api/all-tickers');
        const result = await response.json();
        
        const container = document.getElementById('allMarketsOverview');
        container.innerHTML = '';
        
        result.markets.forEach(market => {
            // 现货卡片
            if (market.spot && market.spot.success) {
                const card = createMarketCard(market.symbol, 'spot', market.spot.data);
                container.appendChild(card);
            }
            
            // 合约卡片
            if (market.futures && market.futures.success) {
                const card = createMarketCard(market.symbol, 'futures', market.futures.data);
                container.appendChild(card);
            }
            
            // 如果两个都不可用
            if ((!market.spot || !market.spot.success) && (!market.futures || !market.futures.success)) {
                const card = document.createElement('div');
                card.className = 'market-overview-card';
                card.innerHTML = `
                    <div class="market-overview-header">
                        <div class="market-overview-symbol">${market.symbol}/USDT</div>
                    </div>
                    <div class="market-unavailable">暂无可用市场</div>
                `;
                container.appendChild(card);
            }
        });
    } catch (error) {
        console.error('加载市场概览失败:', error);
    }
}

// 创建市场卡片
function createMarketCard(symbol, marketType, data) {
    const card = document.createElement('div');
    card.className = 'market-overview-card';
    
    const isUp = data.price_change_percent >= 0;
    const arrow = isUp ? '📈' : '📉';
    const changeClass = isUp ? 'change-up' : 'change-down';
    
    card.innerHTML = `
        <div class="market-overview-header">
            <div class="market-overview-symbol">${symbol}/USDT</div>
            <div class="market-overview-type ${marketType}">
                ${marketType === 'spot' ? '现货' : '合约'}
            </div>
        </div>
        <div class="market-overview-price">$${formatNumber(data.last_price, 4)}</div>
        <div class="market-overview-change ${changeClass}">
            ${arrow} ${(isUp ? '+' : '')}${formatNumber(data.price_change_percent, 2)}%
        </div>
    `;
    
    card.onclick = () => {
        currentSymbol = symbol;
        currentMarketType = marketType;
        
        // 更新按钮状态
        document.querySelectorAll('.symbol-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.symbol === symbol) {
                btn.classList.add('active');
            }
        });
        
        updateMarketTypeButtons();
        refreshCurrentMarket();
        
        // 滚动到顶部
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    
    return card;
}

// 刷新所有数据
function refreshAll() {
    console.log('刷新所有数据...');
    refreshCurrentMarket();
    loadAllMarketsOverview();
}

// 启动自动刷新
function startAutoRefresh() {
    // 立即加载一次
    loadAvailableMarkets().then(() => {
        refreshAll();
    });
    
    // 设置定时刷新（每10秒）
    autoRefreshInterval = setInterval(() => {
        loadTicker();
        loadTrades();
        loadLargeOrders();
        loadAllMarketsOverview();
    }, 10000);
    
    // K线图每30秒更新一次
    setInterval(loadKlines, 30000);
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('页面加载完成，开始初始化...');
    startAutoRefresh();
});

// 加载最近成交
async function loadTrades() {
    try {
        const timeRange = document.getElementById('tradesTimeRangeSelect').value;
        const response = await fetch(`/api/trades/${currentMarketType}/${currentSymbol}?time_range=${timeRange}`);
        const result = await response.json();
        
        if (result.success) {
            // 更新标题
            const timeRangeMinutes = result.time_range_minutes;
            let timeRangeText = '';
            if (timeRangeMinutes) {
                if (timeRangeMinutes < 60) {
                    timeRangeText = ` - 近${timeRangeMinutes}分钟`;
                } else {
                    timeRangeText = ` - 近${timeRangeMinutes / 60}小时`;
                }
            }
            
            document.getElementById('tradesSymbol').textContent = currentSymbol + '/USDT' + timeRangeText;
            document.getElementById('tradesMarketType').textContent = 
                currentMarketType === 'spot' ? '现货' : '合约';
            
            // 统计买卖数据
            let buyCount = 0;
            let sellCount = 0;
            let buyVolume = 0;
            let sellVolume = 0;
            let buyAmount = 0;
            let sellAmount = 0;
            
            const tradesTableBody = document.querySelector('#tradesTable tbody');
            tradesTableBody.innerHTML = '';
            
            result.data.forEach(trade => {
                const isBuy = !trade.is_buyer_maker;
                
                // 统计数据
                if (isBuy) {
                    buyCount++;
                    buyVolume += trade.qty;
                    buyAmount += trade.quote_qty;
                } else {
                    sellCount++;
                    sellVolume += trade.qty;
                    sellAmount += trade.quote_qty;
                }
                
                // 填充表格
                const row = tradesTableBody.insertRow();
                
                row.insertCell(0).textContent = trade.time;
                row.insertCell(1).textContent = formatNumber(trade.price, 4);
                row.insertCell(2).textContent = formatNumber(trade.qty, 6);
                row.insertCell(3).textContent = formatNumber(trade.quote_qty, 2);
                
                const directionCell = row.insertCell(4);
                directionCell.textContent = isBuy ? '🟢买入' : '🔴卖出';
                directionCell.className = isBuy ? 'trade-buy' : 'trade-sell';
            });
            
            // 更新统计信息
            updateTradesStatistics(buyCount, sellCount, buyVolume, sellVolume, buyAmount, sellAmount);
        }
    } catch (error) {
        console.error('加载成交记录失败:', error);
    }
}

// 更新成交统计信息
function updateTradesStatistics(buyCount, sellCount, buyVolume, sellVolume, buyAmount, sellAmount) {
    const totalCount = buyCount + sellCount;
    const totalAmount = buyAmount + sellAmount;
    
    // 更新笔数
    document.getElementById('tradesTotal').textContent = totalCount;
    document.getElementById('tradesBuyCount').textContent = buyCount;
    document.getElementById('tradesSellCount').textContent = sellCount;
    
    // 更新成交量
    document.getElementById('tradesBuyVolume').textContent = formatNumber(buyVolume, 4) + ' ' + currentSymbol;
    document.getElementById('tradesSellVolume').textContent = formatNumber(sellVolume, 4) + ' ' + currentSymbol;
    
    // 更新成交额
    document.getElementById('tradesBuyAmount').textContent = '$' + formatLargeNumber(buyAmount);
    document.getElementById('tradesSellAmount').textContent = '$' + formatLargeNumber(sellAmount);
    
    // 计算买卖力量占比
    const buyRatio = totalAmount > 0 ? (buyAmount / totalAmount * 100) : 50;
    const sellRatio = 100 - buyRatio;
    
    // 更新买卖力量进度条
    document.getElementById('tradesPowerBuy').style.width = buyRatio + '%';
    document.getElementById('tradesPowerSell').style.width = sellRatio + '%';
    document.getElementById('tradesPowerBuyPercent').textContent = formatNumber(buyRatio, 1) + '%';
    document.getElementById('tradesPowerSellPercent').textContent = formatNumber(sellRatio, 1) + '%';
}

// 加载大单分析
async function loadLargeOrders() {
    try {
        const timeRange = document.getElementById('timeRangeSelect').value;
        const threshold = document.getElementById('thresholdSelect').value;
        const response = await fetch(`/api/large-orders/${currentMarketType}/${currentSymbol}?time_range=${timeRange}&threshold=${threshold}`);
        const result = await response.json();
        
        if (result.success) {
            const analysis = result.analysis;
            const timeRangeHours = result.time_range_hours;
            const threshold = document.getElementById('thresholdSelect').value;
            
            // 更新标题
            document.getElementById('largeOrdersSymbol').textContent = currentSymbol + '/USDT';
            document.getElementById('largeOrdersMarketType').textContent = 
                currentMarketType === 'spot' ? '现货' : '合约';
            
            // 更新金额阈值显示
            const thresholdDisplay = document.getElementById('thresholdDisplay');
            thresholdDisplay.textContent = `(金额 ≥ ${formatNumber(parseFloat(threshold), 0)} USDT)`;
            
            // 更新时间范围显示
            const timeRangeDisplay = document.getElementById('timeRangeDisplay');
            if (timeRangeHours) {
                timeRangeDisplay.textContent = ` - 近${timeRangeHours}小时`;
            } else {
                timeRangeDisplay.textContent = '';
            }
            
            // 更新统计数据
            document.getElementById('totalTrades').textContent = analysis.total_trades;
            document.getElementById('largeOrdersCount').textContent = analysis.large_orders_count;
            
            document.getElementById('buyRatio').textContent = formatNumber(analysis.buy_ratio, 1) + '%';
            document.getElementById('buyAmount').textContent = '$' + formatLargeNumber(analysis.buy_amount);
            
            document.getElementById('sellRatio').textContent = formatNumber(analysis.sell_ratio, 1) + '%';
            document.getElementById('sellAmount').textContent = '$' + formatLargeNumber(analysis.sell_amount);
            
            document.getElementById('largeBuyCount').textContent = analysis.large_buy_count;
            document.getElementById('largeSellCount').textContent = analysis.large_sell_count;
            
            // 更新买卖力量进度条
            const buyRatio = analysis.buy_ratio;
            const sellRatio = analysis.sell_ratio;
            
            document.getElementById('powerBuy').style.width = buyRatio + '%';
            document.getElementById('powerSell').style.width = sellRatio + '%';
            document.getElementById('powerBuyPercent').textContent = formatNumber(buyRatio, 1) + '%';
            document.getElementById('powerSellPercent').textContent = formatNumber(sellRatio, 1) + '%';
            
            // 更新大单列表
            const largeOrdersTableBody = document.querySelector('#largeOrdersTable tbody');
            largeOrdersTableBody.innerHTML = '';
            
            analysis.large_orders.forEach(order => {
                const row = largeOrdersTableBody.insertRow();
                const isBuy = order.type === 'buy';
                
                row.className = isBuy ? 'large-order-buy' : 'large-order-sell';
                
                row.insertCell(0).textContent = order.time;
                row.insertCell(1).textContent = formatNumber(order.price, 4);
                row.insertCell(2).textContent = formatNumber(order.qty, 6);
                
                const amountCell = row.insertCell(3);
                amountCell.textContent = '$' + formatNumber(order.amount, 0);
                amountCell.style.fontWeight = 'bold';
                
                const typeCell = row.insertCell(4);
                const typeSpan = document.createElement('span');
                typeSpan.className = `large-order-type ${order.type}`;
                typeSpan.textContent = isBuy ? '🟢 大额买入' : '🔴 大额卖出';
                typeCell.appendChild(typeSpan);
            });
            
            // 如果没有大单
            if (analysis.large_orders.length === 0) {
                const row = largeOrdersTableBody.insertRow();
                const cell = row.insertCell(0);
                cell.colSpan = 5;
                const threshold = document.getElementById('thresholdSelect').value;
                cell.textContent = `暂无大单（金额 ≥ ${formatNumber(parseFloat(threshold), 0)} USDT）`;
                cell.style.textAlign = 'center';
                cell.style.color = '#999';
                cell.style.padding = '20px';
            }
        }
    } catch (error) {
        console.error('加载大单分析失败:', error);
    }
}

// 页面卸载时清理
window.addEventListener('beforeunload', function() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    if (klineChart) {
        klineChart.destroy();
    }
});
