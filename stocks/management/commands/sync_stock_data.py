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
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
import pandas as pd
import requests
import io
import time
import logging
import traceback
import os 

load_dotenv()  # 从 .env 文件加载环境变量


# =======================================================================
# ===           核心数据处理引擎 (重构后)                     ===
# =======================================================================

def update_stock_from_yfinance(stock_obj: Stock):
    """
    用 yfinance 获取并更新股票的价格和市值（如有），logo和网站字段暂留空
    """
    import yfinance as yf
    logger = logging.getLogger(__name__)
    try:
        yf_obj = yf.Ticker(stock_obj.ticker)
        info = yf_obj.info
        # 最新价格
        stock_obj.price = info.get('regularMarketPrice')
        # 市值
        stock_obj.market_cap = info.get('marketCap')
        # logo和weburl暂时留空
        stock_obj.logo = ''
        stock_obj.weburl = ''
        logger.info(f"✅ {stock_obj.ticker}: 已用yfinance更新价格和市值。")
    except Exception as e:
        logger.error(f"❌ {stock_obj.ticker}: 用yfinance获取价格/市值失败: {e}")
    stock_obj.save() # 保存更新


def update_yfinance_and_returns(stock_obj: Stock):
    """
    步骤3: 从yfinance增量更新历史数据并计算收益率
    """
    logger = logging.getLogger(__name__)
    today = date.today()

    # 下载历史数据
    latest_date = HistoricalPrice.objects.filter(stock=stock_obj).aggregate(max_date=Max('date'))['max_date']
    if latest_date:
        start_date = latest_date + timedelta(days=1)
        if start_date > today:
            logger.info(
                f"ℹ️  {stock_obj.ticker}: 历史数据已是最新，无需下载。（数据库最新日期：{latest_date}，今天：{today}）"
            )
            return
        hist_data = yf.download(stock_obj.ticker, start=start_date, progress=False, auto_adjust=True)
    else:
        hist_data = yf.download(stock_obj.ticker, period="max", progress=False, auto_adjust=True)

    # 保存到数据库
    if not hist_data.empty:
        count = save_data_to_db(stock_obj, hist_data)
        logger.info(f"✅ {stock_obj.ticker}: 成功保存 {count} 条历史记录。")
        if count > 0:
            calculate_and_save_returns(stock_obj)
    else:
        logger.info(
            f"ℹ️  {stock_obj.ticker}: 未找到新的历史数据。（可能yfinance无数据或已全部入库）"
        )


def process_single_ticker(ticker: str):
    """
    单个股票处理工作流: yfinance -> 拆股检查 -> yfinance历史 -> 计算
    """
    try:
        stock_obj = Stock.objects.get(ticker=ticker)
        update_stock_from_yfinance(stock_obj)  
        # check_and_handle_splits(stock_obj) # 拆股检查如需保留可继续用yfinance
        update_yfinance_and_returns(stock_obj)
        return f"{ticker}: 更新成功"
    except Stock.DoesNotExist:
        return f"{ticker}: 股票在数据库中不存在"
    except Exception:
        logging.error(f"引擎错误：处理 {ticker} 失败: {traceback.format_exc()}")
        return f"{ticker}: 处理时发生错误"


# === 旧的核心函数 (注释保留) ===
# def download_and_save_stock_data(ticker: str):
#     """
#     核心函数：下载并保存单个股票数据。已移除所有临时缓存逻辑。
#     """
#     logger = logging.getLogger(__name__)
#     today = date.today()
#     try:
#         stock_obj = Stock.objects.get(ticker=ticker)
#         # ... (旧的混合逻辑)
#     except Stock.DoesNotExist:
#         return f"{ticker}:stock_not_found"
#     except Exception:
#         logger.error(f"引擎错误：处理 {ticker} 失败: {traceback.format_exc()}")
#         return f"{ticker}:error"


def check_and_handle_splits(stock_obj: Stock):
    """
    用 yfinance 检查股票自上次更新以来是否有拆股事件，如有则删除历史数据以便重新下载。
    """
    import yfinance as yf
    logger = logging.getLogger(__name__)
    latest_date = HistoricalPrice.objects.filter(stock=stock_obj).aggregate(max_date=Max('date'))['max_date']
    if not latest_date:
        return

    try:
        yf_obj = yf.Ticker(stock_obj.ticker)
        splits = yf_obj.splits
        # 拆股日期大于数据库最新日期，说明有新拆股
        new_split_dates = [d for d in splits.index if d.date() > latest_date]
        if new_split_dates:
            logger.warning(f"⚠️  检测到 {stock_obj.ticker} 有新的拆股事件！将删除本地历史数据并重新下载。")
            HistoricalPrice.objects.filter(stock=stock_obj).delete()
            logger.info(f"✅ {stock_obj.ticker} 的旧历史数据已删除。")
    except Exception as e:
        logger.error(f"❌ 检查拆股时发生未知错误 ({stock_obj.ticker}): {e}")


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
        # 新增：每次保存后打印一条详细日志
        print(f"【历史数据入库】{stock_obj.ticker} 保存 {len(new_records)} 条记录，日期范围: {new_records[0].date} ~ {new_records[-1].date}")
        return len(new_records)
    else:
        return 0



def calculate_and_save_returns(stock_obj: Stock):
    """根据历史价格计算并存储不同周期的收益率"""
    logger = logging.getLogger(__name__)
    today = date.today()
    periods = {
        '1m': 30, '6m': 182, '1y': 365, '3y': 365*3,
        '5y': 365*5, '10y': 365*10
    }
    
    # 获取最新收盘价
    latest_price_entry = HistoricalPrice.objects.filter(stock=stock_obj).order_by('-date').first()
    if not latest_price_entry:
        logger.warning(f"没有找到 {stock_obj.ticker} 的历史价格，无法计算收益率。")
        return

    current_price = latest_price_entry.close
    update_fields = []

    for name, days in periods.items():
        past_date = today - timedelta(days=days)
        # 查找最接近目标日期的历史价格
        past_price_entry = HistoricalPrice.objects.filter(
            stock=stock_obj, date__lte=past_date
        ).order_by('-date').first()

        if past_price_entry and past_price_entry.close > 0:
            past_price = past_price_entry.close
            # 计算收益率: (现价 - 旧价) / 旧价
            rate = (current_price - past_price) / past_price
            setattr(stock_obj, f'return_{name}', rate)
            update_fields.append(f'return_{name}')
        else:
            # 如果找不到足够久远的数据，则将收益率设为None
            setattr(stock_obj, f'return_{name}', None)
            update_fields.append(f'return_{name}')

    if update_fields:
        stock_obj.save(update_fields=update_fields)
        logger.info(f"✅ {stock_obj.ticker}: 成功计算并存储收益率。")


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
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - INFO - %(message)s')
        self.stdout.write(self.style.SUCCESS(f'=== {self.help} ==='))
        start_time = time.time()

        self.translator = GoogleTranslator(source='auto', target='zh-CN')
        specific_ticker = options.get('ticker')

        if specific_ticker:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n--- 单点更新模式：正在处理 {specific_ticker} ---"))
            result = process_single_ticker(specific_ticker.upper())
            self.stdout.write(f"任务完成 -> {result}")
        else:
            self.sync_all_stock_lists()
            self.update_hot_stocks_concurrently(options['limit'], options['max_workers'])
            # 新增：更新市值前100和点击率前100的普通股票历史数据
            self.update_top_stock_history(top_n=100, max_workers=2)
            # 新增：更新市值前20和点击率前20的ETF历史数据
            self.update_top_etf_history(top_n=20, max_workers=2)

        elapsed = time.time() - start_time
        self.stdout.write(f"\n=== 全部任务完成，总耗时: {elapsed:.1f}秒 ===")
    
    def sync_all_stock_lists(self):
        """
        (重构) 同步所有交易所的股票列表。
        现在，每个列表的处理是独立的事务：下载、翻译、写入完成后，再开始下一个。
        """
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- 开始同步股票列表 ---'))
        
        # 处理纳斯达克列表
        self.stdout.write(self.style.MIGRATE_HEADING('\n[阶段1/2] 处理 NASDAQ 列表...'))
        self._sync_single_list(
            url="https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt", 
            exchange_name_default="NASDAQ", 
            is_nasdaq=True
        )

        # 处理其他列表 (NYSE等)
        self.stdout.write(self.style.MIGRATE_HEADING('\n[阶段2/2] 处理 NYSE/OTHER 列表...'))
        self._sync_single_list(
            url="https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt", 
            exchange_name_default="NYSE", 
            is_nasdaq=False
        )

    def _sync_single_list(self, url, exchange_name_default, is_nasdaq):
        """
        (重构) 同步单个交易所列表的完整流程：
        下载 -> 收集 -> 批量翻译 -> 批量写入数据库
        """
        try:
            # --- 数据下载 ---
            self.stdout.write(f"正在从 {url} 下载数据...")
            response = requests.get(url, timeout=30)
            self.stdout.write(f"数据下载完成，状态码: {response.status_code}")
            response.raise_for_status()
            df = pd.read_csv(io.StringIO(response.text), sep='|').iloc[:-1]

            # --- 数据收集 ---
            self.stdout.write("正在从数据库加载所有现有股票对象...")
            existing_stocks_map = {s.ticker: s for s in Stock.objects.all()}
            self.stdout.write(f"加载完成，发现 {len(existing_stocks_map)} 个现有股票。")

            new_stock_data_list, stocks_to_update, names_to_translate, name_map = [], [], [], {}
            update_fields = ['name', 'exchange', 'is_etf', 'market_category', 'financial_status', 'is_active', 'chinese_keywords']

            # 新增：直接过滤特殊类型的股票
            special_keywords = [
                'warrant', 'preferred', 'bond', 'note', 'unit', 'right', 'spac',
                'etn', 'adr', 'depositary receipt', 'structured product', 'temp', 'test', 'swap',
                'future', 'option'
            ]

            for row in df.iterrows():
                ticker = row.get('Symbol', '').strip().upper()
                name = str(row.get('Security Name', '')).lower()
                test_issue = str(row.get('Test Issue', '')).strip()
                # 直接过滤特殊类型
                if test_issue == 'Y' or any(kw in name for kw in special_keywords):
                    if ticker in existing_stocks_map and existing_stocks_map[ticker].is_active:
                        stock_to_deactivate = existing_stocks_map[ticker]
                        stock_to_deactivate.is_active = False
                        stocks_to_update.append(stock_to_deactivate)
                    continue

                data = {}
                if is_nasdaq:
                    data = {
                        'name': str(row.get('Security Name', '')).strip()[:255],
                        'exchange': exchange_name_default,
                        'is_etf': str(row.get('ETF', 'N')).strip().upper() == 'Y',
                        'market_category': str(row.get('Market Category', '')).strip(),
                        'financial_status': str(row.get('Financial Status', '')).strip(),
                        'is_active': True
                    }
                else:  # NYSE 和其他
                    data = {
                        'name': str(row.get('Security Name', '')).strip()[:255],
                        'exchange': self._get_nyse_exchange_name(str(row.get('Exchange', '')).strip()),
                        'is_etf': str(row.get('ETF', 'N')).strip().upper() == 'Y',
                        'is_active': True,
                        'market_category': None,
                        'financial_status': None
                    }

                # 对比并决定是创建还是更新
                if ticker not in existing_stocks_map:
                    data['ticker'] = ticker
                    new_stock_data_list.append(data)
                    if data['name'] and data['name'] not in name_map:
                        name_map[data['name']] = None
                        names_to_translate.append(data['name'])
                else:
                    stock_obj = existing_stocks_map[ticker]
                    has_changed = False
                    
                    for field, new_value in data.items():
                        if getattr(stock_obj, field) != new_value:
                            setattr(stock_obj, field, new_value)
                            has_changed = True
                    
                    if stock_obj.name != data['name']:
                        if data['name'] and data['name'] not in name_map:
                            name_map[data['name']] = None
                            names_to_translate.append(data['name'])
                        stock_obj.name = data['name']
                        has_changed = True

                    if has_changed:
                        stocks_to_update.append(stock_obj)

            # --- 批量翻译 ---
            if names_to_translate:
                self.stdout.write(f"准备分批翻译 {len(names_to_translate)} 个唯一的股票名称...")
                batch_size = 100
                total_translated = 0
                for i in range(0, len(names_to_translate), batch_size):
                    chunk = names_to_translate[i:i + batch_size]
                    start_num, end_num = i + 1, i + len(chunk)
                    self.stdout.write(f"  -> 正在翻译第 {start_num}-{end_num} 个名称...")
                    try:
                        translated_chunk = self.translator.translate_batch(chunk)
                        for original, translated in zip(chunk, translated_chunk):
                            name_map[original] = translated or ''
                        total_translated += len(chunk)
                        self.stdout.write(f"     ...完成。当前总计: {total_translated}/{len(names_to_translate)}")
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"     ...翻译批次 {start_num}-{end_num} 失败: {e}"))
                        for original in chunk: name_map[original] = ''
                    time.sleep(1)
                self.stdout.write("全部分批翻译完成。")

            # --- 批量写入数据库 ---
            # 处理新股
            stocks_to_create_final = [Stock(**{**data, 'chinese_keywords': name_map.get(data['name'], '')}) for data in new_stock_data_list]
            if stocks_to_create_final:
                Stock.objects.bulk_create(stocks_to_create_final, batch_size=1000)
                self.stdout.write(self.style.SUCCESS(f"✅ 在 {exchange_name_default} 列表新增 {len(stocks_to_create_final)} 只股票"))

            # 为待更新的股票回填翻译结果
            for stock_obj in stocks_to_update:
                if stock_obj.name in name_map:
                    stock_obj.chinese_keywords = name_map[stock_obj.name]
            
            if stocks_to_update:
                Stock.objects.bulk_update(stocks_to_update, update_fields, batch_size=1000)
                self.stdout.write(self.style.SUCCESS(f"✅ 在 {exchange_name_default} 列表更新了 {len(stocks_to_update)} 只股票的信息"))

            if not stocks_to_create_final and not stocks_to_update:
                 self.stdout.write(f"ℹ️  {exchange_name_default} 列表没有变化。")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"同步 {exchange_name_default} 列表失败: {e}"))
            traceback.print_exc()

    def _get_nyse_exchange_name(self, code):
        """NYSE系交易所代码映射"""
        return {'N': 'NYSE', 'A': 'NYSE_AMERICAN', 'P': 'NYSE_ARCA'}.get(code, 'OTHER')

    def update_hot_stocks_concurrently(self, limit, max_workers):
        """并发下载热门股票，并确保SPY和QQQ被更新"""
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- 批量并发更新热门股票 ---'))
        
        # === 旧的获取逻辑 (注释保留) ===
        # hot_stocks_query = Stock.objects.filter(query_count__gt=0, is_active=True).order_by('-query_count')[:limit]
        # hot_tickers = {stock.ticker for stock in hot_stocks_query}

        # === 新逻辑：合并市值排名和查询量排名 ===
        # 1. 获取查询量最高的股票
        top_queried_tickers = set(Stock.objects.filter(query_count__gt=0, is_active=True).order_by('-query_count').values_list('ticker', flat=True)[:limit])
        
        # 2. 获取市值最高的股票 (注意：market_cap是文本，需要先转为数字再排序)
        # 我们先获取所有带市值的股票，然后在Python中排序，因为直接在数据库中对文本排序不准确
        stocks_with_mc = Stock.objects.filter(is_active=True, market_cap__isnull=False).exclude(market_cap__exact='')
        
        def sort_key_market_cap(stock):
            mc_str = stock.market_cap.replace('M', '')
            try:
                return float(mc_str)
            except (ValueError, TypeError):
                return 0
        
        sorted_by_mc = sorted(stocks_with_mc, key=sort_key_market_cap, reverse=True)
        top_market_cap_tickers = {s.ticker for s in sorted_by_mc[:limit]}

        # 3. 将热门股与核心ETF合并，并去重
        hot_tickers = top_queried_tickers.union(top_market_cap_tickers)
        tickers_to_update_set = hot_tickers.union({'SPY', 'QQQ'})  # 不再硬编码 QQQ/SPY
        tickers_to_update_set = hot_tickers
        tickers_to_update = list(tickers_to_update_set)
        
        if not tickers_to_update:
            self.stdout.write('没有需要更新的股票。')
            return
        
        # 新增：在主线程中预先更新所有待处理股票的查询统计
        with transaction.atomic():
            Stock.objects.filter(ticker__in=tickers_to_update).update(
                query_count=models.F('query_count') + 1,
                last_queried=timezone.now()
            )
        self.stdout.write(f"已为 {len(tickers_to_update)} 只股票更新查询统计。")

        self.stdout.write(f'将为 {len(tickers_to_update)} 只股票并发检查更新: {tickers_to_update}')
        
        # 3. 使用线程池并发执行下载
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # === 旧逻辑 (注释保留) ===
            # future_to_ticker = {executor.submit(download_and_save_stock_data, ticker): ticker for ticker in tickers_to_update}
            # === 新逻辑 ===
            future_to_ticker = {executor.submit(process_single_ticker, ticker): ticker for ticker in tickers_to_update}
            for future in as_completed(future_to_ticker):
                try: 
                    self.stdout.write(f"任务完成 -> {future.result()}")
                except Exception as exc:
                    ticker = future_to_ticker[future]
                    self.stdout.write(self.style.ERROR(f'处理 {ticker} 时线程出现异常: {exc}'))


    def update_top_etf_history(self, top_n=20, max_workers=5):
        """
        下载市值前100和点击率前100的ETF历史价格数据
        """
        etf_qs = Stock.objects.filter(is_etf=True, is_active=True)
        def mc_val(stock):
            try:
                return float(str(stock.market_cap).replace('M', ''))
            except:
                return 0
        top_mc_etfs = sorted(etf_qs, key=mc_val, reverse=True)[:top_n]
        top_query_etfs = etf_qs.order_by('-query_count')[:top_n]
        tickers = set([s.ticker for s in top_mc_etfs] + [s.ticker for s in top_query_etfs])
        self.stdout.write(f"将批量下载 {len(tickers)} 个ETF的历史数据...")
        self.stdout.write(f"ETF下载列表: {sorted(list(tickers))}")
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {executor.submit(process_single_ticker, ticker): ticker for ticker in tickers}
            for future in as_completed(future_to_ticker):
                try:
                    self.stdout.write(f"ETF任务完成 -> {future.result()}")
                except Exception as exc:
                    ticker = future_to_ticker[future]
                    self.stdout.write(self.style.ERROR(f'ETF处理 {ticker} 时线程异常: {exc}'))

    def update_top_stock_history(self, top_n=100, max_workers=5):
        """
        下载市值前100和点击率前100的普通股票历史价格数据
        """
        stock_qs = Stock.objects.filter(is_etf=False, is_active=True, market_cap__isnull=False).exclude(market_cap__exact='')
        # 市值排序
        def mc_val(stock):
            try:
                return float(str(stock.market_cap).replace('M', ''))
            except:
                return 0
        top_mc_stocks = sorted(stock_qs, key=mc_val, reverse=True)[:top_n]
        # 查询量排序
        top_query_stocks = Stock.objects.filter(is_etf=False, is_active=True).order_by('-query_count')[:top_n]
        # 合并去重
        tickers = set([s.ticker for s in top_mc_stocks] + [s.ticker for s in top_query_stocks])
        self.stdout.write(f"将批量下载 {len(tickers)} 个普通股票的历史数据...")
        self.stdout.write(f"普通股下载列表: {sorted(list(tickers))}")

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {executor.submit(process_single_ticker, ticker): ticker for ticker in tickers}
            for future in as_completed(future_to_ticker):
                try:
                    self.stdout.write(f"普通股任务完成 -> {future.result()}")
                except Exception as exc:
                    ticker = future_to_ticker[future]
                    self.stdout.write(self.style.ERROR(f'普通股处理 {ticker} 时线程异常: {exc}'))