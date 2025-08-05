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

function renderTopStocks(sortField = 'return_5y') {
    fetch(`/api/top-stocks/?sort=${sortField}`)
        .then(res => res.json())
        .then(data => {
            const tbody = document.querySelector('#top-stocks-table tbody');
            tbody.innerHTML = '';
            data.forEach(stock => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><img src="${stock.logo || ''}" alt="logo" style="width:32px;height:32px;"></td>
                    <td>${stock.ticker}</td>
                    <td>${stock.name}</td>
                    <td>${stock.industry || ''}</td>
                    <td>${stock.price ?? '-'}</td>
                    <td>${stock.return_1m ?? '-'}</td>
                    <td>${stock.return_6m ?? '-'}</td>
                    <td>${stock.return_1y ?? '-'}</td>
                    <td>${stock.return_3y ?? '-'}</td>
                    <td>${stock.return_5y ?? '-'}</td>
                    <td>${stock.return_10y ?? '-'}</td>
                `;
                tbody.appendChild(tr);
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