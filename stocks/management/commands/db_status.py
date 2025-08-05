from django.core.management.base import BaseCommand
from stocks.models import Stock, HistoricalPrice

class Command(BaseCommand):
    help = '打印 Stock 和 HistoricalPrice 表的字段及每个字段的非空非0数量'

    def handle(self, *args, **options):
        for model in [Stock, HistoricalPrice]:
            self.stdout.write(f"\n表名: {model._meta.db_table}")
            self.stdout.write("字段非空非0数量:")
            for field in model._meta.fields:
                fname = field.name
                # 构造过滤条件
                kwargs = {f"{fname}__isnull": False}
                # 对数值型字段再过滤非0
                if field.get_internal_type() in ['IntegerField', 'FloatField', 'DecimalField']:
                    kwargs[f"{fname}__gt"] = 0
                # 对字符串型字段过滤非空字符串
                elif field.get_internal_type() in ['CharField', 'TextField']:
                    kwargs[f"{fname}__gt"] = ''
                count = model.objects.filter(**kwargs).count()
                self.stdout.write(f"  - {fname}: {count}")