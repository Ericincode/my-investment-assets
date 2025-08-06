from django.core.management.base import BaseCommand
from stocks.models import Stock, HistoricalPrice
from django.db import transaction
import time

class Command(BaseCommand):
    help = '清空股票表和历史价格表的所有数据，或清空指定字段'

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true', help='确认删除所有数据')
        parser.add_argument('--debug', action='store_true', help='显示调试信息')
        parser.add_argument('--field', type=str, help='指定要清空的字段（仅限Stock表）')
        parser.add_argument('--table', type=str, choices=['stock', 'historical'], help='只清空指定表')
        parser.add_argument('--delete-special', action='store_true', help='删除特殊类型股票（如warrant、preferred等）')

    def handle(self, *args, **options):
        debug = options.get('debug', False)
        field = options.get('field')
        table = options.get('table')
        delete_special = options.get('delete_special', False)

        self.stdout.write(self.style.SUCCESS('=== 股票数据清理工具 ==='))

        if debug:
            self.stdout.write('🔍 调试模式开启')

        try:
            # 测试数据库连接
            if debug:
                self.stdout.write('📡 测试数据库连接...')
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute('SELECT 1')
                self.stdout.write('✅ 数据库连接正常')

            # 删除特殊类型股票
            if delete_special:
                self.stdout.write(self.style.WARNING('⚠️  即将删除特殊类型股票（如warrant、preferred等）'))
                if not options['confirm']:
                    self.stdout.write(self.style.WARNING('💡 如要确认操作，请加 --confirm'))
                    return
                keywords = [
                    'warrant', 'preferred', 'bond', 'note', 'unit', 'right', 'spac',
                    'etn', 'adr', 'depositary receipt', 'structured product', 'temp', 'test', 'swap',
                    'future', 'option'
                ]
                qs = Stock.objects.all()
                to_delete = []
                for stock in qs:
                    name = (stock.name or '').lower()
                    if any(kw in name for kw in keywords):
                        to_delete.append(stock)
                    if hasattr(stock, 'test_issue') and stock.test_issue == 'Y':
                        to_delete.append(stock)
                to_delete = list(set(to_delete))
                self.stdout.write(f'将删除 {len(to_delete)} 条特殊类型股票记录...')
                for stock in to_delete:
                    self.stdout.write(f'删除: {stock.ticker} - {stock.name}')
                    stock.delete()
                self.stdout.write(self.style.SUCCESS('删除完成。'))
                return

            # 清空某个字段
            if field:
                self.stdout.write(self.style.WARNING(f'⚠️  即将清空 Stock 表的字段: {field}'))
                if not options['confirm']:
                    self.stdout.write(self.style.WARNING('💡 如要确认操作，请加 --confirm'))
                    return
                start_time = time.time()
                with transaction.atomic():
                    updated = Stock.objects.update(**{field: None})
                elapsed = time.time() - start_time
                self.stdout.write(self.style.SUCCESS(f'✓ 已清空字段 {field}，共更新 {updated} 条记录，耗时 {elapsed:.2f} 秒'))
                return

            # 只清空某个表
            if table:
                if not options['confirm']:
                    self.stdout.write(self.style.WARNING(f'💡 如要确认删除，请加 --confirm'))
                    return
                start_time = time.time()
                if table == 'historical':
                    count = HistoricalPrice.objects.count()
                    self.stdout.write(f'🗑️  正在删除 HistoricalPrice 表的 {count} 条记录...')
                    with transaction.atomic():
                        HistoricalPrice.objects.all().delete()
                elif table == 'stock':
                    count = Stock.objects.count()
                    self.stdout.write(f'🗑️  正在删除 Stock 表的 {count} 条记录...')
                    with transaction.atomic():
                        Stock.objects.all().delete()
                elapsed = time.time() - start_time
                self.stdout.write(self.style.SUCCESS(f'✓ 已清空 {table} 表，耗时 {elapsed:.2f} 秒'))
                return

            # 默认：全部清空
            stock_count = Stock.objects.count()
            historical_count = HistoricalPrice.objects.count()
            self.stdout.write(f'📊 当前数据统计:')
            self.stdout.write(f'  股票数量: {stock_count:,}')
            self.stdout.write(f'  历史价格记录: {historical_count:,}')

            if stock_count == 0 and historical_count == 0:
                self.stdout.write(self.style.SUCCESS('✅ 数据库已经是空的'))
                return

            if not options['confirm']:
                self.stdout.write(self.style.WARNING('\n⚠️  这将删除所有股票和历史价格数据！'))
                self.stdout.write(self.style.WARNING('💡 如要确认删除，请使用: python manage.py clear_stocks --confirm'))
                return

            self.stdout.write(self.style.WARNING(f'\n🚨 即将删除所有数据...'))
            start_time = time.time()

            # 先删历史价格
            if historical_count > 0:
                self.stdout.write('🗑️  正在删除历史价格记录...')
                batch_size = 10000
                total_deleted = 0
                while True:
                    with transaction.atomic():
                        batch_ids = list(HistoricalPrice.objects.values_list('id', flat=True)[:batch_size])
                        if not batch_ids:
                            break
                        deleted_count = HistoricalPrice.objects.filter(id__in=batch_ids).delete()[0]
                        total_deleted += deleted_count
                self.stdout.write(self.style.SUCCESS(f'✓ 已删除 {total_deleted:,} 条历史价格记录'))

            # 再删股票
            if stock_count > 0:
                self.stdout.write('🗑️  正在删除股票记录...')
                with transaction.atomic():
                    deleted_stocks = Stock.objects.all().delete()
                    self.stdout.write(self.style.SUCCESS(f'✓ 已删除 {deleted_stocks[0]:,} 个股票记录'))

            elapsed_time = time.time() - start_time
            self.stdout.write(f'\n⏱️  删除耗时: {elapsed_time:.2f} 秒')

            # 验证删除结果
            remaining_stocks = Stock.objects.count()
            remaining_historical = HistoricalPrice.objects.count()
            self.stdout.write(f'\n📊 删除后统计:')
            self.stdout.write(f'  剩余股票: {remaining_stocks:,}')
            self.stdout.write(f'  剩余历史记录: {remaining_historical:,}')

            if remaining_stocks == 0 and remaining_historical == 0:
                self.stdout.write(self.style.SUCCESS('\n🎉 数据清理完成！'))
            else:
                self.stdout.write(self.style.WARNING('\n⚠️  清理可能不完整'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ 执行失败: {e}'))
            if debug:
                import traceback
                traceback.print_exc()
            return


# # 执行命令示例
# # 清空所有数据（股票和历史价格）python manage.py clear_stocks
#  --confirm
# # 只清空股票表
# python manage.py clear_stocks --table stock --confirm
# # 只清空历史价格表
# python manage.py clear_stocks --table historical --confirm
# # 只清空股票表的某个字段（如 name 字段）
# python manage.py clear_stocks --field name --confirm
# # 调试模式显示详细信息
# python manage.py clear_stocks --confirm --debug
# # 这样你可以灵活地清空整个表或指定字段，并获得详细反馈。