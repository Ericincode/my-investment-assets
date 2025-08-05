from django.db import models
from django.utils import timezone
from datetime import timedelta

class Stock(models.Model):
    """
    代表一只股票的静态信息和当前数据快照。
    """
    # 股票代码，例如 "AAPL"。这是唯一的标识符。
    ticker = models.CharField(max_length=10, primary_key=True)

    # 公司名称，例如 "Apple Inc."。
    name = models.CharField(max_length=255)
    chinese_keywords = models.CharField(max_length=255, blank=True, null=True, help_text="中文关键词，用于搜索")
    exchange = models.CharField(max_length=50, db_index=True)

    # === 新增/恢复：来自交易所文件的详细信息 ===
    market_category = models.CharField(max_length=1, blank=True, null=True, help_text="市场分类 (来自NASDAQ)")
    financial_status = models.CharField(max_length=1, blank=True, null=True, help_text="财务状况 (来自NASDAQ)")

    is_active = models.BooleanField(default=True, db_index=True)
    # 股票代码，例如 "AAPL"。这是主键。

    # 当前或最近一次知晓的价格。
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # 相比前一天的价格变化。
    change = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # 价格变化的百分比。
    change_percent = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # 公司市值，例如 "2.81T"。
    market_cap = models.CharField(max_length=50, null=True, blank=True)

    # 市盈率。
    pe_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # 每股收益。
    eps = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # 这条数据在我们数据库中最后一次更新的时间戳。
    last_updated = models.DateTimeField(auto_now=True)

    # === 新增：公司信息 ===
    logo = models.URLField(max_length=1024, null=True, blank=True, help_text="公司Logo的URL")
    weburl = models.URLField(max_length=1024, null=True, blank=True, help_text="公司官方网站地址")

    # === 新增：不同时间维度的收益率 ===
    return_1m = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="1个月收益率")
    return_6m = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="6个月收益率")
    return_1y = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="1年收益率")
    return_3y = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="3年收益率")
    return_5y = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="5年收益率")
    return_10y = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="10年收益率")

    listed_date = models.DateField(null=True, blank=True, help_text="上市日期")
    delisted_date = models.DateField(null=True, blank=True, help_text="退市日期")
    is_active = models.BooleanField(default=True, help_text="是否在市")
    financial_status = models.CharField(max_length=10, blank=True, null=True)
    market_category = models.CharField(max_length=10, blank=True, null=True)
    test_issue = models.CharField(max_length=1, blank=True, null=True)
    is_etf = models.BooleanField(default=False, help_text="是否为ETF")

    # === 新增：查询统计字段 ===
    query_count = models.PositiveIntegerField(default=0, db_index=True, help_text="总查询次数")
    last_queried = models.DateTimeField(null=True, blank=True, help_text="最后查询时间")

    class Meta:
        indexes = [
            models.Index(fields=['ticker', 'is_active']),
            models.Index(fields=['-query_count', 'is_active']),  # 热度排序
        ]

    def __str__(self):
        return f"{self.name} ({self.ticker})"


class HistoricalPrice(models.Model):
    """
    优化版历史价格数据，只存储收盘价
    """
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='historical_prices')
    date = models.DateField()
    
    # 价格字段 - 设为可空，只有收盘价是必需的
    open = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    high = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    low = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    close = models.DecimalField(max_digits=10, decimal_places=2)  # 收盘价必需
    
    # 当天的交易量。
    volume = models.BigIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('stock', 'date')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['stock', '-date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"{self.stock.ticker} on {self.date}: ${self.close}"

