"""Build a master report and one comprehensive detail page per ticker."""

import html
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import dashboard_by_excess_annualized as excess_dashboard
import dashboard_by_top_annualized as top_dashboard
import dashboard_stock_selection as selection_dashboard
from common import fund_group_from_label, sanitize_fund_label


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
REPORTS_DIR = OUTPUTS_DIR / "reports"
FUND_REPORTS_DIR = REPORTS_DIR / "funds"
HISTORY_FILE = OUTPUTS_DIR / "tunings" / "backtest_run_history.csv"

# External dashboard links. Update this one value when the Vercel production URL changes.
COMPANY_RESEARCH_URL = "https://stock-investing-avpuzw7i0-tklims-projects.vercel.app/"


def safe_float(row, key, default=np.nan):
    value = row.get(key, default)
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pct(row, key, signed=True):
    value = safe_float(row, key)
    if not np.isfinite(value):
        return "n/a"
    return f"{value:+.2f}%" if signed else f"{value:.2f}%"


def numeric_attr(row, key):
    value = safe_float(row, key)
    return "" if not np.isfinite(value) else f"{value:.12g}"


def usd(row, key):
    value = safe_float(row, key)
    return "n/a" if not np.isfinite(value) else f"${value:,.2f}"


def value_class(row, key):
    """CSS class suffix that colors a metric by its sign."""
    value = safe_float(row, key)
    if not np.isfinite(value):
        return ""
    return " pos" if value >= 0 else " neg"


def relative_url(path, from_dir):
    return os.path.relpath(Path(path), from_dir).replace(os.sep, "/")


def fund_slug(label):
    return sanitize_fund_label(fund_group_from_label(label))


def is_blank(value):
    return value is None or pd.isna(value) or not str(value).strip()


def hydrate_best_excess_metadata(results):
    """Add source-chart metadata, including support for older summary snapshots."""
    hydrated = [dict(row) for row in results]
    if not HISTORY_FILE.exists():
        return hydrated

    history = pd.read_csv(HISTORY_FILE, low_memory=False)
    if "run_id" not in history.columns:
        return hydrated
    history_by_run_id = {
        str(row["run_id"]): row
        for _, row in history.iterrows()
        if not is_blank(row.get("run_id"))
    }

    for row in hydrated:
        if row.get("status") != "completed":
            continue
        run_id = row.get("best_excess_run_id")
        if is_blank(run_id):
            run_id = row.get("source_run_id")
            row["best_excess_run_id"] = run_id
        history_row = history_by_run_id.get(str(run_id))
        if history_row is None:
            continue

        if is_blank(row.get("best_excess_annualized_return_pct")):
            row["best_excess_annualized_return_pct"] = history_row.get(
                "excess_annualized_return_pct", ""
            )
        if is_blank(row.get("best_excess_chart_file")):
            row["best_excess_chart_file"] = history_row.get("chart_file", "")
        if is_blank(row.get("best_excess_data_end")):
            data_end = history_row.get("data_end", "")
            row["best_excess_data_end"] = (
                history_row.get("backtest_end", "") if is_blank(data_end) else data_end
            )
    return hydrated


def hydrate_top_annualized_metadata(results, history_file=HISTORY_FILE):
    """Attach combined, strategy, and buy-and-hold historical leaders."""
    hydrated = [dict(row) for row in results]
    if not Path(history_file).exists():
        return hydrated

    rankings = (
        ("best", "top_annualized"),
        ("strategy", "top_strategy_annualized"),
        ("buy-hold", "top_buy_hold_annualized"),
    )
    for basis, prefix in rankings:
        ranked, _, _ = top_dashboard.load_ranked_history(
            Path(history_file), basis, 0, False
        )
        winners = {
            str(winner["_ticker"]): winner
            for _, winner in ranked.iterrows()
        }
        for row in hydrated:
            ticker = fund_group_from_label(row.get("fund_label", ""))
            winner = winners.get(ticker)
            if winner is None:
                continue
            row[f"{prefix}_return_pct"] = winner.get("_top", "")
            row[f"{prefix}_winner"] = winner.get("_winner", "")
            row[f"{prefix}_run_id"] = winner.get("run_id", "")
            row[f"{prefix}_data_end"] = winner.get(
                "backtest_end", winner.get("data_end", "")
            )
    return hydrated


def latest_stock_price_from_row(row):
    """Return the latest price/date, falling back to the row's source CSV."""
    stored_price = safe_float(row, "latest_stock_price")
    stored_date = str(row.get("latest_stock_price_date", "") or "").strip()
    if np.isfinite(stored_price):
        return stored_price, stored_date or str(row.get("latest_data_end", "") or "")

    data_file = Path(str(row.get("data_file", "") or ""))
    price_column = str(row.get("price_column", "") or "Adj Close")
    if not data_file.exists():
        return np.nan, ""

    try:
        frame = pd.read_csv(data_file, usecols=["Date", price_column])
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame[price_column] = pd.to_numeric(frame[price_column], errors="coerce")
        frame = frame.dropna(subset=["Date", price_column])
        cutoff = pd.to_datetime(row.get("latest_data_end"), errors="coerce")
        if not pd.isna(cutoff):
            frame = frame[frame["Date"] <= cutoff]
        if frame.empty:
            return np.nan, ""
        latest = frame.sort_values("Date").iloc[-1]
        return float(latest[price_column]), latest["Date"].strftime("%Y-%m-%d")
    except (OSError, ValueError, KeyError, pd.errors.ParserError):
        return np.nan, ""


def hydrate_latest_stock_prices(results):
    hydrated = [dict(row) for row in results]
    for row in hydrated:
        price, price_date = latest_stock_price_from_row(row)
        row["latest_stock_price"] = price if np.isfinite(price) else ""
        row["latest_stock_price_date"] = price_date
    return hydrated


def hydrate_master_metadata(results):
    hydrated = hydrate_best_excess_metadata(results)
    hydrated = hydrate_top_annualized_metadata(hydrated)
    return hydrate_latest_stock_prices(hydrated)


def refresh_companion_dashboards(summary_path=None):
    """Refresh the history-ranked and stock-selection companion dashboards."""
    generated = {}
    warnings = []
    if not HISTORY_FILE.exists():
        warnings.append(f"Run history not found: {HISTORY_FILE}")
        try:
            selection_result = selection_dashboard.build_selection_dashboard(
                summary_file=str(summary_path or "")
            )
            generated["selection"] = selection_result["html"]
            generated["selection_csv"] = selection_result["csv"]
        except Exception as exc:
            warnings.append(f"Long-term stock selection dashboard: {exc}")
        return generated, warnings

    try:
        horizon_rankings, considered = excess_dashboard.load_excess_horizon_rankings(
            HISTORY_FILE, excess_dashboard.HISTORY_COLUMNS, 0
        )
        ranked = horizon_rankings["mixed"]["views"]["all"]
        if not ranked.empty:
            output = REPORTS_DIR / "dashboard_excess_annualized.html"
            excess_dashboard.render_excess_horizon_dashboard(
                horizon_rankings, output, HISTORY_FILE, considered,
                excess_dashboard.HISTORY_COLUMNS,
            )
            generated["excess"] = output
    except Exception as exc:
        warnings.append(f"Excess annualized dashboard: {exc}")

    try:
        ranked, considered, tickers = top_dashboard.load_ranked_history(
            HISTORY_FILE, "best", 0, False
        )
        if not ranked.empty:
            output = REPORTS_DIR / "dashboard_top_annualized.html"
            top_dashboard.render_html(
                ranked,
                top_dashboard.build_spec("best", False),
                output,
                HISTORY_FILE,
                "ranked by the best of strategy or buy & hold · slices pooled per ticker",
                f"ranking computed from {considered} run(s) across {tickers} ticker(s) "
                "during the master-dashboard refresh.",
                REPORTS_DIR,
            )
            generated["top"] = output
    except Exception as exc:
        warnings.append(f"Top annualized dashboard: {exc}")

    # The buy-and-hold view has horizon tabs, so it cannot use the standard
    # card renderer above.  Refresh it here as well: otherwise running the
    # normal master-dashboard workflow leaves this companion report stale when
    # a new ticker is added to run history.
    try:
        horizon_rankings, considered = top_dashboard.load_buy_hold_horizon_rankings(
            HISTORY_FILE, 0
        )
        output = REPORTS_DIR / "dashboard_top_annualized_buyhold.html"
        top_dashboard.render_buy_hold_horizon_dashboard(
            horizon_rankings, output, HISTORY_FILE, considered
        )
        generated["buy_hold"] = output
    except Exception as exc:
        warnings.append(f"Buy-and-hold annualized dashboard: {exc}")

    try:
        selection_result = selection_dashboard.build_selection_dashboard(
            summary_file=str(summary_path or "")
        )
        generated["selection"] = selection_result["html"]
        generated["selection_csv"] = selection_result["csv"]
    except Exception as exc:
        warnings.append(f"Long-term stock selection dashboard: {exc}")
    return generated, warnings


def chart_section(row, key, title, description, unavailable_run_id=""):
    chart_value = row.get(key, "")
    chart_path = Path(str(chart_value)) if not is_blank(chart_value) else None
    if chart_path is None or not chart_path.is_file():
        run_detail = (
            f" Run ID: {html.escape(str(unavailable_run_id))}."
            if not is_blank(unavailable_run_id)
            else ""
        )
        return (
            '<section class="chart-panel missing">'
            f"<h2>{html.escape(title)}</h2><p>Chart unavailable.{run_detail}</p></section>"
        )
    src = html.escape(relative_url(chart_path, FUND_REPORTS_DIR), quote=True)
    label = html.escape(str(row.get("fund_label", "fund")))
    return f"""
      <section class="chart-panel">
        <div class="section-heading">
          <div><p class="eyebrow">Chart view</p><h2>{html.escape(title)}</h2></div>
          <p>{html.escape(description)}</p>
        </div>
        <button class="chart-button" type="button" data-src="{src}"
                data-title="{label} — {html.escape(title)}"
                aria-label="Open {html.escape(title)} chart for {label}">
          <img src="{src}" alt="{label} {html.escape(title)} chart" loading="lazy">
          <span>Open chart</span>
        </button>
      </section>
    """


def write_fund_dashboard(row, summary_path):
    FUND_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    label = fund_group_from_label(row.get("fund_label", "Unknown"))
    label_html = html.escape(label)
    data_file = Path(str(row.get("data_file", ""))).name
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chart_updated_at = row.get("run_completed_at", "")
    if is_blank(chart_updated_at):
        chart_updated_at = generated_at
    historical_data_end = row.get("data_end", "n/a")
    if is_blank(historical_data_end):
        historical_data_end = "n/a"
    latest_data_end = row.get("latest_data_end", "n/a")
    if is_blank(latest_data_end):
        latest_data_end = "n/a"
    signal = html.escape(str(row.get("ga_signal", "n/a")))
    signal_class = "positive" if "BUY" in signal.upper() else "neutral"
    last_trade_action = str(row.get("last_trade_action", "n/a"))
    last_trade_class = (
        "buy" if "BUY" in last_trade_action.upper()
        else "sell" if "SELL" in last_trade_action.upper()
        else "unknown"
    )
    detail_path = FUND_REPORTS_DIR / f"{fund_slug(label)}.html"

    dashboard = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{label_html} Backtest Detail</title>
  <style>
    :root{{--ink:#152033;--muted:#687386;--line:#dce3e9;--paper:#fff;--bg:#f4f6f5;
      --green:#0f6e5c;--green-soft:#e6f3ef;--navy:#172b4d}}
    *{{box-sizing:border-box}}
    body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}}
    a{{color:inherit}}
    .topbar{{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;
      gap:18px;padding:14px clamp(18px,4vw,56px);background:rgba(244,246,245,.94);
      border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}}
    .back{{text-decoration:none;font-weight:750;color:var(--green)}}
    .topbar nav{{display:flex;gap:14px;flex-wrap:wrap}}
    .topbar nav a{{font-size:.86rem;color:var(--muted);text-decoration:none}}
    main{{width:min(1500px,calc(100% - 32px));margin:18px auto 64px}}
    .hero{{display:grid;grid-template-columns:1.3fr .7fr;gap:18px;padding:clamp(18px,2.8vw,30px);
      border-radius:20px;background:linear-gradient(135deg,#142b46,#0f6255);color:#fff;
      box-shadow:0 20px 50px rgba(17,42,59,.16)}}
    .eyebrow{{margin:0 0 8px;text-transform:uppercase;letter-spacing:.12em;font-size:.72rem;font-weight:800;color:#72d2bb}}
    h1{{margin:0;font-size:clamp(1.45rem,2.5vw,2.25rem);letter-spacing:-.035em}}
    .hero-copy{{margin:8px 0 0;color:#d5e4e5;max-width:720px;font-size:.9rem;line-height:1.45}}
    .signal{{justify-self:end;align-self:start;padding:10px 14px;border-radius:13px;background:rgba(255,255,255,.12);text-align:right}}
    .signal span{{display:block;color:#c8d9de;font-size:.72rem;text-transform:uppercase;letter-spacing:.08em}}
    .signal strong{{display:block;margin-top:4px;font-size:1.25rem}}
    .signal.positive strong{{color:#8ee3bd}} .signal.neutral strong{{color:#ffd28d}}
    .metrics{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:18px 0 28px}}
    .metric{{padding:18px;border:1px solid var(--line);border-radius:16px;background:var(--paper)}}
    .metric span{{display:block;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}}
    .metric strong{{display:block;margin-top:6px;font-size:clamp(1rem,2vw,1.4rem)}}
    .metric strong.last-trade.buy{{color:#16834b}}
    .metric strong.last-trade.sell{{color:#d45b5b}}
    .metric strong.last-trade.unknown{{color:var(--muted)}}
    .compare{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:28px}}
    .compare-card{{padding:20px;border:1px solid var(--line);border-radius:18px;background:var(--paper)}}
    .compare-card h2{{margin:0 0 12px;font-size:1.05rem}}
    .compare dl{{display:grid;grid-template-columns:1fr auto;gap:8px 20px;margin:0}}
    .compare dt{{color:var(--muted)}} .compare dd{{margin:0;font-weight:700;text-align:right}}
    .charts-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,500px),1fr));
      align-items:start;gap:18px;margin-top:22px}}
    .chart-panel{{min-width:0;padding:20px;border:1px solid var(--line);border-radius:22px;background:var(--paper);
      box-shadow:0 10px 28px rgba(28,45,61,.05)}}
    .section-heading{{display:flex;justify-content:space-between;align-items:end;gap:24px;margin-bottom:16px}}
    .section-heading h2{{margin:0;font-size:1.45rem}} .section-heading>p{{margin:0;color:var(--muted);max-width:620px}}
    .charts-grid .section-heading{{display:block}} .charts-grid .section-heading>p{{margin-top:8px}}
    .chart-button{{position:relative;display:block;width:100%;padding:0;border:0;border-radius:14px;overflow:hidden;background:#e7ebee;cursor:zoom-in}}
    .chart-button img{{display:block;width:100%;height:auto}}
    .chart-button span{{position:absolute;right:12px;bottom:12px;padding:8px 11px;border-radius:8px;color:#fff;
      background:rgba(15,29,43,.82);opacity:0;transition:.18s}}
    .chart-button:hover span,.chart-button:focus-visible span{{opacity:1}}
    footer{{margin-top:24px;color:var(--muted);font-size:.8rem}}
    dialog{{width:calc(100vw - 20px);height:calc(100vh - 20px);max-width:none;max-height:none;border:0;
      border-radius:16px;padding:0;background:#101923;overflow:hidden}}
    dialog::backdrop{{background:rgba(4,10,18,.86)}}
    .viewer-bar{{position:relative;z-index:2;display:flex;justify-content:space-between;
      align-items:center;padding:11px 15px;color:#fff;background:rgba(16,25,35,.92)}}
    .viewer-bar button{{padding:7px 11px;border:1px solid #647181;border-radius:8px;background:#233242;color:#fff}}
    dialog{{display:grid;grid-template-rows:auto minmax(0,1fr)}}
    .viewport{{min-width:0;min-height:0;display:grid;place-items:center;overflow:hidden;padding:12px}}
    #viewerImage{{display:block;max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain}}
    @media(max-width:900px){{.hero{{grid-template-columns:1fr}}.signal{{justify-self:start;text-align:left}}
      .metrics{{grid-template-columns:repeat(2,1fr)}}.compare{{grid-template-columns:1fr}}
      .section-heading{{display:block}}.section-heading>p{{margin-top:8px}}}}
  </style>
</head>
<body>
  <header class="topbar">
    <a class="back" href="../dashboard.html">← Master dashboard</a>
    <nav>
      <a href="../dashboard_latest.html">Latest ranking</a>
      <a href="../dashboard_excess_annualized.html">Excess return</a>
      <a href="../dashboard_top_annualized.html">Top annualized</a>
      <a href="../dashboard_top_annualized_buyhold.html">Top buy &amp; hold</a>
      <a href="../dashboard_stock_selection.html">Stock selection</a>
      <a href="../dashboard_final_simple.html">Final simple</a>
    </nav>
  </header>
  <main>
    <section class="hero">
      <div>
        <p class="eyebrow">Ticker intelligence</p><h1>{label_html}</h1>
        <p class="hero-copy">The winning walk-forward schedule is reproduced from its archived
          source data, then adaptively continued on newer prices. Data source: {html.escape(data_file)} · through
          {html.escape(str(row.get('latest_data_end', 'n/a')))}.</p>
      </div>
      <div class="signal {signal_class}"><span>Current GA signal</span><strong>{signal}</strong></div>
    </section>

    <section class="metrics" aria-label="Latest metrics">
      <div class="metric"><span>Strategy annualized</span><strong>{pct(row, 'latest_adaptive_annualized_return_pct')}</strong></div>
      <div class="metric"><span>Excess annualized</span><strong>{pct(row, 'latest_excess_annualized_return_pct')}</strong></div>
      <div class="metric"><span>Strategy total</span><strong>{pct(row, 'latest_adaptive_return_pct')}</strong></div>
      <div class="metric"><span>Buy &amp; hold annualized</span><strong>{pct(row, 'latest_buy_hold_annualized_return_pct')}</strong></div>
      <div class="metric"><span>Max drawdown</span><strong>{pct(row, 'latest_max_dd_pct', False)}</strong></div>
      <div class="metric"><span>Last trade</span><strong class="last-trade {last_trade_class}">{html.escape(last_trade_action)} · {html.escape(str(row.get('last_trade_date', 'n/a')))}</strong></div>
    </section>

    <section class="compare">
      <article class="compare-card"><h2>Final window parameters</h2><dl>
        <dt>EMA pair</dt><dd>{row.get('short_ema', 'n/a')} / {row.get('long_ema', 'n/a')}</dd>
        <dt>Stop loss</dt><dd>{safe_float(row, 'stop_loss', 0):.2f}%</dd>
        <dt>Cooldown</dt><dd>{row.get('cooldown', 'n/a')} days</dd>
        <dt>RSI bounds</dt><dd>{row.get('rsi_oversold', 'n/a')} / {row.get('rsi_overbought', 'n/a')}</dd>
        <dt>Exposure</dt><dd>{safe_float(row, 'exposure_multiplier', 1):.2f}×</dd>
      </dl></article>
      <article class="compare-card"><h2>Calibration versus latest replay</h2><dl>
        <dt>Historical annualized</dt><dd>{pct(row, 'adaptive_annualized_return_pct')}</dd>
        <dt>Latest annualized</dt><dd>{pct(row, 'latest_adaptive_annualized_return_pct')}</dd>
        <dt>Best excess annualized</dt><dd>{pct(row, 'best_excess_annualized_return_pct') if 'best_excess_annualized_return_pct' in row else pct(row, 'source_excess_annualized_return_pct')}</dd>
        <dt>Latest excess</dt><dd>{pct(row, 'latest_excess_annualized_return_pct')}</dd>
        <dt>Best excess run</dt><dd>{html.escape(str(row.get('best_excess_run_id', row.get('source_run_id', 'n/a'))))}</dd>
        <dt>Historical replay</dt><dd>{html.escape(str(row.get('historical_replay_status', row.get('replay_status', 'n/a'))))}</dd>
        <dt>Latest replay</dt><dd>{html.escape(str(row.get('latest_replay_status', 'n/a')))}</dd>
        <dt>Schedule windows</dt><dd>{html.escape(str(row.get('schedule_window_count', 'n/a')))} + {html.escape(str(row.get('continuation_window_count', 0)))} continuation</dd>
      </dl></article>
    </section>

    <section class="charts-grid" aria-label="Chart views">
      {chart_section(row, 'latest_chart_file', f"Latest technical · data through {latest_data_end}",
        f"The archived winning schedule reproduced exactly, then adaptively retuned on newer prices. Chart generated: {chart_updated_at}.")}
      {chart_section(
        row,
        'best_excess_chart_file',
        f"Best excess annualized · {pct(row, 'best_excess_annualized_return_pct')} · through {row.get('best_excess_data_end', 'n/a')}",
        'The highest non-zero annualized-excess historical run selected from the run history.',
        row.get('best_excess_run_id', row.get('source_run_id', '')),
      )}
      {chart_section(row, 'technical_chart_file', f"Historical technical · source through {historical_data_end}",
        f"Exact walk-forward reproduction over the winning historical window. Chart generated: {chart_updated_at}.")}
      {chart_section(row, 'simple_chart_file', f"Historical simple · source through {historical_data_end}",
        f"A focused view of the same exact historical reproduction. Chart generated: {chart_updated_at}.")}
    </section>

    <footer>Generated {generated_at} from {html.escape(Path(summary_path).name)}.</footer>
  </main>
  <dialog id="viewer">
    <div class="viewer-bar"><strong id="viewerTitle">Chart</strong><button id="closeViewer" type="button">Close</button></div>
    <div class="viewport"><img id="viewerImage" alt=""></div>
  </dialog>
  <script>
    const viewer=document.getElementById('viewer'), image=document.getElementById('viewerImage');
    document.querySelectorAll('.chart-button').forEach(button=>button.addEventListener('click',()=>{{
      image.src=button.dataset.src;image.alt=button.dataset.title;
      document.getElementById('viewerTitle').textContent=button.dataset.title;viewer.showModal();
    }}));
    document.getElementById('closeViewer').onclick=()=>viewer.close();
    viewer.addEventListener('click',event=>{{if(event.target===viewer)viewer.close()}});
  </script>
</body>
</html>"""
    detail_path.write_text(dashboard, encoding="utf-8")
    return detail_path


def write_final_simple_dashboard(results, summary_path):
    """Build a visual index of the historical strategy-versus-buy-and-hold charts."""
    completed = [row for row in results if row.get("status") == "completed"]
    completed.sort(
        key=lambda row: safe_float(row, "adaptive_annualized_return_pct", float("-inf")),
        reverse=True,
    )
    cards = []
    for rank, row in enumerate(completed, start=1):
        chart = Path(str(row.get("simple_chart_file", "")))
        if not chart.exists():
            continue
        label = fund_group_from_label(row.get("fund_label", "Unknown"))
        src = html.escape(relative_url(chart, REPORTS_DIR), quote=True)
        cards.append(
            f'''<article class="card"><div class="card-head"><span class="rank">#{rank}</span><div><h2>{html.escape(label)}</h2>
              <p>Final strategy vs buy &amp; hold</p></div><strong>{pct(row, 'adaptive_annualized_return_pct')}</strong></div>
              <div class="metrics"><span>Excess ann. <b>{pct(row, 'excess_annualized_return_pct')}</b></span>
                <span>Through <b>{html.escape(str(row.get('data_end', 'n/a')))}</b></span></div>
              <button class="chart" data-src="{src}" data-title="{html.escape(label)} — Final simple" type="button">
                <img src="{src}" alt="{html.escape(label)} final simple chart" loading="lazy"><span>Open chart</span></button></article>'''
        )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Final Simple Charts</title><style>
      :root{{--ink:#142033;--muted:#6b7584;--line:#dce3e7;--paper:#fff;--bg:#f4f6f5;--green:#0f6e5c;--soft:#e5f2ee}}
      *{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}}
      header{{padding:17px clamp(16px,4vw,48px) 13px;border-bottom:1px solid var(--line);background:rgba(244,246,245,.94)}}
      header a{{display:inline-block;margin-bottom:8px;color:var(--green);font-weight:750;text-decoration:none}}h1{{margin:0 0 4px;font-size:clamp(1.4rem,3vw,2.05rem);letter-spacing:-.04em}}header p{{margin:0;color:var(--muted)}}
      main{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;padding:24px clamp(16px,4vw,48px) 56px;margin:0}}
      .card{{padding:16px;border:1px solid var(--line);border-radius:18px;background:var(--paper)}}.card-head{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
      .rank{{display:grid;place-items:center;width:34px;height:30px;border-radius:999px;background:var(--soft);color:var(--green);font-weight:850}}h2{{margin:0;font-size:1.12rem}}.card-head p{{margin:3px 0 0;color:var(--muted);font-size:.8rem}}.card-head strong{{margin-left:auto;color:var(--green)}}
      .metrics{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}}.metrics span{{padding:6px 8px;border-radius:8px;background:#f6f8f8;color:var(--muted);font-size:.78rem}}.metrics b{{color:var(--ink)}}
      .chart{{position:relative;display:block;width:100%;padding:0;border:0;border-radius:12px;overflow:hidden;background:#edf0f1;cursor:zoom-in}}.chart img{{display:block;width:100%;height:auto}}.chart span{{position:absolute;right:10px;bottom:10px;padding:6px 9px;border-radius:7px;background:rgba(15,29,43,.8);color:#fff;opacity:0}}.chart:hover span,.chart:focus-visible span{{opacity:1}}
      dialog{{width:calc(100vw - 20px);height:calc(100vh - 20px);max-width:none;max-height:none;padding:0;border:0;border-radius:16px;background:#101923}}dialog::backdrop{{background:rgba(4,10,18,.86)}}.bar{{position:absolute;inset:0 0 auto;z-index:2;display:flex;justify-content:space-between;padding:11px 15px;color:#fff;background:rgba(16,25,35,.92)}}.bar button{{padding:7px 11px;border:1px solid #647181;border-radius:8px;background:#233242;color:#fff}}.viewport{{height:100%;overflow:auto;padding-top:54px}}#viewerImage{{display:block;max-width:none;margin:auto}}
      @media(min-width:1500px){{main{{grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}.card{{padding:12px}}.card-head{{margin-bottom:8px}}.metrics{{margin-bottom:10px;gap:5px}}.metrics span{{padding:5px 7px;font-size:.72rem}}}}@media(min-width:2100px){{main{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}@media(max-width:760px){{main{{grid-template-columns:1fr}}}}</style></head><body><header><a href="dashboard.html">← Master dashboard</a><h1>Final Simple Charts</h1><p>{len(cards)} historical strategy-versus-buy-and-hold charts · generated {generated_at} · source {html.escape(Path(summary_path).name)}</p></header><main>{''.join(cards)}</main>
      <dialog id="viewer"><div class="bar"><strong id="viewerTitle">Chart</strong><button id="close" type="button">Close</button></div><div class="viewport"><img id="viewerImage" alt=""></div></dialog><script>const v=document.getElementById('viewer'),i=document.getElementById('viewerImage');document.querySelectorAll('.chart').forEach(b=>b.onclick=()=>{{i.src=b.dataset.src;i.alt=b.dataset.title;document.getElementById('viewerTitle').textContent=b.dataset.title;v.showModal()}});document.getElementById('close').onclick=()=>v.close();v.addEventListener('click',e=>{{if(e.target===v)v.close()}});</script></body></html>'''
    output = REPORTS_DIR / "dashboard_final_simple.html"
    output.write_text(page, encoding="utf-8")
    return output


def write_master_dashboard(results, summary_path, warnings):
    completed = [row for row in results if row.get("status") == "completed"]
    completed.sort(
        key=lambda row: safe_float(row, "latest_adaptive_annualized_return_pct", float("-inf")),
        reverse=True,
    )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    latest_dates = [
        str(row.get("latest_data_end", ""))
        for row in completed
        if not is_blank(row.get("latest_data_end"))
    ]
    newest_date = max(latest_dates) if latest_dates else "n/a"
    buy_signals = sum("BUY" in str(row.get("ga_signal", "")).upper() for row in completed)
    best_excess = max(
        completed,
        key=lambda row: safe_float(row, "latest_excess_annualized_return_pct", float("-inf")),
        default={},
    )

    cards = []
    for rank, row in enumerate(completed, start=1):
        label = fund_group_from_label(row.get("fund_label", "Unknown"))
        signal = str(row.get("ga_signal", "n/a"))
        is_buy = "BUY" in signal.upper()
        signal_class = "buy" if is_buy else "cash"
        signal_short = "BUY" if is_buy else "CASH"
        latest_strategy_ann = pct(row, "latest_adaptive_annualized_return_pct")
        top_strategy = pct(row, "top_strategy_annualized_return_pct")
        top_strategy_title = html.escape(
            f"Best historical strategy annualized run "
            f"{row.get('top_strategy_annualized_run_id', 'n/a')} through "
            f"{row.get('top_strategy_annualized_data_end', 'n/a')}",
            quote=True,
        )
        top_buy_hold = pct(row, "top_buy_hold_annualized_return_pct")
        top_buy_hold_title = html.escape(
            f"Best historical buy & hold annualized run "
            f"{row.get('top_buy_hold_annualized_run_id', 'n/a')} through "
            f"{row.get('top_buy_hold_annualized_data_end', 'n/a')}",
            quote=True,
        )
        # The combined "top annualized" figure always equals either the
        # strategy or the buy-and-hold leader, so it renders as a winner
        # badge on that column instead of a duplicate column of its own.
        top_annualized_winner = str(row.get("top_annualized_winner", "") or "")
        winner_badge = (
            '<span class="win" title="Best combined historical annualized result">W</span>'
        )
        strategy_badge = winner_badge if top_annualized_winner == "Strategy" else ""
        buy_hold_badge = winner_badge if top_annualized_winner == "Buy & hold" else ""
        top_excess = pct(row, "best_excess_annualized_return_pct")
        top_excess_title = html.escape(
            f"Best historical excess annualized run "
            f"{row.get('best_excess_run_id', 'n/a')}",
            quote=True,
        )
        drawdown_value = safe_float(row, "latest_max_dd_pct")
        if np.isfinite(drawdown_value):
            max_drawdown = f"−{drawdown_value:.2f}%"
            drawdown_class = " neg"
        else:
            max_drawdown = "n/a"
            drawdown_class = ""
        last_price = usd(row, "latest_stock_price")
        price_column = str(row.get("price_column", "Adj Close") or "Adj Close")
        price_date = str(
            row.get("latest_stock_price_date", row.get("latest_data_end", "n/a"))
            or "n/a"
        )
        price_title = html.escape(
            f"{price_column} through {price_date}", quote=True
        )
        through_title = html.escape(
            f"{signal} · data through {row.get('latest_data_end', 'n/a')}",
            quote=True,
        )
        label_attr = html.escape(label, quote=True)
        cards.append(
            f"""<a class="fund-row grid" href="funds/{html.escape(fund_slug(label), quote=True)}.html"
              data-ticker="{label_attr}"
              data-latest-strategy="{numeric_attr(row, 'latest_adaptive_annualized_return_pct')}"
              data-top-strategy="{numeric_attr(row, 'top_strategy_annualized_return_pct')}"
              data-top-buy-hold="{numeric_attr(row, 'top_buy_hold_annualized_return_pct')}"
              data-top-excess="{numeric_attr(row, 'best_excess_annualized_return_pct')}"
              data-max-drawdown="{numeric_attr(row, 'latest_max_dd_pct')}"
              data-last-price="{numeric_attr(row, 'latest_stock_price')}">
              <span class="rank">#{rank}</span>
              <span class="id-cell" title="{through_title}"><span class="ticker">{html.escape(label)}</span><span class="chip {signal_class}"><span class="dot"></span>{signal_short}</span></span>
              <span class="cell" data-column="latestStrategy"><span class="val{value_class(row, 'latest_adaptive_annualized_return_pct')}">{latest_strategy_ann}</span></span>
              <span class="cell" data-column="topStrategy" title="{top_strategy_title}"><span class="val{value_class(row, 'top_strategy_annualized_return_pct')}">{top_strategy}{strategy_badge}</span></span>
              <span class="cell" data-column="topBuyHold" title="{top_buy_hold_title}"><span class="val{value_class(row, 'top_buy_hold_annualized_return_pct')}">{top_buy_hold}{buy_hold_badge}</span></span>
              <span class="cell" data-column="topExcess" title="{top_excess_title}"><span class="val{value_class(row, 'best_excess_annualized_return_pct')}">{top_excess}</span></span>
              <span class="cell" data-column="maxDrawdown"><span class="val{drawdown_class}">{max_drawdown}</span></span>
              <span class="cell" data-column="lastPrice" title="{price_title}"><span class="val">{last_price}</span></span>
              <span class="arrow">→</span></a>"""
        )

    warning_html = ""
    if warnings:
        items = "".join(f"<li>{html.escape(warning)}</li>" for warning in warnings)
        warning_html = f'<aside class="warning"><strong>Partial refresh</strong><ul>{items}</ul></aside>'

    leader = completed[0] if completed else {}
    dashboard = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Backtest Intelligence Hub</title>
  <script>
    try {{
      const stored = localStorage.getItem('stockDashboard.theme.v1');
      document.documentElement.dataset.theme =
        stored === 'dark' || stored === 'light'
          ? stored
          : (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    }} catch (error) {{}}
  </script>
  <style>
    :root{{--ink:#142033;--muted:#6b7584;--line:#dce3e7;--paper:#fff;--bg:#f4f6f5;
      --green:#0f6e5c;--green-soft:#e5f2ee;--green-ring:#bcded3;--red:#a33b2e;
      --amber:#89510e;--amber-soft:#fff0d9;--amber-dot:#d99a3d;
      --buy:#096744;--buy-soft:#dff4e9;--buy-dot:#1fa06a;
      --head-bg:#eef2f1;--pill-bg:#f7f9f8;--dir-bg:#153f3a;--dir-ink:#fff;
      --badge-bg:#142a45;--badge-ink:#8fe0c6;--hover:#9dc4b9;
      --warn-line:#efc286;--warn-bg:#fff4e4;--warn-ink:#71440d;
      --shadow:rgba(25,48,60,.09)}}
    [data-theme="dark"]{{--ink:#e2e9ef;--muted:#93a0ad;--line:#26323d;--paper:#151f29;--bg:#0d141b;
      --green:#43c9a2;--green-soft:#12312a;--green-ring:#1e4a3e;--red:#e07a6a;
      --amber:#e0a95e;--amber-soft:#332512;--amber-dot:#c98f3d;
      --buy:#4ad391;--buy-soft:#0f2e21;--buy-dot:#2fbd7d;
      --head-bg:#1a2631;--pill-bg:#1a2631;--dir-bg:#43c9a2;--dir-ink:#0d1f19;
      --badge-bg:#43c9a2;--badge-ink:#0d1f19;--hover:#2f5548;
      --warn-line:#5a4218;--warn-bg:#2b2110;--warn-ink:#e6c188;
      --shadow:rgba(0,0,0,.4)}}
    *{{box-sizing:border-box}} [hidden]{{display:none!important}} body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}}
    a{{color:inherit;text-decoration:none}} main{{width:min(1280px,calc(100% - 32px));margin:0 auto 72px}}
    .hero{{margin-top:16px;padding:clamp(20px,2.8vw,32px);border-radius:22px;color:#fff;
      background:radial-gradient(circle at 85% 15%,rgba(91,213,181,.26),transparent 28%),linear-gradient(135deg,#142a45,#0d6355);
      box-shadow:0 24px 60px rgba(20,46,62,.18)}}
    .eyebrow{{margin:0 0 10px;text-transform:uppercase;letter-spacing:.14em;font-size:.74rem;font-weight:800;color:#77d5bc}}
    h1{{margin:0;font-size:clamp(1.65rem,2.5vw,2.55rem);line-height:1.08;letter-spacing:-.045em}}
    @media(min-width:901px){{.hero h1{{white-space:nowrap}}}}
    .hero-copy{{max-width:760px;margin:10px 0 0;color:#d2e3e3;font-size:.94rem;line-height:1.5}}
    .hero-meta{{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}}
    .hero-meta span,.hero-meta a{{padding:8px 11px;border:1px solid rgba(255,255,255,.18);border-radius:999px;background:rgba(255,255,255,.07);font-size:.82rem}}
    .hero-meta a{{color:#fff;font-weight:750;text-decoration:none;transition:background .18s,border-color .18s}}
    .hero-meta a:hover,.hero-meta a:focus-visible{{background:rgba(255,255,255,.16);border-color:rgba(255,255,255,.42)}}
    .summary{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0 20px}}
    .stat{{padding:14px 16px;border:1px solid var(--line);border-radius:14px;background:var(--paper)}}
    .stat span{{display:block;color:var(--muted);font-size:.68rem;text-transform:uppercase;letter-spacing:.07em}}
    .stat strong{{display:block;margin-top:4px;font-size:1.25rem}}
    .section-head{{display:flex;justify-content:space-between;align-items:end;gap:20px;margin:22px 0 10px}}
    .section-head h2{{margin:0;font-size:1.28rem;letter-spacing:-.025em}} .section-head p{{margin:0;color:var(--muted);font-size:.9rem}}
    .dashboards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}}
    .dashboard-link{{display:grid;grid-template-columns:auto minmax(0,1fr);column-gap:8px;align-content:start;min-height:106px;padding:12px 14px;border:1px solid var(--line);border-radius:16px;background:var(--paper);
      transition:transform .18s,box-shadow .18s,border-color .18s}}
    .dashboard-link:hover{{transform:translateY(-3px);border-color:var(--hover);box-shadow:0 15px 35px var(--shadow)}}
    .dashboard-link .number{{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:8px;background:var(--green-soft);color:var(--green);font-size:.8rem;font-weight:850}}
    .dashboard-link h3{{margin:0;align-self:center;font-size:1rem}} .dashboard-link p{{grid-column:1/-1;margin:6px 0 0;color:var(--muted);font-size:.84rem;line-height:1.35}}
    .sort-bar{{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:8px;padding:8px 10px;border:1px solid var(--line);border-radius:14px;background:var(--paper)}}
    .sort-label{{margin-right:2px;color:var(--muted);font-size:.76rem;font-weight:800;text-transform:uppercase;letter-spacing:.06em}}
    .sort-pill,.sort-direction,.theme-toggle{{min-height:34px;padding:7px 11px;border:1px solid var(--line);border-radius:999px;background:var(--pill-bg);color:var(--ink);font:inherit;font-size:.78rem;font-weight:750;cursor:pointer}}
    .sort-pill[aria-pressed="true"]{{border-color:var(--green-ring);background:var(--green-soft);color:var(--green)}}
    .sort-direction{{margin-left:auto;background:var(--dir-bg);color:var(--dir-ink);border-color:var(--dir-bg)}}
    .sort-pill:focus-visible,.sort-direction:focus-visible,.theme-toggle:focus-visible{{outline:3px solid rgba(29,126,232,.28);outline-offset:2px}}
    .column-chooser{{position:relative}}.column-chooser summary{{display:flex;align-items:center;min-height:34px;padding:7px 11px;border:1px solid var(--line);border-radius:999px;background:var(--pill-bg);font-size:.78rem;font-weight:750;cursor:pointer;list-style:none}}
    .column-chooser summary::-webkit-details-marker{{display:none}}.column-chooser[open] summary{{border-color:var(--green-ring);background:var(--green-soft);color:var(--green)}}
    .column-panel{{position:absolute;right:0;z-index:6;width:250px;margin-top:6px;padding:10px;border:1px solid var(--line);border-radius:12px;background:var(--paper);box-shadow:0 16px 40px var(--shadow)}}
    .column-panel label{{display:flex;align-items:center;gap:8px;padding:7px 5px;font-size:.82rem}}.column-panel input{{accent-color:var(--green)}}
    .column-panel button{{width:100%;margin-top:6px;padding:8px;border:1px solid var(--line);border-radius:9px;background:var(--pill-bg);color:var(--ink);font:inherit;font-size:.78rem;font-weight:750;cursor:pointer}}
    .asof-bar{{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin:10px 2px 6px;color:var(--muted);font-size:.8rem}}
    .asof-bar b{{color:var(--ink)}}
    .fund-list{{--visible-column-count:6;border:1px solid var(--line);border-radius:14px;background:var(--paper);overflow:hidden}}
    .grid{{display:grid;grid-template-columns:44px 158px repeat(var(--visible-column-count),minmax(0,1fr)) 26px;
      gap:8px;align-items:center;padding:0 14px}}
    .fund-head{{position:sticky;top:0;z-index:5;min-height:34px;background:var(--head-bg);border-bottom:1px solid var(--line);
      font-size:.66rem;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
    .fund-head [data-column]{{display:flex;align-items:center;justify-content:flex-end;gap:4px;white-space:nowrap;min-width:0;overflow:hidden}}
    .fund-head .sorted{{color:var(--green);box-shadow:inset 0 -2px 0 var(--green)}}
    .info{{display:inline-grid;place-items:center;width:13px;height:13px;border-radius:50%;flex:none;
      border:1px solid var(--line);color:var(--muted);font-size:.58rem;font-style:normal;cursor:help}}
    .fund-row{{min-height:42px;border-bottom:1px solid var(--line);transition:background .12s}}
    .fund-row:last-child{{border-bottom:none}}
    .fund-row:hover{{background:var(--head-bg)}}
    .rank{{color:var(--muted);font-size:.78rem;font-weight:750;font-variant-numeric:tabular-nums}}
    .id-cell{{display:flex;align-items:center;gap:8px;min-width:0}}
    .ticker{{font-size:.95rem;font-weight:850;letter-spacing:-.01em}}
    .chip{{display:inline-flex;align-items:center;gap:5px;padding:2px 8px 2px 6px;border-radius:5px;
      font-size:.64rem;font-weight:800;letter-spacing:.03em;white-space:nowrap}}
    .chip .dot{{width:6px;height:6px;border-radius:50%}}
    .chip.cash{{color:var(--amber);background:var(--amber-soft)}} .chip.cash .dot{{background:var(--amber-dot)}}
    .chip.buy{{color:var(--buy);background:var(--buy-soft)}} .chip.buy .dot{{background:var(--buy-dot)}}
    .cell{{display:flex;align-items:center;justify-content:flex-end;align-self:stretch;min-width:0}}
    .cell.sorted{{background:var(--green-soft);box-shadow:inset 1px 0 0 var(--green-ring),inset -1px 0 0 var(--green-ring)}}
    .cell.sorted .val{{font-size:.95rem;font-weight:850}}
    .val{{font-size:.86rem;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap;
      overflow:hidden;text-overflow:ellipsis}}
    .val.pos{{color:var(--green)}} .val.neg{{color:var(--red)}}
    .win{{display:inline-block;margin-left:5px;padding:1px 5px;border-radius:4px;background:var(--badge-bg);
      color:var(--badge-ink);font-size:.58rem;font-weight:800;letter-spacing:.05em;vertical-align:1px}}
    .arrow{{font-size:1.05rem;color:var(--green);text-align:right}}
    .warning{{margin-top:18px;padding:16px 18px;border:1px solid var(--warn-line);border-radius:14px;background:var(--warn-bg);color:var(--warn-ink)}}
    .warning ul{{margin:7px 0 0;padding-left:20px}} footer{{margin-top:28px;color:var(--muted);font-size:.8rem}}
    @media(max-width:1050px){{.summary{{grid-template-columns:repeat(2,1fr)}}.dashboards{{grid-template-columns:repeat(2,1fr)}}}}
    @media(max-width:650px){{main{{width:min(100% - 20px,1460px)}}.summary{{grid-template-columns:1fr 1fr}}
      .sort-label{{width:100%}}.sort-direction{{margin-left:0}}.column-panel{{left:0;right:auto}}
      .list-scroll{{overflow-x:auto;border-radius:14px}}
      .fund-list{{min-width:560px}}
      .grid{{grid-template-columns:36px 140px repeat(var(--visible-column-count),minmax(88px,1fr)) 22px}}
      .section-head{{display:block}}.section-head p{{margin-top:7px}}}}
  </style>
</head>
<body><main>
  <section class="hero"><p class="eyebrow">Backtest intelligence hub</p>
    <h1>One view for every winning strategy.</h1>
    <p class="hero-copy">Explore the latest full-history replay, inspect each ticker's technical and simple
      final charts, compare run history, or build a diversified long-term research shortlist.</p>
    <div class="hero-meta"><span>{len(completed)} tickers</span><span>Latest local data {html.escape(newest_date)}</span>
      <a href="{html.escape(COMPANY_RESEARCH_URL, quote=True)}" target="_blank" rel="noopener noreferrer">Company Research ↗</a>
    </div>
  </section>
  <section class="summary" aria-label="Run summary">
    <div class="stat"><span>Latest leader</span><strong>{html.escape(str(leader.get('fund_label', 'n/a')))} · {pct(leader, 'latest_adaptive_annualized_return_pct')}</strong></div>
    <div class="stat"><span>Best latest excess</span><strong>{html.escape(str(best_excess.get('fund_label', 'n/a')))} · {pct(best_excess, 'latest_excess_annualized_return_pct')}</strong></div>
    <div class="stat"><span>Buy signals</span><strong>{buy_signals} of {len(completed)}</strong></div>
    <div class="stat"><span>Newest observation</span><strong>{html.escape(newest_date)}</strong></div>
  </section>
  <section class="dashboards">
    <a class="dashboard-link" href="dashboard_latest.html"><span class="number">1</span><h3>Latest ranking</h3>
      <p>Rank the selected winning parameters on each ticker's full locally available history.</p></a>
    <a class="dashboard-link" href="dashboard_excess_annualized.html"><span class="number">2</span><h3>Excess annualized ranking</h3>
      <p>Find the historical strategy runs that beat buy and hold by the widest annualized margin.</p></a>
    <a class="dashboard-link" href="dashboard_top_annualized.html"><span class="number">3</span><h3>Top annualized return</h3>
      <p>Compare the strongest annualized outcome from either the strategy or buy and hold.</p></a>
    <a class="dashboard-link" href="dashboard_final_simple.html"><span class="number">4</span><h3>Final simple charts</h3>
      <p>Browse each historical strategy-versus-buy-and-hold chart in one place.</p></a>
    <a class="dashboard-link" href="dashboard_top_annualized_buyhold.html"><span class="number">5</span><h3>Buy &amp; hold horizons</h3>
      <p>Compare price-derived buy-and-hold growth across 20Y, 10Y, 5Y, 4Y, and 3Y windows.</p></a>
    <a class="dashboard-link" href="dashboard_stock_selection.html"><span class="number">6</span><h3>Long-term stock selection</h3>
      <p>Combine return persistence, drawdown, volatility, benchmark consistency, and industry caps into a research shortlist.</p></a>
  </section>
  <section class="sort-bar" aria-label="Stock sorting controls">
    <span class="sort-label">Sort stocks</span>
    <button class="sort-pill" type="button" data-sort-key="latestStrategy" aria-pressed="true">Latest strategy</button>
    <button class="sort-pill" type="button" data-sort-key="topStrategy" aria-pressed="false">Strategy ann.</button>
    <button class="sort-pill" type="button" data-sort-key="topBuyHold" aria-pressed="false">B&amp;H ann.</button>
    <button class="sort-pill" type="button" data-sort-key="topExcess" aria-pressed="false">Excess</button>
    <button class="sort-pill" type="button" data-sort-key="maxDrawdown" aria-pressed="false">Drawdown</button>
    <button class="sort-pill" type="button" data-sort-key="lastPrice" aria-pressed="false">Price</button>
    <button class="sort-direction" id="sortDirection" type="button" aria-label="Change to lowest first">Highest first ↓</button>
    <details class="column-chooser" id="columnChooser">
      <summary>Columns (<span id="columnCount">0</span>)</summary>
      <div class="column-panel" role="group" aria-label="Visible stock columns">
        <label><input type="checkbox" data-column-toggle="latestStrategy">Latest strategy</label>
        <label><input type="checkbox" data-column-toggle="topStrategy">Top strategy annualized</label>
        <label><input type="checkbox" data-column-toggle="topBuyHold">Top buy &amp; hold annualized</label>
        <label><input type="checkbox" data-column-toggle="topExcess">Top excess</label>
        <label><input type="checkbox" data-column-toggle="maxDrawdown">Max drawdown</label>
        <label><input type="checkbox" data-column-toggle="lastPrice">Last price</label>
        <button id="resetColumns" type="button">Reset responsive defaults</button>
      </div>
    </details>
    <button class="theme-toggle" id="themeToggle" type="button" aria-label="Switch color theme">🌙 Dark</button>
  </section>
  <div class="asof-bar">
    <span>{len(completed)} tickers · {buy_signals} buy signal{'' if buy_signals == 1 else 's'} · <b>W</b> marks the better of strategy vs buy &amp; hold</span>
    <span>All data through <b>{html.escape(newest_date)}</b></span>
  </div>
  <div class="list-scroll"><section class="fund-list" aria-label="Stock rankings">
    <div class="fund-head grid" aria-hidden="true">
      <span>#</span>
      <span>Ticker / Signal</span>
      <span data-column="latestStrategy">Latest strategy <i class="info" title="Annualized strategy return from the latest full-history replay: the archived winning walk-forward schedule is reproduced, then adaptively continued on newer local prices through the latest date. This is not the best historical run">i</i></span>
      <span data-column="topStrategy">Strategy ann. <i class="info" title="Best historical strategy annualized run — hover a value for run ID and as-of date">i</i></span>
      <span data-column="topBuyHold">B&amp;H ann. <i class="info" title="Best historical buy &amp; hold annualized run — hover a value for run ID and as-of date">i</i></span>
      <span data-column="topExcess">Excess <i class="info" title="Best historical excess annualized run — hover a value for run ID">i</i></span>
      <span data-column="maxDrawdown">Drawdown <i class="info" title="Maximum peak-to-trough decline in strategy NAV during the latest replay. It is shown as a negative percentage; smaller losses are better">i</i></span>
      <span data-column="lastPrice">Price</span>
      <span></span>
    </div>
    {''.join(cards) if cards else '<p>No completed final backtests were available.</p>'}</section></div>
  {warning_html}
  <footer>Built {generated_at} · Master dashboard generated from {html.escape(str(summary_path))}.</footer>
  <script>
    (() => {{
      const list = document.querySelector('.fund-list');
      const pills = [...document.querySelectorAll('.sort-pill')];
      const directionButton = document.getElementById('sortDirection');
      const columnToggles = [...document.querySelectorAll('[data-column-toggle]')];
      const columnCount = document.getElementById('columnCount');
      const resetColumns = document.getElementById('resetColumns');
      if (!list || !directionButton) return;
      const rows = [...list.querySelectorAll('.fund-row')];
      const columnKeys = [
        'latestStrategy','topStrategy','topBuyHold',
        'topExcess','maxDrawdown','lastPrice'
      ];
      const storageKey = 'stockDashboard.visibleColumns.v2';
      // Drawdown ranks best-first as the smallest loss; everything else as
      // the largest gain.
      const defaultDirections = {{maxDrawdown: 'asc'}};
      let sortKey = 'latestStrategy';
      let direction = 'desc';

      const responsiveDefaults = () => {{
        if (window.innerWidth > 1050) return [...columnKeys];
        if (window.innerWidth > 650) {{
           return ['latestStrategy','topStrategy','topBuyHold','topExcess'];
        }}
        return ['latestStrategy','topExcess'];
      }};
      const readStoredColumns = () => {{
        try {{
          const raw = window.localStorage.getItem(storageKey);
          if (raw === null) return null;
          const parsed = JSON.parse(raw);
          return Array.isArray(parsed) &&
            parsed.every((key) => columnKeys.includes(key)) ? parsed : null;
        }} catch (error) {{
          return null;
        }}
      }};
      const storedColumns = readStoredColumns();
      let hasCustomColumns = storedColumns !== null;
      let visibleColumns = new Set(storedColumns || responsiveDefaults());

      const applyColumns = () => {{
        list.querySelectorAll('[data-column]').forEach((column) => {{
          column.hidden = !visibleColumns.has(column.dataset.column);
        }});
        list.style.setProperty('--visible-column-count', visibleColumns.size);
        columnToggles.forEach((toggle) => {{
          toggle.checked = visibleColumns.has(toggle.dataset.columnToggle);
        }});
        if (columnCount) columnCount.textContent = String(visibleColumns.size);
      }};
      const saveColumns = () => {{
        try {{
          window.localStorage.setItem(storageKey, JSON.stringify([...visibleColumns]));
        }} catch (error) {{
          // Local file storage may be unavailable; current-page controls still work.
        }}
      }};

      const numericValue = (row) => {{
        const value = Number.parseFloat(row.dataset[sortKey]);
        return Number.isFinite(value) ? value : null;
      }};
      const tickerCompare = (left, right) =>
        left.dataset.ticker.localeCompare(right.dataset.ticker, undefined, {{sensitivity:'base'}});

      const applySort = () => {{
        rows.sort((left, right) => {{
          const leftValue = numericValue(left);
          const rightValue = numericValue(right);
          if (leftValue === null && rightValue !== null) return 1;
          if (rightValue === null && leftValue !== null) return -1;
          if (leftValue !== null && rightValue !== null && leftValue !== rightValue) {{
            return direction === 'desc' ? rightValue - leftValue : leftValue - rightValue;
          }}
          return tickerCompare(left, right);
        }});
        rows.forEach((row, index) => {{
          row.querySelector('.rank').textContent = `#${{index + 1}}`;
          list.append(row);
        }});
        list.querySelectorAll('[data-column]').forEach((cell) =>
          cell.classList.toggle('sorted', cell.dataset.column === sortKey)
        );
        pills.forEach((pill) =>
          pill.setAttribute('aria-pressed', String(pill.dataset.sortKey === sortKey))
        );
        const descending = direction === 'desc';
        directionButton.textContent = descending ? 'Highest first ↓' : 'Lowest first ↑';
        directionButton.setAttribute(
          'aria-label',
          descending ? 'Change to lowest first' : 'Change to highest first'
        );
      }};

      pills.forEach((pill) => pill.addEventListener('click', () => {{
        sortKey = pill.dataset.sortKey;
        direction = defaultDirections[sortKey] || 'desc';
        if (!visibleColumns.has(sortKey)) {{
          visibleColumns.add(sortKey);
          hasCustomColumns = true;
          applyColumns();
          saveColumns();
        }}
        applySort();
      }}));
      directionButton.addEventListener('click', () => {{
        direction = direction === 'desc' ? 'asc' : 'desc';
        applySort();
      }});
      columnToggles.forEach((toggle) => toggle.addEventListener('change', () => {{
        if (toggle.checked) visibleColumns.add(toggle.dataset.columnToggle);
        else visibleColumns.delete(toggle.dataset.columnToggle);
        hasCustomColumns = true;
        applyColumns();
        saveColumns();
      }}));
      if (resetColumns) resetColumns.addEventListener('click', () => {{
        try {{ window.localStorage.removeItem(storageKey); }} catch (error) {{}}
        hasCustomColumns = false;
        visibleColumns = new Set(responsiveDefaults());
        applyColumns();
      }});
      window.addEventListener('resize', () => {{
        if (hasCustomColumns) return;
        visibleColumns = new Set(responsiveDefaults());
        applyColumns();
      }});

      const themeKey = 'stockDashboard.theme.v1';
      const themeButton = document.getElementById('themeToggle');
      const applyTheme = (theme) => {{
        document.documentElement.dataset.theme = theme;
        if (themeButton) {{
          themeButton.textContent = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
        }}
      }};
      applyTheme(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
      if (themeButton) themeButton.addEventListener('click', () => {{
        const next =
          document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        try {{ window.localStorage.setItem(themeKey, next); }} catch (error) {{}}
      }});

      applyColumns();
      applySort();
    }})();
  </script>
</main></body></html>"""
    output = REPORTS_DIR / "dashboard.html"
    output.write_text(dashboard, encoding="utf-8")
    return output


def build_dashboard_suite(results, summary_path):
    """Generate detail pages, history comparisons, and the master page."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    results = hydrate_master_metadata(results)
    completed = [row for row in results if row.get("status") == "completed"]
    details = [write_fund_dashboard(row, summary_path) for row in completed]
    final_simple = write_final_simple_dashboard(results, summary_path)
    companions, warnings = refresh_companion_dashboards(summary_path)
    master = write_master_dashboard(results, summary_path, warnings)
    return {
        "master": master,
        "details": details,
        "final_simple": final_simple,
        "companions": companions,
        "warnings": warnings,
    }
