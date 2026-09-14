import csv
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import cleanup_outputs as cleanup
import publish_reports_site as publisher
from chart_inventory import scan_reports, sha256_file


class InventoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.outputs = self.root / 'outputs'
        self.reports = self.outputs / 'reports'
        self.charts = self.outputs / 'charts'
        self.site = self.root / 'site'
        self.reports.mkdir(parents=True)
        self.charts.mkdir()
        self.report('dashboard.html', '<html>Dashboard</html>')

    def report(self, name, content):
        path = self.reports / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def chart(self, name):
        path = self.charts / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'PNG fixture ' + name.encode())
        os.utime(path, (1700000000, 1700000000))
        return path

    def build(self, **kwargs):
        return publisher.build_site(self.reports, self.charts, self.site, **kwargs)

    def test_nested_encoded_legacy_external_and_temp_references(self):
        name = 'nested/a & b.PNG'
        self.chart(name)
        self.report('funds/AAPL.htm', '<img src="../../charts/nested/a%20%26%20b.PNG?v=1#x">'
                    '<button data-src="../../charts/nested/a &amp; b.PNG"></button>'
                    '<a href="../../charts/nested/a%20%26%20b.PNG">chart</a>'
                    '<img src="https://example.com/missing.png">'
                    '<img src="//example.com/missing.png">')
        self.report('~$ignore.html', '<img src="../charts/missing.png">')
        (self.reports / '~$locked.xlsx').write_bytes(b'temp')
        inventory = self.build()
        self.assertEqual(set(inventory.charts), {name})
        self.assertEqual(inventory.charts[name], {'funds/AAPL.htm'})
        self.assertTrue((self.site / 'charts' / name).is_file())
        self.assertFalse((self.site / 'reports' / '~$locked.xlsx').exists())
        manifest = json.loads((self.site / 'chart-manifest.json').read_text())
        self.assertEqual(manifest['schema_version'], 2)
        self.assertEqual(manifest['reports']['funds/AAPL.htm'], [name])

    def test_missing_unsafe_empty_and_unreadable_block_apply(self):
        old = self.chart('old.png')
        for content in ('<img src="../charts/missing.png">',
                        '<img src="../../outside.png">', '',
                        '<img src="../charts/%2e%2e/outside.png">'):
            with self.subTest(content=content):
                self.report('dashboard.html', content)
                with self.assertRaises(ValueError):
                    cleanup.cleanup_charts(self.outputs, older_than_days=0, apply=True)
                self.assertTrue(old.exists())
                self.assertFalse((self.outputs / 'todelete').exists())
        self.report('dashboard.html', '<html>ok</html>')
        original = Path.read_bytes
        def unreadable(path):
            if path == self.reports / 'dashboard.html':
                raise PermissionError('locked report')
            return original(path)
        with patch.object(Path, 'read_bytes', unreadable):
            with self.assertRaisesRegex(ValueError, 'locked report'):
                cleanup.cleanup_charts(self.outputs, apply=True)
        (self.reports / 'dashboard.html').unlink()
        with self.assertRaises(ValueError):
            cleanup.cleanup_final_charts(self.outputs, apply=True)
        self.reports.rmdir()
        with self.assertRaises(ValueError):
            cleanup.cleanup_final_charts(self.outputs, apply=True)

    def test_end_to_end_cleanup_preserves_published_bytes_and_newest(self):
        linked = self.chart('AAPL-final-latest-20260101-100000.png')
        stale = self.chart('nested/AAPL-final-latest-20260201-100000.png')
        newest = self.chart('AAPL-final-latest-20260301-100000.png')
        self.report('funds/AAPL.html', f'<img src="../../charts/{linked.name}">')
        self.build()
        before = sha256_file(self.site / 'charts' / linked.name)
        result = cleanup.cleanup_final_charts(self.outputs, apply=True)
        self.assertTrue(linked.exists())
        self.assertTrue(newest.exists())
        self.assertFalse(stale.exists())
        self.assertTrue((result.manifest_path.parent / 'nested' / stale.name).exists())
        with result.manifest_path.open(encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([r['status'] for r in rows], ['planned', 'moving', 'moved', 'committed'])
        self.assertEqual(len(rows[0]['sha256']), 64)
        self.build()
        self.assertEqual(before, sha256_file(self.site / 'charts' / linked.name))
        scan_reports(self.reports, self.charts).require_valid()

    def test_general_cleanup_also_keeps_newest(self):
        newest = self.chart('AAPL-final-simple-20260301-100000.png')
        self.chart('AAPL-final-simple-20260201-100000.png')
        result = cleanup.cleanup_charts(self.outputs, older_than_days=0, apply=True)
        self.assertTrue(newest.exists())
        self.assertEqual(result.moved_files, 1)

    def test_non_final_cleanup_archives_old_tuned_charts_only(self):
        old_names = (
            'AAPL-4Y-1.0Y-6M-generic-ga10-tuned-20260725-171239.png',
            'AAPL-4Y-1.0Y-6M-generic-ga10-tuned-20260725-171702.png',
        )
        old = [self.chart(name) for name in old_names]
        published = self.chart('published-tuned-20260701-100000.png')
        recent = self.chart('recent-tuned-20260815-100000.png')
        final = self.chart('AAPL-final-simple-20260701-100000.png')
        recent_timestamp = datetime(2026, 8, 16).timestamp()
        os.utime(recent, (recent_timestamp, recent_timestamp))
        self.report('funds/AAPL.html', f'<img src="../../charts/{published.name}">')

        result = cleanup.cleanup_non_final_charts(
            self.outputs, now=datetime(2026, 9, 14),
        )

        planned = {source.name for source, _ in result.planned_moves}
        self.assertEqual(planned, set(old_names))
        self.assertEqual(result.eligible_files, 2)
        self.assertEqual(result.protected_files, 1)
        self.assertEqual(result.recent_files, 1)
        self.assertEqual(result.out_of_scope_files, 1)
        self.assertTrue(all(path.exists() for path in old))
        self.assertTrue(final.exists())

    def test_non_final_cleanup_ignores_csv_only_references_and_preserves_paths(self):
        old = self.chart('nested/old-tuned.png')
        tunings = self.outputs / 'tunings'
        tunings.mkdir()
        with (tunings / 'history.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(['chart_file'])
            writer.writerow([str(old)])

        result = cleanup.cleanup_non_final_charts(
            self.outputs, older_than_days=30, apply=True, now=datetime(2026, 9, 14),
        )

        self.assertFalse(old.exists())
        self.assertTrue((result.manifest_path.parent / 'nested' / old.name).exists())

    def test_non_final_cleanup_uses_shared_validation_and_rollback(self):
        old = self.chart('old-tuned.png')
        original = cleanup.move_no_replace

        def changing_report(source, destination):
            original(source, destination)
            self.report('new.html', '<img src="../charts/old-tuned.png">')

        with patch.object(cleanup, 'move_no_replace', side_effect=changing_report):
            with self.assertRaises(ValueError):
                cleanup.cleanup_non_final_charts(
                    self.outputs, older_than_days=30, apply=True, now=datetime(2026, 9, 14),
                )
        self.assertTrue(old.exists())
        journal = next((self.outputs / 'todelete').rglob('cleanup_manifest_*.csv'))
        self.assertIn('rolled_back', journal.read_text())

    def test_post_move_report_change_rolls_back(self):
        old = self.chart('old.png')
        original = cleanup.move_no_replace
        def changing(source, destination):
            original(source, destination)
            if source == old:
                self.report('new.html', '<img src="../charts/old.png">')
        with patch.object(cleanup, 'move_no_replace', side_effect=changing):
            with self.assertRaises(ValueError):
                cleanup.cleanup_charts(self.outputs, older_than_days=0, apply=True)
        self.assertTrue(old.exists())
        journal = next((self.outputs / 'todelete').rglob('cleanup_manifest_*.csv'))
        self.assertIn('rolled_back', journal.read_text())

    def test_pre_move_report_change_blocks_moves(self):
        self.chart('old.png')
        original = cleanup.sha256_file
        def changing(path):
            self.report('new.html', '<html>new</html>')
            return original(path)
        with patch.object(cleanup, 'sha256_file', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'changed'):
                cleanup.cleanup_charts(self.outputs, older_than_days=0, apply=True)
        self.assertTrue((self.charts / 'old.png').exists())

    def test_interrupted_move_rolls_back_and_journal_exists_first(self):
        old = self.chart('old.png')
        original = cleanup.move_no_replace
        def interrupt(source, destination):
            if source == old:
                journal = next((self.outputs / 'todelete').rglob('cleanup_manifest_*.csv'))
                self.assertIn('moving', journal.read_text())
                original(source, destination)
                raise KeyboardInterrupt()
            original(source, destination)
        with patch.object(cleanup, 'move_no_replace', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                cleanup.cleanup_charts(self.outputs, older_than_days=0, apply=True)
        self.assertTrue(old.exists())

    def test_exclusive_move_does_not_overwrite_collision(self):
        source = self.chart('source.png')
        destination = self.chart('destination.png')
        before = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            cleanup.move_no_replace(source, destination)
        self.assertTrue(source.exists())
        self.assertEqual(destination.read_bytes(), before)

    def test_check_only_and_bad_build_leave_site_untouched(self):
        self.build(check_only=True)
        self.assertFalse(self.site.exists())
        self.build()
        before = (self.site / 'chart-manifest.json').read_bytes()
        self.report('bad.html', '<img src="../charts/missing.png">')
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(before, (self.site / 'chart-manifest.json').read_bytes())

    def test_publish_removes_stale_managed_entries_preserves_git(self):
        self.build()
        (self.site / '.git').mkdir()
        (self.site / '.git' / 'marker').write_text('keep')
        (self.site / 'reports' / 'stale.html').write_text('<img src="../charts/missing.png">')
        (self.site / 'charts' / 'stale.png').write_bytes(b'stale')
        self.build()
        self.assertFalse((self.site / 'reports' / 'stale.html').exists())
        self.assertFalse((self.site / 'charts' / 'stale.png').exists())
        self.assertEqual((self.site / '.git' / 'marker').read_text(), 'keep')

    def test_install_failure_restores_previous_site(self):
        self.build()
        before = (self.site / 'reports' / 'dashboard.html').read_bytes()
        self.report('dashboard.html', '<html>new generation</html>')
        original = Path.rename
        def fail(path, target):
            if path.name == 'charts' and path.parent.name == 'stage':
                raise PermissionError('injected install failure')
            return original(path, target)
        with patch.object(Path, 'rename', fail):
            with self.assertRaises(PermissionError):
                self.build()
        self.assertEqual((self.site / 'reports' / 'dashboard.html').read_bytes(), before)
        self.assertTrue((self.site / 'charts').is_dir())

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):
            publisher.build_site(self.reports, self.charts, self.outputs, check_only=True)

    def test_csv_retention_is_additional_only_for_general_mode(self):
        old = self.chart('AAPL-final-simple-20260101-100000.png')
        self.chart('AAPL-final-simple-20260301-100000.png')
        tunings = self.outputs / 'tunings'
        tunings.mkdir()
        with (tunings / 'history.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(['chart_file'])
            writer.writerow([str(old)])
        general = cleanup.cleanup_charts(self.outputs, older_than_days=0)
        final = cleanup.cleanup_final_charts(self.outputs)
        self.assertEqual(general.eligible_files, 0)
        self.assertEqual(final.eligible_files, 1)

    def test_multiple_linked_versions_survive(self):
        names = [f'AAPL-final-simple-20260{month}01-100000.png' for month in (1, 2, 3)]
        for name in names:
            self.chart(name)
        self.report('legacy.htm', ''.join(f'<a href="../charts/{name}">chart</a>' for name in names[:2]))
        self.assertEqual(cleanup.cleanup_final_charts(self.outputs, apply=True).moved_files, 0)

    def test_unreadable_directory_blocks_validation(self):
        with patch('chart_inventory.os.walk', side_effect=PermissionError('cannot enumerate')):
            with self.assertRaisesRegex(ValueError, 'cannot enumerate'):
                self.build(check_only=True)

    def test_interruption_between_link_and_unlink_keeps_original(self):
        source = self.chart('old.png')
        def interrupt(source, destination):
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, destination)
            raise KeyboardInterrupt()
        with patch.object(cleanup, 'move_no_replace', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                cleanup.cleanup_charts(self.outputs, older_than_days=0, apply=True)
        self.assertTrue(source.exists())
        self.assertEqual(list((self.outputs / 'todelete').rglob('old.png')), [])


if __name__ == '__main__':
    unittest.main()
