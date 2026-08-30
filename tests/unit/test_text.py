from pathlib import Path
from shutil import copyfile

import pytest
from PIL import ImageFont, ImageOps

from tronic_printer.text import (
    FontCatalog,
    FontSpec,
    TextAlign,
    TextLayoutConfig,
    prepare_text,
    render_text,
)


@pytest.fixture
def dejavu_sans() -> Path:
    loaded = ImageFont.truetype("DejaVuSans.ttf", 12)
    return Path(loaded.path)


def test_render_text_supports_unicode_newlines_and_exact_width(dejavu_sans: Path) -> None:
    rendered = render_text(
        "Pergel Dávid\nTóth András",
        FontSpec(path=dejavu_sans, size=24),
        TextLayoutConfig(width=200, margin=10, line_spacing=3),
    )

    assert rendered.lines == ("Pergel Dávid", "Tóth András")
    assert rendered.image.size[0] == 200
    assert ImageOps.invert(rendered.image).getbbox() is not None
    assert rendered.font.family == "DejaVu Sans"


def test_long_words_and_sentences_wrap_within_printable_width(dejavu_sans: Path) -> None:
    rendered = render_text(
        "ordinary words Supercalifragilisticexpialidocious",
        FontSpec(path=dejavu_sans, size=20),
        TextLayoutConfig(width=120, margin=8),
    )

    assert len(rendered.lines) >= 3
    draw_width = rendered.image.width - 16
    loaded = rendered.font.font
    assert all(loaded.getlength(line) <= draw_width for line in rendered.lines)


@pytest.mark.parametrize("alignment", list(TextAlign))
def test_every_alignment_renders_to_a_one_bit_prepared_raster(
    alignment: TextAlign,
    dejavu_sans: Path,
) -> None:
    prepared = prepare_text(
        "Árvíztűrő tükörfúrógép",
        FontSpec(path=dejavu_sans, size=18),
        TextLayoutConfig(width=192, margin=8, align=alignment),
    )

    assert prepared.prepared.raster.width == 192
    assert set(prepared.prepared.preview.tobytes()) <= {0, 255}
    assert prepared.prepared.black_pixels > 0
    assert prepared.summary()["align"] == alignment.value


def test_font_catalog_discovers_family_and_resolves_style(
    tmp_path: Path,
    dejavu_sans: Path,
) -> None:
    copied = tmp_path / "portable-test-font.ttf"
    copyfile(dejavu_sans, copied)
    catalog = FontCatalog((tmp_path,))

    face = catalog.resolve("DejaVu Sans")

    assert face.path == copied
    assert face.family == "DejaVu Sans"
    assert catalog.describe("dejavu") == [face.summary()]


def test_text_configuration_and_font_errors_are_reported(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="text cannot be empty"):
        render_text("  ")
    with pytest.raises(ValueError, match="margin"):
        TextLayoutConfig(width=20, margin=10)
    with pytest.raises(ValueError, match="font file does not exist"):
        render_text("hello", FontSpec(path=tmp_path / "missing.ttf"))
    with pytest.raises(ValueError, match="exceeds maximum"):
        render_text("one\ntwo", layout=TextLayoutConfig(max_height=10))
    with pytest.raises(ValueError, match="either a font family"):
        FontSpec(family="Example", path=tmp_path / "example.ttf")
    with pytest.raises(ValueError, match="glyph wider"):
        render_text("W", layout=TextLayoutConfig(width=1, margin=0))
