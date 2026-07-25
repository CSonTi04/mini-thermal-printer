import hashlib
from pathlib import Path

from PIL import Image

from tronic_printer.showcase import SHOWCASE_RECIPES, build_showcase_pages

RESOURCE = Path(__file__).parents[1] / "resources" / "Lenna_(test_image).png"
RESOURCE_SHA256 = "7E497501A28BCF9A353CCADF6EB9216BF098AC32888FB542FB9BFE71D486761F"


def test_lenna_resource_matches_pinned_hash() -> None:
    assert hashlib.sha256(RESOURCE.read_bytes()).hexdigest().upper() == RESOURCE_SHA256


def test_four_labeled_showcase_pages_are_deterministic_and_printable() -> None:
    with Image.open(RESOURCE) as source:
        pages = build_showcase_pages(source)

    assert [page.recipe.slug for page in pages] == [
        "floyd-photo",
        "ordered-newsprint",
        "gritty-noir",
        "outline-sketch",
    ]
    assert len(pages) == len(SHOWCASE_RECIPES) == 4
    for page in pages:
        assert page.raster.width == 384
        assert page.raster.height > page.image.raster.height == 384
        assert page.preview.size == (page.raster.width, page.raster.height)
        assert page.summary()["effects"] == page.recipe.effect_text()
        assert set(page.preview.tobytes()) <= {0, 255}


def test_showcase_pages_have_distinct_image_rasters() -> None:
    with Image.open(RESOURCE) as source:
        pages = build_showcase_pages(source)

    assert len({page.image.raster.data for page in pages}) == 4
