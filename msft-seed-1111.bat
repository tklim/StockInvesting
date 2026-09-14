python backtest/backtest_stocks.py --lookback-years 1 --offset-months 3 --pop_ranges 16 --gen_ranges 8 --ga-search-preset grid --strategy-profile generic --price-column "Adj Close" --reuse-tuned-params --data-file MSFT-3Y.csv --fund-group MSFT --ga-seed 1111 --transition-policy none

python backtest/backtest_stocks.py --lookback-years 1 --offset-months 3 --pop_ranges 16 --gen_ranges 8 --ga-search-preset grid --strategy-profile generic --price-column "Adj Close" --reuse-tuned-params --data-file MSFT-3Y.csv --fund-group MSFT --ga-seed 1111 --transition-policy grandfather

python backtest/backtest_stocks.py --lookback-years 1 --offset-months 3 --pop_ranges 16 --gen_ranges 8 --ga-search-preset grid --strategy-profile generic --price-column "Adj Close" --reuse-tuned-params --data-file MSFT-3Y.csv --fund-group MSFT --ga-seed 2222 --transition-policy none

python backtest/backtest_stocks.py --lookback-years 1 --offset-months 3 --pop_ranges 16 --gen_ranges 8 --ga-search-preset grid --strategy-profile generic --price-column "Adj Close" --reuse-tuned-params --data-file MSFT-3Y.csv --fund-group MSFT --ga-seed 2222 --transition-policy grandfather