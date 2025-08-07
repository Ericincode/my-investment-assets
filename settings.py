from django.contrib import admin
from .models import Stock, HistoricalPrice

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    """
    自定义 Stock 模型在后台管理面板中的显示方式。
    """
    list_display = (
        'ticker', 'name', 'chinese_keywords', 'exchange', 'price', 'market_cap',
        'is_active', 
    )
    search_fields = ('ticker', 'name', 'chinese_keywords', 'exchange')
    list_filter = ('exchange', 'is_active')
    ordering = ('-last_updated',)

@admin.register(HistoricalPrice)
class HistoricalPriceAdmin(admin.ModelAdmin):
    """
    自定义 HistoricalPrice 模型的显示方式。
    """
    list_display = (
        'stock', 'date',  'close', 'volume'
    )
    search_fields = ('stock__ticker', 'stock__name')
    list_filter = ('date', 'stock')
    ordering = ('-date',)