from pathlib import Path

import pytest
from PIL import Image

from tronic_printer.image import image_to_raster, load_raster


def test_image_adapter_thresholds_and_resizes() -> None:
    image = Image.new("L", (2, 1))
    image.putdata([0, 255])

    raster = image_to_raster(image, width=2)

    assert raster.width == 2
    assert raster.height == 1
    assert raster.data == b"\x80"


def test_image_adapter_validates_inputs() -> None:
    image = Image.new("L", (1, 1))
    with pytest.raises(ValueError, match="width"):
        image_to_raster(image, width=0)
    with pytest.raises(ValueError, match="threshold"):
        image_to_raster(image, threshold=256)


def test_image_adapter_preserves_non_proportional_compatibility() -> None:
    image = Image.new("L", (2, 3), color=0)

    raster = image_to_raster(image, width=4, preserve_aspect_ratio=False)

    assert raster.width == 4
    assert raster.height == 3


def test_load_raster_closes_source_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.png"
    Image.new("L", (2, 1), color=0).save(path)

    raster = load_raster(str(path), width=2)

    assert raster.data == b"\xC0"
