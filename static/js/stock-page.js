document.addEventListener('DOMContentLoaded', function() {
    let apexChart = null;
    let fullHistoricalData = [];

    // --- CHART FUNCTION: ApexCharts (Working and Optimized) ---
    function createApexChart(seriesData) {
        const chartContainer = document.getElementById('apex-chart-container');
        if (!chartContainer) return;
        chartContainer.innerHTML = '';

        const options = {
            chart: { type: 'area', height: 400, animations: { enabled: false } },
            series: [{ name: 'Price', data: seriesData }],
            dataLabels: { enabled: false },
            xaxis: { type: 'datetime', labels: { datetimeUTC: false } },
            yaxis: { labels: { formatter: (value) => value ? value.toFixed(2) : '' } },
            tooltip: { 
                x: { format: 'dd MMM yyyy' },
                crosshairs: { show: true, width: 1, stroke: { color: '#b6b6b6', dashArray: 0 } }
            },
            stroke: { curve: 'smooth', width: 2 },
            fill: { type: 'gradient', gradient: { opacityFrom: 0.4, opacityTo: 0.05 } }
        };
        
        apexChart = new ApexCharts(chartContainer, options);
        apexChart.render();
    }
    
    // --- FUNCTION to update the date range for the ApexChart ---
    function updateApexChartRange(range) {
        document.querySelectorAll('.chart-controls button').forEach(b => b.classList.remove('active'));
        const activeButton = document.querySelector(`.chart-controls button[data-range="${range}"]`);
        if (activeButton) activeButton.classList.add('active');

        const now = new Date();
        let min;
        
        const earliestDate = fullHistoricalData.length > 0 ? new Date(fullHistoricalData[0].date).getTime() : new Date('2010-01-01').getTime();

        switch (range) {
            case '1M': min = new Date().setMonth(now.getMonth() - 1); break;
            case '6M': min = new Date().setMonth(now.getMonth() - 6); break;
            case 'YTD': min = new Date(new Date().getFullYear(), 0, 1).getTime(); break;
            case '1Y': min = new Date().setFullYear(now.getFullYear() - 1); break;
            case '5Y': min = new Date().setFullYear(now.getFullYear() - 5); break;
            case 'MAX': min = earliestDate; break;
        }
        
        if (apexChart) {
            apexChart.zoomX(min, new Date().getTime());
        }
    }

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
                // --- THIS IS THE CRITICAL CODE THAT WAS MISSING ---
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
                // --- END OF MISSING CODE ---
                
                if (data.historical && data.historical.length > 0) {
                    fullHistoricalData = data.historical.sort((a,b) => new Date(a.date) - new Date(b.date));
                    const seriesDataForApex = fullHistoricalData.map(d => [new Date(d.date).getTime(), parseFloat(d.close)]);
                    
                    createApexChart(seriesDataForApex);
                    
                    document.querySelectorAll('.chart-controls button').forEach(button => {
                        button.addEventListener('click', () => updateApexChartRange(button.dataset.range));
                    });
                    updateApexChartRange('1Y');
                } else {
                    document.getElementById('apex-chart-container').innerText = "No historical data for chart.";
                }

                setupTabs();
            })
            .catch(error => {
                console.error('Error fetching stock details:', error);
                document.querySelector('main').innerHTML = `<h1>Error: Could not load data for ${ticker}.</h1>`;
            });
    }

    initializeStockPage();
});