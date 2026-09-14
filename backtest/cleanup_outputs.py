"""Archive unused chart PNGs; dry-run by default, --apply moves into todelete.

All modes protect HTML report dependencies. General charts cleanup also protects
chart-bearing tuning CSV references; non-final cleanup deliberately ignores them.
No permanent deletion is performed.
"""
from __future__ import annotations

import argparse
import csv
import html
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from chart_inventory import scan_reports, require_unchanged, sha256_file, walk_files

DEFAULT_OUTPUTS_DIR = Path(__file__).resolve().parent / 'outputs'
FINAL_CHART_RE = re.compile(
    r'^(?P<label>.+)-final-(?P<kind>technical|latest|simple)-'
    r'(?P<timestamp>\d{8}-\d{6})\.png$', re.IGNORECASE)


@dataclass
class CleanupResult:
    total_files: int = 0
    png_files: int = 0
    protected_files: int = 0
    recent_files: int = 0
    out_of_scope_files: int = 0
    eligible_files: int = 0
    eligible_bytes: int = 0
    moved_files: int = 0
    moved_bytes: int = 0
    non_png_files: int = 0
    missing_references: list = field(default_factory=list)
    bad_references: list = field(default_factory=list)
    planned_moves: list = field(default_factory=list)
    manifest_path: Path | None = None
    blocked: bool = False


def _reference_to_chart_path(raw, charts):
    # CSVs historically contain absolute paths, bare names and outputs/charts paths.
    value = html.unescape(unquote(raw)).replace('\\', '/')
    marker = '/charts/'
    if marker in value.lower():
        value = value[value.lower().rfind(marker) + len(marker):]
    candidate = (charts / value).resolve()
    return candidate if candidate.is_relative_to(charts) else None


def csv_protection(outputs):
    charts = (outputs / 'charts').resolve()
    protected, missing, bad, fingerprints = set(), [], [], {}
    tunings = outputs / 'tunings'
    if not tunings.exists():
        return protected, missing, bad, fingerprints
    for path in walk_files(tunings):
        if path.suffix.lower() != '.csv':
            continue
        fingerprints[str(path)] = sha256_file(path)
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            columns = [c for c in (reader.fieldnames or []) if 'chart' in c.lower()]
            if not columns:
                continue
            for row in reader:
                for column in columns:
                    raw = row.get(column)
                    if not raw or not raw.lower().endswith('.png'):
                        continue
                    candidate = _reference_to_chart_path(raw, charts)
                    if candidate is None:
                        bad.append(f'{path.name}: unsafe chart {raw}')
                    elif candidate.is_file():
                        protected.add(candidate)
                    else:
                        missing.append(f'{path.name}: missing {raw}')
    return protected, missing, bad, fingerprints


def newest_final_charts(files):
    grouped = {}
    for path in files:
        match = FINAL_CHART_RE.fullmatch(path.name)
        if not match:
            continue
        # Invalid date stamps block planning rather than silently selecting a version.
        stamp = datetime.strptime(match['timestamp'], '%Y%m%d-%H%M%S')
        grouped.setdefault((match['label'].casefold(), match['kind'].casefold()), []).append((stamp, path))
    # Keep all tied newest timestamps, including copies in different subdirectories.
    return {p for versions in grouped.values() for stamp, p in versions
            if stamp == max(s for s, _ in versions)}


def _unique_destination(directory, name):
    destination = directory / name
    index = 1
    while destination.exists():
        destination = directory / f'{Path(name).stem}__{index}{Path(name).suffix}'
        index += 1
    return destination


def move_no_replace(source, destination):
    """Same-volume archival via exclusive hard link then unlink; never overwrite.

    A crash between these operations leaves both copies; the prewritten journal
    and SHA-256 identify them. No copy/delete fallback across volumes is allowed.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.link(source, destination)
    source.unlink()


def _move_planned_charts(result, archive, reason, run_at, validate):
    validate()
    if not result.planned_moves:
        return
    archive.mkdir(parents=True, exist_ok=True)
    result.manifest_path = archive / f'cleanup_manifest_{run_at:%Y%m%d_%H%M%S}_{uuid4().hex}.csv'
    rows = []
    for source, destination in result.planned_moves:
        rows.append(dict(source=str(source), destination=str(destination),
                         size_bytes=source.stat().st_size, sha256=sha256_file(source),
                         reason=reason, run_at=run_at.isoformat(), status='planned'))
    with result.manifest_path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()

        def record(row, status):
            writer.writerow(dict(row, status=status))
            stream.flush()
            os.fsync(stream.fileno())

        for row in rows:
            record(row, 'planned')
        attempted = []
        try:
            validate()  # After hashing and journaling, immediately before moves.
            for row in rows:
                source, destination = Path(row['source']), Path(row['destination'])
                if sha256_file(source) != row['sha256']:
                    raise ValueError(f'Chart changed after planning: {source}')
                if destination.exists():
                    raise FileExistsError(destination)
                record(row, 'moving')
                attempted.append(row)
                move_no_replace(source, destination)
                record(row, 'moved')
                result.moved_files += 1
                result.moved_bytes += row['size_bytes']
            validate()
            for row in rows:
                record(row, 'committed')
        except BaseException as error:
            rollback_errors = []
            for row in reversed(attempted):
                source, destination = Path(row['source']), Path(row['destination'])
                try:
                    if destination.exists():
                        if sha256_file(destination) != row['sha256']:
                            raise ValueError(f'Archived file changed: {destination}')
                        if source.exists():
                            if not os.path.samefile(source, destination):
                                raise FileExistsError(f'Restore destination occupied: {source}')
                            destination.unlink()  # Remove only duplicate hard link from interrupted move.
                        else:
                            move_no_replace(destination, source)
                    elif not source.exists():
                        raise FileNotFoundError(f'Both locations missing: {source}')
                    record(row, 'rolled_back')
                except BaseException as rollback_error:
                    rollback_errors.append(str(rollback_error))
                    record(row, 'rollback_failed')
            result.moved_files = result.moved_bytes = 0
            if rollback_errors:
                raise RuntimeError(f'Recovery required using {result.manifest_path}: '
                                   + '; '.join(rollback_errors)) from error
            raise


def _cleanup(
    outputs_dir,
    *,
    final=False,
    non_final=False,
    older_than_days=30,
    apply=False,
    now=None,
):
    if final and non_final:
        raise ValueError('final and non_final cleanup modes are mutually exclusive')
    if older_than_days < 0:
        raise ValueError('older_than_days must be zero or greater')
    outputs = Path(outputs_dir).resolve()
    charts = outputs / 'charts'
    if not charts.is_dir():
        raise FileNotFoundError(f'Charts directory does not exist: {charts}')
    run_at = now or datetime.now()
    inventory = scan_reports(outputs / 'reports', charts)
    result = CleanupResult(missing_references=list(inventory.missing),
                           bad_references=list(inventory.errors),
                           blocked=bool(inventory.missing or inventory.errors))
    files = sorted(walk_files(charts))
    protected = {charts / name for name in inventory.charts}
    if not non_final:
        protected.update(newest_final_charts(files))
    csv_state = None
    if not final and not non_final:
        csv_state = csv_protection(outputs)
        protected.update(csv_state[0])
        result.missing_references.extend(csv_state[1])
        result.bad_references.extend(csv_state[2])
    archive = outputs / 'todelete' / 'charts'
    if final:
        archive /= 'final-versions'
    elif non_final:
        archive /= 'non-final'
    archive /= run_at.strftime('%Y-%m-%d')
    if not archive.resolve().is_relative_to(outputs) or archive.resolve().is_relative_to(charts):
        raise ValueError(f'Archive escapes outputs or overlaps charts: {archive}')
    result.total_files = len(files)
    for path in files:
        if path.suffix.lower() != '.png':
            result.non_png_files += 1
            continue
        result.png_files += 1
        is_final = bool(FINAL_CHART_RE.fullmatch(path.name))
        if non_final and is_final:
            result.out_of_scope_files += 1
        elif path in protected:
            result.protected_files += 1
        elif final and not is_final:
            result.out_of_scope_files += 1
        elif not final and datetime.fromtimestamp(path.stat().st_mtime) >= run_at - timedelta(days=older_than_days):
            result.recent_files += 1
        else:
            result.eligible_files += 1
            result.eligible_bytes += path.stat().st_size
            relative = path.relative_to(charts)
            result.planned_moves.append((path, _unique_destination(archive / relative.parent, path.name)))

    def validate():
        inventory.require_valid()
        require_unchanged(inventory, outputs / 'reports', charts)
        if not archive.resolve().is_relative_to(outputs) or archive.resolve().is_relative_to(charts):
            raise ValueError(f'Archive path changed or overlaps charts: {archive}')
        for source, destination in result.planned_moves:
            if not destination.resolve().is_relative_to(archive.resolve()):
                raise ValueError(f'Archive destination escapes archive: {destination}')
        if csv_state is not None:
            current = csv_protection(outputs)
            if csv_state[2]:
                raise ValueError('Unsafe CSV chart references: ' + '; '.join(csv_state[2]))
            if current != csv_state:
                raise ValueError('Tuning CSV inventory changed; retry after generation finishes')

    if apply:
        if final:
            reason = 'superseded final chart; report links and newest retained'
        elif non_final:
            reason = f'unpublished non-final PNG older than {older_than_days} days'
        else:
            reason = f'unreferenced PNG older than {older_than_days} days'
        _move_planned_charts(result, archive, reason, run_at, validate)
    return result


def cleanup_charts(outputs_dir=DEFAULT_OUTPUTS_DIR, *, older_than_days=30, apply=False, now=None):
    return _cleanup(outputs_dir, final=False, older_than_days=older_than_days, apply=apply, now=now)


def cleanup_final_charts(outputs_dir=DEFAULT_OUTPUTS_DIR, *, apply=False, now=None):
    return _cleanup(outputs_dir, final=True, apply=apply, now=now)


def cleanup_non_final_charts(
    outputs_dir=DEFAULT_OUTPUTS_DIR,
    *,
    older_than_days=30,
    apply=False,
    now=None,
):
    """Archive old non-final PNGs unused by current published HTML reports."""
    return _cleanup(
        outputs_dir,
        non_final=True,
        older_than_days=older_than_days,
        apply=apply,
        now=now,
    )


def print_result(result, *, apply, verbose):
    print(f"{'APPLY' if apply else 'DRY RUN'}: chart cleanup")
    print(f'Files scanned: {result.total_files}; PNG: {result.png_files}')
    print(
        f'Protected: {result.protected_files}; recent: {result.recent_files}; '
        f'final/out of scope: {result.out_of_scope_files}'
    )
    print(f'Eligible: {result.eligible_files} ({result.eligible_bytes / 1048576:.1f} MiB); moved: {result.moved_files}')
    print(f'Missing references: {len(result.missing_references)}; errors: {len(result.bad_references)}')
    if result.blocked:
        print('Application blocked: repair report inventory before cleanup.')
    if result.manifest_path:
        print(f'Journal: {result.manifest_path}')
    if verbose:
        for source, destination in result.planned_moves:
            print(f'PLAN: {source} -> {destination}')
    issues = result.missing_references + result.bad_references
    for issue in (issues if verbose else issues[:20]):
        print(issue)
    if not verbose and len(issues) > 20:
        print(f'{len(issues) - 20} more diagnostics; use --verbose for all.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('charts', 'final-charts', 'non-final-charts'):
        sub = commands.add_parser(name)
        sub.add_argument('--apply', action='store_true')
        sub.add_argument('--verbose', action='store_true')
        if name in ('charts', 'non-final-charts'):
            sub.add_argument('--older-than-days', type=int, default=30)
    args = parser.parse_args()
    try:
        result = _cleanup(
            DEFAULT_OUTPUTS_DIR,
            final=args.command == 'final-charts',
            non_final=args.command == 'non-final-charts',
            older_than_days=getattr(args, 'older_than_days', 30),
            apply=args.apply,
        )
        print_result(result, apply=args.apply, verbose=args.verbose)
        return 2 if result.blocked or result.bad_references else 0
    except (OSError, ValueError, RuntimeError, csv.Error) as error:
        print(f'ERROR: {error}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
