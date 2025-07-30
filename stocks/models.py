from django.db import models

class Stock(models.Model):
    """
    代表一只股票的静态信息和当前数据快照。
    """
    # 股票代码，例如 "AAPL"。这是唯一的标识符。
    ticker = models.CharField(max_length=10, primary_key=True)

    # 公司名称，例如 "Apple Inc."。
    name = models.CharField(max_length=255)

    chinese_keywords = models.CharField(max_length=255, blank=True, help_text="逗号分隔的中文名称、别名或关键词")


    # 交易的交易所，例如 "NASDAQ"。
    exchange = models.CharField(max_length=50, null=True, blank=True)

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

    def __str__(self):
        return f"{self.name} ({self.ticker})"


class HistoricalPrice(models.Model):
    """
    代表一只特定股票某一个交易日的历史价格数据 (开高低收, 成交量)。
    """
    # 一个多对一的关系：一个Stock可以拥有多个HistoricalPrice。
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name='historical_prices')

    # 这条价格记录的具体日期。
    date = models.DateField()

    # 当天的四个关键价格。
    open = models.DecimalField(max_digits=10, decimal_places=2)
    high = models.DecimalField(max_digits=10, decimal_places=2)
    low = models.DecimalField(max_digits=10, decimal_places=2)
    close = models.DecimalField(max_digits=10, decimal_places=2)

    # 当天的交易量。
    volume = models.BigIntegerField()

    class Meta:
        # 确保每天每只股票只能有一条价格记录。
        unique_together = ('stock', 'date')
        # 默认按日期排序，最新在前。
        ordering = ['-date']

    def __str__(self):
        return f"{self.stock.ticker} on {self.date}"