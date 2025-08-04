// stock-page.js

document.addEventListener('DOMContentLoaded', function() {
    // 全局图表实例变量
    let mainChart = null;
    let ratioChart = null; // 为第二个图表预留
    let stockManager = null;

    // 功能函数：设置页面顶部的标签页切换
    function setupTabs() {
        const tabLinks = document.querySelectorAll('.tab-link');
        const tabContents = document.querySelectorAll('.tab-content');
        
        tabLinks.forEach(link => {
            link.addEventListener('click', () => {
                tabLinks.forEach(l => l.classList.remove('active'));
                tabContents.forEach(c => c.classList.remove('active'));
                
                const tabId = link.dataset.tab;
                const activeContent = document.getElementById(tabId);
                link.classList.add('active');
                if (activeContent) activeContent.classList.add('active');
            });
        });
    }

    // 计算简单移动平均线 (SMA) 函数
    function calcSMA(arr, period) {
        const validData = arr.filter(item => 
            item.close !== null && 
            item.close !== undefined && 
            !isNaN(parseFloat(item.close))
        );
        
        return validData.map((item, idx, all) => {
            if (idx < period - 1) {
                return [new Date(item.date).getTime(), null];
            }

            const slice = all.slice(idx - period + 1, idx + 1);
            const sum = slice.reduce((a, b) => a + parseFloat(b.close), 0);
            return [new Date(item.date).getTime(), sum / period];
        });
    }

    // 核心类：用于管理股票数据获取和状态轮询
    class StockDataManager {
        constructor(ticker) {
            this.ticker = ticker;
            this.downloadInterval = null;
            this.maxRetries = 30;
            this.retryCount = 0;
            this.fullStockData = null;
        }

        async fetchStockData(range = '10Y') {
            try {
                const response = await fetch(`/api/stocks/${this.ticker}/?range=${range}`);
                const data = await response.json();
                
                if (data.downloading) {
                    this.showDownloadingStatus();
                    this.startPolling();
                } else if (data.historical && data.historical.length > 0) {
                    this.fullStockData = data;
                    this.renderChart(data);
                } else {
                    this.showNoDataMessage();
                }
            } catch (error) {
                console.error('获取股票数据失败:', error);
                this.showErrorMessage('数据获取失败，请检查网络连接或刷新页面。');
            }
        }

        showDownloadingStatus() {
            const container = document.getElementById('apex-chart-container');
            container.innerHTML = `
                <div class="download-status">
                    <h3>正在下载 ${this.ticker} 的历史数据...</h3>
                    <p>首次下载可能需要1-2分钟，请稍候。</p>
                </div>
            `;
        }
        
        startPolling() {
            this.retryCount = 0;
            this.downloadInterval = setInterval(() => {
                this.checkDownloadStatus();
            }, 10000);
        }

        async checkDownloadStatus() {
            this.retryCount++;
            try {
                const response = await fetch(`/api/check-status/${this.ticker}/`);
                const data = await response.json();
                
                if (data.has_data && data.record_count > 0) {
                    this.stopPolling();
                    this.showSuccess(data.record_count);
                    setTimeout(() => this.fetchStockData(), 2000);
                } else if (this.retryCount >= this.maxRetries) {
                    this.stopPolling();
                    this.showTimeout();
                }
            } catch (error) {
                console.error('检查下载状态失败:', error);
                if (this.retryCount >= this.maxRetries) {
                    this.stopPolling();
                    this.showError('检查下载状态时发生网络错误。');
                }
            }
        }

        stopPolling() {
            if (this.downloadInterval) {
                clearInterval(this.downloadInterval);
                this.downloadInterval = null;
            }
        }
        
        showSuccess(recordCount) {
            const container = document.getElementById('apex-chart-container');
            container.innerHTML = `
                <div class="download-status">
                    <h3>下载完成！</h3>
                    <p>成功下载 ${recordCount} 条历史数据。正在加载图表...</p>
                </div>
            `;
        }

        showTimeout() {
            const container = document.getElementById('apex-chart-container');
            container.innerHTML = `<div class="download-status"><h3>下载超时</h3><p>请稍后刷新页面重试。</p></div>`;
        }

        showNoDataMessage() {
            const container = document.getElementById('apex-chart-container');
            container.innerHTML = `<div class="download-status"><h3>暂无数据</h3><p>无法获取 ${this.ticker} 的历史数据。</p></div>`;
        }

        showErrorMessage(message) {
            const container = document.getElementById('apex-chart-container');
            container.innerHTML = `<div class="download-status"><h3>错误</h3><p>${message}</p></div>`;
        }

        renderChart(data) {
            if (mainChart) {
                mainChart.destroy();
                mainChart = null;
            }
            const chartContainer = document.getElementById('apex-chart-container');
            if (!chartContainer) return;
            chartContainer.innerHTML = "";

            const historicalData = data.historical || [];
            if (historicalData.length === 0) {
                this.showNoDataMessage();
                return;
            }

            const options = this.getChartOptions(data);
            mainChart = new ApexCharts(chartContainer, options);
            mainChart.render();
            this.setupRangeButtons();
        }

        async updateChartWithRange(range) {
            await this.fetchStockData(range);
        }
        
        setupRangeButtons() {
            const controls = document.querySelector('.stock-chart .chart-controls');
            // 使用事件委托，避免重复绑定事件
            if (controls && !controls.dataset.listenerAttached) {
                controls.addEventListener('click', (event) => {
                    const button = event.target.closest('button[data-range]');
                    if (button) {
                        controls.querySelectorAll('button[data-range]').forEach(btn => btn.classList.remove('active'));
                        button.classList.add('active');
                        this.updateChartWithRange(button.dataset.range);
                    }
                });
                controls.dataset.listenerAttached = 'true';
            }
        }
        
        getChartOptions(data) {
            const historicalData = data.historical || [];
            return {
                series: [{
                    name: '收盘价',
                    data: historicalData.map(item => [new Date(item.date).getTime(), parseFloat(item.close)])
                }, {
                    name: '5日均线',
                    data: calcSMA(historicalData, 5)
                }, {
                    name: '120日均线',
                    data: calcSMA(historicalData, 120)
                }],
                chart: {
                    type: 'line',
                    height: '80%',
                    zoom: { enabled: true },
                    animations: { enabled: false } // 禁用动画以提高重绘性能
                },
                colors: ['#008FFB', '#00E396', '#FEB019'],
                stroke: { width: [2, 1, 1], curve: 'straight' },
                xaxis: {
                    type: 'datetime',
                    tooltip: { enabled: true }
                },
                yaxis: {
                    labels: {
                        formatter: function(val) {
                            return (val !== null && !isNaN(val)) ? Number(val).toFixed(2) : '0.00';
                        }
                    },
                    tooltip: { enabled: true }
                },
                tooltip: {
                    x: { format: 'yyyy-MM-dd' },
                    y: {
                        formatter: function(val) {
                           return (val !== null && !isNaN(val)) ? '$' + Number(val).toFixed(2) : '$0.00';
                        }
                    }
                },
                legend: {
                    position: 'top',
                    horizontalAlign: 'right'
                },
                title: {
                    text: `${data.ticker} 历史价格`,
                    align: 'left'
                }
            };
        }
    }

    // --- 原生全屏控制逻辑 ---
    function setupFullscreenControls() {
        const fullscreenBtn = document.getElementById('fullscreen-chart-btn');
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', () => {
                const section = document.querySelector('.stock-chart');
                toggleNativeFullscreen(section);
            });
        }

        const ratioFullscreenBtn = document.getElementById('fullscreen-ratio-chart-btn');
        if (ratioFullscreenBtn) {
            ratioFullscreenBtn.addEventListener('click', () => {
                const section = document.querySelector('.stock-qqq-ratio-chart');
                toggleNativeFullscreen(section);
            });
        }
    }

    function toggleNativeFullscreen(element) {
        if (!element) return;
        if (!document.fullscreenElement) {
            element.requestFullscreen().catch(err => {
                console.error(`进入全屏模式失败: ${err.message}`);
            });
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        }
    }

    document.addEventListener('fullscreenchange', () => {
        const fullscreenBtn = document.getElementById('fullscreen-chart-btn');
        const ratioFullscreenBtn = document.getElementById('fullscreen-ratio-chart-btn');
        const isFullscreen = !!document.fullscreenElement;

        // 更新所有全屏按钮的文本
        if (fullscreenBtn) {
            fullscreenBtn.textContent = isFullscreen && document.fullscreenElement.contains(fullscreenBtn) ? '退出全屏' : '全屏显示';
        }
        if (ratioFullscreenBtn) {
            ratioFullscreenBtn.textContent = isFullscreen && document.fullscreenElement.contains(ratioFullscreenBtn) ? '退出全屏' : '全屏显示';
        }

        // 延迟执行，确保DOM更新完毕后图表能获取到正确的容器尺寸
        setTimeout(() => {
            if (mainChart && typeof mainChart.windowResizeHandler === 'function') {
                mainChart.windowResizeHandler();
            }
            if (ratioChart && typeof ratioChart.windowResizeHandler === 'function') {
                ratioChart.windowResizeHandler();
            }
        }, 150);
    });

    // --- 页面初始化逻辑 ---
    setupTabs();
    setupFullscreenControls();

    const urlParams = new URLSearchParams(window.location.search);
    const ticker = urlParams.get('ticker');
    
    if (ticker) {
        document.title = `${ticker.toUpperCase()} - 股票详情`;
        const stockNameElement = document.getElementById('stock-name');
        if(stockNameElement) stockNameElement.textContent = ticker.toUpperCase();
        
        stockManager = new StockDataManager(ticker.toUpperCase());
        stockManager.fetchStockData();
        // TODO: 在这里初始化第二个图表的数据和渲染
    } else {
        const container = document.getElementById('apex-chart-container');
        if(container) container.innerHTML = `<h2>请在URL中提供一个股票代码，例如：?ticker=AAPL</h2>`;
    }
});