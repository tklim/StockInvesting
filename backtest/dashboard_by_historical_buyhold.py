"""Build a historical buy-and-hold ranking dashboard.

The dashboard answers: "Which stocks had the strongest buy-and-hold return at
each point in the recent past?"  It uses full-ticker local price histories,
not strategy run-history rows, so every card is explicitly a price-derived
comparison.

The outer navigation selects how many years ago the window ended.  The inner
navigation selects the length of the buy-and-hold window ending at that point.
For example, ``1Y ago / 1Y horizon`` ends approximately one year before each
ticker's latest observation and begins one year before that endpoint.

Usage::

    python dashboard_by_historical_buyhold.py
    python dashboard_by_historical_buyhold.py --top-funds 5
    python dashboard_by_historical_buyhold.py --years-ago 1 2 --horizons 1 2 3
"""

import argparse
import html
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import dashboard_by_top_annualized as top_dashboard
from dashboard_render import format_pct


REPO_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = REPO_ROOT / "outputs" / "reports"
DEFAULT_DATA_DIR = REPO_ROOT / "data"
DEFAULT_OUTPUT_NAME = "dashboard_top_buyhold_historical.html"
DEFAULT_YEARS_AGO = (10, 5, 4, 3, 2, 1)
DEFAULT_HORIZONS = (1, 2, 3, 4, 5, 10, 15)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build historical buy-and-hold rankings from local full-ticker prices."
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Directory containing full-ticker CSV files (default: {DEFAULT_DATA_DIR}).",
    )
    parser.add_argument(
        "--output-name",
        default=DEFAULT_OUTPUT_NAME,
        help=f"HTML filename or path (default: {DEFAULT_OUTPUT_NAME}).",
    )
    parser.add_argument(
        "--years-ago",
        nargs="+",
        type=int,
        choices=(1, 2, 3, 4, 5, 10),
        default=DEFAULT_YEARS_AGO,
        metavar="YEARS",
        help="Outer age groups to render: 1Y to 5Y ago, plus 10Y ago.",
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        choices=(1, 2, 3, 4, 5, 10, 15),
        default=DEFAULT_HORIZONS,
        metavar="YEARS",
        help="Buy-and-hold horizons to render: 1Y to 5Y, plus 10Y and 15Y.",
    )
    parser.add_argument(
        "--top-funds",
        type=int,
        default=0,
        help="Number of stocks shown per panel. 0 = all eligible stocks (default).",
    )
    return parser.parse_args()


def _resolve_data_dir(data_dir=None):
    path = Path(data_dir or DEFAULT_DATA_DIR)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def _read_price_series(source):
    """Read one CSV into a clean Date/Price/RawPrice frame."""
    try:
        frame = pd.read_csv(source, low_memory=False)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return None
    if "Date" not in frame.columns:
        return None

    price_column = next(
        (column for column in ("NAV", "Adj Close", "Close") if column in frame.columns),
        None,
    )
    if price_column is None:
        return None

    raw_price = (
        pd.to_numeric(frame["Close"], errors="coerce")
        if "Close" in frame.columns
        else pd.Series(np.nan, index=frame.index)
    )
    values = pd.DataFrame(
        {
            "Date": pd.to_datetime(frame["Date"], errors="coerce"),
            "Price": pd.to_numeric(frame[price_column], errors="coerce"),
            "RawPrice": raw_price,
        }
    ).dropna(subset=["Date", "Price"])
    values = values[values["Price"] > 0].sort_values("Date")
    if values.empty:
        return None
    values = values.drop_duplicates("Date", keep="last").reset_index(drop=True)
    return price_column, values


def load_full_ticker_price_series(data_dir=None):
    """Load eligible full-ticker CSVs, excluding generated slice files."""
    data_dir = _resolve_data_dir(data_dir)
    series = []
    for source in sorted(data_dir.glob("*.csv")):
        # Files such as AAPL-3Y.csv are derived slices and must not be treated
        # as independent stock histories.
        if "-" in source.stem:
            continue
        loaded = _read_price_series(source)
        if loaded is None:
            continue
        price_column, values = loaded
        if len(values) < 2:
            continue
        series.append(
            {
                "ticker": source.stem,
                "data_file": source,
                "price_column": price_column,
                "values": values,
                "latest_date": values["Date"].iloc[-1],
            }
        )
    return series


def _historical_window(item, years_ago, horizon):
    """Build one historical window ending at ``years_ago`` before latest data."""
    values = item["values"]
    latest = item["latest_date"]
    target_end = latest - pd.DateOffset(years=years_ago)
    end_candidates = values[values["Date"] <= target_end]
    if end_candidates.empty:
        return None
    end_row = end_candidates.iloc[-1]

    target_start = end_row["Date"] - pd.DateOffset(years=horizon)
    start_candidates = values[
        (values["Date"] >= target_start) & (values["Date"] <= end_row["Date"])
    ]
    if len(start_candidates) < 2:
        return None
    start_row = start_candidates.iloc[0]
    elapsed_days = (end_row["Date"] - start_row["Date"]).days
    elapsed_years = elapsed_days / 365.25
    # Permit the first trading day after a calendar cutoff, but do not turn a
    # materially shorter history into a claimed horizon.
    if elapsed_years <= 0 or elapsed_days < horizon * 365.25 - 14:
        return None

    start_price = float(start_row["Price"])
    end_price = float(end_row["Price"])
    total_return = (end_price / start_price - 1.0) * 100.0
    annualized = ((end_price / start_price) ** (1.0 / elapsed_years) - 1.0) * 100.0
    return {
        "fund_label": item["ticker"],
        "fund_slice_label": item["ticker"],
        "_ticker": item["ticker"],
        "data_file": str(item["data_file"]),
        "price_column": item["price_column"],
        "data_start": start_row["Date"].strftime("%Y-%m-%d"),
        "data_end": end_row["Date"].strftime("%Y-%m-%d"),
        "backtest_start": start_row["Date"].strftime("%Y-%m-%d"),
        "backtest_end": end_row["Date"].strftime("%Y-%m-%d"),
        "anchor_date": latest.strftime("%Y-%m-%d"),
        "age_years": years_ago,
        "horizon_years": horizon,
        "_source_years": elapsed_years,
        "_total_return": total_return,
        "_top": annualized,
        "_buy_hold": annualized,
        "_adaptive": np.nan,
        "_data_derived": True,
    }


def build_historical_buy_hold_rows(data_dir=None, years_ago=1, horizon=1):
    """Return ranked price-derived rows for one age/horizon combination."""
    rows = []
    for item in load_full_ticker_price_series(data_dir):
        row = _historical_window(item, int(years_ago), int(horizon))
        if row is not None:
            rows.append(row)
    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values(["_top", "_ticker"], ascending=[False, True])
        .reset_index(drop=True)
    )


def load_historical_rankings(
    data_dir=None,
    years_ago=DEFAULT_YEARS_AGO,
    horizons=DEFAULT_HORIZONS,
    top_funds=0,
):
    """Build all requested age x horizon rankings."""
    data_dir = _resolve_data_dir(data_dir)
    series = load_full_ticker_price_series(data_dir)
    rankings = {}
    for age in sorted({int(value) for value in years_ago}, reverse=True):
        age_rankings = {}
        for horizon in sorted({int(value) for value in horizons}):
            rows = []
            for item in series:
                row = _historical_window(item, age, horizon)
                if row is not None:
                    rows.append(row)
            if rows:
                frame = (
                    pd.DataFrame(rows)
                    .sort_values(["_top", "_ticker"], ascending=[False, True])
                    .reset_index(drop=True)
                )
            else:
                frame = pd.DataFrame()
            eligible_count = len(frame)
            if top_funds and top_funds > 0:
                frame = frame.head(top_funds).reset_index(drop=True)
            age_rankings[horizon] = {
                "age_years": age,
                "horizon_years": horizon,
                "rows": frame,
                "eligible_count": eligible_count,
            }
        rankings[age] = age_rankings
    return rankings, len(series), data_dir


def _date_text(row, key):
    value = row.get(key, "")
    return "n/a" if value is None or pd.isna(value) else str(value)


def _build_card(row, rank):
    ticker = html.escape(str(row.get("_ticker", "Unknown")))
    annualized = top_dashboard.safe_float(row, "_top")
    value_class = "pos" if np.isfinite(annualized) and annualized >= 0 else "neg"
    chart = top_dashboard.simple_buy_hold_svg(row)
    chart_html = chart or (
        '<div class="chart-missing">Price chart unavailable for this historical window.</div>'
    )
    source_years = top_dashboard.safe_float(row, "_source_years")
    source_text = f"{source_years:.2f}Y" if np.isfinite(source_years) else "n/a"
    return f"""<article class="rank-card">
      <div class="card-head"><span class="rank">#{rank}</span><h2>{ticker}</h2>
        <div class="headline {value_class}"><small>Buy &amp; hold annualized</small><strong>{format_pct(annualized)}</strong></div>
      </div>
      <div class="chips">
        <span>Age <b>{int(row.get('age_years', 0))}Y ago</b></span>
        <span>Horizon <b>{int(row.get('horizon_years', 0))}Y</b></span>
        <span>Window <b>{html.escape(_date_text(row, 'data_start'))} → {html.escape(_date_text(row, 'data_end'))}</b></span>
        <span>Total return <b>{format_pct(row.get('_total_return'))}</b></span>
        <span>Actual years <b>{source_text}</b></span>
        <span>Anchor <b>{html.escape(_date_text(row, 'anchor_date'))}</b></span>
        <span>Derived from <b>local price data</b></span>
      </div>
      {chart_html}
    </article>"""


def _build_table(rows):
    table_rows = []
    for rank, (_, row) in enumerate(rows.iterrows(), 1):
        ticker = html.escape(str(row.get("_ticker", "Unknown")))
        annualized = top_dashboard.safe_float(row, "_top")
        total_return = top_dashboard.safe_float(row, "_total_return")
        actual_years = top_dashboard.safe_float(row, "_source_years")
        table_rows.append(
            f'''<tr><td class="table-rank" data-sort-value="{rank}">{rank}</td>
              <td data-sort-value="{ticker}"><b>{ticker}</b></td>
              <td class="{'neg' if np.isfinite(annualized) and annualized < 0 else 'pos'}" data-sort-value="{annualized if np.isfinite(annualized) else ''}">{format_pct(annualized)}</td>
              <td data-sort-value="{total_return if np.isfinite(total_return) else ''}">{format_pct(total_return)}</td>
              <td data-sort-value="{row.get('age_years', '')}">{int(row.get('age_years', 0))}Y ago</td>
              <td data-sort-value="{row.get('horizon_years', '')}">{int(row.get('horizon_years', 0))}Y</td>
              <td data-sort-value="{actual_years if np.isfinite(actual_years) else ''}">{actual_years:.2f}Y</td>
              <td data-sort-value="{html.escape(_date_text(row, 'data_end'))}">{html.escape(_date_text(row, 'data_start'))} → {html.escape(_date_text(row, 'data_end'))}</td></tr>'''
        )
    return f'''<div class="table-view" data-view-content="table" hidden><div class="table-wrap"><table class="ranking-table">
      <caption>Stock ranking — compact sortable view</caption><thead><tr>
      <th><button class="table-sort" data-sort-type="number">Rank</button></th><th><button class="table-sort" data-sort-type="text">Ticker</button></th>
      <th><button class="table-sort" data-sort-type="number" data-sort-desc="true">Buy &amp; hold ann.</button></th><th><button class="table-sort" data-sort-type="number">Total return</button></th>
      <th><button class="table-sort" data-sort-type="number">Age</button></th><th><button class="table-sort" data-sort-type="number">Horizon</button></th>
      <th><button class="table-sort" data-sort-type="number">Actual years</button></th><th><button class="table-sort" data-sort-type="text">Window</button></th>
      </tr></thead><tbody>{''.join(table_rows)}</tbody></table></div></div>'''


HISTORICAL_STYLE = """
  :root{--ink:#172033;--muted:#667085;--line:#dce2ea;--surface:#fff;--accent:#176b5b;--accent-soft:#e8f4f1;--bg:#f3f5f7;--pos:#12855b;--neg:#c9362c}
  *{box-sizing:border-box}[hidden]{display:none!important}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}
  header{position:sticky;top:0;z-index:10;padding:17px clamp(16px,4vw,48px) 13px;background:rgba(243,245,247,.96);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
  .back-link{display:inline-flex;margin-bottom:7px;color:var(--accent);font-size:.78rem;font-weight:800;text-decoration:none}.back-link:hover{text-decoration:underline}
  .header-tools{display:flex;justify-content:space-between;align-items:center;gap:10px}.theme-toggle{padding:7px 11px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:inherit;font-size:.76rem;font-weight:800;cursor:pointer}.theme-toggle:hover,.theme-toggle:focus-visible{border-color:#8fc5b6;color:var(--accent)}
  h1{margin:0 0 4px;font-size:clamp(1.4rem,3vw,2.05rem)}header p{margin:0;color:var(--muted);font-size:.88rem}.source{margin-top:5px;font-size:.76rem}
  .tabs,.horizon-tabs{display:flex;gap:7px;overflow-x:auto;padding-bottom:2px}.tabs{align-items:center;margin-top:12px}.horizon-tabs{margin:0 0 14px}
  .tab-label{flex:0 0 auto;margin-right:4px;color:var(--muted);font-size:.76rem;font-weight:850;letter-spacing:.055em;text-transform:uppercase;white-space:nowrap}
  .tab,.horizon-tab{flex:0 0 auto;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:inherit;font-size:.8rem;font-weight:750;cursor:pointer}
  .tab[aria-selected=true],.horizon-tab[aria-selected=true]{border-color:#8fc5b6;background:var(--accent-soft);color:var(--accent)}
  main{margin:0;padding:24px clamp(16px,4vw,48px) 56px}.group-note{margin:0 0 14px;color:var(--muted);font-size:.87rem}
  .ranking-grid{display:grid;gap:14px;grid-template-columns:repeat(2,minmax(0,1fr))}.rank-card{min-width:0;padding:15px;border:1px solid var(--line);border-radius:16px;background:var(--surface);box-shadow:0 7px 22px rgba(19,33,55,.05)}
  .card-head{display:flex;align-items:center;gap:10px}.rank{display:grid;place-items:center;min-width:36px;height:29px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:850}h2{margin:0;font-size:1.12rem;overflow-wrap:anywhere}
  .headline{margin-left:auto;text-align:right}.headline small{display:block;color:var(--muted);font-size:.66rem;text-transform:uppercase;letter-spacing:.05em}.headline strong{font-size:1.22rem}.headline.pos strong{color:var(--pos)}.headline.neg strong{color:var(--neg)}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin:11px 0}.chips span{padding:6px 8px;border-radius:8px;background:#f7f8fa;color:var(--muted);font-size:.75rem}.chips b{color:var(--ink)}
  .simple-chart{margin:0;padding:7px 9px 8px;border-radius:11px;background:#f8faf9}.simple-chart svg{display:block;width:100%;height:auto;max-height:150px}.chart-endpoints{display:grid;grid-template-columns:1fr 1fr;gap:14px;color:var(--muted);font-size:.73rem}.endpoint{display:grid;gap:2px}.endpoint-end{text-align:right}.endpoint-date{font-weight:750;color:var(--ink)}.endpoint small{margin-right:4px;font-size:.66em;text-transform:uppercase;letter-spacing:.035em}.endpoint strong{color:var(--ink)}
  .chart-missing,.empty{padding:34px 18px;border:1px dashed #bcc5cf;border-radius:14px;background:rgba(255,255,255,.55);color:var(--muted);text-align:center}
  .view-switch{display:flex;gap:7px;margin:0 0 12px}.view-toggle{padding:7px 10px;border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--ink);font:inherit;font-size:.76rem;font-weight:750;cursor:pointer}.view-toggle[aria-pressed="true"]{border-color:#8fc5b6;background:var(--accent-soft);color:var(--accent)}
  .table-wrap{overflow:visible;border:1px solid var(--line);border-radius:14px;background:var(--surface);box-shadow:0 7px 22px rgba(19,33,55,.05)}.ranking-table{width:100%;border-collapse:collapse;font-size:.78rem;white-space:nowrap}.ranking-table caption{padding:10px 12px;text-align:left;color:var(--muted);font-size:.75rem;font-weight:700}.ranking-table th{position:sticky;top:0;z-index:1;background:#f7f9fb;border-bottom:1px solid var(--line);text-align:left}.ranking-table td{padding:8px 10px;border-bottom:1px solid #edf0f4}.ranking-table tbody tr:last-child td{border-bottom:0}.ranking-table tbody tr:hover{background:#f8fafc}.ranking-table .table-rank{color:var(--muted);font-weight:800}.ranking-table .pos{color:var(--pos);font-weight:850}.ranking-table .neg{color:var(--neg);font-weight:850}.table-sort{width:100%;padding:8px 10px;border:0;background:transparent;color:var(--muted);font:inherit;font-weight:800;text-align:left;cursor:pointer}.table-sort:hover,.table-sort:focus-visible{color:var(--accent)}
  body.dark{--ink:#edf4fb;--muted:#a8b3c2;--line:#304253;--surface:#172333;--accent:#69d0b4;--accent-soft:#203d3d;--bg:#0d141c;--pos:#69d0b4;--neg:#ff8178}body.dark header{background:rgba(13,20,28,.96)}body.dark .chips span{background:#22303d}body.dark .rank-card,body.dark .table-wrap{box-shadow:0 8px 24px rgba(0,0,0,.24)}body.dark .simple-chart{background:#111b25}body.dark .ranking-table th{background:#202d39}body.dark .ranking-table tbody tr:hover{background:#22303d}
  dialog{width:calc(100vw - 24px);height:calc(100vh - 24px);max-width:none;max-height:none;padding:0;border:0;border-radius:16px;background:#111827;overflow:hidden}dialog::backdrop{background:rgba(3,8,18,.82)}.viewer-bar{position:absolute;inset:0 0 auto 0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;background:rgba(17,24,39,.9);color:#fff}.viewer-bar strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.controls{display:flex;gap:7px}.controls button{border:1px solid #667085;background:#263246;color:#fff;border-radius:8px;padding:7px 11px;cursor:pointer}.viewport{width:100%;height:100%;overflow:hidden;cursor:grab;touch-action:none}.viewport.dragging{cursor:grabbing}#viewerImage{position:absolute;left:50%;top:50%;max-width:none;transform-origin:center;user-select:none;pointer-events:none}
  @media(min-width:1500px){.ranking-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.rank-card{padding:12px}.chips{margin:8px 0;gap:5px}.chips span{padding:5px 7px;font-size:.72rem}.simple-chart svg{height:112px;max-height:112px}}@media(min-width:2100px){.ranking-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.simple-chart svg{height:96px;max-height:96px}}@media(max-width:760px){.ranking-grid{grid-template-columns:1fr}.chart-endpoints{grid-template-columns:1fr;gap:8px}.endpoint-end{text-align:left}}
"""


def render_historical_dashboard(
    rankings,
    output_path,
    data_dir,
    source_count,
    years_ago=DEFAULT_YEARS_AGO,
    horizons=DEFAULT_HORIZONS,
):
    """Render the nested age/horizon HTML dashboard."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ages = sorted({int(value) for value in years_ago}, reverse=True)
    selected_horizons = sorted({int(value) for value in horizons})
    age_tabs, age_panels = [], []

    for age_index, age in enumerate(ages):
        age_key = f"{age}y"
        age_selected = "true" if age_index == 0 else "false"
        age_tabs.append(
            f'<button class="tab" type="button" role="tab" id="age-tab-{age_key}" '
            f'data-age="{age_key}" aria-controls="age-panel-{age_key}" '
            f'aria-selected="{age_selected}">{age}Y ago</button>'
        )
        horizon_tabs, horizon_panels = [], []
        for horizon_index, horizon in enumerate(selected_horizons):
            horizon_key = f"{horizon}y"
            selected = "true" if horizon_index == 0 else "false"
            group = rankings.get(age, {}).get(horizon, {"rows": pd.DataFrame(), "eligible_count": 0})
            rows = group["rows"]
            horizon_tabs.append(
                f'<button class="horizon-tab" type="button" role="tab" '
                f'data-age="{age_key}" data-horizon="{horizon_key}" '
                f'aria-controls="horizon-panel-{age_key}-{horizon_key}" '
                f'aria-selected="{selected}">{horizon}Y horizon ({len(rows)})</button>'
            )
            if rows.empty:
                content = '<div class="empty">No eligible full-ticker price history covers this historical window.</div>'
            else:
                cards = "".join(_build_card(row, rank) for rank, (_, row) in enumerate(rows.iterrows(), 1))
                content = (
                    '<div class="view-switch" role="group" aria-label="Display mode">'
                    '<button class="view-toggle" type="button" data-view="chart" aria-pressed="true">Chart cards</button>'
                    '<button class="view-toggle" type="button" data-view="table" aria-pressed="false">Compact table</button></div>'
                    f'<div data-view-content="chart"><div class="ranking-grid">{cards}</div></div>{_build_table(rows)}'
                )
            horizon_panels.append(
                f'<div class="horizon-panel" role="tabpanel" id="horizon-panel-{age_key}-{horizon_key}" '
                f'data-age-panel="{age_key}" data-horizon-panel="{horizon_key}" '
                f'{"" if horizon_index == 0 else "hidden"}>{content}</div>'
            )
        age_panels.append(
            f'<section class="age-panel" role="tabpanel" id="age-panel-{age_key}" '
            f'data-age-panel-container="{age_key}" {"" if age_index == 0 else "hidden"}>'
            f'<p class="group-note">Historical buy-and-hold ranking ending approximately {age} year(s) before each stock\'s latest observation. '
            f'{source_count} full-ticker source file(s) were inspected.</p>'
            f'<nav class="horizon-tabs" role="tablist" aria-label="Buy-and-hold horizon for {age}Y ago">'
            f'{"".join(horizon_tabs)}</nav>{"".join(horizon_panels)}</section>'
        )

    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Historical Buy &amp; Hold Ranking</title><style>{HISTORICAL_STYLE}</style></head><body>
<header><div class="header-tools"><a class="back-link" href="dashboard.html">← Master dashboard</a><button class="theme-toggle" id="themeToggle" type="button">Dark mode</button></div><h1>Historical Buy &amp; Hold Ranking</h1>
<p>Price-derived stock rankings by historical endpoint and holding horizon · generated {generated_at}</p>
<p class="source">Source: full-ticker local price data in <code>{html.escape(str(data_dir))}</code> · {source_count} source file(s) inspected. No strategy run-history rows are used.</p>
<nav class="tabs" role="tablist" aria-label="Years ago"><span class="tab-label">Turn Back The Clock</span>{"".join(age_tabs)}</nav></header><main>{"".join(age_panels)}</main>
<dialog id="viewer"><div class="viewer-bar"><strong id="viewerTitle">Chart</strong><div class="controls"><button id="zoomOut" type="button">−</button><button id="resetZoom" type="button">Reset</button><button id="zoomIn" type="button">+</button><button id="closeViewer" type="button">Close</button></div></div><div class="viewport" id="viewport"><img id="viewerImage" alt=""></div></dialog>
<script>
const ageTabs=[...document.querySelectorAll('.tab')],agePanels=[...document.querySelectorAll('.age-panel')];
function hashFor(age,horizon){{return `#${{age}}/${{horizon}}`;}}
function currentHorizon(age){{const tabs=[...document.querySelectorAll(`.horizon-tab[data-age="${{age}}"]`)];return tabs.find(tab=>tab.getAttribute('aria-selected')==='true')?.dataset.horizon||tabs[0]?.dataset.horizon||'1y';}}
function selectHorizon(age,horizon,focus=false,updateHash=true){{const tabs=[...document.querySelectorAll(`.horizon-tab[data-age="${{age}}"]`)];const panels=[...document.querySelectorAll(`#age-panel-${{age}} .horizon-panel`)];if(!tabs.some(tab=>tab.dataset.horizon===horizon))horizon=tabs[0]?.dataset.horizon||'1y';tabs.forEach(tab=>{{const active=tab.dataset.horizon===horizon;tab.setAttribute('aria-selected',String(active));if(active&&focus)tab.focus();}});panels.forEach(panel=>panel.hidden=panel.dataset.horizonPanel!==horizon);if(updateHash&&history.replaceState)history.replaceState(null,'',hashFor(age,horizon));}}
function selectAge(age,focus=false,horizon=null,updateHash=true){{if(!ageTabs.some(tab=>tab.dataset.age===age))age=ageTabs[0]?.dataset.age||'1y';ageTabs.forEach(tab=>{{const active=tab.dataset.age===age;tab.setAttribute('aria-selected',String(active));if(active&&focus)tab.focus();}});agePanels.forEach(panel=>panel.hidden=panel.dataset.agePanelContainer!==age);selectHorizon(age,horizon||currentHorizon(age),false,updateHash);}}
ageTabs.forEach(tab=>tab.addEventListener('click',()=>selectAge(tab.dataset.age)));document.querySelector('.tabs').addEventListener('keydown',event=>{{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const current=ageTabs.findIndex(tab=>tab.getAttribute('aria-selected')==='true');const next=event.key==='Home'?0:event.key==='End'?ageTabs.length-1:event.key==='ArrowRight'?(current+1)%ageTabs.length:(current-1+ageTabs.length)%ageTabs.length;selectAge(ageTabs[next].dataset.age,true);}});
document.querySelectorAll('.horizon-tab').forEach(tab=>tab.addEventListener('click',()=>selectHorizon(tab.dataset.age,tab.dataset.horizon)));document.querySelectorAll('.horizon-tabs').forEach(nav=>nav.addEventListener('keydown',event=>{{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const tabs=[...nav.querySelectorAll('.horizon-tab')],current=tabs.findIndex(tab=>tab.getAttribute('aria-selected')==='true');const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:event.key==='ArrowRight'?(current+1)%tabs.length:(current-1+tabs.length)%tabs.length;selectHorizon(tabs[next].dataset.age,tabs[next].dataset.horizon,true);}}));
const requested=location.hash.slice(1).split('/');selectAge(requested[0]||ageTabs[0]?.dataset.age||'1y',false,requested[1]||null,false);window.addEventListener('hashchange',()=>{{const parts=location.hash.slice(1).split('/');selectAge(parts[0]||ageTabs[0]?.dataset.age||'1y',false,parts[1]||null,false);}});
const themeToggle=document.getElementById('themeToggle');function setTheme(dark){{document.body.classList.toggle('dark',dark);themeToggle.textContent=dark?'Light mode':'Dark mode';themeToggle.setAttribute('aria-pressed',String(dark));try{{localStorage.setItem('historical-buyhold-theme',dark?'dark':'light');}}catch(error){{}}}}let darkTheme=false;try{{darkTheme=localStorage.getItem('historical-buyhold-theme')==='dark';}}catch(error){{}}setTheme(darkTheme);themeToggle.addEventListener('click',()=>setTheme(!document.body.classList.contains('dark')));
document.querySelectorAll('.view-toggle').forEach(button=>button.addEventListener('click',()=>{{const panel=button.closest('.horizon-panel'),view=button.dataset.view;panel.querySelectorAll('.view-toggle').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));panel.querySelectorAll('[data-view-content]').forEach(item=>item.hidden=item.dataset.viewContent!==view);}}));
document.querySelectorAll('.ranking-table').forEach(table=>table.querySelectorAll('.table-sort').forEach((button,index)=>button.addEventListener('click',()=>{{const body=table.tBodies[0],type=button.dataset.sortType;const descending=button.dataset.sortedDesc==='true'?false:button.dataset.sortDesc==='true';const rows=[...body.rows].sort((left,right)=>{{const a=left.cells[index].dataset.sortValue||'',b=right.cells[index].dataset.sortValue||'';const result=type==='number'?(Number(a||'-Infinity')-Number(b||'-Infinity')):a.localeCompare(b);return descending?-result:result;}});body.append(...rows);[...body.rows].forEach((row,rank)=>{{row.cells[0].textContent=rank+1;row.cells[0].dataset.sortValue=rank+1;}});table.querySelectorAll('.table-sort').forEach(item=>{{item.dataset.sortedDesc='';item.removeAttribute('aria-sort');}});button.dataset.sortedDesc=String(descending);button.setAttribute('aria-sort',descending?'descending':'ascending');}})));
const viewer=document.getElementById('viewer'),viewport=document.getElementById('viewport'),image=document.getElementById('viewerImage');let scale=1,x=0,y=0,drag=false,startX=0,startY=0;function render(){{image.style.transform=`translate(calc(-50% + ${{x}}px),calc(-50% + ${{y}}px)) scale(${{scale}})`;}}function fit(){{if(!image.naturalWidth)return;scale=Math.min(1,(viewport.clientWidth-36)/image.naturalWidth,(viewport.clientHeight-86)/image.naturalHeight);x=0;y=0;render();}}function zoom(factor){{scale=Math.min(8,Math.max(.5,scale*factor));render();}}image.addEventListener('load',fit);document.querySelectorAll('.simple-chart').forEach(chart=>chart.addEventListener('click',()=>{{const svg=chart.querySelector('svg');if(!svg)return;const blob=new Blob([svg.outerHTML],{{type:'image/svg+xml'}});image.src=URL.createObjectURL(blob);document.getElementById('viewerTitle').textContent=chart.closest('.rank-card')?.querySelector('h2')?.textContent||'Chart';viewer.showModal();}}));document.getElementById('closeViewer').onclick=()=>viewer.close();document.getElementById('zoomIn').onclick=()=>zoom(1.25);document.getElementById('zoomOut').onclick=()=>zoom(.8);document.getElementById('resetZoom').onclick=fit;viewport.addEventListener('wheel',event=>{{event.preventDefault();zoom(event.deltaY<0?1.15:.87);}},{{passive:false}});viewport.addEventListener('pointerdown',event=>{{drag=true;startX=event.clientX-x;startY=event.clientY-y;viewport.setPointerCapture(event.pointerId);viewport.classList.add('dragging');}});viewport.addEventListener('pointermove',event=>{{if(!drag)return;x=event.clientX-startX;y=event.clientY-startY;render();}});viewport.addEventListener('pointerup',()=>{{drag=false;viewport.classList.remove('dragging');}});viewer.addEventListener('click',event=>{{if(event.target===viewer)viewer.close();}});
</script></body></html>'''
    # Inline SVG cards are composed from reusable multi-line templates. Strip
    # trailing spaces from every generated line so publication validation stays
    # clean without changing the rendered document.
    page = "\n".join(line.rstrip() for line in page.splitlines()) + "\n"
    output_path.write_text(page, encoding="utf-8")
    return output_path


def main():
    args = parse_args()
    data_dir = _resolve_data_dir(args.data_dir)
    output_path = Path(args.output_name)
    if not output_path.is_absolute():
        output_path = REPORTS_DIR / output_path
    rankings, source_count, data_dir = load_historical_rankings(
        data_dir,
        years_ago=args.years_ago,
        horizons=args.horizons,
        top_funds=args.top_funds,
    )
    render_historical_dashboard(
        rankings,
        output_path,
        data_dir,
        source_count,
        years_ago=args.years_ago,
        horizons=args.horizons,
    )
    panel_count = len(args.years_ago) * len(args.horizons)
    populated = sum(
        1
        for age in rankings.values()
        for group in age.values()
        if not group["rows"].empty
    )
    print(f"Inspected {source_count} full-ticker source file(s).")
    print(f"Rendered {populated} populated panel(s) out of {panel_count}.")
    print(f"Dashboard saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
