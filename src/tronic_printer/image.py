"""Compatibility helpers over the extensible image-preparation pipeline."""

from __future__ import annotations

from PIL import Image

from tronic_printer.domain import RasterImage
from tronic_printer.preprocessing import ImagePreparationConfig, load_prepared_image, prepare_image


def image_to_raster(
    image: Image.Image,
    *,
    width: int = 384,
    threshold: int = 128,
    preserve_aspect_ratio: bool = True,
) -> RasterImage:
    config = ImagePreparationConfig(
        width=width,
        threshold=threshold,
        preserve_aspect_ratio=preserve_aspect_ratio,
    )
    return prepare_image(image, config, registry=None).raster


def load_raster(path: str, **kwargs: object) -> RasterImage:
    config = ImagePreparationConfig(**kwargs)
    return load_prepared_image(path, config).raster
