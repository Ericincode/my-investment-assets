from django.core.management.base import BaseCommand
from stocks.models import Stock, HistoricalPrice
from django.db import transaction
import time

class Command(BaseCommand):
    help = '清空股票表和历史价格表的所有数据'

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true', help='确认删除所有数据')
        parser.add_argument('--debug', action='store_true', help='显示调试信息')

    def handle(self, *args, **options):
        debug = options.get('debug', False)
        
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
            
            # 获取当前数据统计
            if debug:
                self.stdout.write('📊 查询股票数量...')
            stock_count = Stock.objects.count()
            if debug:
                self.stdout.write(f'   股票数量: {stock_count:,}')
                self.stdout.write('📊 查询历史价格数量...')
            historical_count = HistoricalPrice.objects.count()
            if debug:
                self.stdout.write(f'   历史价格数量: {historical_count:,}')
            
            self.stdout.write(f'📊 当前数据统计:')
            self.stdout.write(f'  股票数量: {stock_count:,}')
            self.stdout.write(f'  历史价格记录: {historical_count:,}')
            
            if stock_count == 0 and historical_count == 0:
                self.stdout.write(self.style.SUCCESS('✅ 数据库已经是空的'))
                return
            
            # 安全确认
            if not options['confirm']:
                self.stdout.write(self.style.WARNING('\n⚠️  这将删除所有股票和历史价格数据！'))
                self.stdout.write(self.style.WARNING('💡 如要确认删除，请使用: python manage.py clear_stocks --confirm'))
                return
            
            # 最后确认
            self.stdout.write(self.style.WARNING(f'\n🚨 即将删除:'))
            self.stdout.write(f'   - {stock_count:,} 个股票记录')
            self.stdout.write(f'   - {historical_count:,} 条历史价格记录')
            
            start_time = time.time()
            
            # 先删除历史价格（外键约束）
            if historical_count > 0:
                self.stdout.write('\n🗑️  正在删除历史价格记录...')
                if debug:
                    self.stdout.write('   开始删除历史价格...')
                
                # 分批删除，避免内存问题
                batch_size = 10000
                total_deleted = 0
                while True:
                    if debug:
                        self.stdout.write(f'   删除批次，已删除: {total_deleted}')
                    
                    with transaction.atomic():
                        batch_ids = list(HistoricalPrice.objects.values_list('id', flat=True)[:batch_size])
                        if not batch_ids:
                            break
                        deleted_count = HistoricalPrice.objects.filter(id__in=batch_ids).delete()[0]
                        total_deleted += deleted_count
                        
                        if debug:
                            self.stdout.write(f'   批次删除: {deleted_count}')
                
                self.stdout.write(self.style.SUCCESS(f'✓ 已删除 {total_deleted:,} 条历史价格记录'))
            
            # 再删除股票
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