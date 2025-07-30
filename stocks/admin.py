from django.contrib import admin
from .models import Stock, HistoricalPrice

# 在这里注册您的模型。

class StockAdmin(admin.ModelAdmin):
    """
    自定义 Stock 模型在后台管理面板中的显示方式。
    """
    list_display = ('ticker', 'name', 'exchange', 'price', 'last_updated')
    search_fields = ('ticker', 'name')

class HistoricalPriceAdmin(admin.ModelAdmin):
    """
    自定义 HistoricalPrice 模型的显示方式。
    """
    list_display = ('stock', 'date', 'open', 'high', 'low', 'close', 'volume')
    search_fields = ('stock__ticker',) # 按关联股票的代码进行搜索
    list_filter = ('date',) # 允许按日期进行筛选

# 将 Stock 模型及其自定义管理选项注册到后台
admin.site.register(Stock, StockAdmin)

# 将 HistoricalPrice 模型及其自定义管理选项注册到后台
admin.site.register(HistoricalPrice, HistoricalPriceAdmin)