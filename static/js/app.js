// 全局变量
let klineChart = null;
let autoRefreshInterval = null;

// 格式化数字
function formatNumber(num, decimals = 2) {
    return num.toLocaleString('zh-CN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

// 格式化大数字
function formatLargeNumber(num) {
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

// 加载24小时统计数据
async function loadTicker() {
    try {
        const response = await fetch('/api/ticker');
        const result = await response.json();
        
        if (result.success) {
            const data = result.data;
            
            // 更新当前价格
            document.getElementById('currentPrice').textContent = 
                '$' + formatNumber(data.last_price, 2);
            
            // 更新涨跌
            const change = data.price_change;
            const changePercent = data.price_change_percent;
            const changeElement = document.getElementById('priceChange');
            const changePercentElement = document.getElementById('priceChangePercent');
            
            const isUp = change >= 0;
            const arrow = isUp ? '📈' : '📉';
            const className = isUp ? 'price-up' : 'price-down';
            
            changeElement.textContent = (isUp ? '+' : '') + formatNumber(change, 2);
            changeElement.className = 'card-value ' + className;
            
            changePercentElement.textContent = arrow + ' ' + (isUp ? '+' : '') + 
                formatNumber(changePercent, 2) + '%';
            changePercentElement.className = 'card-subtitle ' + className;
            
            // 更新最高价
            document.getElementById('highPrice').textContent = 
                '$' + formatNumber(data.high_price, 2);
            
            // 更新最低价
            document.getElementById('lowPrice').textContent = 
                '$' + formatNumber(data.low_price, 2);
            
            // 更新成交量
            document.getElementById('volume').textContent = 
                formatLargeNumber(data.volume);
            
            // 更新成交额
            document.getElementById('quoteVolume').textContent = 
                '$' + formatLargeNumber(data.quote_volume);
            
            updateLastUpdateTime();
        }
    } catch (error) {
        console.error('加载24小时统计失败:', error);
    }
}

// 加载订单深度
async function loadOrderbook() {
    try {
        const response = await fetch('/api/orderbook?limit=10');
        const result = await response.json();
        
        if (result.success) {
            const data = result.data;
            
            // 更新卖单
            const askTableBody = document.querySelector('#askTable tbody');
            askTableBody.innerHTML = '';
            data.asks.reverse().forEach(([price, qty]) => {
                const row = askTableBody.insertRow();
                row.className = 'ask-row';
                row.insertCell(0).textContent = formatNumber(price, 2);
                row.insertCell(1).textContent = formatNumber(qty, 6);
            });
            
            // 更新买单
            const bidTableBody = document.querySelector('#bidTable tbody');
            bidTableBody.innerHTML = '';
            data.bids.forEach(([price, qty]) => {
                const row = bidTableBody.insertRow();
                row.className = 'bid-row';
                row.insertCell(0).textContent = formatNumber(price, 2);
                row.insertCell(1).textContent = formatNumber(qty, 6);
            });
        }
    } catch (error) {
        console.error('加载订单深度失败:', error);
    }
}

// 加载最近成交
async function loadTrades() {
    try {
        const response = await fetch('/api/trades?limit=20');
        const result = await response.json();
        
        if (result.success) {
            const tradesTableBody = document.querySelector('#tradesTable tbody');
            tradesTableBody.innerHTML = '';
            
            result.data.forEach(trade => {
                const row = tradesTableBody.insertRow();
                const isBuy = !trade.is_buyer_maker;
                
                row.insertCell(0).textContent = trade.time;
                row.insertCell(1).textContent = formatNumber(trade.price, 2);
                row.insertCell(2).textContent = formatNumber(trade.qty, 6);
                
                const directionCell = row.insertCell(3);
                directionCell.textContent = isBuy ? '🟢买入' : '🔴卖出';
                directionCell.className = isBuy ? 'trade-buy' : 'trade-sell';
            });
        }
    } catch (error) {
        console.error('加载最近成交失败:', error);
    }
}

// 加载K线数据
async function loadKlines() {
    try {
        const interval = document.getElementById('intervalSelect').value;
        const response = await fetch(`/api/klines?interval=${interval}&limit=50`);
        const result = await response.json();
        
        if (result.success) {
            const data = result.data;
            
            // 准备图表数据
            const labels = data.map(k => k.time);
            const prices = data.map(k => k.close);
            const volumes = data.map(k => k.volume);
            
            // 销毁旧图表
            if (klineChart) {
                klineChart.destroy();
            }
            
            // 创建新图表
            const ctx = document.getElementById('klineChart').getContext('2d');
            klineChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '价格 (USDT)',
                        data: prices,
                        borderColor: 'rgb(102, 126, 234)',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHoverRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top'
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            callbacks: {
                                label: function(context) {
                                    return '价格: $' + formatNumber(context.parsed.y, 2);
                                }
                            }
                        }
                    },
                    scales: {
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
                        y: {
                            display: true,
                            title: {
                                display: true,
                                text: '价格 (USDT)'
                            },
                            ticks: {
                                callback: function(value) {
                                    return '$' + formatNumber(value, 0);
                                }
                            }
                        }
                    },
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

// 加载多币种数据
async function loadMultiSymbols() {
    try {
        const response = await fetch('/api/multi-symbols');
        const result = await response.json();
        
        if (result.success) {
            const container = document.getElementById('multiSymbols');
            container.innerHTML = '';
            
            result.data.forEach(coin => {
                const card = document.createElement('div');
                card.className = 'symbol-card';
                
                const isUp = coin.change_percent >= 0;
                const arrow = isUp ? '📈' : '📉';
                const changeClass = isUp ? 'change-up' : 'change-down';
                
                card.innerHTML = `
                    <div class="symbol-name">${coin.symbol}</div>
                    <div class="symbol-price">$${formatNumber(coin.price, 2)}</div>
                    <div class="symbol-change ${changeClass}">
                        ${arrow} ${(isUp ? '+' : '')}${formatNumber(coin.change_percent, 2)}%
                    </div>
                `;
                
                container.appendChild(card);
            });
        }
    } catch (error) {
        console.error('加载多币种数据失败:', error);
    }
}

// 刷新所有数据
function refreshAll() {
    console.log('刷新所有数据...');
    loadTicker();
    loadOrderbook();
    loadTrades();
    loadKlines();
    loadMultiSymbols();
}

// 启动自动刷新
function startAutoRefresh() {
    // 立即加载一次
    refreshAll();
    
    // 设置定时刷新（每10秒）
    autoRefreshInterval = setInterval(() => {
        loadTicker();
        loadOrderbook();
        loadTrades();
        loadMultiSymbols();
    }, 10000);
    
    // K线图每30秒更新一次
    setInterval(loadKlines, 30000);
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('页面加载完成，开始初始化...');
    startAutoRefresh();
});

// 页面卸载时清理
window.addEventListener('beforeunload', function() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    if (klineChart) {
        klineChart.destroy();
    }
});
