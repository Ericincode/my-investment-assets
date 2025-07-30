from django.urls import path
from . import views

urlpatterns = [
    # 页面URL
    path('', views.index_view, name='index'),
    path('pages/stock.html', views.stock_page_view, name='stock_page'),

    # API URL
    path('api/search/', views.search_stocks, name='search_stocks'),
    path('api/stock/<str:ticker>/', views.stock_detail_api, name='stock_detail_api'),
]