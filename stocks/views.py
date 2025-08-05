# 文件名: stocks/views.py
# 【最终简化版】完整代码

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from .models import Stock, HistoricalPrice
from django.db.models import Q, Case, When, Max
from datetime import date, timedelta
import threading
import subprocess
import os

def index_view(request):
    """渲染主页"""
    return render(request, 'index.html')

def stock_page_view(request):
    """渲染股票详情页的HTML框架"""
    return render(request, 'pages/stock.html')

def search_stocks(request):
    """股票搜索API"""
    query = request.GET.get('q', '').strip().upper()
    if len(query) < 2:
        return JsonResponse([], safe=False)
    
    search_results = Stock.objects.filter(
        Q(ticker__icontains=query) |
        Q(name__icontains=query) |
        Q(chinese_keywords__icontains=query)
    ).annotate(
        ranking=Case(
            When(ticker__iexact=query, then=1),
            When(ticker__istartswith=query, then=2),
            default=3
        )
    ).order_by('ranking', 'ticker')[:10]
    
    results_list = [{'ticker': stock.ticker, 'name': stock.name} for stock in search_results]
    return JsonResponse(results_list, safe=False)

def stock_detail_api(request, ticker):
    """获取股票详情，并在需要时触发后台下载"""
    stock = get_object_or_404(Stock, pk=ticker.upper())
    
    response_data = {
        'ticker': stock.ticker, 'name': stock.name, 'exchange': stock.exchange,
        'price': stock.price, 'change': stock.change, 'change_percent': stock.change_percent,
        'market_cap': stock.market_cap, 'pe_ratio': stock.pe_ratio, 'eps': stock.eps,
        'historical': [], 'downloading': False
    }
    
    historical_data_query = stock.historical_prices.all().order_by('-date')

    if historical_data_query.exists():
        # 如果数据已存在，则按前端请求的范围返回数据
        range_param = request.GET.get('range', '1Y').upper()
        range_map = {'1M': 21, '6M': 126, '1Y': 252, '5Y': 1260, '10Y': 2520}
        count = range_map.get(range_param)
        final_query = historical_data_query[:count] if count else historical_data_query # 'MAX' 的情况
        
        response_data['historical'] = [
            {
                'date': price.date.strftime('%Y-%m-%d'), 
                'close': float(price.close) if price.close is not None else 0.0
            } 
            for price in final_query
            if price.close is not None  # 过滤掉 close 为 None 的记录
        ]
    else:
        # 如果数据不存在，则触发后台下载
        response_data['downloading'] = True
        
        def download_in_background():
            """使用 sync_stock_data 命令下载单个股票数据"""
            try:
                # 获取项目根目录的 manage.py 路径
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                manage_py = os.path.join(base_dir, 'manage.py')
                venv_python = os.path.join(base_dir, '.venv', 'bin', 'python')
                
                # 使用虚拟环境的 Python 执行命令
                cmd = [venv_python, manage_py, 'sync_stock_data', '--ticker', ticker.upper()]
                
                print(f"Executing command: {' '.join(cmd)}")
                subprocess.run(cmd, cwd=base_dir, check=True)
                
            except subprocess.CalledProcessError as e:
                print(f"下载命令执行失败: {e}")
            except Exception as e:
                print(f"下载过程中出现错误: {e}")
        
        # 在后台线程中执行下载
        thread = threading.Thread(target=download_in_background)
        thread.daemon = True
        thread.start()
        
    return JsonResponse(response_data)

def check_download_status(request, ticker):
    """检查特定股票的数据下载状态"""
    try:
        stock = Stock.objects.get(ticker=ticker.upper())
        historical_count = HistoricalPrice.objects.filter(stock=stock).count()
        
        # 检查最新数据日期，判断是否需要下载
        latest_date = HistoricalPrice.objects.filter(stock=stock).aggregate(
            max_date=Max('date')
        )['max_date']
        
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # 判断下载状态：
        # 1. 如果没有数据，说明正在下载
        # 2. 如果有数据但最新日期太老（超过3天），说明可能正在更新
        is_downloading = False
        if historical_count == 0:
            is_downloading = True
        elif latest_date and (today - latest_date).days > 3:
            # 数据太老，可能正在更新
            is_downloading = False  # 暂时不显示下载中，因为有历史数据可以显示
        
        return JsonResponse({
            'ticker': ticker.upper(),
            'has_data': historical_count > 0,
            'record_count': historical_count,
            'latest_date': latest_date.strftime('%Y-%m-%d') if latest_date else None,
            'downloading': is_downloading
        })
    except Stock.DoesNotExist:
        return JsonResponse({'error': 'Stock not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def stock_vs_qqq_ratio(request, ticker):
    """
    计算并返回指定股票与QQQ的价格比率。
    """
    # 1. 一次性查询两只股票的价格数据，提高效率
    prices = HistoricalPrice.objects.filter(
        stock__ticker__in=[ticker.upper(), 'QQQ']
    ).order_by('date').values('stock__ticker', 'date', 'close')

    # 2. 将数据整理成字典，格式: {'AAPL': {date: close}, 'QQQ': {date: close}}
    data = {}
    for p in prices:
        ticker_symbol = p['stock__ticker']
        if ticker_symbol not in data:
            data[ticker_symbol] = {}
        data[ticker_symbol][p['date']] = p['close']

    stock_prices = data.get(ticker.upper(), {})
    qqq_prices = data.get('QQQ', {})

    # 3. 找到共同的交易日并计算比值
    common_dates = sorted(stock_prices.keys() & qqq_prices.keys())
    
    ratio_data = []
    for d in common_dates:
        stock_close = stock_prices.get(d)
        qqq_close = qqq_prices.get(d)
        # 确保分母不为0
        if stock_close is not None and qqq_close is not None and qqq_close > 0:
            ratio_data.append({
                'date': d.strftime('%Y-%m-%d'),
                'ratio': float(stock_close) / float(qqq_close)
            })

    return JsonResponse({'ratio_data': ratio_data})

def top_stocks(request):
    """获取热门股票列表"""
    sort_field = request.GET.get('sort', 'return_5y')
    allowed_fields = [
        'return_1m', 'return_6m', 'return_1y', 'return_3y', 'return_5y', 'return_10y'
    ]
    if sort_field not in allowed_fields:
        sort_field = 'return_5y'
    stocks = Stock.objects.filter(is_active=True).exclude(market_cap__isnull=True)
    stocks = stocks.order_by(f'-{sort_field}')[:20]
    data = []
    for s in stocks:
        data.append({
            'logo': s.logo,
            'ticker': s.ticker,
            'name': s.name,
            'industry': getattr(s, 'industry', ''),  # 如果有行业字段
            'price': s.price,
            'return_1m': s.return_1m,
            'return_6m': s.return_6m,
            'return_1y': s.return_1y,
            'return_3y': s.return_3y,
            'return_5y': s.return_5y,
            'return_10y': s.return_10y,
        })
    return JsonResponse(data, safe=False)