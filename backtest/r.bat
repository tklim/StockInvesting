rem python backtest_stocks.py --data-files data\META-3Y.csv --ga-search-preset focused  --reuse-tuned-params --pop_ranges 1  --gen_ranges 1

rem python backtest_stocks.py --data-files data\MSFT-4Y.csv --lookback-years 3 --offset-months 3 --short-ema-bounds 12 16 --long-ema-bounds 65 69 --rsi-oversold-bounds 26 28 --rsi-overbought-bounds 62 64 --stop-loss-bounds 13 15 --ga-search-preset focused --pop_ranges 4 --gen_ranges 2 --transition-policy grandfather

python backtest_stocks.py --data-files data\JPM-3Y.csv --lookback-years 1 --offset-months 6 --ga-search-preset grid --pop_ranges 4 --gen_ranges 2

rem python backtest_stocks.py --lookback-years 1 --offset-months 3 --pop_ranges 4 --gen_ranges 2 --ga-search-preset grid --strategy-profile generic --price-column "Adj Close" --reuse-tuned-params --data-file MSFT-3Y.csv --fund-group MSFT --ga-seed 999 --ga-warm-start