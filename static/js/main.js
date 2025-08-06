// 加载HTML组件的函数 (页头和页脚)
function loadComponent(path, selector, callback) {
    fetch(path)
        .then(response => {
            if (!response.ok) throw new Error(`网络响应不正常: ${path}`);
            return response.text();
        })
        .then(html => {
            const element = document.querySelector(selector);
            if (element) {
                element.innerHTML = html;
            }
            if (callback) callback();
        })
        .catch(error => console.error(`从 ${path} 加载组件出错:`, error));
}

// 处理实际搜索导航的函数
function performSearch(query) {
    const upperQuery = query.toUpperCase();
    console.log(`正在导航至股票页面: ${upperQuery}`);
    window.location.href = `/pages/stock.html?ticker=${upperQuery}`;
}

// 初始化所有依赖于页头的脚本的函数
function initializeHeaderScripts() {
    const searchInput = document.querySelector('.search-bar input');
    const searchResultsContainer = document.querySelector('.search-results');
    const menuToggle = document.querySelector('.menu-toggle');
    const navLinks = document.querySelector('.nav-links');

    if (searchInput && searchResultsContainer) {
        // 使用我们API的自动补全逻辑
        searchInput.addEventListener('input', function() {
            const query = searchInput.value.trim();
            searchResultsContainer.innerHTML = '';

            if (query.length < 2) {
                searchResultsContainer.style.display = 'none';
                return;
            }

            fetch(`/api/search/?q=${query}`)
                .then(response => response.json())
                .then(data => {
                    if (data.length > 0) {
                        data.forEach(stock => {
                            const item = document.createElement('div');
                            item.className = 'result-item';
                            item.textContent = `${stock.ticker} - ${stock.name}`;
                            item.addEventListener('click', () => performSearch(stock.ticker));
                            searchResultsContainer.appendChild(item);
                        });
                        searchResultsContainer.style.display = 'block';
                    } else {
                        searchResultsContainer.style.display = 'none';
                    }
                });
        });

        // 当用户点击别处时隐藏结果
        searchInput.addEventListener('blur', () => {
            setTimeout(() => { searchResultsContainer.style.display = 'none'; }, 200);
        });
    }

    // 响应式菜单逻辑
    if (menuToggle && navLinks) {
        menuToggle.addEventListener('click', () => navLinks.classList.toggle('menu-open'));
    }
}

function formatMarketCap(val) {
    if (!val) return '-';
    // 支持字符串和数字
    let num = typeof val === 'string' ? parseFloat(val.replace(/,/g, '')) : val;
    if (isNaN(num)) return val;
    if (num >= 1e12) return (num / 1e12).toFixed(2) + 'T';
    if (num >= 1e9)  return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6)  return (num / 1e6).toFixed(2) + 'M';
    if (num >= 1e4)  return (num / 1e3).toFixed(2) + 'K';
    return num.toLocaleString();
}

function formatPercentOrTimes(val) {
    if (val === null || val === undefined) return '-';
    const num = parseFloat(val);
    if (isNaN(num)) return '-';
    if (num >= 10) {
        // 超过1000%（即10）显示为“x倍”，最多三位数字
        return num >= 100 ? `${Math.round(num)}倍` : `${num.toFixed(1)}倍`;
    }
    // 小于10时显示为百分比，最多三位数字
    return `${(num * 100).toFixed(num * 100 >= 100 ? 0 : 2)}%`;
}

function renderTopStocks(sortField = 'return_5y') {
    fetch(`/api/top-stocks/?sort=${sortField}`)
        .then(res => res.json())
        .then(data => {
            const tbody = document.querySelector('#top-stocks-table tbody');
            tbody.innerHTML = '';
            data.forEach(stock => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><img src="${stock.logo || ''}" alt="logo" style="width:32px;height:32px;border-radius:6px;background:#f5f5f5;"></td>
                    <td style="font-weight:bold;">${stock.ticker}</td>
                    <td>
                        <div style="font-size:1.05em;">
                            <span style="color:#1976d2;cursor:pointer;text-decoration:underline;" class="stock-keyword" data-ticker="${stock.ticker}">
                                ${stock.chinese_keywords || stock.name || '-'}
                            </span>
                        </div>
                        <div style="font-size:0.85em;color:#888;">${stock.name}</div>
                    </td>
                    <td style="color:#555;">${stock.industry || ''}</td>
                    <td class="market-cap-cell">${formatMarketCap(stock.market_cap)}</td>
                    <td style="font-family:monospace;">${stock.price ?? '-'}</td>
                    <td style="color:#388e3c;">${formatPercentOrTimes(stock.return_1m)}</td>
                    <td style="color:#388e3c;">${formatPercentOrTimes(stock.return_6m)}</td>
                    <td style="color:#388e3c;">${formatPercentOrTimes(stock.return_1y)}</td>
                    <td style="color:#388e3c;">${formatPercentOrTimes(stock.return_3y)}</td>
                    <td style="color:#388e3c;">${formatPercentOrTimes(stock.return_5y)}</td>
                    <td style="color:#388e3c;">${formatPercentOrTimes(stock.return_10y)}</td>
                `;
                tbody.appendChild(tr);
            }); // ← 这里补上闭合大括号
            // 绑定点击事件：跳转详情页
            tbody.querySelectorAll('.stock-keyword').forEach(el => {
                el.addEventListener('click', () => {
                    window.location.href = `/pages/stock.html?ticker=${el.dataset.ticker}`;
                });
            });
        });
}

// --- 主执行流程 ---
document.addEventListener('DOMContentLoaded', function() {
    loadComponent('/static/components/header.html', 'header', initializeHeaderScripts);
    loadComponent('/static/components/footer.html', 'footer');
    renderTopStocks();

    document.querySelectorAll('.top-stocks th.sortable').forEach(th => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', function() {
            const sortField = th.getAttribute('data-sort');
            renderTopStocks(sortField);
        });
    });
});