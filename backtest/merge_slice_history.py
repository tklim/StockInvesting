"""Fold legacy per-slice fund folders into their fund-group folder.

Runs made before `--fund-group` existed wrote history into their own
`outputs/funds/<TICKER>-<N>Y/` folder. Current runs route every slice of a ticker
into the group folder instead (`fund_group_from_label` in common.py strips the
`-NY` suffix), record the group in the `fund_label` column, and keep the slice
name in the `fund_slice_label` column and in per-slice filenames. That leaves the
old slice folders behind holding rows that exist nowhere else.

This script only relocates rows; it does not rewrite their `fund_label` values.
Run `backfill_fund_label.py` afterwards to regroup any legacy labels it moved.

This script appends those orphaned rows into the group history files, skipping any
row already present, then optionally removes the emptied legacy folder. Derived
files (`*-top5_parameter_sets.csv`) are never merged: the group folder regenerates
them per slice on every run, so the copy there is authoritative.

Appends happen under the same cross-process lock the backtester uses, so this is
safe to run while backtests are appending to the same files.

Usage:
    python merge_slice_history.py                  # dry run: report what would move
    python merge_slice_history.py --apply          # perform the merge
    python merge_slice_history.py --apply --remove # merge, then delete legacy folders
    python merge_slice_history.py --slices AAPL-3Y # limit to specific slice labels
"""

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from common import OUTPUTS_DIR, file_lock, fund_group_from_label

FUNDS_DIR = OUTPUTS_DIR / "funds"

# Dedup keys per history kind, most specific first. A row counts as "already
# present" when its key tuple is already in the group file.
HISTORY_KINDS = {
    "run_history": ["run_id"],
    "tuning_history": ["run_id", "window_sequence", "param_set_id"],
    "window_history": ["run_id", "window_sequence"],
}

# Regenerated per slice by refresh_top5_parameter_sets(); never merge these.
DERIVED_SUFFIXES = ("-top5_parameter_sets.csv",)

SLICE_SUFFIX = re.compile(r"-\d+Y$", re.IGNORECASE)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge legacy per-slice fund folders into their fund-group folder.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--apply", action="store_true",
                        help="Actually write. Without this the script only reports.")
    parser.add_argument("--remove", action="store_true",
                        help="With --apply, delete each legacy folder after a verified merge.")
    parser.add_argument("--slices", nargs="+", default=None,
                        help="Slice labels to process (default: every -NY folder found).")
    parser.add_argument("--backup-dir", default=None,
                        help="Where to copy legacy folders before removal "
                             "(default: outputs/funds/_legacy_backup_<timestamp>).")
    return parser.parse_args()


def discover_slice_folders(only=None):
    """Legacy folders are those whose name still carries a -NY slice suffix."""
    if not FUNDS_DIR.exists():
        return []
    found = []
    for path in sorted(FUNDS_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        if not SLICE_SUFFIX.search(path.name):
            continue
        if only and path.name not in only:
            continue
        found.append(path)
    return found


def group_history_path(group, kind):
    return FUNDS_DIR / group / "tunings" / f"{group}-backtest_{kind}.csv"


def slice_history_path(slice_dir, kind):
    return slice_dir / "tunings" / f"{slice_dir.name}-backtest_{kind}.csv"


def missing_rows(legacy_path, group_path, keys):
    """Rows in the legacy file whose key tuple is absent from the group file.

    Returns (rows_to_append, note). rows_to_append is aligned to the group file's
    column order so the append is a plain tail-write.
    """
    legacy = pd.read_csv(legacy_path, low_memory=False)
    if legacy.empty:
        return None, "legacy file is empty"

    if not group_path.exists():
        return legacy, "group file absent - all rows are new"

    group = pd.read_csv(group_path, low_memory=False)
    usable = [k for k in keys if k in legacy.columns and k in group.columns]
    if not usable:
        return None, f"no shared dedup key from {keys}; refusing to guess"

    group_keys = set(map(tuple, group[usable].astype(str).values))
    legacy_keys = legacy[usable].astype(str).apply(tuple, axis=1)
    new = legacy[~legacy_keys.isin(group_keys)].copy()
    if new.empty:
        return None, f"all {len(legacy)} row(s) already present (key {usable})"

    extra = [c for c in new.columns if c not in group.columns]
    if extra:
        # Widening would require rewriting the whole group file; flag instead of
        # silently dropping data.
        return new, f"WARNING legacy has {len(extra)} column(s) absent from group: {extra[:4]}"

    return new.reindex(columns=group.columns), f"{len(new)} new row(s) by key {usable}"


def append_rows(group_path, rows):
    """Append under the shared lock; returns (before, after) row counts."""
    with file_lock(group_path):
        before = sum(1 for _ in open(group_path, encoding="utf-8", errors="replace")) - 1
        rows.to_csv(group_path, mode="a", index=False, header=False)
        after = sum(1 for _ in open(group_path, encoding="utf-8", errors="replace")) - 1
    return before, after


def report_migrations(slice_dir, group):
    """Per-run report CSVs to move into the group's reports/ folder.

    Report filenames already carry the slice label and a run timestamp, so they are
    unique artifacts rather than derived summaries - the group folder is simply where
    current runs put them. Anything already present at the destination is left alone.
    """
    source_dir = slice_dir / "reports"
    if not source_dir.is_dir():
        return [], []
    destination_dir = FUNDS_DIR / group / "reports"
    to_move, already_there = [], []
    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            continue
        destination = destination_dir / path.name
        (already_there if destination.exists() else to_move).append((path, destination))
    return to_move, already_there


def leftover_files(slice_dir, migrating):
    """Files in the legacy folder that this script neither merges nor moves."""
    merged_names = {slice_history_path(slice_dir, kind).name for kind in HISTORY_KINDS}
    moving = {source for source, _ in migrating}
    leftovers = []
    for path in sorted(slice_dir.rglob("*")):
        if path.is_dir() or path.name in merged_names or path in moving:
            continue
        kind = "derived, regenerated in group folder" if path.name.endswith(DERIVED_SUFFIXES) else "unrecognised"
        leftovers.append((path, kind))
    return leftovers


def main():
    args = parse_args()
    slice_dirs = discover_slice_folders(args.slices)
    if not slice_dirs:
        print("No legacy -NY slice folders found under outputs/funds/. Nothing to do.")
        return 0

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] {len(slice_dirs)} legacy slice folder(s): "
          f"{', '.join(d.name for d in slice_dirs)}\n")

    planned, moves = {}, {}
    for slice_dir in slice_dirs:
        group = fund_group_from_label(slice_dir.name)
        if group == slice_dir.name:
            print(f"{slice_dir.name}: group name is unchanged - not a slice folder, skipping.\n")
            continue

        print(f"{slice_dir.name}  ->  funds/{group}/")
        per_slice = []
        for kind, keys in HISTORY_KINDS.items():
            legacy_path = slice_history_path(slice_dir, kind)
            if not legacy_path.exists():
                print(f"  {kind:15s} (no legacy file)")
                continue
            group_path = group_history_path(group, kind)
            rows, note = missing_rows(legacy_path, group_path, keys)
            print(f"  {kind:15s} {note}")
            if rows is not None and not note.startswith("WARNING"):
                per_slice.append((group_path, rows))
            elif note.startswith("WARNING"):
                print(f"  {'':15s} -> skipped; resolve the column mismatch first")

        to_move, already_there = report_migrations(slice_dir, group)
        if to_move:
            print(f"  reports         {len(to_move)} file(s) to move into funds/{group}/reports/")
        if already_there:
            print(f"  reports         {len(already_there)} already present at destination (left alone)")

        for path, why in leftover_files(slice_dir, to_move + already_there):
            print(f"  not merged:     {path.relative_to(FUNDS_DIR)}  ({why})")
        planned[slice_dir] = per_slice
        moves[slice_dir] = to_move
        print()

    total = sum(len(rows) for items in planned.values() for _, rows in items)
    move_total = sum(len(items) for items in moves.values())
    if not args.apply:
        print(f"Would append {total} row(s) and move {move_total} report file(s). "
              "Re-run with --apply to perform it.")
        return 0

    if total == 0:
        print("Nothing to append.")
    for slice_dir, items in planned.items():
        for group_path, rows in items:
            before, after = append_rows(group_path, rows)
            gained = after - before
            status = "ok" if gained == len(rows) else f"MISMATCH (expected +{len(rows)})"
            print(f"appended {len(rows):4d} -> {group_path.name}: {before} -> {after} rows  {status}")

    for slice_dir, items in moves.items():
        for source, destination in items:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                print(f"skipped move (destination appeared): {destination.name}")
                continue
            shutil.move(str(source), str(destination))
        if items:
            print(f"moved {len(items):4d} report file(s) from {slice_dir.name} -> "
                  f"{items[0][1].parent.relative_to(FUNDS_DIR)}/")

    if not args.remove:
        print("\nMerge complete. Legacy folders left in place; re-run with --remove to delete them.")
        return 0

    backup_root = Path(args.backup_dir) if args.backup_dir else (
        FUNDS_DIR / f"_legacy_backup_{datetime.now():%Y%m%d_%H%M%S}"
    )
    backup_root.mkdir(parents=True, exist_ok=True)
    print()
    for slice_dir in planned:
        destination = backup_root / slice_dir.name
        shutil.copytree(slice_dir, destination)
        shutil.rmtree(slice_dir)
        print(f"removed {slice_dir.name}  (backup: {destination.relative_to(OUTPUTS_DIR)})")
    print(f"\nBackups kept under {backup_root}. Delete them once you are satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
