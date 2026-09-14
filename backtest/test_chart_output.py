import tempfile
import unittest
from pathlib import Path
from unittest import mock

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from PIL import Image

import chart_output
import migrate_dashboard_chart_resolution as migration


def make_png(path, size, color="white"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


class ChartOutputTests(unittest.TestCase):
    def test_constrained_dimensions_preserve_aspect_for_common_shapes(self):
        self.assertEqual(
            chart_output.constrained_dimensions(3000, 2400),
            (1600, 1280),
        )
        self.assertEqual(
            chart_output.constrained_dimensions(3000, 1500),
            (1920, 960),
        )
        self.assertEqual(
            chart_output.constrained_dimensions(2000, 2000),
            (1280, 1280),
        )
        self.assertEqual(
            chart_output.constrained_dimensions(1200, 800),
            (1200, 800),
        )

    def test_save_figure_png_enforces_envelope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "technical.png"
            figure = plt.figure(figsize=(15, 12))
            plt.plot([0, 1], [0, 1])
            stats = chart_output.save_figure_png(figure, output)
            plt.close(figure)
            self.assertLessEqual(stats.width, chart_output.CHART_PNG_MAX_WIDTH)
            self.assertLessEqual(stats.height, chart_output.CHART_PNG_MAX_HEIGHT)
            self.assertTrue(output.is_file())

    def test_resize_png_atomic_skips_image_already_within_envelope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = make_png(Path(temp_dir) / "small.png", (800, 600))
            before, after = chart_output.resize_png_atomic(output)
            self.assertEqual(before, after)


class DashboardChartMigrationTests(unittest.TestCase):
    def build_tree(self, temp_dir, image_count=1):
        root = Path(temp_dir)
        reports = root / "outputs" / "reports"
        charts = root / "outputs" / "charts"
        fund_page = reports / "funds" / "TEST.html"
        fund_page.parent.mkdir(parents=True)
        links = []
        paths = []
        for index in range(image_count):
            path = make_png(
                charts / f"chart-{index}.png",
                (3000, 2400),
                color=(index * 30, 100, 150),
            )
            paths.append(path)
            links.append(f'<img src="../../charts/{path.name}">')
            links.append(f'<button data-src="../../charts/{path.name}"></button>')
        outside = make_png(root / "outside.png", (3000, 2400))
        links.append('<img src="../../../outside.png">')
        links.append('<img src="https://example.com/remote.png">')
        fund_page.write_text("\n".join(links), encoding="utf-8")
        return reports, charts, paths, outside

    def test_collect_dashboard_pngs_deduplicates_and_rejects_outside_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports, charts, paths, _ = self.build_tree(temp_dir, image_count=2)
            linked = migration.collect_dashboard_pngs(reports, charts)
            self.assertEqual(linked, [path.resolve() for path in paths])

    def test_apply_migration_creates_backup_manifest_and_preserves_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports, charts, paths, _ = self.build_tree(temp_dir)
            html_before = (reports / "funds" / "TEST.html").read_text(encoding="utf-8")
            result = migration.apply_migration(
                reports,
                charts,
                Path(temp_dir) / "migrations",
                timestamp="test-run",
            )
            self.assertEqual(result["linked_count"], 1)
            self.assertEqual(result["resized_count"], 1)
            self.assertTrue(result["manifest_path"].is_file())
            self.assertTrue(
                (result["migration_dir"] / "originals" / paths[0].name).is_file()
            )
            stats = chart_output.png_stats(paths[0])
            self.assertEqual((stats.width, stats.height), (1600, 1280))
            self.assertEqual(
                (reports / "funds" / "TEST.html").read_text(encoding="utf-8"),
                html_before,
            )

    def test_apply_migration_rolls_back_every_chart_after_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            reports, charts, paths, _ = self.build_tree(temp_dir, image_count=2)
            original_hashes = [chart_output.sha256_file(path) for path in paths]
            real_resize = chart_output.resize_png_atomic
            calls = {"count": 0}

            def fail_second(path):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise RuntimeError("simulated failure")
                return real_resize(path)

            with mock.patch.object(
                migration.chart_output,
                "resize_png_atomic",
                side_effect=fail_second,
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                    migration.apply_migration(
                        reports,
                        charts,
                        Path(temp_dir) / "migrations",
                        timestamp="rollback-run",
                    )
            self.assertEqual(
                [chart_output.sha256_file(path) for path in paths],
                original_hashes,
            )
            manifest = (
                Path(temp_dir) / "migrations" / "rollback-run" / "manifest.csv"
            ).read_text(encoding="utf-8")
            self.assertIn("rolled_back", manifest)


if __name__ == "__main__":
    unittest.main()
