"""Build a fund backtest dashboard ranked by EXCESS ANNUALIZED RETURN.

`final_backtest_from_summary.py` picks the best historical parameter row per fund
(by excess annualized return) and writes a per-run `final_backtest_summary_*.csv`,
plus a dashboard ranked by the strategy's *own* annualized return. This companion
script is a lightweight post-processor: it reads that summary CSV and rebuilds the
dashboard (HTML + one-fund-per-page PDF) ranked and headlined by how much the
strategy beat buy & hold on an annualized basis (excess annualized return).

It re-uses the chart images the main run already generated, so it does not re-run
any backtests. Run `final_backtest_from_summary.py` first, then this.

Usage:
    python dashboard_by_excess_annualized.py                 # newest summary, latest window, all funds
    python dashboard_by_excess_annualized.py --window final  # rank by the windowed (not latest) excess
    python dashboard_by_excess_annualized.py --top-funds 5   # only the 5 best funds
    python dashboard_by_excess_annualized.py --summary-file outputs/tunings/final_backtest_summary_XXXX.csv
"""

import argparse
import html
import os
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

SCRIPT_DIR = Path(__file__).resolve().parent
# Self-contained module: data/ and outputs/ live inside backtest/ (see common.py).
REPO_ROOT = SCRIPT_DIR
OUTPUTS_DIR = REPO_ROOT / "outputs"
TUNINGS_DIR = OUTPUTS_DIR / "tunings"
REPORTS_DIR = OUTPUTS_DIR / "reports"

# Column sets for the two windows the main run records. "latest" is the full/most
# recent price window; "final" is the historical backtest window of the winning run.
WINDOW_COLUMNS = {
    "latest": {
        "excess": "latest_excess_annualized_return_pct",
        "adaptive_annualized": "latest_adaptive_annualized_return_pct",
        "buy_hold_annualized": "latest_buy_hold_annualized_return_pct",
        "adaptive_return": "latest_adaptive_return_pct",
        "max_dd": "latest_max_dd_pct",
        "through": "latest_data_end",
        "chart": "latest_chart_file",
    },
    "final": {
        "excess": "excess_annualized_return_pct",
        "adaptive_annualized": "adaptive_annualized_return_pct",
        "buy_hold_annualized": "buy_hold_annualized_return_pct",
        "adaptive_return": "adaptive_return_pct",
        "max_dd": "max_dd_pct",
        "through": "data_end",
        "chart": "simple_chart_file",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rebuild the fund backtest dashboard ranked by excess annualized return."
    )
    parser.add_argument(
        "--summary-file",
        default=None,
        help="final_backtest_summary_*.csv to read (default: newest in outputs/tunings/).",
    )
    parser.add_argument(
        "--window",
        choices=sorted(WINDOW_COLUMNS.keys()),
        default="latest",
        help="Which recorded window to rank/display: 'latest' full window (default) or "
        "'final' historical backtest window.",
    )
    parser.add_argument(
        "--top-funds",
        type=int,
        default=0,
        help="Number of top funds to show after ranking. 0 = all (default).",
    )
    return parser.parse_args()


def newest_summary_file():
    candidates = sorted(
        TUNINGS_DIR.glob("final_backtest_summary_*.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No final_backtest_summary_*.csv found in {TUNINGS_DIR}. "
            "Run final_backtest_from_summary.py first."
        )
    return candidates[-1]


def safe_float(row, key, default=np.nan):
    value = row.get(key, default)
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_ranked_results(summary_path, cols, top_funds):
    df = pd.read_csv(summary_path)
    if "status" in df.columns:
        df = df[df["status"].astype(str).str.lower() == "completed"]

    missing = [key for key in ("excess", "chart") if cols[key] not in df.columns]
    if missing:
        raise ValueError(
            f"Summary file is missing required column(s) for the '{cols}' window: "
            f"{[cols[key] for key in missing]}"
        )

    df = df[df[cols["chart"]].notna()].copy()
    df = df[df[cols["chart"]].map(lambda p: Path(str(p)).exists())]
    df["_excess"] = pd.to_numeric(df[cols["excess"]], errors="coerce")
    df = df.dropna(subset=["_excess"])
    df = df.sort_values("_excess", ascending=False)
    if top_funds and top_funds > 0:
        df = df.head(top_funds)
    return df.reset_index(drop=True)


def pct(row, key):
    value = row.get(key)
    return "n/a" if value is None or pd.isna(value) else f"{float(value):+.2f}%"


def build_cards(df, cols):
    cards = []
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        chart_path = Path(str(row[cols["chart"]]))
        chart_src = os.path.relpath(chart_path, REPORTS_DIR).replace(os.sep, "/")
        fund_label = html.escape(str(row.get("fund_label", "Unknown fund")))
        chart_alt = html.escape(f"Strategy chart for {row.get('fund_label', 'fund')}")
        excess_value = safe_float(row, cols["excess"])
        excess_class = "pos" if np.isfinite(excess_value) and excess_value >= 0 else "neg"
        cards.append(
            f"""
            <article class="fund-card">
              <div class="card-heading">
                <div><span class="rank">#{rank}</span><h2>{fund_label}</h2></div>
                <div class="headline {excess_class}"><span>Excess annualized</span><strong>{pct(row, cols['excess'])}</strong></div>
              </div>
              <div class="metrics">
                <span>Strategy ann. <b>{pct(row, cols['adaptive_annualized'])}</b></span>
                <span>Buy &amp; hold ann. <b>{pct(row, cols['buy_hold_annualized'])}</b></span>
                <span>Strategy total <b>{pct(row, cols['adaptive_return'])}</b></span>
                <span>Max drawdown <b>{pct(row, cols['max_dd'])}</b></span>
                <span>Through <b>{html.escape(str(row.get(cols['through'], 'n/a')))}</b></span>
              </div>
              <button class="chart-button" type="button" data-src="{html.escape(chart_src, quote=True)}" data-title="{fund_label}" aria-label="Open zoomable chart for {fund_label}">
                <img src="{html.escape(chart_src, quote=True)}" alt="{chart_alt}" loading="lazy">
                <span class="zoom-hint">Click to zoom</span>
              </button>
            </article>
            """
        )
    return cards


def write_dashboard(df, cols, window, output_path):
    cards = build_cards(df, cols)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    window_label = "latest full window" if window == "latest" else "historical backtest window"
    dashboard = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fund Backtest Dashboard — Excess Annualized Return</title>
  <style>
    :root{{--ink:#172033;--muted:#667085;--line:#dce2ea;--surface:#fff;--accent:#176b5b;--accent-soft:#e8f4f1;--bg:#f3f5f7;--pos:#12855b;--neg:#c9362c}}
    *{{box-sizing:border-box}}
    body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}}
    header{{position:sticky;top:0;z-index:10;padding:20px clamp(18px,4vw,52px);background:rgba(243,245,247,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}}
    header h1{{margin:0 0 5px;font-size:clamp(1.45rem,3vw,2.2rem)}}
    header p{{margin:0;color:var(--muted)}}
    main{{display:grid;gap:22px;padding:28px clamp(16px,3vw,42px) 56px;max-width:1900px;margin:auto}}
    .fund-card{{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 8px 26px rgba(19,33,55,.06)}}
    .card-heading,.card-heading>div,.metrics{{display:flex;align-items:center}}
    .card-heading{{justify-content:space-between;gap:18px;margin-bottom:13px}}
    .card-heading>div:first-child{{gap:10px;min-width:0}}
    .rank{{display:grid;place-items:center;min-width:38px;height:30px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:800}}
    h2{{font-size:clamp(1rem,2vw,1.35rem);margin:0;overflow-wrap:anywhere}}
    .headline{{display:flex;flex-direction:column!important;align-items:flex-end!important;white-space:nowrap}}
    .headline span{{font-size:.76rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
    .headline strong{{font-size:1.35rem}}
    .headline.pos strong{{color:var(--pos)}}
    .headline.neg strong{{color:var(--neg)}}
    .metrics{{flex-wrap:wrap;gap:8px;margin-bottom:14px}}
    .metrics span{{padding:7px 10px;border-radius:9px;background:#f7f8fa;color:var(--muted);font-size:.84rem}}
    .metrics b{{color:var(--ink)}}
    .chart-button{{display:block;position:relative;width:100%;padding:0;border:0;border-radius:12px;overflow:hidden;background:#e8ebef;cursor:zoom-in}}
    .chart-button img{{display:block;width:100%;height:auto}}
    .zoom-hint{{position:absolute;right:12px;bottom:12px;padding:7px 10px;border-radius:8px;background:rgba(16,24,40,.78);color:#fff;font-size:.78rem;opacity:0;transition:opacity .18s}}
    .chart-button:hover .zoom-hint,.chart-button:focus-visible .zoom-hint{{opacity:1}}
    dialog{{width:calc(100vw - 24px);height:calc(100vh - 24px);max-width:none;max-height:none;padding:0;border:0;border-radius:16px;background:#111827;overflow:hidden}}
    dialog::backdrop{{background:rgba(3,8,18,.82)}}
    .viewer-bar{{position:absolute;inset:0 0 auto 0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;background:rgba(17,24,39,.9);color:white}}
    .viewer-bar strong{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .controls{{display:flex;gap:7px}}
    .controls button{{border:1px solid #667085;background:#263246;color:white;border-radius:8px;padding:7px 11px;cursor:pointer}}
    .viewport{{width:100%;height:100%;overflow:hidden;cursor:grab;touch-action:none}}
    .viewport.dragging{{cursor:grabbing}}
    #viewerImage{{position:absolute;left:50%;top:50%;max-width:none;transform-origin:center;user-select:none;pointer-events:none}}
    @media (min-width:1200px){{main{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
    @page{{size:A4 landscape;margin:8mm}}
    @media print{{
      body{{background:#fff}}
      header,dialog,.zoom-hint{{display:none!important}}
      main{{display:block;max-width:none;padding:0;margin:0}}
      .fund-card{{height:194mm;margin:0;padding:4mm;border:0;border-radius:0;box-shadow:none;overflow:hidden;break-inside:avoid;page-break-inside:avoid;break-after:page;page-break-after:always}}
      .fund-card:last-child{{break-after:auto;page-break-after:auto}}
      .card-heading{{margin-bottom:2mm}}
      .metrics{{margin-bottom:2mm;gap:1.5mm}}
      .metrics span{{padding:1.5mm 2mm}}
      .chart-button{{height:158mm;border-radius:0;cursor:default;overflow:hidden}}
      .chart-button img{{width:100%;height:100%;object-fit:contain}}
    }}
  </style>
</head>
<body>
  <header><h1>Fund Backtest Dashboard — Excess Annualized Return</h1><p>{len(df)} funds · sorted by excess annualized return (strategy − buy &amp; hold) · {window_label} · generated {generated_at}</p></header>
  <main>{''.join(cards) if cards else '<p>No completed results were available.</p>'}</main>
  <dialog id="viewer">
    <div class="viewer-bar"><strong id="viewerTitle">Chart</strong><div class="controls"><button id="zoomOut" type="button">−</button><button id="resetZoom" type="button">Reset</button><button id="zoomIn" type="button">+</button><button id="closeViewer" type="button">Close</button></div></div>
    <div class="viewport" id="viewport"><img id="viewerImage" alt=""></div>
  </dialog>
  <script>
    const viewer=document.getElementById('viewer'), viewport=document.getElementById('viewport'), image=document.getElementById('viewerImage');
    let scale=1,x=0,y=0,drag=false,startX=0,startY=0;
    function render(){{image.style.transform=`translate(calc(-50% + ${{x}}px),calc(-50% + ${{y}}px)) scale(${{scale}})`}}
    function fit(){{if(!image.naturalWidth)return;scale=Math.min(1,(viewport.clientWidth-36)/image.naturalWidth,(viewport.clientHeight-86)/image.naturalHeight);x=0;y=0;render()}}
    function reset(){{fit()}}
    function zoom(factor){{scale=Math.min(8,Math.max(.5,scale*factor));render()}}
    image.addEventListener('load',fit);
    document.querySelectorAll('.chart-button').forEach(button=>button.addEventListener('click',()=>{{image.src=button.dataset.src;image.alt=button.dataset.title;document.getElementById('viewerTitle').textContent=button.dataset.title;viewer.showModal();if(image.complete)fit()}}));
    document.getElementById('closeViewer').onclick=()=>viewer.close();
    document.getElementById('zoomIn').onclick=()=>zoom(1.25);document.getElementById('zoomOut').onclick=()=>zoom(.8);document.getElementById('resetZoom').onclick=reset;
    viewport.addEventListener('wheel',event=>{{event.preventDefault();zoom(event.deltaY<0?1.15:.87)}},{{passive:false}});
    viewport.addEventListener('pointerdown',event=>{{drag=true;startX=event.clientX-x;startY=event.clientY-y;viewport.setPointerCapture(event.pointerId);viewport.classList.add('dragging')}});
    viewport.addEventListener('pointermove',event=>{{if(!drag)return;x=event.clientX-startX;y=event.clientY-startY;render()}});
    viewport.addEventListener('pointerup',()=>{{drag=false;viewport.classList.remove('dragging')}});
    viewer.addEventListener('click',event=>{{if(event.target===viewer)viewer.close()}});
  </script>
</body>
</html>"""
    output_path.write_text(dashboard, encoding="utf-8")
    return output_path


def write_pdf(df, cols, pdf_path):
    def render(path):
        with PdfPages(path) as pdf:
            for rank, (_, row) in enumerate(df.iterrows(), start=1):
                chart_path = Path(str(row[cols["chart"]]))
                if not chart_path.exists():
                    continue
                figure = plt.figure(figsize=(11.69, 8.27), facecolor="white")
                fund_label = str(row.get("fund_label", "Unknown fund"))
                excess = safe_float(row, cols["excess"])
                excess_color = "#12855b" if np.isfinite(excess) and excess >= 0 else "#c9362c"
                figure.text(0.045, 0.948, f"#{rank}  {fund_label}", fontsize=17, fontweight="bold", color="#172033", va="top")
                figure.text(
                    0.955, 0.948,
                    f"Excess annualized {excess:+.2f}%" if np.isfinite(excess) else "Excess annualized n/a",
                    fontsize=15, fontweight="bold", color=excess_color, ha="right", va="top",
                )
                metrics_line = (
                    f"Strategy annualized {safe_float(row, cols['adaptive_annualized']):+.2f}%    |    "
                    f"Buy & hold annualized {safe_float(row, cols['buy_hold_annualized']):+.2f}%    |    "
                    f"Strategy total {safe_float(row, cols['adaptive_return']):+.2f}%    |    "
                    f"Max drawdown {safe_float(row, cols['max_dd']):.2f}%    |    "
                    f"Through {row.get(cols['through'], 'n/a')}"
                )
                figure.text(0.045, 0.895, metrics_line, fontsize=9.5, color="#596579", va="top")
                chart_axis = figure.add_axes([0.035, 0.035, 0.93, 0.82])
                chart_axis.imshow(plt.imread(chart_path))
                chart_axis.set_axis_off()
                pdf.savefig(figure)
                plt.close(figure)

    try:
        render(pdf_path)
        return pdf_path
    except PermissionError:
        fallback = REPORTS_DIR / f"{pdf_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        render(fallback)
        print(f"Warning: {pdf_path} is locked. Saved PDF to {fallback}")
        return fallback


def main():
    args = parse_args()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.summary_file:
        summary_path = Path(args.summary_file)
        if not summary_path.is_absolute():
            summary_path = REPO_ROOT / summary_path
        if not summary_path.exists():
            raise FileNotFoundError(f"Summary file not found: {summary_path}")
    else:
        summary_path = newest_summary_file()

    cols = WINDOW_COLUMNS[args.window]
    df = load_ranked_results(summary_path, cols, args.top_funds)
    if df.empty:
        print(f"No completed rows with charts found in {summary_path}. Nothing to render.")
        return 0

    suffix = "" if args.window == "latest" else f"_{args.window}"
    dashboard_path = write_dashboard(df, cols, args.window, REPORTS_DIR / f"dashboard_excess_annualized{suffix}.html")
    pdf_path = write_pdf(df, cols, REPORTS_DIR / f"dashboard_excess_annualized{suffix}.pdf")

    print(f"Source summary: {summary_path}")
    print(f"Ranked {len(df)} fund(s) by excess annualized return ({args.window} window):")
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        print(f"  #{rank:>2}  {str(row.get('fund_label','?')):<8}  {pct(row, cols['excess'])}")
    print(f"\nDashboard saved to: {dashboard_path}")
    print(f"One-fund-per-page PDF saved to: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
