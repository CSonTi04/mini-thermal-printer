"""Clean-room driver for the Lidl TRONIC Mini Pocket Printer."""

from tronic_printer.application import PrinterApplication, build_application
from tronic_printer.domain import DeviceInfo, PrinterStatus, RasterImage
from tronic_printer.preprocessing import (
    IMAGE_EFFECT_API_VERSION,
    DitherMode,
    EffectSpec,
    ImageEffect,
    ImageEffectRegistry,
    ImagePreparationConfig,
    PreparedImage,
    build_effect_registry,
    prepare_image,
)
from tronic_printer.showcase import (
    SHOWCASE_RECIPES,
    ImageRecipe,
    ShowcasePage,
    build_showcase_page,
    build_showcase_pages,
)

__all__ = [
    "DeviceInfo",
    "DitherMode",
    "EffectSpec",
    "IMAGE_EFFECT_API_VERSION",
    "ImageEffect",
    "ImageEffectRegistry",
    "ImagePreparationConfig",
    "ImageRecipe",
    "PreparedImage",
    "PrinterApplication",
    "PrinterStatus",
    "RasterImage",
    "SHOWCASE_RECIPES",
    "ShowcasePage",
    "build_application",
    "build_effect_registry",
    "build_showcase_page",
    "build_showcase_pages",
    "prepare_image",
]

__version__ = "0.3.0"
