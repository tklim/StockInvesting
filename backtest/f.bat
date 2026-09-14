REM # 1. Refresh local price data
REM .\down.bat

C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  final_backtest_from_summary.py
C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  dashboard_by_top_annualized.py --basis buy-hold --derive-buyhold-horizons 20y 10y 5y 4y 3y 2y 1y
C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  dashboard_by_historical_buyhold.py

REM TOP10-SELECTION

REM # 2. Generate the latest top-10 selection
C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  dashboard_stock_selection.py
REM # 3. Run the one-year selection backtest
C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  dashboard_stock_selection_backtest.py
REM # 4. Run score statistical analysis
C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  dashboard_stock_selection_score_analysis.py

C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  dashboard_by_top_annualized.py --top-fund 0


C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe dashboard_by_excess_annualized.py --top-fund 0


C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  dashboard_master.py
C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  dashboard_render.py

C:\Users\tklim\AppData\Local\Programs\Python\Python312\python.exe  publish_reports_site.py --reports-dir outputs\reports --charts-dir outputs\charts --site-dir C:\tmp\stockinvesting-pages-site

REM CLEAN UP 
python cleanup_outputs.py final-charts --apply --verbose

python cleanup_outputs.py non-final-charts --apply --verbose
