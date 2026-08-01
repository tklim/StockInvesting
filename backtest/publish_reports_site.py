"""Build a portable static site from generated dashboard reports.

The report HTML uses paths such as ``../charts/example.png``. This script
preserves that relationship inside a deployable site and copies only the chart
images that the reports actually reference.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


CHART_REFERENCE = re.compile(
    r"(?:src|data-src)\s*=\s*['\"]\.\./charts/([^'\"]+\.png)['\"]",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--charts-dir", type=Path, required=True)
    parser.add_argument("--site-dir", type=Path, required=True)
    return parser.parse_args()


def safe_chart_path(charts_dir: Path, reference: str) -> Path:
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe chart reference: {reference}")

    candidate = (charts_dir / relative).resolve()
    charts_root = charts_dir.resolve()
    if not candidate.is_relative_to(charts_root):
        raise ValueError(f"Chart reference escapes charts directory: {reference}")
    return candidate


def main() -> None:
    args = parse_args()
    reports_dir = args.reports_dir.resolve()
    charts_dir = args.charts_dir.resolve()
    site_dir = args.site_dir.resolve()

    if not reports_dir.is_dir():
        raise FileNotFoundError(f"Reports directory not found: {reports_dir}")
    if not charts_dir.is_dir():
        raise FileNotFoundError(f"Charts directory not found: {charts_dir}")

    site_reports = site_dir / "reports"
    site_charts = site_dir / "charts"
    shutil.copytree(reports_dir, site_reports, dirs_exist_ok=True)

    references: set[str] = set()
    for report in sorted(site_reports.rglob("*.html")):
        references.update(CHART_REFERENCE.findall(report.read_text(encoding="utf-8")))

    missing: list[str] = []
    copied: list[str] = []
    for reference in sorted(references):
        source = safe_chart_path(charts_dir, reference)
        if not source.is_file():
            missing.append(reference)
            continue
        destination = site_charts / reference
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(reference)

    if missing:
        raise FileNotFoundError(
            "Referenced chart files are missing:\n" + "\n".join(missing)
        )

    (site_dir / "index.html").write_text(
        "<!doctype html>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta http-equiv=\"refresh\" content=\"0; url=reports/dashboard.html\">\n"
        "<title>StockInvesting dashboards</title>\n"
        "<p><a href=\"reports/dashboard.html\">Open dashboards</a></p>\n",
        encoding="utf-8",
    )
    (site_dir / "chart-manifest.json").write_text(
        json.dumps({"charts": copied}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Built site with {len(copied)} chart images from {len(references)} references.")


if __name__ == "__main__":
    main()
