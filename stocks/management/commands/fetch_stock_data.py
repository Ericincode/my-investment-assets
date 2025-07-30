import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from stocks.models import Stock, HistoricalPrice
from googletrans import Translator, LANGUAGES

class Command(BaseCommand):
    help = 'Updates stock data using yfinance and translates names.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- Starting yfinance data update ---'))
        
        stocks_to_update = Stock.objects.all()
        tickers = [stock.ticker for stock in stocks_to_update]
        self.stdout.write(f'Processing {len(tickers)} tickers...')

        # --- Initialize Translator ---
        translator = Translator()

        # --- Fetch Bulk Info ---
        tickers_string = " ".join(tickers)
        yf_tickers = yf.Tickers(tickers_string)

        for ticker_str in tickers:
            try:
                ticker_obj = yf_tickers.tickers[ticker_str]
                info = ticker_obj.info
                
                if not info:
                    self.stdout.write(self.style.WARNING(f'No info for {ticker_str}, skipping.'))
                    continue

                stock_instance = Stock.objects.get(ticker=ticker_str)
                
                english_name = info.get('longName', ticker_str)
                stock_instance.name = english_name
                
                # --- AUTO-TRANSLATION LOGIC ---
                # Only translate if the keywords field is currently empty
                                # --- 自动翻译逻辑 (简化版) ---
                # 仅当关键词字段当前为空时才进行翻译。
                if not stock_instance.chinese_keywords:
                    try:
                        translated_name = translator.translate(english_name, dest='zh-cn').text
                        stock_instance.chinese_keywords = translated_name
                        self.stdout.write(f"  已将 '{english_name}' 翻译为 '{translated_name}'")
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"  无法为 {ticker_str} 翻译名称: {e}"))

                        
                # ... (rest of the fields: exchange, market_cap, etc.) ...
                stock_instance.exchange = info.get('exchange', 'N/A')
                stock_instance.market_cap = info.get('marketCap')
                stock_instance.pe_ratio = info.get('trailingPE')
                stock_instance.eps = info.get('trailingEps')
                stock_instance.price = info.get('currentPrice', info.get('previousClose'))
                
                stock_instance.save()
                self.stdout.write(self.style.SUCCESS(f'Successfully updated info for {ticker_str}'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Could not fetch info for {ticker_str}: {e}'))


        # --- 2. 批量获取历史数据 ---
        self.stdout.write('正在批量获取历史数据...')
        
        # 确定我们需要数据的最新日期
        latest_trading_day = self.get_latest_trading_day()
        
        # 确定我们需要开始获取的最早日期
        # (基于我们数据库中最近更新的股票)
        start_date = "2010-01-01" # 完整下载的默认起始日期
        
        try:
            # yfinance功能强大，可以一次性下载所有代码的数据
            hist_data = yf.download(tickers, start=start_date, end=latest_trading_day + timedelta(days=1), progress=False)
            
            if not hist_data.empty:
                # 数据以多层列的格式返回，我们需要处理它。
                self.stdout.write('正在处理并保存历史数据...')
                
                # 遍历我们列表中的每只股票
                for stock in stocks_to_update:
                    new_entries = []
                    # 提取当前股票的数据
                    stock_hist = hist_data.loc[:, (slice(None), stock.ticker)]
                    stock_hist = stock_hist.droplevel(1, axis=1).dropna()

                    for index, row in stock_hist.iterrows():
                        # 创建HistoricalPrice对象，但先不保存（为了效率）
                        new_entries.append(
                            HistoricalPrice(
                                stock=stock,
                                date=index.date(),
                                open=row['Open'],
                                high=row['High'],
                                low=row['Low'],
                                close=row['Close'],
                                volume=row['Volume']
                            )
                        )
                    
                    # 使用bulk_create在一次数据库查询中插入所有新条目
                    HistoricalPrice.objects.bulk_create(new_entries, ignore_conflicts=True)
                    self.stdout.write(f'  为 {stock.ticker} 处理了 {len(new_entries)} 条历史记录')

            self.stdout.write(self.style.SUCCESS('历史数据更新完成。'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'在历史数据下载过程中发生错误: {e}'))


    def get_latest_trading_day(self):
        """ 一个获取上一个交易日（周一至周五）的简单函数 """
        today = date.today()
        offset = 0
        while True:
            check_date = today - timedelta(days=offset)
            if check_date.weekday() < 5: # 周一是0，周五是4
                return check_date
            offset += 1