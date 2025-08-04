from django.contrib import admin
from .models import Stock, HistoricalPrice

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    """
    自定义 Stock 模型在后台管理面板中的显示方式。
    """
    list_display = (
        'ticker', 'name', 'chinese_keywords', 'exchange', 'price', 'market_cap',
        'pe_ratio', 'eps', 'listed_date', 'delisted_date', 'is_active', 'last_updated'
    )
    search_fields = ('ticker', 'name', 'chinese_keywords', 'exchange')
    list_filter = ('exchange', 'is_active', 'listed_date', 'delisted_date')
    ordering = ('-last_updated',)

@admin.register(HistoricalPrice)
class HistoricalPriceAdmin(admin.ModelAdmin):
    """
    自定义 HistoricalPrice 模型的显示方式。
    """
    list_display = (
        'stock', 'date', 'open', 'high', 'low', 'close', 'volume'
    )
    search_fields = ('stock__ticker', 'stock__name')
    list_filter = ('date', 'stock')
    ordering = ('-date',)