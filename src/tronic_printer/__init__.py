"""Clean-room driver for the Lidl TRONIC Mini Pocket Printer."""

from tronic_printer.application import PrinterApplication, build_application
from tronic_printer.domain import DeviceInfo, PrinterStatus, RasterImage
from tronic_printer.niimbot import (
    B1_PROFILE,
    NiimbotFrameBuffer,
    NiimbotPacket,
    PrinterProfile,
    decode_row,
    encode_empty_row,
    encode_print_start,
    encode_row,
    encode_set_page_size,
)
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
    "B1_PROFILE",
    "DeviceInfo",
    "DitherMode",
    "EffectSpec",
    "IMAGE_EFFECT_API_VERSION",
    "ImageEffect",
    "ImageEffectRegistry",
    "ImagePreparationConfig",
    "ImageRecipe",
    "NiimbotFrameBuffer",
    "NiimbotPacket",
    "PreparedImage",
    "PrinterApplication",
    "PrinterProfile",
    "PrinterStatus",
    "RasterImage",
    "SHOWCASE_RECIPES",
    "ShowcasePage",
    "build_application",
    "build_effect_registry",
    "build_showcase_page",
    "build_showcase_pages",
    "decode_row",
    "encode_empty_row",
    "encode_print_start",
    "encode_row",
    "encode_set_page_size",
    "prepare_image",
]

__version__ = "0.3.0"
