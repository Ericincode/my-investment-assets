document.addEventListener('DOMContentLoaded', function() {
    // --- FUNCTION to handle tab switching ---
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

    // --- FUNCTION to calculate Simple Moving Average (SMA) ---
    function calcSMA(arr, period) {
        return arr.map((item, idx, all) => {
            if (idx < period - 1) return [new Date(item.date).getTime(), null];
            const closes = all.slice(idx - period + 1, idx + 1).map(i => parseFloat(i.close));
            if (closes.some(isNaN)) return [new Date(item.date).getTime(), null];
            const sum = closes.reduce((a, b) => a + b, 0);
            return [new Date(item.date).getTime(), sum / period];
        });
    }

    // --- MAIN INITIALIZATION FUNCTION FOR THE PAGE ---
    function initializeStockPage() {
        const urlParams = new URLSearchParams(window.location.search);
        const ticker = urlParams.get('ticker');
        if (!ticker) { return; }

        fetch(`/api/stock/${ticker}/`)
            .then(response => {
                if (!response.ok) throw new Error('Stock not found in database');
                return response.json();
            })
            .then(data => {
                console.log('API返回数据:', data);
                const formatNumber = (num, decimals = 2) => {
                    const parsed = parseFloat(num);
                    return !isNaN(parsed) ? parsed.toFixed(decimals) : 'N/A';
                };
                
                document.title = `${data.name || ticker} (${data.ticker}) - 股票详情`;
                document.getElementById('stock-name').textContent = `${data.name || ticker} (${data.ticker})`;
                document.getElementById('stock-price').textContent = `${formatNumber(data.price)} USD`;
                const changeEl = document.getElementById('stock-change');
                const change = parseFloat(data.change);
                const changePercent = parseFloat(data.change_percent) * 100;
                changeEl.textContent = `${formatNumber(change)} (${formatNumber(changePercent)}%)`;
                if (!isNaN(change)) {
                    changeEl.style.color = change < 0 ? 'red' : 'green';
                }

                const financialsEl = document.getElementById('financials-data');
                financialsEl.innerHTML = `
                    <ul>
                        <li><strong>市值 (Market Cap):</strong> ${data.market_cap || 'N/A'}</li>
                        <li><strong>市盈率 (P/E Ratio):</strong> ${formatNumber(data.pe_ratio)}</li>
                        <li><strong>每股收益 (EPS):</strong> ${formatNumber(data.eps)}</li>
                    </ul>
                `;

                // TradingView 图表替换
                const chartContainer = document.getElementById('apex-chart-container');
                console.log('图表容器:', chartContainer);
                if (chartContainer) {
                    if (!Array.isArray(data.historical) || data.historical.length === 0) {
                        console.warn('历史数据为空，无法显示图表');
                        chartContainer.innerHTML = "暂无历史数据，无法显示图表。";
                        return;
                    }

                    const series = [
                        {
                            name: '收盘价',
                            data: data.historical.map(item => [new Date(item.date).getTime(), item.close])
                        },
                        {
                            name: '5日均线',
                            data: calcSMA(data.historical, 5)
                        },
                        {
                            name: '120日均线',
                            data: calcSMA(data.historical, 120)
                        }
                    ];

                    console.log('series:', series);

                    const isFullscreen = document.fullscreenElement && document.fullscreenElement.classList.contains('stock-chart');
                    const chartHeight = isFullscreen ? '80%' : 400;

                    const options = {
                        chart: {
                            type: 'line',
                            height: chartHeight,
                            zoom: { enabled: true }
                        },
                        series: series,
                        colors: ['#008FFB', '#00E396', '#FEB019'],
                        stroke: { width: [1, 1, 1] },
                        xaxis: {
                            type: 'datetime',
                            labels: {
                                datetimeFormatter: {
                                    year: 'yyyy-M-d',
                                    month: 'yyyy-M-d',
                                    day: 'yyyy-M-d',
                                    hour: 'yyyy-M-d'
                                }
                            }
                        },
                        yaxis: {
                            tooltip: { enabled: true },
                            labels: {
                                formatter: function(val) {
                                    return Math.round(val);
                                }
                            }
                        },
                        tooltip: { x: { format: 'yyyy-M-d' } },
                        legend: {
                            show: true,
                            markers: { width: 16, height: 4, radius: 2 },
                            showForSingleSeries: true,
                            onItemClick: { toggleDataSeries: true },
                            onItemHover: { highlightDataSeries: true }
                        }
                    };

                    chartContainer.innerHTML = "";
                    const chart = new ApexCharts(chartContainer, options);
                    chart.render();
                }

                console.log('5日均线数据前10:', calcSMA(data.historical, 5).slice(0, 10));
                console.log('5日均线数据后10:', calcSMA(data.historical, 5).slice(-10));
                console.log('120日均线数据前130:', calcSMA(data.historical, 120).slice(0, 130));
                console.log('120日均线数据后10:', calcSMA(data.historical, 120).slice(-10));

                setupTabs();
            })
            .catch(error => {
                console.error('Error fetching stock details:', error);
                document.querySelector('main').innerHTML = `<h1>Error: Could not load data for ${ticker}.</h1>`;
            });
    }

    function loadChartWithRange(range) {
        const urlParams = new URLSearchParams(window.location.search);
        const ticker = urlParams.get('ticker');
        fetch(`/api/stock/${ticker}/?range=${range}`)
            .then(response => response.json())
            .then(data => {
                console.log('周期切换，收到数据:', data); // 调试日志
                renderChart(data);
            });
    }

    document.querySelectorAll('.chart-controls button').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.chart-controls button').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadChartWithRange(btn.getAttribute('data-range'));
        });
    });
    // 缺省改为10年
    loadChartWithRange('10Y');

    let lastChartData = null;
    let chart = null; // 放在最顶部

    function renderChart(data) {
        console.log('渲染图表，数据:', data); // 调试日志
        lastChartData = data; // 修正：每次渲染都保存最新数据
        const isFullscreen = document.fullscreenElement && document.fullscreenElement.classList.contains('stock-chart');
        const chartHeight = isFullscreen ? '80%' : 400;

        const series = [
            {
                name: '收盘价',
                data: data.historical.map(item => [new Date(item.date).getTime(), item.close])
            },
            {
                name: '5日均线',
                data: calcSMA(data.historical, 5)
            },
            {
                name: '120日均线',
                data: calcSMA(data.historical, 120)
            }
        ];
        console.log('series:', series);

        const options = {
            chart: {
                type: 'line',
                height: chartHeight,
                zoom: { enabled: true }
            },
            series: series,
            colors: ['#008FFB', '#00E396', '#FEB019'],
            stroke: { width: [1, 1, 1] },
            xaxis: {
                type: 'datetime',
                labels: {
                    datetimeFormatter: {
                        year: 'yyyy-M-d',
                        month: 'yyyy-M-d',
                        day: 'yyyy-M-d',
                        hour: 'yyyy-M-d'
                    }
                }
            },
            yaxis: {
                tooltip: { enabled: true },
                labels: {
                    formatter: function(val) {
                        return Math.round(val);
                    }
                }
            },
            tooltip: { x: { format: 'yyyy-M-d' } },
            legend: {
                show: true,
                markers: { width: 16, height: 4, radius: 2 },
                showForSingleSeries: true,
                onItemClick: { toggleDataSeries: true },
                onItemHover: { highlightDataSeries: true }
            }
        };

        const chartContainer = document.getElementById('apex-chart-container');
        chartContainer.innerHTML = "";
        if (chart) {
            chart.destroy();
        }
        chart = new ApexCharts(chartContainer, options);
        chart.render();
    }

    const fullscreenBtn = document.getElementById('fullscreen-chart-btn');
    fullscreenBtn.addEventListener('click', function() {
        const chartSection = document.querySelector('.stock-chart');
        if (!document.fullscreenElement) {
            chartSection.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    });

    // 监听全屏状态变化，切换按钮文本
    document.addEventListener('fullscreenchange', function() {
        console.log('全屏切换，lastChartData:', lastChartData);
        if (document.fullscreenElement && document.fullscreenElement.classList.contains('stock-chart')) {
            fullscreenBtn.textContent = '返回';
        } else {
            fullscreenBtn.textContent = '全屏显示';
        }
        // 只重新渲染图表，不重新请求数据
        if (lastChartData) {
            renderChart(lastChartData);
        }
    });

    initializeStockPage();

    // 监听窗口大小变化（包括全屏时），自动刷新图表高度
    window.addEventListener('resize', function() {
        if (document.fullscreenElement && lastChartData) {
            renderChart(lastChartData);
        }
    });
});