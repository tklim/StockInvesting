"""Resize only PNGs linked by the currently generated dashboard HTML files."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import chart_output


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
DEFAULT_REPORTS_DIR = OUTPUTS_DIR / "reports"
DEFAULT_CHARTS_DIR = OUTPUTS_DIR / "charts"
DEFAULT_MIGRATIONS_DIR = OUTPUTS_DIR / "chart_resolution_migrations"


class ImageLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() not in {"img", "button"}:
            return
        for name, value in attrs:
            if name.lower() in {"src", "data-src"} and value:
                self.links.append(value)


def _is_within(path, directory):
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
        return True
    except ValueError:
        return False


def collect_dashboard_pngs(reports_dir=DEFAULT_REPORTS_DIR,
                           charts_dir=DEFAULT_CHARTS_DIR):
    """Return existing, local chart PNGs linked from current dashboard HTML."""
    reports_dir = Path(reports_dir)
    charts_dir = Path(charts_dir).resolve()
    linked = set()
    for html_path in sorted(reports_dir.rglob("*.html")):
        parser = ImageLinkParser()
        parser.feed(html_path.read_text(encoding="utf-8", errors="ignore"))
        for value in parser.links:
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc:
                continue
            candidate = (html_path.parent / unquote(parsed.path)).resolve()
            if (
                candidate.suffix.lower() == ".png"
                and _is_within(candidate, charts_dir)
                and candidate.is_file()
            ):
                linked.add(candidate)
    return sorted(linked)


def _atomic_restore(backup, target):
    temporary = target.with_name(f".{target.name}.restore.tmp")
    shutil.copy2(backup, temporary)
    os.replace(temporary, target)


def _write_manifest(path, records):
    columns = [
        "status", "chart_file", "original_width", "original_height",
        "original_bytes", "original_sha256", "new_width", "new_height",
        "new_bytes", "new_sha256", "backup_file",
    ]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)


def migration_inventory(reports_dir=DEFAULT_REPORTS_DIR,
                        charts_dir=DEFAULT_CHARTS_DIR):
    linked = collect_dashboard_pngs(reports_dir, charts_dir)
    records = []
    for path in linked:
        stats = chart_output.png_stats(path)
        target_width, target_height = chart_output.constrained_dimensions(
            stats.width, stats.height
        )
        records.append({
            "path": path,
            "stats": stats,
            "target_width": target_width,
            "target_height": target_height,
            "needs_resize": (target_width, target_height)
            != (stats.width, stats.height),
        })
    return records


def apply_migration(reports_dir=DEFAULT_REPORTS_DIR,
                    charts_dir=DEFAULT_CHARTS_DIR,
                    migrations_dir=DEFAULT_MIGRATIONS_DIR,
                    timestamp=None):
    charts_dir = Path(charts_dir).resolve()
    inventory = migration_inventory(reports_dir, charts_dir)
    candidates = [record for record in inventory if record["needs_resize"]]
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    migration_dir = Path(migrations_dir) / stamp
    if migration_dir.exists():
        raise FileExistsError(f"Migration directory already exists: {migration_dir}")
    backup_dir = migration_dir / "originals"
    backup_dir.mkdir(parents=True)
    manifest_path = migration_dir / "manifest.csv"

    records = []
    backups = {}
    try:
        for item in candidates:
            path = item["path"]
            relative = path.relative_to(charts_dir)
            backup = backup_dir / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            backups[path] = backup

        for item in candidates:
            path = item["path"]
            before, after = chart_output.resize_png_atomic(path)
            backup = backups[path]
            records.append({
                "status": "resized",
                "chart_file": str(path),
                "original_width": before.width,
                "original_height": before.height,
                "original_bytes": before.byte_size,
                "original_sha256": before.sha256,
                "new_width": after.width,
                "new_height": after.height,
                "new_bytes": after.byte_size,
                "new_sha256": after.sha256,
                "backup_file": str(backup),
            })
        _write_manifest(manifest_path, records)
    except Exception:
        for target, backup in backups.items():
            _atomic_restore(backup, target)
        rollback_records = []
        for item in candidates:
            before = item["stats"]
            backup = backups.get(item["path"], "")
            rollback_records.append({
                "status": "rolled_back",
                "chart_file": str(item["path"]),
                "original_width": before.width,
                "original_height": before.height,
                "original_bytes": before.byte_size,
                "original_sha256": before.sha256,
                "new_width": "",
                "new_height": "",
                "new_bytes": "",
                "new_sha256": "",
                "backup_file": str(backup),
            })
        _write_manifest(manifest_path, rollback_records)
        raise
    return {
        "linked_count": len(inventory),
        "resized_count": len(candidates),
        "migration_dir": migration_dir,
        "manifest_path": manifest_path,
        "records": records,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Resize dashboard-linked PNGs to a 1920x1280 envelope."
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes; otherwise perform a dry run.")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--charts-dir", type=Path, default=DEFAULT_CHARTS_DIR)
    parser.add_argument("--migrations-dir", type=Path, default=DEFAULT_MIGRATIONS_DIR)
    return parser.parse_args()


def main():
    args = parse_args()
    inventory = migration_inventory(args.reports_dir, args.charts_dir)
    candidates = [record for record in inventory if record["needs_resize"]]
    original_bytes = sum(record["stats"].byte_size for record in candidates)
    print(
        f"Dashboard-linked PNGs: {len(inventory)}; "
        f"need resize: {len(candidates)}; "
        f"current size: {original_bytes / 1024 / 1024:.1f} MB"
    )
    if not args.apply:
        print("Dry run only. Re-run with --apply to back up and resize these files.")
        return 0
    result = apply_migration(
        args.reports_dir, args.charts_dir, args.migrations_dir
    )
    new_bytes = sum(record["new_bytes"] for record in result["records"])
    print(
        f"Resized {result['resized_count']} PNGs to at most "
        f"{chart_output.CHART_PNG_MAX_WIDTH}x{chart_output.CHART_PNG_MAX_HEIGHT}."
    )
    print(f"New size: {new_bytes / 1024 / 1024:.1f} MB")
    print(f"Manifest and backups: {result['migration_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
