# 文件名: stocks/management/commands/sync_stock_data.py
# 【最终简化版】完整代码 - 已修复

import pandas as pd
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import models
from stocks.models import Stock, HistoricalPrice
from django.db.models import Max
import time
import yfinance as yf
import logging
from django.db import transaction
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.utils import timezone
import traceback
import requests
import io

# =======================================================================
# ===           核心数据处理引擎 (已移除缓存逻辑)               ===
# =======================================================================
def download_and_save_stock_data(ticker: str):
    """
    核心函数：下载并保存单个股票数据。已移除所有临时缓存逻辑。
    """
    logger = logging.getLogger(__name__)
    today = date.today()
    
    try:
        # 步骤 1: 更新查询计数并获取股票对象
        stock_obj = None
        with transaction.atomic():
            stock_to_update = Stock.objects.select_for_update().get(ticker=ticker)
            stock_to_update.query_count += 1
            stock_to_update.last_queried = timezone.now()
            stock_to_update.save()
            
            stock_obj = Stock.objects.get(ticker=ticker)
            logger.info(f"股票 {ticker} 的查询次数已更新为: {stock_obj.query_count}")

        # 步骤 2: 下载逻辑
        latest_date = HistoricalPrice.objects.filter(stock=stock_obj).aggregate(max_date=Max('date'))['max_date']
        
        if latest_date:
            start_date = latest_date + timedelta(days=1)
            if start_date > today: return f"{ticker}:up_to_date"
            hist_data = yf.download(ticker, start=start_date, progress=False, auto_adjust=True, repair=True)
        else:
            hist_data = yf.download(ticker, period="max", progress=False, auto_adjust=True, repair=True)

        # 步骤 3: 保存数据
        if not hist_data.empty:
            count = save_data_to_db(stock_obj, hist_data)
            return f"{ticker}:downloaded_{count}_records"
        else:
            return f"{ticker}:no_new_data"

    except Stock.DoesNotExist:
        return f"{ticker}:stock_not_found"
    except Exception:
        logger.error(f"引擎错误：处理 {ticker} 失败: {traceback.format_exc()}")
        return f"{ticker}:error"

def save_data_to_db(stock_obj, hist_data):
    """将历史数据保存到数据库"""
    if hist_data.empty:
        return 0
    
    new_records = []
    for index, row in hist_data.iterrows():
        try:
            close_value = row['Close']
            if hasattr(close_value, 'iloc'): close_value = close_value.iloc[0]
            
            volume_value = row['Volume']
            if hasattr(volume_value, 'iloc'): volume_value = volume_value.iloc[0]
            
            close_price = float(close_value) if pd.notna(close_value) and close_value is not None else None
            volume = int(float(volume_value)) if pd.notna(volume_value) and volume_value is not None else None
            
            if close_price and close_price > 0:
                new_records.append(HistoricalPrice(
                    stock=stock_obj,
                    date=index.date(),
                    close=close_price,
                    volume=volume
                ))
        except (ValueError, TypeError, AttributeError) as e:
            print(f"跳过问题记录 {index}: {e}")
            continue
    
    if new_records:
        HistoricalPrice.objects.bulk_create(new_records, ignore_conflicts=True)
        print(f"成功保存 {len(new_records)} 条记录")
        return len(new_records)
    else:
        print("没有有效记录可保存")
        return 0

# =======================================================================
# ===                     Django Management Command                  ===
# =======================================================================
class Command(BaseCommand):
    help = '【最终简化版】同步列表并按需/批量更新股票数据'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10, help='批量更新热门股时，处理的数量限制')
        parser.add_argument('--max-workers', type=int, default=5, help='并发下载的线程数')
        parser.add_argument('--ticker', type=str, help='只下载并更新指定的单个股票代码')

    def handle(self, *args, **options):
        """主处理函数，负责根据参数进行任务分发"""
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - INFO - %(message)s')
        self.stdout.write(self.style.SUCCESS(f'=== {self.help} ==='))
        start_time = time.time()

        specific_ticker = options.get('ticker')

        if specific_ticker:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n--- 单点更新模式：正在处理 {specific_ticker} ---"))
            result = download_and_save_stock_data(specific_ticker.upper())
            self.stdout.write(f"任务完成 -> {result}")
        else:
            self.sync_all_stock_lists()
            self.update_hot_stocks_concurrently(options['limit'], options['max_workers'])

        elapsed = time.time() - start_time
        self.stdout.write(f"\n=== 全部任务完成，总耗时: {elapsed:.1f}秒 ===")
    
    def sync_all_stock_lists(self):
        """同步所有交易所的股票列表"""
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- 开始同步股票列表 ---'))
        self._sync_single_list("https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt", "NASDAQ", is_nasdaq=True)
        self._sync_single_list("https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt", "NYSE", is_nasdaq=False)

    def _sync_single_list(self, url, exchange_name_default, is_nasdaq):
        """同步单个交易所列表的内部实现"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            df = pd.read_csv(io.StringIO(response.text), sep='|').iloc[:-1]
            existing_tickers = set(Stock.objects.values_list('ticker', flat=True))
            new_stocks = []
            
            for _, row in df.iterrows():
                if is_nasdaq:
                    ticker, name, exchange = str(row.get('Symbol', '')).strip(), str(row.get('Security Name', '')).strip()[:255], exchange_name_default
                else: 
                    ticker, name, exchange = str(row.get('ACT Symbol', '')).strip(), str(row.get('Security Name', '')).strip()[:255], self._get_nyse_exchange_name(str(row.get('Exchange', '')).strip())
                
                test_issue = str(row.get('Test Issue', '')).strip()
                if ticker and test_issue != 'Y' and ticker not in existing_tickers:
                    new_stocks.append(Stock(ticker=ticker, name=name, exchange=exchange, is_active=True))

            if new_stocks:
                Stock.objects.bulk_create(new_stocks, batch_size=1000)
                self.stdout.write(self.style.SUCCESS(f"✅ 在 {exchange_name_default} 列表新增 {len(new_stocks)} 只股票"))
            else:
                self.stdout.write(f"ℹ️  {exchange_name_default} 列表没有新股票。")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"同步 {exchange_name_default} 列表失败: {e}"))

    def _get_nyse_exchange_name(self, code):
        """NYSE系交易所代码映射"""
        return {'N': 'NYSE', 'A': 'NYSE_AMERICAN', 'P': 'NYSE_ARCA'}.get(code, 'OTHER')

    def update_hot_stocks_concurrently(self, limit, max_workers):
        """并发下载热门股票，并确保SPY和QQQ被更新"""
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- 批量并发更新热门股票 ---'))
        
        # 1. 获取热门股票
        hot_stocks_query = Stock.objects.filter(query_count__gt=0, is_active=True).order_by('-query_count')[:limit]
        hot_tickers = {stock.ticker for stock in hot_stocks_query}
        
        # 2. 将热门股与核心ETF合并，并去重
        tickers_to_update_set = hot_tickers.union({'SPY', 'QQQ'})
        tickers_to_update = list(tickers_to_update_set)
        
        if not tickers_to_update:
            self.stdout.write('没有需要更新的股票。')
            return
        
        self.stdout.write(f'将为 {len(tickers_to_update)} 只股票并发检查更新: {tickers_to_update}')
        
        # 3. 使用线程池并发执行下载
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {executor.submit(download_and_save_stock_data, ticker): ticker for ticker in tickers_to_update}
            for future in as_completed(future_to_ticker):
                try: 
                    self.stdout.write(f"任务完成 -> {future.result()}")
                except Exception as exc:
                    ticker = future_to_ticker[future]
                    self.stdout.write(self.style.ERROR(f'处理 {ticker} 时线程出现异常: {exc}'))