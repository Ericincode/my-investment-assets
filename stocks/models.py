# 文件路径: stocks/models.py
# 【最终精简版】

from django.db import models

class Stock(models.Model):
    """
    代表一只股票的核心信息，专为长期投资者设计。
    """
    # 股票代码，例如 "AAPL"。这是唯一的标识符。
    ticker = models.CharField(max_length=10, primary_key=True)

    # --- 公司基本信息 (主要来自 Finnhub) ---
    name = models.CharField(max_length=255, help_text="公司名称")
    chinese_keywords = models.CharField(max_length=255, blank=True, null=True, help_text="中文关键词，用于搜索")
    exchange = models.CharField(max_length=50, db_index=True, help_text="交易所")
    country = models.CharField(max_length=50, blank=True, null=True, help_text="公司所在国家")
    finnhub_industry = models.CharField(max_length=100, blank=True, null=True, help_text="Finnhub行业分类")
    ipo = models.DateField(null=True, blank=True, help_text="上市日期")
    logo = models.URLField(max_length=1024, null=True, blank=True, help_text="公司Logo的URL")
    weburl = models.URLField(max_length=1024, null=True, blank=True, help_text="公司官方网站地址")
    phone = models.CharField(max_length=50, blank=True, null=True, help_text="公司电话")
    market_cap = models.BigIntegerField(null=True, blank=True, db_index=True, help_text="公司市值(完整数值)")

    # --- 核心价格与状态 ---
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="最新收盘价")
    is_active = models.BooleanField(default=True, db_index=True, help_text="是否为活跃交易的股票")
    is_etf = models.BooleanField(default=False, help_text="是否为ETF")
    last_updated = models.DateTimeField(auto_now=True, help_text="此条记录在数据库中最后一次更新的时间")

    # --- 长期收益率 ---
    return_1m = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="1个月收益率")
    return_6m = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="6个月收益率")
    return_1y = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="1年收益率")
    return_3y = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="3年收益率")
    return_5y = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="5年收益率")
    return_10y = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="10年收益率")

    # --- 查询统计字段 ---
    query_count = models.PositiveIntegerField(default=0, db_index=True, help_text="总查询次数")
    last_queried = models.DateTimeField(null=True, blank=True, help_text="最后查询时间")

    # --- 兼容旧列表同步脚本的字段 ---
    financial_status = models.CharField(max_length=10, blank=True, null=True)
    market_category = models.CharField(max_length=10, blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['ticker', 'is_active']),
            models.Index(fields=['-query_count', 'is_active']),
            models.Index(fields=['-market_cap', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.ticker})"


class HistoricalPrice(models.Model):
    """
    【已简化】存储股票的历史收盘价和交易量。
    """
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='historical_prices')
    date = models.DateField()
    
    # 只保留收盘价和交易量
    close = models.DecimalField(max_digits=10, decimal_places=2)
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