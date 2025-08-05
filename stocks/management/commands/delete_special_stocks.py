from stocks.models import Stock

# 关键词列表（全部小写）
keywords = [
    'warrant', 'preferred', 'bond', 'note', 'unit', 'right', 'spac',
    'etn', 'adr', 'depositary receipt', 'structured product', 'temp', 'test', 'swap',
    'future', 'option'
]

# 查询并删除
qs = Stock.objects.all()
to_delete = []
for stock in qs:
    name = (stock.name or '').lower()
    if any(kw in name for kw in keywords):
        to_delete.append(stock)
    if hasattr(stock, 'test_issue') and stock.test_issue == 'Y':
        to_delete.append(stock)

# 去重
to_delete = list(set(to_delete))
print(f'将删除 {len(to_delete)} 条特殊类型股票记录...')
for stock in to_delete:
    print(f'删除: {stock.ticker} - {stock.name}')
    stock.delete()

print('删除完成。')

# python manage.py shell < stocks/management/commands/delete_special_stocks.py