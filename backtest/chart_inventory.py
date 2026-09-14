"""Shared, fail-closed inventory of local PNG dependencies in HTML reports."""

from dataclasses import dataclass, field
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import os


def sha256_file(path):
    with Path(path).open('rb') as stream:
        digest = sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def walk_files(root):
    """Unlike rglob, propagate enumeration failures; never follow directory links."""
    def fail(error):
        raise error
    for directory, dirs, names in os.walk(root, onerror=fail):
        dirs[:] = sorted(d for d in dirs if not d.startswith('~$'))
        for name in dirs + names:
            path = Path(directory) / name
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise ValueError(f'Linked filesystem entry is unsupported: {path}')
        for name in sorted(names):
            if not name.startswith('~$'):
                yield Path(directory) / name


class PNGParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('src', 'data-src', 'href') and value:
                self.references.append(value)
            if tag == 'base' and key == 'href':
                raise ValueError('HTML base href is unsupported; use report-relative URLs')


@dataclass
class Inventory:
    charts: dict = field(default_factory=dict)  # chart-relative path -> owning reports
    reports: dict = field(default_factory=dict)  # report-relative path -> SHA-256
    missing: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def require_valid(self):
        issues = self.errors + self.missing
        if issues:
            raise ValueError('Report chart validation failed:\n' + '\n'.join(issues))
        return self

    def fingerprint(self):
        return (self.reports, self.charts)

    def manifest(self):
        return {'schema_version': 2, 'charts': sorted(self.charts),
                'reports': {report: sorted(c for c, owners in self.charts.items() if report in owners)
                            for report in sorted(self.reports)}}


def scan_reports(reports_dir, charts_dir):
    reports_dir, charts_dir = Path(reports_dir).resolve(), Path(charts_dir).resolve()
    inventory = Inventory()
    if not reports_dir.is_dir() or not charts_dir.is_dir():
        inventory.errors.append(f'Reports/charts directory missing: {reports_dir}, {charts_dir}')
        return inventory
    try:
        reports = [p for p in walk_files(reports_dir) if p.suffix.lower() in ('.html', '.htm')]
        for report in reports:
            owner = report.relative_to(reports_dir).as_posix()
            try:
                data = report.read_bytes()
                inventory.reports[owner] = sha256(data).hexdigest()
                if not data.strip():
                    raise ValueError('empty HTML report')
                parser = PNGParser()
                parser.feed(data.decode('utf-8-sig'))
                parser.close()
                for raw in parser.references:
                    url = urlsplit(raw.replace('\\', '/'))
                    if url.netloc or (url.scheme and len(url.scheme) != 1 and url.scheme.lower() != 'file'):
                        continue
                    decoded = unquote(url.path).replace('\\', '/')
                    if not decoded.lower().endswith('.png'):
                        continue
                    if Path(decoded).name.startswith('~$'):
                        continue
                    if url.scheme or decoded.startswith('/') or Path(decoded).is_absolute():
                        raise ValueError(f'nonportable PNG reference: {raw}')
                    candidate = (report.parent / decoded).resolve()
                    if not candidate.is_relative_to(charts_dir):
                        raise ValueError(f'PNG reference escapes charts directory: {raw}')
                    name = candidate.relative_to(charts_dir).as_posix()
                    inventory.charts.setdefault(name, set()).add(owner)
                    if not candidate.is_file():
                        inventory.missing.append(f'{owner}: missing {name}')
            except (OSError, UnicodeError, ValueError) as error:
                inventory.errors.append(f'{owner}: {error}')
        if not reports:
            inventory.errors.append(f'No HTML reports found: {reports_dir}')
    except (OSError, ValueError) as error:
        inventory.errors.append(str(error))
    return inventory


def require_unchanged(previous, reports_dir, charts_dir):
    current = scan_reports(reports_dir, charts_dir).require_valid()
    if current.fingerprint() != previous.fingerprint():
        raise ValueError('Report inventory changed during operation; retry after generation finishes')
    return current
