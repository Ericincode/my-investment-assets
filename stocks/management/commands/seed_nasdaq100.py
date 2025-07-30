import pandas as pd
from django.core.management.base import BaseCommand
from stocks.models import Stock

class Command(BaseCommand):
    help = 'Seeds the database with the list of NASDAQ 100 tickers from Wikipedia.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting to seed NASDAQ 100 tickers...'))
        
        # The URL for the Wikipedia page listing NASDAQ-100 components
        url = 'https://en.wikipedia.org/wiki/NASDAQ-100'
        
        try:
            # pandas.read_html reads HTML tables into a list of DataFrame objects
            tables = pd.read_html(url)
            
            # NOTE: We need to find the correct table on the page.
            # This can change if Wikipedia updates its page structure.
            # We look for a table that has a "Ticker" column.
            nasdaq_table = None
            for table in tables:
                if 'Ticker' in table.columns:
                    nasdaq_table = table
                    break
            
            if nasdaq_table is None:
                self.stdout.write(self.style.ERROR('Could not find the NASDAQ 100 components table on the Wikipedia page.'))
                return

            # Get the list of tickers from the 'Ticker' column
            tickers = nasdaq_table['Ticker'].tolist()

            # --- IMPORTANT MODIFICATION FOR DEVELOPMENT ---
            # To avoid hitting the API limit on our first run, let's only seed the first 5 stocks.
            # In a real production setup, you would remove this line to seed all 100+.


            count = 0
            for ticker in tickers:

                stock, created = Stock.objects.get_or_create(ticker=ticker)
                if created:
                    count += 1
                    self.stdout.write(f'  CREATED new entry for {ticker}')
                # ADD THIS ELSE BLOCK
                else:
                    self.stdout.write(f'  SKIPPED {ticker} (already exists)')

            self.stdout.write(self.style.SUCCESS(f'Operation complete. Created {count} new stock entries.'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'An error occurred: {e}'))