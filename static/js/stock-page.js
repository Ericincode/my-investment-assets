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

    // 新增：计算线性回归趋势线
    function calcTrendLine(data) {
        if (!data || data.length < 2) return [];
        const x = Array.from({ length: data.length }, (_, i) => i);
        const y = data.map(p => p.ratio);

        const sumX = x.reduce((a, b) => a + b, 0);
        const sumY = y.reduce((a, b) => a + b, 0);
        const sumXY = x.reduce((a, i) => a + x[i] * y[i], 0);
        const sumXX = x.reduce((a, i) => a + x[i] * x[i], 0);
        const n = data.length;

        const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
        const intercept = (sumY - slope * sumX) / n;

        return data.map((point, i) => [
            new Date(point.date).getTime(),
            intercept + slope * i
        ]);
    }

    // 核心类：用于管理股票数据获取和状态轮询
    class StockDataManager {
        constructor(ticker) {
            this.ticker = ticker;
            this.downloadInterval = null;
            this.maxRetries = 30;
            this.retryCount = 0;
            this.fullStockData = null;
            this.fullRatioData = null; // 新增：初始化比值数据
        }

        updateHeader(data) {
            const stockNameEl = document.getElementById('stock-name');
            const stockPriceEl = document.getElementById('stock-price');
            const stockChangeEl = document.getElementById('stock-change');

            if (stockNameEl) stockNameEl.textContent = data.name || this.ticker;
            
            if (stockPriceEl) {
                stockPriceEl.textContent = data.price ? `$${Number(data.price).toFixed(2)}` : 'N/A';
            }

            if (stockChangeEl) {
                if (data.change && data.change_percent) {
                    const change = Number(data.change);
                    const changePercent = Number(data.change_percent);
                    const sign = change >= 0 ? '+' : '';
                    stockChangeEl.textContent = `${sign}${change.toFixed(2)} (${sign}${changePercent.toFixed(2)}%)`;
                    stockChangeEl.className = 'stock-change'; // 重置 class
                    stockChangeEl.classList.add(change >= 0 ? 'positive' : 'negative');
                } else {
                    stockChangeEl.textContent = '';
                }
            }
        }

        // 修改：默认范围改为 MAX
        async fetchStockData(range = 'MAX') {
            try {
                const response = await fetch(`/api/stocks/${this.ticker}/?range=${range}`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                this.updateHeader(data);

                if (data.downloading) {
                    this.showDownloadingStatus();
                    this.startPolling();
                } else if (data.historical && data.historical.length > 0) {
                    this.fullStockData = data;
                    // 修改：传入默认范围
                    this.renderChart(data, range); 
                    this.fetchAndRenderRatioChart();
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
        
        // 新增：获取并渲染比值图表
        async fetchAndRenderRatioChart() {
            // 修改：动态设置比值图标题
            const ratioTitleEl = document.getElementById('ratio-chart-title');
            if (ratioTitleEl) {
                ratioTitleEl.textContent = `${this.ticker} 与 QQQ 的比值趋势`;
            }

            try {
                const response = await fetch(`/api/stock-vs-qqq-ratio/${this.ticker}/`);
                const data = await response.json();
                if (data.ratio_data && data.ratio_data.length > 0) {
                    this.fullRatioData = data.ratio_data;
                    // 修改：默认加载 MAX 范围
                    this.renderRatioChart('MAX'); 
                    this.setupRatioChartButtons();
                } else {
                    document.getElementById('apex-ratio-chart-container').innerHTML = `<p>无法生成与QQQ的比值图。</p>`;
                }
            } catch (error) {
                console.error('获取比值数据失败:', error);
                document.getElementById('apex-ratio-chart-container').innerHTML = `<p>获取比值数据时出错。</p>`;
            }
        }

        // 新增：渲染比值图表
        renderRatioChart(range = '最长') {
            const container = document.getElementById('apex-ratio-chart-container');
            if (!container || !this.fullRatioData) return;

            const filteredData = this.filterRatioDataByRange(this.fullRatioData, range);

            const seriesData = filteredData.map(item => [new Date(item.date).getTime(), item.ratio]);
            const trendData = calcTrendLine(filteredData);

            const options = {
                series: [{
                    name: '比值',
                    data: seriesData
                }, {
                    name: '趋势线',
                    data: trendData
                }],
                // 移除: chart: { type: 'line', height: 350, animations: { enabled: false } },
                chart: { type: 'line', animations: { enabled: false } }, // 修正：移除 height
                stroke: { width: [2, 2], curve: 'straight', dashArray: [0, 5] },
                colors: ['#FF4560', '#775DD0'],
                title: { text: `${this.ticker} / QQQ 比值趋势`, align: 'left' },
                xaxis: { type: 'datetime' },
                yaxis: { labels: { formatter: (val) => val.toFixed(3) } },
                tooltip: { x: { format: 'yyyy-MM-dd' } }
            };

            if (ratioChart) {
                ratioChart.updateOptions(options);
            } else {
                ratioChart = new ApexCharts(container, options);
                ratioChart.render();
            }
        }

        // 新增：为比值图表设置独立的按钮
        setupRatioChartButtons() {
            const rangeButtons = document.querySelectorAll('.ratio-chart-controls button[data-ratio-range]');
            rangeButtons.forEach(btn => {
                if (btn.dataset.listenerAttached) return;
                btn.dataset.listenerAttached = 'true';

                btn.addEventListener('click', () => {
                    rangeButtons.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    const range = btn.dataset.ratioRange;
                    if (this.fullRatioData) {
                        this.renderRatioChart(range);
                    }
                });
            });
        }

        // 新增：根据范围过滤比值数据
        filterRatioDataByRange(data, range) {
            if (range === '最长' || range === 'MAX') return data; // 修正：也处理 MAX
            
            let startDate;
            const now = new Date(); // 基准日期

            switch(range) {
                case 'YTD': 
                    startDate = new Date(now.getFullYear(), 0, 1); 
                    break;
                case '1M': 
                    startDate = new Date(new Date().setMonth(now.getMonth() - 1)); 
                    break;
                case '6M': 
                    startDate = new Date(new Date().setMonth(now.getMonth() - 6)); 
                    break;
                case '1Y': 
                    startDate = new Date(new Date().setFullYear(now.getFullYear() - 1)); 
                    break;
                case '10Y': 
                    startDate = new Date(new Date().setFullYear(now.getFullYear() - 10)); 
                    break;
                default: 
                    return data;
            }
            return data.filter(item => new Date(item.date) >= startDate);
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

        renderChart(data, range) { // 修改：接收 range 参数
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

            // 新增：调用增长率计算函数
            this.calculateAndDisplayGrowth(historicalData, range);

            const options = this.getChartOptions(data);
            mainChart = new ApexCharts(chartContainer, options);
            mainChart.render();
            this.setupRangeButtons();
        }

        // 新增：计算并显示增长率的函数
        calculateAndDisplayGrowth(historicalData, range) {
            const container = document.getElementById('growth-rate-info');
            if (!container) return;

            if (!historicalData || historicalData.length < 2) {
                container.textContent = '';
                return;
            }

            const startData = historicalData[0];
            const endData = historicalData[historicalData.length - 1];

            const startPrice = startData.close;
            const endPrice = endData.close;

            const startDate = new Date(startData.date);
            const endDate = new Date(endData.date);

            const years = (endDate - startDate) / (1000 * 60 * 60 * 24 * 365.25);

            if (years <= 0 || startPrice <= 0) {
                container.textContent = '';
                return;
            }

            const totalGrowth = (endPrice / startPrice) - 1;
            const cagr = (Math.pow(endPrice / startPrice, 1 / years)) - 1;

            // 将 YTD, 1M 等转换为中文
            const rangeMap = {'YTD': '年初至今', '1M': '1个月', '6M': '6个月', '1Y': '1年', '10Y': '10年'};
            let rangeText = rangeMap[range] || `${years.toFixed(1)}年`;
            if (range === 'MAX') rangeText = `${years.toFixed(1)}年`;


            container.innerHTML = `<strong>${rangeText}</strong>增长率: <strong>${(totalGrowth * 100).toFixed(2)}%</strong>，年复合增长率: <strong>${(cagr * 100).toFixed(2)}%</strong>`;
        }

        async updateChartWithRange(range) {
            if (!this.fullStockData) {
                await this.fetchStockData(range);
                return;
            }
            
            const filteredHistoricalData = this.filterDataByRange(this.fullStockData.historical, range);
            const filteredData = {
                ...this.fullStockData,
                historical: filteredHistoricalData
            };
            // 修改：传入当前范围
            this.renderChart(filteredData, range);
        }

        filterDataByRange(data, range) {
            // 修正：此函数现在接收一个数组
            const historicalData = data || [];
            if (range === '最长' || range === 'MAX') return historicalData;

            let startDate;
            const now = new Date(); // 基准日期

            switch(range) {
                case 'YTD':
                    startDate = new Date(now.getFullYear(), 0, 1);
                    break;
                case '1M':
                    startDate = new Date(new Date().setMonth(now.getMonth() - 1));
                    break;
                case '6M':
                    startDate = new Date(new Date().setMonth(now.getMonth() - 6));
                    break;
                case '1Y':
                    startDate = new Date(new Date().setFullYear(now.getFullYear() - 1));
                    break;
                case '10Y':
                    startDate = new Date(new Date().setFullYear(now.getFullYear() - 10));
                    break;
                default:
                    return historicalData;
            }

            return historicalData.filter(item => new Date(item.date) >= startDate);
        }
        
        setupRangeButtons() {
            // 修正：使用属性选择器来找到所有带 data-range 属性的按钮
            const rangeButtons = document.querySelectorAll('.chart-controls button[data-range]');
            rangeButtons.forEach(btn => {
                // 防止重复绑定事件
                if (btn.dataset.listenerAttached) return;
                btn.dataset.listenerAttached = 'true';

                btn.addEventListener('click', () => {
                    // 再次查询以确保我们操作的是最新的按钮列表
                    document.querySelectorAll('.chart-controls button[data-range]').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    const range = btn.dataset.range;
                    this.updateChartWithRange(range);
                });
            });
        }
        
        getChartOptions(data) {
            const seriesData = data.historical.map(item => [new Date(item.date).getTime(), item.close]);
            const sma50 = calcSMA(data.historical, 50);
            const sma200 = calcSMA(data.historical, 200);

            // 修改：动态生成图表标题
            const latestData = data.historical[data.historical.length - 1];
            const latestDate = new Date(latestData.date).toLocaleDateString();
            const latestPrice = Number(latestData.close).toFixed(2);
            const chartTitle = `${this.ticker} 历史价格 (最新: ${latestDate} 价格 ${latestPrice})`;

            return {
                series: [
                    { name: '价格', data: seriesData },
                    { name: '50日均线', data: sma50 },
                    { name: '200日均线', data: sma200 }
                ],
                // 移除: chart: { type: 'line', height: '100%', animations: { enabled: false } },
                chart: { type: 'line', animations: { enabled: false } }, // 修正：移除 height
                title: { text: chartTitle, align: 'left' },
                xaxis: { type: 'datetime' },
                yaxis: {
                    labels: { formatter: (val) => `$${val.toFixed(2)}` },
                    tooltip: { enabled: true }
                },
                stroke: { width: [2, 1, 1], curve: 'straight' },
                colors: ['#008FFB', '#F2B90C', '#FF4560'],
                tooltip: { x: { format: 'yyyy-MM-dd' } }
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
        const fullscreenContainer = document.fullscreenElement;

        // 更新所有全屏按钮的文本
        if (fullscreenBtn) {
            fullscreenBtn.textContent = isFullscreen && fullscreenContainer && fullscreenContainer.contains(fullscreenBtn) ? '退出全屏' : '全屏显示';
        }
        if (ratioFullscreenBtn) {
            ratioFullscreenBtn.textContent = isFullscreen && fullscreenContainer && fullscreenContainer.contains(ratioFullscreenBtn) ? '退出全屏' : '全屏显示';
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
    } else {
        const container = document.getElementById('apex-chart-container');
        if(container) container.innerHTML = `<h2>请在URL中提供一个股票代码，例如：?ticker=AAPL</h2>`;
    }
});