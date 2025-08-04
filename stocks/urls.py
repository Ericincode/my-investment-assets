# 文件名: stocks/urls.py
# 【已修复】

from django.urls import path
from . import views

urlpatterns = [
    # 页面URL
    path('', views.index_view, name='index'),
    path('pages/stock.html', views.stock_page_view, name='stock_page'),

    # ===================================================================
    # ===                    核心修改在此处                       ===
    # ===================================================================
    # API URL
    path('api/search/', views.search_stocks, name='search_stocks'),
    
    # 修复：确保这个 URL 指向我们唯一的、功能完备的视图函数 `stock_detail_api`
    path('api/stocks/<str:ticker>/', views.stock_detail_api, name='stock_detail_api'),
    
    path('api/stock_vs_qqq_ratio/<str:ticker>/', views.stock_vs_qqq_ratio, name='stock_vs_qqq_ratio'),

    # 新增：确保检查状态的 URL 也能正常工作
    path('api/check-status/<str:ticker>/', views.check_download_status, name='check_download_status'),
]