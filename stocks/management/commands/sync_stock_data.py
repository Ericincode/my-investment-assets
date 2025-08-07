# 文件路径: stocks/management/commands/sync_stock_data.py
# 【最终版：专注长期投资，流程精简高效】

import pandas as pd
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.db import models
from stocks.models import Stock, HistoricalPrice
from django.db.models import Max
import time
import yfinance as yf
from yfinance.shared import YFInvalidPeriodError
import logging
from django.db import transaction
from concurrent.futures import ThreadPoolExecutor
from django.utils import timezone
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
import requests
import io
import traceback
import os
import finnhub
import random

load_dotenv()

# =======================================================================
# ===           全局设置和 Finnhub 客户端初始化            ===
# =======================================================================
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
if not FINNHUB_API_KEY:
    raise ValueError("错误: 请在 .env 文件中设置 FINNHUB_API_KEY")

finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
logger = logging.getLogger(__name__)

# =======================================================================
# ===           核心数据处理引擎 (最终版)                     ===
# =======================================================================

def update_stock_profile_from_finnhub(stock_obj: Stock):
    # (此函数逻辑不变，已包含智能重试)
    max_retries = 3
    base_delay = 10
    for attempt in range(max_retries):
        try:
            profile = finnhub_client.company_profile2(symbol=stock_obj.ticker)
            if not profile:
                logger.warning(f"⚠️ {stock_obj.ticker}: Finnhub 未返回有效的公司 Profile。")
                return
            stock_obj.country = profile.get('country')
            stock_obj.exchange = (profile.get('exchange') or '').split(' ')[0]
            stock_obj.finnhub_industry = profile.get('finnhubIndustry')
            ipo_date_str = profile.get('ipo')
            if ipo_date_str:
                try: stock_obj.ipo = date.fromisoformat(ipo_date_str)
                except (ValueError, TypeError): stock_obj.ipo = None
            stock_obj.logo = profile.get('logo')
            mcap_million = profile.get('marketCapitalization', 0)
            stock_obj.market_cap = int(mcap_million * 1_000_000) if mcap_million else None
            stock_obj.name = profile.get('name')
            stock_obj.phone = profile.get('phone')
            stock_obj.weburl = profile.get('weburl')
            stock_obj.save()
            logger.info(f"✅ {stock_obj.ticker}: 已从 Finnhub 更新公司 Profile。")
            return
        except finnhub.FinnhubAPIException as e:
            if e.status_code == 429 and attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt) + random.uniform(0, 5)
                logger.warning(f"Finnhub API 限流 for {stock_obj.ticker}. Attempt {attempt + 1}/{max_retries}. Retrying in {wait_time:.1f} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"❌ {stock_obj.ticker}: Finnhub API 异常: {e}")
                return
        except Exception as e:
            logger.error(f"❌ {stock_obj.ticker}: 更新 Profile 失败 (非API错误): {e}")
            return
    logger.error(f"❌ {stock_obj.ticker}: Finnhub 更新失败，已达最大重试次数。")

def update_historical_data_and_latest_price(stock_obj: Stock):
    # (此函数逻辑已更新，修复了错误并简化了价格保存)
    hist_data = None
    latest_date_in_db = HistoricalPrice.objects.filter(stock=stock_obj).aggregate(max_date=Max('date'))['max_date']

    try:
        if latest_date_in_db:
            if latest_date_in_db >= date.today():
                 logger.info(f"ℹ️ {stock_obj.ticker}: 历史数据已最新。")
                 calculate_and_save_returns(stock_obj)
                 return
            start_date_str = (latest_date_in_db + timedelta(days=1)).strftime('%Y-%m-%d')
            hist_data = yf.download(stock_obj.ticker, start=start_date_str, progress=False, auto_adjust=True)
        else:
            logger.info(f"ℹ️ {stock_obj.ticker}: 无本地历史数据，将下载全量。")
            hist_data = yf.download(stock_obj.ticker, period="max", progress=False, auto_adjust=True)
    except YFInvalidPeriodError:
        logger.error(f"❌ {stock_obj.ticker}: yfinance 不支持 'max' 周期，跳过历史数据下载。")
        return # 优雅退出
    except Exception as e:
        logger.error(f"❌ {stock_obj.ticker}: yfinance 下载失败: {e}")
        return

    if hist_data is not None and not hist_data.empty:
        last_row = hist_data.iloc[-1]
        try:
            # 健壮性检查: 确保价格是有效数字
            if pd.notna(last_row['Close']):
                stock_obj.price = Decimal(str(last_row['Close']))
                stock_obj.save(update_fields=['price'])
                logger.info(f"✅ {stock_obj.ticker}: 已更新最新价格: {stock_obj.price}")
            else:
                 logger.warning(f"⚠️ {stock_obj.ticker}: yfinance返回的最新价格无效 (NaN)。")

            count = save_data_to_db(stock_obj, hist_data) # 保存简化后的历史数据
            if count > 0:
                logger.info(f"✅ {stock_obj.ticker}: 成功保存 {count} 条新历史记录。")
                calculate_and_save_returns(stock_obj) # 关键：计算收益率
        except (InvalidOperation, TypeError) as e:
            logger.error(f"❌ {stock_obj.ticker}: 从yfinance数据解析价格失败: {e}")
    else:
        logger.info(f"ℹ️ {stock_obj.ticker}: 未找到新的历史数据。")

def save_data_to_db(stock_obj, hist_data):
    # 【已简化】只保存 close 和 volume
    if hist_data.empty: return 0
    new_records = []
    for index, row in hist_data.iterrows():
        try:
            close_value = row.get('Close')
            if pd.notna(close_value) and close_value > 0:
                new_records.append(HistoricalPrice(
                    stock=stock_obj,
                    date=index.date(),
                    close=Decimal(str(close_value)),
                    volume=int(row.get('Volume', 0))
                ))
        except (ValueError, TypeError, InvalidOperation):
            continue
    if new_records:
        HistoricalPrice.objects.bulk_create(new_records, ignore_conflicts=True, batch_size=1000)
        return len(new_records)
    return 0

def calculate_and_save_returns(stock_obj: Stock):
    # (此函数逻辑不变，它已经是基于收盘价的)
    today = date.today()
    periods = {'1m': 30, '6m': 182, '1y': 365, '3y': 365*3, '5y': 365*5, '10y': 365*10}
    latest_price_entry = HistoricalPrice.objects.filter(stock=stock_obj).order_by('-date').first()
    if not latest_price_entry: return
    current_price = latest_price_entry.close
    update_fields = []
    for name, days in periods.items():
        past_date = today - timedelta(days=days)
        past_price_entry = HistoricalPrice.objects.filter(stock=stock_obj, date__lte=past_date).order_by('-date').first()
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
    """单个股票的深度更新完整流程"""
    try:
        stock_obj = Stock.objects.get(ticker=ticker)
        # 1. 更新公司 Profile
        update_stock_profile_from_finnhub(stock_obj)
        # 2. 更新历史价格、最新价，并计算收益率
        update_historical_data_and_latest_price(stock_obj)
        return f"{ticker}: 深度更新成功"
    except Stock.DoesNotExist:
        return f"{ticker}: 股票不存在"
    except Exception:
        logging.error(f"引擎错误：处理 {ticker} 失败: {traceback.format_exc()}")
        return f"{ticker}: 处理时发生严重错误"

# =======================================================================
# ===           Django Management Command (最终版)                ===
# =======================================================================
class Command(BaseCommand):
    help = '【最终版】同步股票数据，专注长期投资核心指标'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='选取查询量最多的股票数量')
        parser.add_argument('--top-marketcap', type=int, default=10, help='选取市值最高的股票数量')
        parser.add_argument('--max-workers', type=int, default=5, help='并发下载的线程数 (建议不超过5)')
        parser.add_argument('--ticker', type=str, help='只对指定的单个股票代码进行深度更新')

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.stdout.write(self.style.SUCCESS(f'=== {self.help} ==='))
        start_time = time.time()
        self.options = options

        if options.get('ticker'):
            self.stdout.write(self.style.MIGRATE_HEADING(f"--- 单点深度更新模式：正在处理 {options['ticker']} ---"))
            result = process_single_ticker_deep(options['ticker'].upper())
            self.stdout.write(self.style.SUCCESS(f"任务完成 -> {result}"))
        else:
            self.run_batch_update()

        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f"\n=== 全部任务完成，总耗时: {elapsed:.1f}秒 ==="))

    def run_batch_update(self):
        # --- [步骤 1/4] ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- [步骤 1/4] 开始：同步交易所股票列表 ---'))
        self.sync_all_stock_lists()
        self.stdout.write(self.style.SUCCESS('✅ [步骤 1/4] 完成：交易所股票列表同步完毕。'))
        
        # --- [步骤 2/4] ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- [步骤 2/4] 开始：检查并回填缺失的股票市值 ---'))
        self.batch_backfill_market_cap()
        self.stdout.write(self.style.SUCCESS('✅ [步骤 2/4] 完成：市值回填任务结束。'))
        
        # --- [步骤 3/4] ---
        self.stdout.write(self.style.MIGRATE_HEADING('\n--- [步骤 3/4] 开始：确定深度更新目标 ---'))
        tickers_for_deep_update = self.get_deep_update_targets()
        self.stdout.write(f"共确定 {len(tickers_for_deep_update)} 个需要深度更新的股票。")
        self.stdout.write(self.style.SUCCESS('✅ [步骤 3/4] 完成：更新目标已确定。'))

        # --- [步骤 4/4] ---
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n--- [步骤 4/4] 开始：并发深度更新 ({len(tickers_for_deep_update)}只重点股) ---'))
        if tickers_for_deep_update:
            with transaction.atomic():
                Stock.objects.filter(ticker__in=tickers_for_deep_update).update(
                    query_count=models.F('query_count') + 1, last_queried=timezone.now())
            with ThreadPoolExecutor(max_workers=self.options['max_workers']) as executor:
                results = executor.map(process_single_ticker_deep, tickers_for_deep_update)
                for result in results: self.stdout.write(f"深度更新 -> {result}")
        else:
            self.stdout.write("没有需要深度更新的目标。")
        self.stdout.write(self.style.SUCCESS('✅ [步骤 4/4] 完成：深度更新任务结束。'))

    def batch_backfill_market_cap(self, batch_size=200, sleep_between_batches=2):
        """【新】分批回填缺失的市值"""
        tickers_missing_mcap = list(Stock.objects.filter(is_active=True, market_cap__isnull=True).values_list('ticker', flat=True))
        if not tickers_missing_mcap:
            self.stdout.write("所有活跃股票均有市值数据，无需回填。")
            return

        self.stdout.write(f"发现 {len(tickers_missing_mcap)} 只股票缺失市值，开始分批回填...")
        for i in range(0, len(tickers_missing_mcap), batch_size):
            batch_tickers = tickers_missing_mcap[i:i+batch_size]
            self.stdout.write(f"正在处理批次 {i//batch_size + 1} ({len(batch_tickers)} 只股票)...")
            yf_data = yf.Tickers(" ".join(batch_tickers))
            stocks_to_update = []
            for ticker_obj in yf_data.tickers.values():
                try:
                    mcap_val = ticker_obj.info.get('marketCap')
                    if mcap_val:
                        stock = Stock(ticker=ticker_obj.ticker, market_cap=int(mcap_val))
                        stocks_to_update.append(stock)
                except Exception: continue
            
            if stocks_to_update:
                Stock.objects.bulk_update(stocks_to_update, ['market_cap'], batch_size=500)
                self.stdout.write(f"本批次成功更新 {len(stocks_to_update)} 只股票的市值。")
            
            time.sleep(sleep_between_batches)

    def get_deep_update_targets(self) -> set:
        """【已修改】获取市值前10和查询量前100的股票"""
        limit = self.options['limit']
        top_mc = self.options['top_marketcap']
        targets = set()
        
        top_queried = Stock.objects.filter(is_active=True).order_by('-query_count')[:limit]
        targets.update([s.ticker for s in top_queried])
        
        top_mc_stocks = Stock.objects.filter(is_active=True, market_cap__isnull=False).order_by('-market_cap')[:top_mc]
        targets.update([s.ticker for s in top_mc_stocks])
        
        return targets

    # (sync_all_stock_lists 及其辅助函数保持不变)
    def sync_all_stock_lists(self):
        self.translator = GoogleTranslator(source='auto', target='zh-CN')
        existing_stocks_map = {s.ticker: s for s in Stock.objects.all()}
        self._sync_single_list(url="https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt", exchange_name_default="NASDAQ", is_nasdaq=True, existing_stocks_map=existing_stocks_map)
        self._sync_single_list(url="https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt", exchange_name_default="NYSE", is_nasdaq=False, existing_stocks_map=existing_stocks_map)
        self._batch_translate_names()

    def _sync_single_list(self, url, exchange_name_default, is_nasdaq, existing_stocks_map):
        try:
            self.stdout.write(f"正在从 {url} 下载 {exchange_name_default} 列表...")
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            df = pd.read_csv(io.StringIO(response.text), sep='|').iloc[:-1]
            new_stock_data_list, stocks_to_update = [], []
            update_fields = ['name', 'is_etf', 'market_category', 'financial_status', 'is_active']
            if not is_nasdaq: update_fields.append('exchange')
            for _, row in df.iterrows():
                ticker = str(row.get('Symbol', '')).strip().upper()
                if not ticker: continue
                raw_name = str(row.get('Security Name', '')).strip()
                name = raw_name.split('-')[0].strip()
                if str(row.get('Test Issue', 'N')).strip() == 'Y' or str(row.get('NextShares', 'N')).strip().upper() == 'Y':
                    if ticker in existing_stocks_map and existing_stocks_map[ticker].is_active:
                        existing_stocks_map[ticker].is_active = False
                        stocks_to_update.append(existing_stocks_map[ticker])
                    continue
                data = {'name': name[:255], 'is_etf': str(row.get('ETF', 'N')).strip().upper() == 'Y', 'is_active': True}
                if is_nasdaq:
                    data.update({'market_category': str(row.get('Market Category', '')).strip(), 'financial_status': str(row.get('Financial Status', '')).strip()})
                else:
                    data.update({'exchange': self._get_nyse_exchange_name(str(row.get('Exchange', '')).strip())})
                if ticker not in existing_stocks_map:
                    data['ticker'] = ticker
                    new_stock_data_list.append(Stock(**data))
                else:
                    stock_obj = existing_stocks_map[ticker]
                    has_changed = any(getattr(stock_obj, field) != new_value for field, new_value in data.items())
                    if has_changed:
                        for field, new_value in data.items(): setattr(stock_obj, field, new_value)
                        stocks_to_update.append(stock_obj)
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