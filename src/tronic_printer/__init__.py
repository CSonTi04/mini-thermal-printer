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

__all__ = [
    "DeviceInfo",
    "DitherMode",
    "EffectSpec",
    "IMAGE_EFFECT_API_VERSION",
    "ImageEffect",
    "ImageEffectRegistry",
    "ImagePreparationConfig",
    "PreparedImage",
    "PrinterApplication",
    "PrinterStatus",
    "RasterImage",
    "build_application",
    "build_effect_registry",
    "prepare_image",
]

__version__ = "0.1.0"
