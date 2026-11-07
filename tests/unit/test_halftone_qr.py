"""Tests for the halftone QR code renderer (src/tronic_printer/halftone_qr.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from tronic_printer import cli
from tronic_printer.halftone_qr import (
    PRESETS,
    HalftoneDither,
    HalftoneOptions,
    MarksMode,
    _alignment_centers,
    _build_functional_mask,
    _dither_background,
    halftone_qr_to_raster,
    render_halftone_qr,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gradient_image(size: int = 64) -> Image.Image:
    """Create a smooth grayscale gradient for realistic background tests."""
    img = Image.new("L", (size, size))
    pixels = [((x + y) * 255 // (2 * size - 2)) for y in range(size) for x in range(size)]
    img.putdata(pixels)
    return img


def _solid_image(value: int = 128, size: int = 64) -> Image.Image:
    img = Image.new("L", (size, size))
    img.putdata([value] * (size * size))
    return img


def _get_qr_matrix(data: str, error: str = "h") -> tuple[list[list[bool]], int]:
    """Return (is_dark 2-D grid, version) using segno."""
    import io

    import segno
    code = segno.make_qr(data, error=error)
    buf = io.BytesIO()
    code.save(buf, kind="png", scale=1, border=0, dark="black", light="white")
    buf.seek(0)
    with Image.open(buf) as png:
        size = png.width
        lum_img = png.convert("L")
        _get = getattr(lum_img, "get_flattened_data", lum_img.getdata)
        lum = list(_get())
    return (
        [[lum[r * size + c] < 128 for c in range(size)] for r in range(size)],
        code.version,
    )


# ---------------------------------------------------------------------------
# HalftoneOptions validation
# ---------------------------------------------------------------------------

class TestHalftoneOptions:
    def test_defaults_are_valid(self) -> None:
        opts = HalftoneOptions()
        assert opts.grid == 6
        assert opts.core == 2
        assert opts.dither is HalftoneDither.FLOYD_STEINBERG
        assert opts.error_level == "h"
        assert opts.marks is MarksMode.ALL
        assert opts.border == 4
        assert opts.mask is None

    def test_presets_are_valid_configurations(self) -> None:
        for label, (n, c) in PRESETS.items():
            opts = HalftoneOptions(grid=n, core=c)
            assert opts.grid == n, label
            assert opts.core == c, label

    def test_invalid_grid_raises(self) -> None:
        with pytest.raises(ValueError, match="grid"):
            HalftoneOptions(grid=1)

    def test_core_too_large_raises(self) -> None:
        with pytest.raises(ValueError, match="core"):
            HalftoneOptions(grid=4, core=4)

    def test_bad_error_level_raises(self) -> None:
        with pytest.raises(ValueError, match="error_level"):
            HalftoneOptions(error_level="x")

    def test_bad_mask_raises(self) -> None:
        with pytest.raises(ValueError, match="mask"):
            HalftoneOptions(mask=8)

    def test_negative_border_raises(self) -> None:
        with pytest.raises(ValueError, match="border"):
            HalftoneOptions(border=-1)


# ---------------------------------------------------------------------------
# Dithering
# ---------------------------------------------------------------------------

class TestDitherBackground:
    def test_all_modes_produce_correct_dimensions(self) -> None:
        img = _gradient_image(16)
        for mode in HalftoneDither:
            result = _dither_background(img, mode)
            assert len(result) == 16, mode
            assert all(len(row) == 16 for row in result), mode
            assert all(isinstance(v, bool) for row in result for v in row), mode

    def test_threshold_dark_image_is_mostly_black(self) -> None:
        img = _solid_image(10, size=8)
        result = _dither_background(img, HalftoneDither.THRESHOLD)
        blacks = sum(v for row in result for v in row)
        assert blacks == 64  # all dark

    def test_threshold_light_image_is_mostly_white(self) -> None:
        img = _solid_image(240, size=8)
        result = _dither_background(img, HalftoneDither.THRESHOLD)
        blacks = sum(v for row in result for v in row)
        assert blacks == 0  # all light

    def test_atkinson_distributes_error(self) -> None:
        # Mid-grey with Atkinson should produce about 50% black
        img = _solid_image(128, size=16)
        result = _dither_background(img, HalftoneDither.ATKINSON)
        blacks = sum(v for row in result for v in row)
        assert 0 < blacks < 256  # some black and some white


# ---------------------------------------------------------------------------
# Functional mask
# ---------------------------------------------------------------------------

class TestFunctionalMask:
    def test_finder_region_always_marked_in_all_mode(self) -> None:
        # Version 1 QR = 21 modules
        mask = _build_functional_mask(21, 1, MarksMode.ALL)
        # Top-left corner 8×8
        for r in range(8):
            for c in range(8):
                assert mask[r][c], f"({r},{c}) not marked"
        # Top-right corner
        for r in range(8):
            for c in range(21 - 8, 21):
                assert mask[r][c], f"({r},{c}) not marked"
        # Bottom-left corner
        for r in range(21 - 8, 21):
            for c in range(8):
                assert mask[r][c], f"({r},{c}) not marked"

    def test_timing_marked_in_all_mode(self) -> None:
        mask = _build_functional_mask(21, 1, MarksMode.ALL)
        for i in range(8, 13):  # 8..12 for size=21 (size-9=12)
            assert mask[6][i], f"timing row col {i}"
            assert mask[i][6], f"timing col row {i}"

    def test_timing_not_marked_in_finders_mode(self) -> None:
        mask = _build_functional_mask(21, 1, MarksMode.FINDERS)
        for i in range(8, 13):
            assert not mask[6][i], f"timing should not be in finders mode col {i}"

    def test_none_mode_produces_all_false(self) -> None:
        mask = _build_functional_mask(21, 1, MarksMode.NONE)
        assert not any(v for row in mask for v in row)

    def test_alignment_marked_for_version_7(self) -> None:
        # Version 7 has alignment centres at (22, 22), (22, 38), (38, 22), (38, 38)
        # (excluding finder-overlapping ones)
        mask = _build_functional_mask(45, 7, MarksMode.ALL)  # size = 4*7+17 = 45
        centres = _alignment_centers(7)
        assert len(centres) > 0
        for cr, cc in centres:
            assert mask[cr][cc], f"alignment centre ({cr},{cc}) not marked"


# ---------------------------------------------------------------------------
# render_halftone_qr – core correctness
# ---------------------------------------------------------------------------

class TestRenderHalftoneQr:
    def test_output_is_1bit_pil_image(self) -> None:
        img = _gradient_image()
        result = render_halftone_qr("test", img)
        assert result.mode == "1"

    def test_output_is_square(self) -> None:
        img = _gradient_image()
        result = render_halftone_qr("test", img)
        assert result.width == result.height

    def test_dimensions_match_formula(self) -> None:
        opts = HalftoneOptions(grid=3, core=1, border=4)
        import segno
        code = segno.make_qr("hello", error="h")
        qr_size = len(list(code.matrix))
        expected = (qr_size + 2 * 4) * 3

        img = _gradient_image()
        result = render_halftone_qr("hello", img, opts)
        assert result.width == expected

    def test_core_subpixels_match_qr_matrix(self) -> None:
        """Every core subpixel must carry the exact QR module colour."""
        opts = HalftoneOptions(grid=3, core=1, border=0, marks=MarksMode.NONE)
        img = _gradient_image()
        result = render_halftone_qr("X", img, opts)

        is_dark_qr, _ver = _get_qr_matrix("X", "h")
        qr_size = len(is_dark_qr)
        N, C = 3, 1
        core_start = (N - C) // 2
        core_end = core_start + C

        pix = result.convert("L").load()
        mismatches = 0
        for r in range(qr_size):
            for c in range(qr_size):
                for sy in range(core_start, core_end):
                    for sx in range(core_start, core_end):
                        px = pix[c * N + sx, r * N + sy]  # PIL: (x,y)
                        expected_dark = is_dark_qr[r][c]
                        actual_dark = px < 128
                        if actual_dark != expected_dark:
                            mismatches += 1
        assert mismatches == 0, f"{mismatches} core subpixel mismatches"

    def test_quiet_zone_is_white(self) -> None:
        opts = HalftoneOptions(grid=3, core=1, border=4)
        img = _gradient_image()
        result = render_halftone_qr("QZ", img, opts)
        pix = result.convert("L").load()
        N, border = 3, 4
        # Top border rows
        for y in range(border * N):
            for x in range(result.width):
                assert pix[x, y] > 128, f"quiet zone not white at ({x},{y})"

    def test_finder_region_is_solid_in_all_mode(self) -> None:
        """With marks=all, finder subpixels must equal QR module colour exactly."""
        opts = HalftoneOptions(grid=4, core=2, border=2, marks=MarksMode.ALL)
        img = _solid_image(128)
        result = render_halftone_qr("FINDERS", img, opts)

        is_dark_qr, _ver = _get_qr_matrix("FINDERS", "h")
        N, border = 4, 2
        pix = result.convert("L").load()

        mismatches = 0
        for r in range(8):  # finder+separator region
            for c in range(8):
                if r >= len(is_dark_qr) or c >= len(is_dark_qr[0]):
                    continue
                for sy in range(N):
                    for sx in range(N):
                        px_x = (border + c) * N + sx
                        px_y = (border + r) * N + sy
                        expected_dark = is_dark_qr[r][c]
                        actual_dark = pix[px_x, px_y] < 128
                        if actual_dark != expected_dark:
                            mismatches += 1
        assert mismatches == 0, f"{mismatches} finder region mismatches"

    def test_empty_data_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            render_halftone_qr("", _gradient_image())

    def test_color_image_is_accepted(self) -> None:
        img = Image.new("RGB", (64, 64), (100, 150, 200))
        result = render_halftone_qr("RGB", img)
        assert result.mode == "1"

    def test_contrast_and_brightness_accepted(self) -> None:
        opts = HalftoneOptions(contrast=1.5, brightness=0.8, invert=True)
        img = _gradient_image()
        result = render_halftone_qr("CB", img, opts)
        assert result.mode == "1"

    def test_border_zero_produces_smaller_output(self) -> None:
        img = _gradient_image()
        with_border = render_halftone_qr("B", img, HalftoneOptions(border=4, grid=3))
        without_border = render_halftone_qr("B", img, HalftoneOptions(border=0, grid=3))
        assert without_border.width < with_border.width


# ---------------------------------------------------------------------------
# halftone_qr_to_raster
# ---------------------------------------------------------------------------

class TestHalftoneQrToRaster:
    def test_scales_up_correctly(self) -> None:
        # Create a 10×10 1-bit image
        img = Image.new("1", (10, 10))
        scaled, dps = halftone_qr_to_raster(img, max_width=100)
        assert dps == 10
        assert scaled.width == 100
        assert scaled.height == 100

    def test_raises_when_too_large(self) -> None:
        big = Image.new("1", (400, 400))
        with pytest.raises(ValueError, match="does not fit"):
            halftone_qr_to_raster(big, max_width=384)


# ---------------------------------------------------------------------------
# ZXing decode – QR must be scannable for every preset
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "preset,error_level",
    [
        ("3/1", "h"),
        ("5/1", "h"),
        ("5/3", "h"),
        ("6/2", "h"),
        ("3/1", "m"),
        ("6/2", "m"),
    ],
)
def test_halftone_qr_is_decodable(preset: str, error_level: str) -> None:
    zxingcpp = pytest.importorskip("zxingcpp")

    grid, core = PRESETS[preset]
    opts = HalftoneOptions(
        grid=grid,
        core=core,
        error_level=error_level,
        marks=MarksMode.ALL,
        border=4,
        dither=HalftoneDither.FLOYD_STEINBERG,
    )
    text = "https://example.com/halftone-qr-test"
    bg = _gradient_image(128)
    rendered = render_halftone_qr(text, bg, opts)
    scaled, _dps = halftone_qr_to_raster(rendered, max_width=384)

    # zxingcpp expects a grayscale or RGB image
    gray = scaled.convert("L")
    results = zxingcpp.read_barcodes(gray)
    decoded = [r.text for r in results if r.format.name == "QRCode"]
    assert text in decoded, (
        f"preset={preset} error={error_level}: QR not decoded. "
        f"Got results: {[(r.format, r.text) for r in results]}"
    )


# ---------------------------------------------------------------------------
# Marks mode – finders stay solid regardless of background
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("marks", [MarksMode.ALL, MarksMode.FINDERS])
def test_finder_top_left_is_solid_for_marks_mode(marks: MarksMode) -> None:
    """With marks!=none, the top-left 7×7 finder must be pure black/white."""
    opts = HalftoneOptions(grid=3, core=1, border=0, marks=marks)
    # Solid 50% grey background – without reference marks all non-core pixels
    # would be 50% grey dithered, introducing mixed colours in finder region
    img = _solid_image(128, size=256)
    result = render_halftone_qr("MARKS", img, opts)

    is_dark_qr, _ver = _get_qr_matrix("MARKS", "h")
    N = 3
    pix = result.convert("L").load()

    for r in range(7):
        for c in range(7):
            expected_dark = is_dark_qr[r][c]
            for sy in range(N):
                for sx in range(N):
                    px = pix[c * N + sx, r * N + sy]
                    actual_dark = px < 128
                    assert actual_dark == expected_dark, (
                        f"marks={marks.value}: finder ({r},{c}) subpixel ({sy},{sx}) wrong"
                    )


# ---------------------------------------------------------------------------
# CLI – prepare-halftone-qr writes a preview PNG and prints JSON
# ---------------------------------------------------------------------------

def test_prepare_halftone_qr_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    img_path = tmp_path / "bg.png"
    _gradient_image(64).save(img_path)
    output = tmp_path / "out.png"

    rc = cli.main([
        "prepare-halftone-qr",
        "--data", "https://example.com",
        "--image", str(img_path),
        "--grid", "3",
        "--core", "1",
        "--error-level", "h",
        "--output", str(output),
    ])
    assert rc == 0
    assert output.is_file()
    summary = json.loads(capsys.readouterr().out)
    assert summary["width"] > 0
    assert summary["dots_per_subpixel"] >= 1
    assert "preview" in summary


def test_prepare_halftone_qr_all_dithers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    img_path = tmp_path / "bg.png"
    _gradient_image(64).save(img_path)

    for dither in HalftoneDither:
        output = tmp_path / f"out_{dither.value}.png"
        rc = cli.main([
            "prepare-halftone-qr",
            "--data", "hi",
            "--image", str(img_path),
            "--grid", "3",
            "--core", "1",
            "--dither", dither.value,
            "--output", str(output),
        ])
        assert rc == 0, f"dither={dither.value} failed"
        capsys.readouterr()


def test_prepare_halftone_qr_validation_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    img_path = tmp_path / "bg.png"
    _gradient_image(64).save(img_path)

    with pytest.raises(SystemExit):
        cli.main([
            "prepare-halftone-qr",
            "--data", "hi",
            "--image", str(img_path),
            "--grid", "1",  # invalid: < 2
            "--core", "1",
            "--output", str(tmp_path / "x.png"),
        ])
