"""Validate and build a portable static dashboard site from current reports."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from chart_inventory import scan_reports, require_unchanged, sha256_file


MANAGED = ('reports', 'charts', 'index.html', 'chart-manifest.json')


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports-dir', type=Path, required=True)
    parser.add_argument('--charts-dir', type=Path, required=True)
    parser.add_argument('--site-dir', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true', help='Validate without writing files.')
    return parser.parse_args()


def validate_roots(reports, charts, site):
    for left, right in ((reports, charts), (reports, site), (charts, site)):
        if left.is_relative_to(right) or right.is_relative_to(left):
            raise ValueError(f'Source/destination directories overlap: {left}, {right}')
    for name in MANAGED:
        path = site / name
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError(f'Managed destination is a filesystem link: {path}')


def install_stage(stage, site, backup):
    """Swap only managed entries, restoring the previous build on failure."""
    saved, installed = [], []
    site.mkdir(parents=True, exist_ok=True)
    backup.mkdir()
    try:
        for name in MANAGED:
            old = site / name
            if old.exists():
                old.rename(backup / name)
                saved.append(name)
            (stage / name).rename(old)
            installed.append(name)
    except BaseException as error:
        try:
            for name in reversed(installed):
                (site / name).rename(stage / name)
            for name in reversed(saved):
                (backup / name).rename(site / name)
        except BaseException as rollback_error:
            raise RuntimeError(f'Publish rollback incomplete; recovery files at {backup.parent}: '
                               f'{rollback_error}') from error
        raise


def build_site(reports_dir, charts_dir, site_dir, *, check_only=False):
    reports, charts, site = (Path(p).resolve() for p in (reports_dir, charts_dir, site_dir))
    validate_roots(reports, charts, site)
    inventory = scan_reports(reports, charts).require_valid()
    if not (reports / 'dashboard.html').is_file():
        raise ValueError('Required landing report dashboard.html is missing')
    if check_only:
        return inventory
    site.parent.mkdir(parents=True, exist_ok=True)
    # Keep recovery files on failure, including an interrupted installation.
    work = Path(tempfile.mkdtemp(prefix='.report-build-', dir=site.parent))
    stage = work / 'stage'
    stage.mkdir()
    shutil.copytree(reports, stage / 'reports', ignore=shutil.ignore_patterns('~$*'))
    (stage / 'charts').mkdir()
    for name in sorted(inventory.charts):
        source, destination = charts / name, stage / 'charts' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if sha256_file(source) != sha256_file(destination):
            raise ValueError(f'Chart changed while copying: {name}; staging retained at {work}')
    staged = scan_reports(stage / 'reports', stage / 'charts').require_valid()
    if staged.fingerprint() != inventory.fingerprint():
        raise ValueError(f'Reports changed while copying; staging retained at {work}')
    require_unchanged(inventory, reports, charts)
    (stage / 'index.html').write_text(
        '<!doctype html>\n<meta charset="utf-8">\n'
        '<meta http-equiv="refresh" content="0; url=reports/dashboard.html">\n'
        '<title>StockInvesting dashboards</title>\n'
        '<p><a href="reports/dashboard.html">Open dashboards</a></p>\n', encoding='utf-8')
    (stage / 'chart-manifest.json').write_text(
        json.dumps(inventory.manifest(), indent=2) + '\n', encoding='utf-8')
    install_stage(stage, site, work / 'backup')
    # Exact mkdtemp-owned directory: only this build and the old managed outputs.
    shutil.rmtree(work)
    return inventory


def main():
    args = parse_args()
    try:
        inventory = build_site(args.reports_dir, args.charts_dir, args.site_dir,
                               check_only=args.check_only)
    except (OSError, ValueError, RuntimeError) as error:
        print(f'ERROR: {error}')
        return 2
    verb = 'Validated' if args.check_only else 'Built site with'
    print(f'{verb} {len(inventory.charts)} chart images from {len(inventory.reports)} reports.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
