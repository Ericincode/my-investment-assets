from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404
from .models import Stock, HistoricalPrice


from django.db.models import Q, Case, When


from django.shortcuts import render

def index_view(request):
    return render(request, 'index.html')

def stock_page_view(request):
    return render(request, 'pages/stock.html')



def search_stocks(request):
    """
    一个带智能排序的股票搜索API端点。
    """
    query = request.GET.get('q', '').strip().upper() # 将查询标准化为大写
    
    if len(query) < 2:
        return JsonResponse([], safe=False)

    # --- 智能排序逻辑 ---
    search_results = Stock.objects.filter(
        Q(ticker__icontains=query) |
        Q(name__icontains=query) |
        Q(chinese_keywords__icontains=query)
    ).annotate(
        # 基于匹配类型创建一个排序分数
        ranking=Case(
            When(ticker__iexact=query, then=1),    # 精确匹配ticker = 1 (最高)
            When(ticker__istartswith=query, then=2), # ticker以查询开头 = 2
            default=3                             # 其他匹配 = 3
        )
    ).order_by('ranking', 'ticker')[:10] # 按我们的分数排序，然后按字母顺序

    results_list = [
        {'ticker': stock.ticker, 'name': stock.name}
        for stock in search_results
    ]

    return JsonResponse(results_list, safe=False)

def stock_detail_api(request, ticker):
    """
    API endpoint to return all data for a single stock.
    """
    print(f"--- API HIT: Received request for ticker: {ticker} ---") # 添加此行

    stock = get_object_or_404(Stock, pk=ticker.upper())

    historical_data = stock.historical_prices.all()[:252]

    data = {
        'ticker': stock.ticker,
        'name': stock.name,
        'exchange': stock.exchange,
        'price': stock.price,
        'change': stock.change,
        'change_percent': stock.change_percent,
        'market_cap': stock.market_cap,
        'pe_ratio': stock.pe_ratio,
        'eps': stock.eps,
        'historical': [
            {
                'date': price.date.strftime('%Y-%m-%d'),
                'close': price.close
            }
            for price in historical_data
        ]
    }
    
    return JsonResponse(data)