"""Shared, screen-sized PNG rendering and resizing helpers."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


CHART_PNG_BASE_DPI = 140
CHART_PNG_COMPRESS_LEVEL = 9
CHART_PNG_MAX_WIDTH = 1920
CHART_PNG_MAX_HEIGHT = 1280


@dataclass(frozen=True)
class PngStats:
    width: int
    height: int
    byte_size: int
    sha256: str


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_stats(path):
    path = Path(path)
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    return PngStats(width, height, path.stat().st_size, sha256_file(path))


def constrained_dimensions(width, height, max_width=CHART_PNG_MAX_WIDTH,
                           max_height=CHART_PNG_MAX_HEIGHT):
    """Return aspect-preserving dimensions within the requested envelope."""
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        raise ValueError("PNG dimensions must be positive")
    scale = min(1.0, float(max_width) / width, float(max_height) / height)
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def _temporary_png(path, label):
    path = Path(path)
    return path.with_name(f".{path.name}.{label}.{uuid.uuid4().hex}.tmp.png")


def _write_constrained_png(source, destination, max_width, max_height,
                           compress_level):
    source = Path(source)
    destination = Path(destination)
    with Image.open(source) as image:
        image.load()
        target = constrained_dimensions(
            image.width, image.height, max_width, max_height
        )
        output = (
            image.resize(target, Image.Resampling.LANCZOS)
            if target != image.size
            else image.copy()
        )
        save_options = {
            "format": "PNG",
            "compress_level": int(compress_level),
        }
        dpi = image.info.get("dpi")
        if dpi:
            save_options["dpi"] = dpi
        output.save(destination, **save_options)
        output.close()


def resize_png_atomic(path, max_width=CHART_PNG_MAX_WIDTH,
                      max_height=CHART_PNG_MAX_HEIGHT,
                      compress_level=CHART_PNG_COMPRESS_LEVEL):
    """Downsize one PNG in place when needed and return before/after stats."""
    path = Path(path)
    before = png_stats(path)
    if before.width <= max_width and before.height <= max_height:
        return before, before

    temporary = _temporary_png(path, "resize")
    try:
        _write_constrained_png(
            path, temporary, max_width, max_height, compress_level
        )
        after = png_stats(temporary)
        if after.width > max_width or after.height > max_height:
            raise ValueError(
                f"Resized PNG exceeds {max_width}x{max_height}: "
                f"{after.width}x{after.height}"
            )
        os.replace(temporary, path)
        return before, png_stats(path)
    finally:
        temporary.unlink(missing_ok=True)


def figure_render_dpi(figure, base_dpi=CHART_PNG_BASE_DPI,
                      max_width=CHART_PNG_MAX_WIDTH,
                      max_height=CHART_PNG_MAX_HEIGHT):
    """Choose a DPI that does not render the nominal canvas above the cap."""
    width_inches, height_inches = figure.get_size_inches()
    if width_inches <= 0 or height_inches <= 0:
        raise ValueError("Figure dimensions must be positive")
    return min(
        float(base_dpi),
        float(max_width) / float(width_inches),
        float(max_height) / float(height_inches),
    )


def save_figure_png(figure, output_path, base_dpi=CHART_PNG_BASE_DPI,
                    max_width=CHART_PNG_MAX_WIDTH,
                    max_height=CHART_PNG_MAX_HEIGHT,
                    compress_level=CHART_PNG_COMPRESS_LEVEL,
                    bbox_inches="tight"):
    """Atomically save a Matplotlib figure as a validated screen-fit PNG."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _temporary_png(output_path, "render")
    try:
        figure.savefig(
            rendered,
            format="png",
            dpi=figure_render_dpi(
                figure, base_dpi, max_width, max_height
            ),
            bbox_inches=bbox_inches,
            pil_kwargs={"compress_level": int(compress_level)},
        )
        stats = png_stats(rendered)
        if stats.width > max_width or stats.height > max_height:
            constrained = _temporary_png(output_path, "constrain")
            try:
                _write_constrained_png(
                    rendered,
                    constrained,
                    max_width,
                    max_height,
                    compress_level,
                )
                rendered.unlink(missing_ok=True)
                rendered = constrained
            finally:
                if constrained != rendered:
                    constrained.unlink(missing_ok=True)
        final_stats = png_stats(rendered)
        if final_stats.width > max_width or final_stats.height > max_height:
            raise ValueError(
                f"Rendered PNG exceeds {max_width}x{max_height}: "
                f"{final_stats.width}x{final_stats.height}"
            )
        os.replace(rendered, output_path)
        return png_stats(output_path)
    finally:
        rendered.unlink(missing_ok=True)
