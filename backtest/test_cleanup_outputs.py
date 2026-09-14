import csv
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import cleanup_outputs


RUN_AT = datetime(2026, 9, 1, 21, 30, 0)


class ChartCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.outputs = Path(self.temp_dir.name) / "outputs"
        self.charts = self.outputs / "charts"
        self.reports = self.outputs / "reports"
        self.tunings = self.outputs / "tunings"
        for directory in (self.charts, self.reports, self.tunings):
            directory.mkdir(parents=True)
        (self.reports / 'dashboard.html').write_text('<html>Dashboard</html>', encoding='utf-8')

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_chart(self, name, days_old=31):
        path = self.charts / name
        path.write_bytes(b"png")
        timestamp = (RUN_AT - timedelta(days=days_old)).timestamp()
        os.utime(path, (timestamp, timestamp))
        return path

    def test_dry_run_preserves_files_and_archive(self):
        old_chart = self.add_chart("old.png")

        result = cleanup_outputs.cleanup_charts(self.outputs, now=RUN_AT)

        self.assertEqual(result.eligible_files, 1)
        self.assertEqual(result.moved_files, 0)
        self.assertTrue(old_chart.exists())
        self.assertFalse((self.outputs / "todelete").exists())

    def test_html_and_csv_references_protect_old_charts(self):
        html_chart = self.add_chart("html.png")
        csv_chart = self.add_chart("csv.png")
        missing_chart = "missing.png"
        (self.reports / "dashboard.html").write_text(
            '<img src="../charts/html.png"><img src="../charts/missing.png">',
            encoding="utf-8",
        )
        with (self.tunings / "history.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["chart_file", "label"])
            writer.writeheader()
            writer.writerow({"chart_file": str(csv_chart), "label": "kept"})

        result = cleanup_outputs.cleanup_charts(self.outputs, now=RUN_AT)

        self.assertEqual(result.protected_files, 2)
        self.assertEqual(result.eligible_files, 0)
        self.assertTrue(html_chart.exists())
        self.assertTrue(csv_chart.exists())
        self.assertTrue(any(missing_chart in path for path in result.missing_references))

    def test_apply_moves_only_old_unreferenced_png_and_writes_manifest(self):
        old_chart = self.add_chart("old.png")
        recent_chart = self.add_chart("recent.png", days_old=30)
        note = self.charts / "note.txt"
        note.write_text("keep", encoding="utf-8")

        result = cleanup_outputs.cleanup_charts(self.outputs, apply=True, now=RUN_AT)

        archive = self.outputs / "todelete" / "charts" / "2026-09-01"
        self.assertFalse(old_chart.exists())
        self.assertTrue((archive / "old.png").exists())
        self.assertTrue(recent_chart.exists())
        self.assertTrue(note.exists())
        self.assertEqual(result.moved_files, 1)
        self.assertTrue(result.manifest_path.is_file())
        with result.manifest_path.open(newline="", encoding="utf-8") as handle:
            manifest = list(csv.DictReader(handle))
        self.assertEqual(manifest[0]["reason"], "unreferenced PNG older than 30 days")

    def test_existing_archive_file_gets_deterministic_suffix(self):
        old_chart = self.add_chart("old.png")
        archive = self.outputs / "todelete" / "charts" / "2026-09-01"
        archive.mkdir(parents=True)
        (archive / "old.png").write_bytes(b"existing")

        cleanup_outputs.cleanup_charts(self.outputs, apply=True, now=RUN_AT)

        self.assertFalse(old_chart.exists())
        self.assertTrue((archive / "old.png").exists())
        self.assertTrue((archive / "old__1.png").exists())

    def test_bad_and_outside_references_are_not_protected(self):
        chart = self.add_chart("old.png")
        (self.reports / "dashboard.html").write_text(
            '<img src="../../outside.png">', encoding="utf-8"
        )

        result = cleanup_outputs.cleanup_charts(self.outputs, now=RUN_AT)

        self.assertTrue(result.bad_references)
        self.assertEqual(result.eligible_files, 1)
        self.assertTrue(chart.exists())

    def test_final_chart_cleanup_retains_any_report_link_and_newest_other_types(self):
        linked = self.add_chart("AAPL-final-latest-20260801-100000.png")
        newer_unlinked = self.add_chart("AAPL-final-latest-20260901-100000.png")
        technical_old = self.add_chart("AAPL-final-technical-20260801-100000.png")
        technical_new = self.add_chart("AAPL-final-technical-20260901-100000.png")
        simple_old = self.add_chart("AAPL-final-simple-20260801-100000.png")
        simple_new = self.add_chart("AAPL-final-simple-20260901-100000.png")
        non_final = self.add_chart("AAPL-3Y-tuned-20260801-100000.png")
        # This is deliberately not dashboard_latest.html: every report is
        # published, so any report-linked chart must survive final cleanup.
        (self.reports / "dashboard_excess_annualized_final.html").write_text(
            '<img src="../charts/AAPL-final-latest-20260801-100000.png">',
            encoding="utf-8",
        )

        result = cleanup_outputs.cleanup_final_charts(self.outputs, now=RUN_AT)

        self.assertEqual(result.protected_files, 4)
        self.assertEqual(result.eligible_files, 2)
        self.assertNotIn(linked, [source for source, _ in result.planned_moves])
        self.assertNotIn(newer_unlinked, [source for source, _ in result.planned_moves])
        self.assertIn(technical_old, [source for source, _ in result.planned_moves])
        self.assertNotIn(technical_new, [source for source, _ in result.planned_moves])
        self.assertIn(simple_old, [source for source, _ in result.planned_moves])
        self.assertNotIn(simple_new, [source for source, _ in result.planned_moves])
        self.assertTrue(non_final.exists())

    def test_final_chart_apply_archives_and_writes_manifest(self):
        old = self.add_chart("AAPL-final-simple-20260801-100000.png")
        self.add_chart("AAPL-final-simple-20260901-100000.png")

        result = cleanup_outputs.cleanup_final_charts(self.outputs, apply=True, now=RUN_AT)

        archive = self.outputs / "todelete" / "charts" / "final-versions" / "2026-09-01"
        self.assertFalse(old.exists())
        self.assertTrue((archive / old.name).exists())
        self.assertTrue(result.manifest_path.is_file())


if __name__ == "__main__":
    unittest.main()
