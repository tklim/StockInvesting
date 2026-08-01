"""Shared HTML + PDF rendering for the fund backtest dashboards.

Every dashboard shows the same thing structurally: funds ranked by some headline
metric, each with a few supporting numbers and the chart its run produced. Only the
metric, the labels and the supporting chips differ. That shared shell — the card
layout, the zoomable chart viewer, the print rules that give one fund per PDF page —
lives here so the dashboards cannot drift apart visually.

A dashboard supplies a `DashboardSpec` describing how to read one row, then calls
`render_html` / `render_pdf`.
"""

import html
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

POSITIVE_COLOR = "#12855b"
NEGATIVE_COLOR = "#c9362c"


@dataclass
class DashboardSpec:
    """How to turn one ranked row into a card.

    title:          page + browser title.
    headline_label: caption above the big number (e.g. "Excess annualized").
    headline:       row -> float, the ranked metric. NaN renders as "n/a".
    chart:          row -> Path of the chart image to embed.
    name:           row -> fund display name.
    chips:          row -> list of (label, value) supporting metrics.
    badge:          row -> short qualifier shown next to the headline, or None.
                    Used where the headline needs attribution (e.g. whether a
                    top annualized return came from the strategy or buy & hold).
    """

    title: str
    headline_label: str
    headline: Callable[[dict], float]
    chart: Callable[[dict], Path]
    name: Callable[[dict], str]
    chips: Callable[[dict], list] = field(default=lambda row: [])
    badge: Optional[Callable[[dict], Optional[str]]] = None


def source_provenance(source_path):
    """Name, last-modified timestamp and full path of the file a dashboard read."""
    source_path = Path(source_path)
    try:
        built_at = datetime.fromtimestamp(source_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        built_at = "unknown"
    return source_path.name, built_at, str(source_path)


def format_pct(value):
    return "n/a" if value is None or not np.isfinite(value) else f"{float(value):+.2f}%"


STYLE = """
    :root{--ink:#172033;--muted:#667085;--line:#dce2ea;--surface:#fff;--accent:#176b5b;--accent-soft:#e8f4f1;--bg:#f3f5f7;--pos:#12855b;--neg:#c9362c}
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}
    header{position:sticky;top:0;z-index:10;padding:20px clamp(18px,4vw,52px);background:rgba(243,245,247,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
    header h1{margin:0 0 5px;font-size:clamp(1.45rem,3vw,2.2rem)}
    header p{margin:0;color:var(--muted)}
    .source{margin-top:6px!important;font-size:.82rem}
    .source code{padding:1px 5px;border-radius:5px;background:var(--accent-soft);color:var(--accent);font-size:.8rem}
    main{display:grid;gap:22px;padding:28px clamp(16px,3vw,42px) 56px;max-width:1900px;margin:auto}
    .fund-card{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 8px 26px rgba(19,33,55,.06)}
    .card-heading,.card-heading>div,.metrics{display:flex;align-items:center}
    .card-heading{justify-content:space-between;gap:18px;margin-bottom:13px}
    .card-heading>div:first-child{gap:10px;min-width:0}
    .rank{display:grid;place-items:center;min-width:38px;height:30px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font-weight:800}
    h2{font-size:clamp(1rem,2vw,1.35rem);margin:0;overflow-wrap:anywhere}
    .headline{display:flex;flex-direction:column!important;align-items:flex-end!important;white-space:nowrap}
    .headline span{font-size:.76rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
    .headline strong{font-size:1.35rem}
    .headline.pos strong{color:var(--pos)}
    .headline.neg strong{color:var(--neg)}
    .badge{display:inline-block;margin-left:8px;padding:3px 9px;border-radius:999px;background:#eef1f5;color:#4a5568;font-size:.72rem;font-weight:700;text-transform:none;letter-spacing:0;vertical-align:middle}
    .badge.strategy{background:#e8f4f1;color:#176b5b}
    .badge.market{background:#fdf0e6;color:#96591f}
    .metrics{flex-wrap:wrap;gap:8px;margin-bottom:14px}
    .metrics span{padding:7px 10px;border-radius:9px;background:#f7f8fa;color:var(--muted);font-size:.84rem}
    .metrics b{color:var(--ink)}
    .chart-button{display:block;position:relative;width:100%;padding:0;border:0;border-radius:12px;overflow:hidden;background:#e8ebef;cursor:zoom-in}
    .chart-button img{display:block;width:100%;height:auto}
    .zoom-hint{position:absolute;right:12px;bottom:12px;padding:7px 10px;border-radius:8px;background:rgba(16,24,40,.78);color:#fff;font-size:.78rem;opacity:0;transition:opacity .18s}
    .chart-button:hover .zoom-hint,.chart-button:focus-visible .zoom-hint{opacity:1}
    dialog{width:calc(100vw - 24px);height:calc(100vh - 24px);max-width:none;max-height:none;padding:0;border:0;border-radius:16px;background:#111827;overflow:hidden}
    dialog::backdrop{background:rgba(3,8,18,.82)}
    .viewer-bar{position:absolute;inset:0 0 auto 0;z-index:3;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;background:rgba(17,24,39,.9);color:white}
    .viewer-bar strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .controls{display:flex;gap:7px}
    .controls button{border:1px solid #667085;background:#263246;color:white;border-radius:8px;padding:7px 11px;cursor:pointer}
    .viewport{width:100%;height:100%;overflow:hidden;cursor:grab;touch-action:none}
    .viewport.dragging{cursor:grabbing}
    #viewerImage{position:absolute;left:50%;top:50%;max-width:none;transform-origin:center;user-select:none;pointer-events:none}
    @media (min-width:1200px){main{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @page{size:A4 landscape;margin:8mm}
    @media print{
      body{background:#fff}
      header,dialog,.zoom-hint{display:none!important}
      main{display:block;max-width:none;padding:0;margin:0}
      .fund-card{height:194mm;margin:0;padding:4mm;border:0;border-radius:0;box-shadow:none;overflow:hidden;break-inside:avoid;page-break-inside:avoid;break-after:page;page-break-after:always}
      .fund-card:last-child{break-after:auto;page-break-after:auto}
      .card-heading{margin-bottom:2mm}
      .metrics{margin-bottom:2mm;gap:1.5mm}
      .metrics span{padding:1.5mm 2mm}
      .chart-button{height:158mm;border-radius:0;cursor:default;overflow:hidden}
      .chart-button img{width:100%;height:100%;object-fit:contain}
    }
"""

VIEWER_SCRIPT = """
    const viewer=document.getElementById('viewer'), viewport=document.getElementById('viewport'), image=document.getElementById('viewerImage');
    let scale=1,x=0,y=0,drag=false,startX=0,startY=0;
    function render(){image.style.transform=`translate(calc(-50% + ${x}px),calc(-50% + ${y}px)) scale(${scale})`}
    function fit(){if(!image.naturalWidth)return;scale=Math.min(1,(viewport.clientWidth-36)/image.naturalWidth,(viewport.clientHeight-86)/image.naturalHeight);x=0;y=0;render()}
    function reset(){fit()}
    function zoom(factor){scale=Math.min(8,Math.max(.5,scale*factor));render()}
    image.addEventListener('load',fit);
    document.querySelectorAll('.chart-button').forEach(button=>button.addEventListener('click',()=>{image.src=button.dataset.src;image.alt=button.dataset.title;document.getElementById('viewerTitle').textContent=button.dataset.title;viewer.showModal();if(image.complete)fit()}));
    document.getElementById('closeViewer').onclick=()=>viewer.close();
    document.getElementById('zoomIn').onclick=()=>zoom(1.25);document.getElementById('zoomOut').onclick=()=>zoom(.8);document.getElementById('resetZoom').onclick=reset;
    viewport.addEventListener('wheel',event=>{event.preventDefault();zoom(event.deltaY<0?1.15:.87)},{passive:false});
    viewport.addEventListener('pointerdown',event=>{drag=true;startX=event.clientX-x;startY=event.clientY-y;viewport.setPointerCapture(event.pointerId);viewport.classList.add('dragging')});
    viewport.addEventListener('pointermove',event=>{if(!drag)return;x=event.clientX-startX;y=event.clientY-startY;render()});
    viewport.addEventListener('pointerup',()=>{drag=false;viewport.classList.remove('dragging')});
    viewer.addEventListener('click',event=>{if(event.target===viewer)viewer.close()});
"""


def _badge_html(spec, row):
    if spec.badge is None:
        return ""
    text = spec.badge(row)
    if not text:
        return ""
    # "market" styling for anything attributing the number to buy & hold.
    variant = "market" if "hold" in str(text).lower() else "strategy"
    return f'<span class="badge {variant}">{html.escape(str(text))}</span>'


def build_cards(df, spec, reports_dir):
    cards = []
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        chart_path = Path(str(spec.chart(row)))
        chart_src = os.path.relpath(chart_path, reports_dir).replace(os.sep, "/")
        name = html.escape(str(spec.name(row)))
        chart_alt = html.escape(f"Strategy chart for {spec.name(row)}")
        value = spec.headline(row)
        tone = "pos" if np.isfinite(value) and value >= 0 else "neg"
        chips = "".join(
            f"<span>{html.escape(str(label))} <b>{html.escape(str(text))}</b></span>"
            for label, text in spec.chips(row)
        )
        cards.append(
            f"""
            <article class="fund-card">
              <div class="card-heading">
                <div><span class="rank">#{rank}</span><h2>{name}</h2></div>
                <div class="headline {tone}"><span>{html.escape(spec.headline_label)}{_badge_html(spec, row)}</span><strong>{format_pct(value)}</strong></div>
              </div>
              <div class="metrics">{chips}</div>
              <button class="chart-button" type="button" data-src="{html.escape(chart_src, quote=True)}" data-title="{name}" aria-label="Open zoomable chart for {name}">
                <img src="{html.escape(chart_src, quote=True)}" alt="{chart_alt}" loading="lazy">
                <span class="zoom-hint">Click to zoom</span>
              </button>
            </article>
            """
        )
    return cards


def render_html(df, spec, output_path, source_path, subtitle, provenance_note, reports_dir):
    cards = build_cards(df, spec, reports_dir)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_name, source_built_at, source_full = source_provenance(source_path)
    title = html.escape(spec.title)
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{STYLE}</style>
</head>
<body>
  <header>
    <h1>{title}</h1>
    <p>{len(df)} funds · {html.escape(subtitle)} · generated {generated_at}</p>
    <p class="source">Source <code title="{html.escape(source_full, quote=True)}">{html.escape(source_name)}</code> last written {source_built_at} — {html.escape(provenance_note)}</p>
  </header>
  <main>{''.join(cards) if cards else '<p>No results were available.</p>'}</main>
  <dialog id="viewer">
    <div class="viewer-bar"><strong id="viewerTitle">Chart</strong><div class="controls"><button id="zoomOut" type="button">−</button><button id="resetZoom" type="button">Reset</button><button id="zoomIn" type="button">+</button><button id="closeViewer" type="button">Close</button></div></div>
    <div class="viewport" id="viewport"><img id="viewerImage" alt=""></div>
  </dialog>
  <script>{VIEWER_SCRIPT}</script>
</body>
</html>"""
    output_path.write_text(page, encoding="utf-8")
    return output_path


METRICS_LEFT = 0.045
METRICS_RIGHT = 0.955
METRICS_BASELINE = 0.895


def _draw_fitted_line(figure, line, max_fontsize=9.5, min_fontsize=6.0):
    """Draw the metrics line, shrinking it until it fits the page width.

    The chip count varies per dashboard, so a fixed font size silently clips the
    right-hand chips. Measure, then step down until it fits.
    """
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    available = (METRICS_RIGHT - METRICS_LEFT) * figure.get_figwidth() * figure.dpi

    text = figure.text(METRICS_LEFT, METRICS_BASELINE, line, fontsize=max_fontsize,
                       color="#596579", va="top")
    size = max_fontsize
    while size > min_fontsize and text.get_window_extent(renderer).width > available:
        size -= 0.5
        text.set_fontsize(size)
    return text


def render_pdf(df, spec, pdf_path, source_path, reports_dir=None):
    # The HTML header is display:none in print, so each PDF page carries provenance.
    source_name, source_built_at, _ = source_provenance(source_path)
    provenance = f"Source {source_name} · last written {source_built_at}"

    def draw(path):
        with PdfPages(path) as pdf:
            for rank, (_, row) in enumerate(df.iterrows(), start=1):
                chart_path = Path(str(spec.chart(row)))
                if not chart_path.exists():
                    continue
                figure = plt.figure(figsize=(11.69, 8.27), facecolor="white")
                value = spec.headline(row)
                color = POSITIVE_COLOR if np.isfinite(value) and value >= 0 else NEGATIVE_COLOR
                badge = spec.badge(row) if spec.badge else None
                heading = f"#{rank}  {spec.name(row)}"
                figure.text(0.045, 0.948, heading, fontsize=17, fontweight="bold",
                            color="#172033", va="top")
                headline = f"{spec.headline_label} {format_pct(value)}"
                if badge:
                    headline += f"  ({badge})"
                figure.text(0.955, 0.948, headline, fontsize=15, fontweight="bold",
                            color=color, ha="right", va="top")
                chips = spec.chips(row)
                if chips:
                    line = "    |    ".join(f"{label} {text}" for label, text in chips)
                    _draw_fitted_line(figure, line)
                figure.text(0.955, 0.014, provenance, fontsize=7, color="#98a1b0",
                            ha="right", va="bottom")
                axis = figure.add_axes([0.035, 0.042, 0.93, 0.813])
                axis.imshow(plt.imread(chart_path))
                axis.set_axis_off()
                pdf.savefig(figure)
                plt.close(figure)

    try:
        draw(pdf_path)
        return pdf_path
    except PermissionError:
        fallback = pdf_path.with_name(
            f"{pdf_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{pdf_path.suffix}"
        )
        draw(fallback)
        print(f"Warning: {pdf_path} is locked. Saved PDF to {fallback}")
        return fallback
