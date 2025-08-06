# 文件名: stocks/management/commands/sync_stock_data.py
# 【重构优化版】完整代码

import pandas as pd
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
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
import requests
import io
import traceback
import os

load_dotenv()

# =======================================================================
# ===           核心数据处理引擎 (重构后)                     ===
# =======================================================================

def update_stock_from_yfinance(stock_obj: Stock):
    """
    用 yfinance 获取并更新股票的最新价格和市值。
    关键改动：将市值 marketCap 存为整数 BigIntegerField。
    """
    logger = logging.getLogger(__name__)
    try:
        yf_obj = yf.Ticker(stock_obj.ticker)
        info = yf_obj.info

        # --- 修复点：info 可能为 None 或无效 ---
        if not info or not isinstance(info, dict):
            logger.error(f"❌ {stock_obj.ticker}: yfinance未返回有效info对象，跳过更新。")
            return
        # --- 修复结束 ---

        # 最新价格
        price_val = info.get('regularMarketPrice')
        stock_obj.price = Decimal(str(price_val)) if price_val is not None else None

        # 市值 (存为整数)
        mcap_val = info.get('marketCap')
        stock_obj.market_cap = int(mcap_val) if mcap_val is not None else None
        
        # logo和weburl暂时留空
        stock_obj.logo = info.get('logo_url', '')
        stock_obj.weburl = info.get('website', '')
        
        stock_obj.save()
        logger.info(f"✅ {stock_obj.ticker}: 已用yfinance更新价格({stock_obj.price})和市值({stock_obj.market_cap})。")

    except Exception as e:
        logger.error(f"❌ {stock_obj.ticker}: 用yfinance获取价格/市值失败: {e}")


def update_yfinance_and_returns(stock_obj: Stock):
    """步骤3: 从yfinance增量更新历史数据并计算收益率"""
    logger = logging.getLogger(__name__)
    today = date.today()

    latest_date = HistoricalPrice.objects.filter(stock=stock_obj).aggregate(max_date=Max('date'))['max_date']
    if latest_date:
        start_date = latest_date + timedelta(days=1)
        if start_date > today:
            logger.info(f"ℹ️  {stock_obj.ticker}: 历史数据已是最新，无需下载。")
            return
        hist_data = yf.download(stock_obj.ticker, start=start_date, progress=False, auto_adjust=True)
    else:
        hist_data = yf.download(stock_obj.ticker, period="max", progress=False, auto_adjust=True)

    if not hist_data.empty:
        count = save_data_to_db(stock_obj, hist_data)
        logger.info(f"✅ {stock_obj.ticker}: 成功保存 {count} 条历史记录。")
        if count > 0:
            calculate_and_save_returns(stock_obj)
    else:
        logger.info(f"ℹ️  {stock_obj.ticker}: 未找到新的历史数据。")


# 文件名: stocks/management/commands/sync_stock_data.py
# 【仅需修改此函数】

def save_data_to_db(stock_obj, hist_data):
    """将历史数据保存到数据库 (已修复 Series ambiguous 错误)"""
    if hist_data.empty:
        return 0
    
    new_records = []
    for index, row in hist_data.iterrows():
        try:
            close_value = row.get('Close')
            # --- 关键修复 ---
            # 检查返回的是否为 Series 对象，如果是，则取出第一个元素。
            # 这可以处理 yfinance 在某些特殊情况下返回 Series 而不是标量值的问题。
            if hasattr(close_value, 'iloc'):
                close_value = close_value.iloc[0] if not close_value.empty else None

            volume_value = row.get('Volume')
            if hasattr(volume_value, 'iloc'):
                volume_value = volume_value.iloc[0] if not volume_value.empty else None
            # --- 修复结束 ---
            
            # 现在 close_value 可以安全地进行比较
            if pd.notna(close_value) and close_value > 0:
                new_records.append(HistoricalPrice(
                    stock=stock_obj,
                    date=index.date(),
                    close=Decimal(str(close_value)), # 使用Decimal保证精度
                    volume=int(volume_value) if pd.notna(volume_value) and volume_value is not None else None
                ))
        except (ValueError, TypeError, InvalidOperation) as e:
            # 修改日志，使其包含原始错误信息，便于调试
            logging.warning(f"跳过有问题的数据行 {index.date()} for {stock_obj.ticker}: {e}", exc_info=True)
            continue
    
    if new_records:
        HistoricalPrice.objects.bulk_create(new_records, ignore_conflicts=True)
        logging.info(f"【历史数据入库】{stock_obj.ticker} 保存 {len(new_records)} 条记录，日期范围: {new_records[0].date} ~ {new_records[-1].date}")
        return len(new_records)
    return 0

def calculate_and_save_returns(stock_obj: Stock):
    """根据历史价格计算并存储不同周期的收益率"""
    logger = logging.getLogger(__name__)
    today = date.today()
    periods = {'1m': 30, '6m': 182, '1y': 365, '3y': 365*3, '5y': 365*5, '10y': 365*10}
    
    latest_price_entry = HistoricalPrice.objects.filter(stock=stock_obj).order_by('-date').first()
    if not latest_price_entry:
        logger.warning(f"没有找到 {stock_obj.ticker} 的历史价格，无法计算收益率。")
        return

    current_price = latest_price_entry.close
    update_fields = []

    for name, days in periods.items():
        past_date = today - timedelta(days=days)
        past_price_entry = HistoricalPrice.objects.filter(
            stock=stock_obj, date__lte=past_date
        ).order_by('-date').first()

        field_name = f'return_{name}'
        if past_price_entry and past_price_entry.close > 0:
            rate = (current_price - past_price_entry.close) / past_price_entry.close
            setattr(stock_obj, field_name, rate)
        else:
            setattr(stock_obj, field_name, None)
        update_fields.append(field_name)

    if update_fields:
        stock_obj.save(update_fields=update_fields)
        logger.info(f"✅ {stock_obj.ticker}: 成功计算并存储收益率。")


def process_single_ticker_deep(ticker: str):
    """
    单个股票的“深度”处理工作流：更新价格/市值 -> 检查拆股 -> 更新历史数据 -> 计算收益率。
    """
    try:
        stock_obj = Stock.objects.get(ticker=ticker)
        # 第一步：总是先更新最新的价格和市值
        update_stock_from_yfinance(stock_obj)
        # 第二步：更新历史数据并计算收益率
        update_yfinance_and_returns(stock_obj)
        return f"{ticker}: 深度更新成功"
    except Stock.DoesNotExist:
        return f"{ticker}: 股票在数据库中不存在"
    except Exception:
        logging.error(f"引擎错误：处理 {ticker} 失败: {traceback.format_exc()}")
        return f"{ticker}: 处理时发生严重错误"

# =======================================================================
# ===                     Django Management Command                  ===
# =======================================================================
class Command(BaseCommand):
    help = '【重构优化版】同步并更新股票数据，消除冗余，提升效率'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='选取热门/头部股票时，每个分类的数量')
        parser.add_argument('--max-workers', type=int, default=10, help='并发下载的线程数')
        parser.add_argument('--ticker', type=str, help='只对指定的单个股票代码进行深度更新')
        parser.add_argument('--shallow-update-only', action='store_true', help='只执行对所有股票的浅度更新(价格/市值)')

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.stdout.write(self.style.SUCCESS(f'=== {self.help} ==='))
        start_time = time.time()

        self.translator = GoogleTranslator(source='auto', target='zh-CN')
        specific_ticker = options.get('ticker')
        limit = options['limit']
        max_workers = options['max_workers']

        if specific_ticker:
            # --- 单点更新模式 ---
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n--- 单点深度更新模式：正在处理 {specific_ticker} ---"))
            result = process_single_ticker_deep(specific_ticker.upper())
            self.stdout.write(f"任务完成 -> {result}")

        elif options['shallow_update_only']:
            # --- 仅浅度更新模式 ---
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n--- 仅浅度更新模式：更新所有活跃股票的价格和市值 ---"))
            all_active_tickers = list(Stock.objects.filter(is_active=True).values_list('ticker', flat=True))
            self.batch_update_price_and_market_cap(all_active_tickers, max_workers)

        else:
            # --- 默认的完整批量模式 (已重构) ---
            
            # 1. 同步所有交易所的股票列表
            existing_stocks_map = self.sync_all_stock_lists()

            # 2. 确定需要“深度更新”和“浅度更新”的股票集合，避免重叠
            self.stdout.write(self.style.MIGRATE_HEADING('\n--- [步骤1/3] 确定更新目标 ---'))
            
            tickers_for_deep_update = self.get_deep_update_targets(limit)
            self.stdout.write(f"共确定 {len(tickers_for_deep_update)} 个需要深度更新的股票。")
            
            all_active_tickers = set(existing_stocks_map.keys())
            tickers_for_shallow_update = list(all_active_tickers - tickers_for_deep_update)
            self.stdout.write(f"共确定 {len(tickers_for_shallow_update)} 个需要浅度更新的股票。")

            # 3. 对深度更新目标执行完整流程 (并发)
            self.stdout.write(self.style.MIGRATE_HEADING('\n--- [步骤2/3] 开始并发深度更新 ---'))
            if tickers_for_deep_update:
                # 更新查询统计
                with transaction.atomic():
                    Stock.objects.filter(ticker__in=tickers_for_deep_update).update(
                        query_count=models.F('query_count') + 1,
                        last_queried=timezone.now()
                    )
                self.stdout.write(f"已为 {len(tickers_for_deep_update)} 只股票更新查询统计。")

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_ticker = {executor.submit(process_single_ticker_deep, ticker): ticker for ticker in tickers_for_deep_update}
                    for future in as_completed(future_to_ticker):
                        try:
                            self.stdout.write(f"深度更新 -> {future.result()}")
                        except Exception as exc:
                            self.stdout.write(self.style.ERROR(f'处理 {future_to_ticker[future]} 时线程异常: {exc}'))
            else:
                self.stdout.write("没有需要深度更新的目标。")

            # 4. 对浅度更新目标只更新价格和市值 (并发)
            self.stdout.write(self.style.MIGRATE_HEADING('\n--- [步骤3/3] 开始并发浅度更新 ---'))
            if tickers_for_shallow_update:
                self.batch_update_price_and_market_cap(tickers_for_shallow_update, max_workers, batch_size=200)
            else:
                self.stdout.write("没有需要浅度更新的目标。")

        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f"\n=== 全部任务完成，总耗时: {elapsed:.1f}秒 ==="))

    def get_deep_update_targets(self, limit: int) -> set:
        """
        获取所有需要深度更新的股票 Ticker，合并并去重。
        利用已优化的 market_cap 字段直接在数据库中排序。
        """
        targets = set()

        # 按查询量
        top_queried = Stock.objects.filter(is_active=True).order_by('-query_count')[:limit]
        targets.update([s.ticker for s in top_queried])

        # 按市值 (普通股)
        top_mc_stocks = Stock.objects.filter(is_active=True, is_etf=False, market_cap__isnull=False).order_by('-market_cap')[:limit]
        targets.update([s.ticker for s in top_mc_stocks])

        # 按市值 (ETF)
        top_mc_etfs = Stock.objects.filter(is_active=True, is_etf=True, market_cap__isnull=False).order_by('-market_cap')[:limit]
        targets.update([s.ticker for s in top_mc_etfs])

        return targets

    def sync_all_stock_lists(self) -> dict:
        """
        同步所有交易所的股票列表，并返回所有现有股票的 map 以供后续使用。
        """
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- 开始同步股票列表 ---'))
        
        # 优化点：只加载一次所有股票到内存
        self.stdout.write("正在从数据库加载所有现有股票对象...")
        existing_stocks_map = {s.ticker: s for s in Stock.objects.all()}
        self.stdout.write(f"加载完成，发现数据库有 {len(existing_stocks_map)} 个现有股票。")

        self._sync_single_list(
            url="https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt", 
            exchange_name_default="NASDAQ", 
            is_nasdaq=True,
            existing_stocks_map=existing_stocks_map
        )
        self._sync_single_list(
            url="https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt", 
            exchange_name_default="NYSE", 
            is_nasdaq=False,
            existing_stocks_map=existing_stocks_map
        )
        
        # 批量翻译
        self._batch_translate_names()
        
        return existing_stocks_map

    def _sync_single_list(self, url, exchange_name_default, is_nasdaq, existing_stocks_map):
        # (内部实现与原版类似，但接收 existing_stocks_map 参数)
        # ... 此处省略与原版几乎相同的 _sync_single_list 内部代码 ...
        # 主要区别是不再于函数内部加载 existing_stocks_map
        # 为保持完整性，此处粘贴完整代码
        try:
            self.stdout.write(f"正在从 {url} 下载 {exchange_name_default} 列表...")
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            df = pd.read_csv(io.StringIO(response.text), sep='|').iloc[:-1]

            new_stock_data_list, stocks_to_update = [], []
            update_fields = ['name', 'exchange', 'is_etf', 'market_category', 'financial_status', 'is_active']
            special_keywords = ['right', 'warrant', 'unit', 'preferred']

            active_tickers_from_file = set()

            for _, row in df.iterrows():
                ticker = str(row.get('Symbol', '')).strip().upper()
                if not ticker: continue
                
                raw_name = str(row.get('Security Name', '')).strip()
                name = raw_name.split('-')[0].strip()
                name_lower = name.lower()
                test_issue = str(row.get('Test Issue', '')).strip()
                nextshares = str(row.get('NextShares', 'N')).strip().upper()

                if test_issue == 'Y' or nextshares == 'Y' or any(kw in name_lower for kw in special_keywords):
                    if ticker in existing_stocks_map and existing_stocks_map[ticker].is_active:
                        stock_to_deactivate = existing_stocks_map[ticker]
                        stock_to_deactivate.is_active = False
                        stocks_to_update.append(stock_to_deactivate)
                    continue
                
                active_tickers_from_file.add(ticker)
                
                data = {
                    'name': name[:255],
                    'is_etf': str(row.get('ETF', 'N')).strip().upper() == 'Y',
                    'is_active': True
                }
                if is_nasdaq:
                    data.update({
                        'exchange': exchange_name_default,
                        'market_category': str(row.get('Market Category', '')).strip(),
                        'financial_status': str(row.get('Financial Status', '')).strip(),
                    })
                else:
                    data.update({
                        'exchange': self._get_nyse_exchange_name(str(row.get('Exchange', '')).strip()),
                    })

                if ticker not in existing_stocks_map:
                    data['ticker'] = ticker
                    new_stock_data_list.append(Stock(**data))
                else:
                    stock_obj = existing_stocks_map[ticker]
                    has_changed = any(getattr(stock_obj, field) != new_value for field, new_value in data.items())
                    if has_changed:
                        for field, new_value in data.items():
                            setattr(stock_obj, field, new_value)
                        stocks_to_update.append(stock_obj)
            
            # (批量写入数据库逻辑与之前相同)
            if new_stock_data_list:
                Stock.objects.bulk_create(new_stock_data_list, batch_size=1000)
                self.stdout.write(self.style.SUCCESS(f"✅ 在 {exchange_name_default} 列表新增 {len(new_stock_data_list)} 只股票"))
            if stocks_to_update:
                Stock.objects.bulk_update(stocks_to_update, update_fields, batch_size=1000)
                self.stdout.write(self.style.SUCCESS(f"✅ 在 {exchange_name_default} 列表更新了 {len(stocks_to_update)} 只股票的信息"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"同步 {exchange_name_default} 列表失败: {e}"))
            traceback.print_exc()

    def _batch_translate_names(self):
        """统一翻译所有中文名为空的活跃股票"""
        to_translate = Stock.objects.filter(chinese_keywords__in=['', None], is_active=True)
        if not to_translate.exists(): return
        
        names_to_translate = list(to_translate.values('pk', 'name'))
        self.stdout.write(f"准备翻译 {len(names_to_translate)} 个未翻译的股票名称...")
        batch_size = 200
        for i in range(0, len(names_to_translate), batch_size):
            chunk = names_to_translate[i:i+batch_size]
            names_only = [item['name'] for item in chunk]
            try:
                translated_chunk = self.translator.translate_batch(names_only)
                for item, chinese in zip(chunk, translated_chunk):
                    Stock.objects.filter(pk=item['pk']).update(chinese_keywords=chinese or '')
                self.stdout.write(self.style.SUCCESS(f"✅ 批次 {i//batch_size + 1} 翻译完成"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ 批次 {i//batch_size + 1} 翻译失败: {e}"))

    def _get_nyse_exchange_name(self, code):
        return {'N': 'NYSE', 'A': 'NYSE_AMERICAN', 'P': 'NYSE_ARCA'}.get(code, 'OTHER')

    def batch_update_price_and_market_cap(self, tickers: list, max_workers: int, batch_size: int = 200):
        """
        (新) 使用 yf.Tickers 对大量股票进行高效的浅度更新(价格/市值)。
        使用 bulk_update 提升数据库写入性能。
        """
        self.stdout.write(f"将对 {len(tickers)} 只股票进行批量浅度更新...")
        
        for i in range(0, len(tickers), batch_size):
            batch_tickers = tickers[i:i+batch_size]
            tickers_str = " ".join(batch_tickers)
            stocks_to_update = []
            
            try:
                yf_data = yf.Tickers(tickers_str)
                
                for ticker in batch_tickers:
                    try:
                        info = yf_data.tickers[ticker].info
                        # yfinance在ticker无效时info返回{'isSpam': True}或类似结构
                        if info.get('regularMarketPrice') is None and info.get('marketCap') is None:
                            logging.warning(f"⚠️ {ticker}: 批量获取时未返回有效价格/市值，跳过。")
                            continue

                        stock_obj = Stock.objects.get(ticker=ticker)
                        
                        price_val = info.get('regularMarketPrice')
                        stock_obj.price = Decimal(str(price_val)) if price_val is not None else None

                        mcap_val = info.get('marketCap')
                        stock_obj.market_cap = int(mcap_val) if mcap_val is not None else None
                        
                        stocks_to_update.append(stock_obj)

                    except Stock.DoesNotExist:
                        logging.error(f"❌ {ticker}: 在数据库中未找到，无法更新。")
                    except Exception as e:
                        logging.error(f"❌ {ticker}: 解析批量数据失败: {e}")

                if stocks_to_update:
                    Stock.objects.bulk_update(stocks_to_update, ['price', 'market_cap'], batch_size=500)
                    self.stdout.write(f"批次 {i//batch_size + 1}: 成功更新 {len(stocks_to_update)}/{len(batch_tickers)} 只股票的价格/市值。")

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"批次 {i//batch_size + 1} 批量下载失败: {e}"))

            time.sleep(1) # 每批次之间稍作停顿，防止API限流