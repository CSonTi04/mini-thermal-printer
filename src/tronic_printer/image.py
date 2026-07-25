"""Pillow adapter for converting ordinary images into domain rasters."""

from __future__ import annotations

from PIL import Image, ImageOps

from tronic_printer.domain import RasterImage


def image_to_raster(
    image: Image.Image,
    *,
    width: int = 384,
    threshold: int = 128,
    preserve_aspect_ratio: bool = True,
) -> RasterImage:
    if width <= 0:
        raise ValueError("width must be positive")
    if threshold not in range(256):
        raise ValueError("threshold must be between 0 and 255")

    grayscale = ImageOps.grayscale(image)
    if preserve_aspect_ratio:
        height = max(1, round(grayscale.height * width / grayscale.width))
        grayscale = grayscale.resize((width, height), Image.Resampling.BILINEAR)
    elif grayscale.width != width:
        grayscale = grayscale.resize((width, grayscale.height), Image.Resampling.BILINEAR)

    pixels = grayscale.tobytes()
    rows = [
        [pixels[y * width + x] < threshold for x in range(width)]
        for y in range(grayscale.height)
    ]
    return RasterImage.from_rows(rows)


def load_raster(path: str, **kwargs: object) -> RasterImage:
    with Image.open(path) as image:
        return image_to_raster(image, **kwargs)
