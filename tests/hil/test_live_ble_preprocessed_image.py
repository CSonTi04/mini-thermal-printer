import pytest
from PIL import Image, ImageDraw

from tronic_printer.application import build_application
from tronic_printer.messages import PrintRaster
from tronic_printer.ports import PrinterTransport
from tronic_printer.preprocessing import (
    DitherMode,
    EffectSpec,
    ImagePreparationConfig,
    build_effect_registry,
    prepare_image,
)


@pytest.mark.hil
@pytest.mark.printing
def test_live_ble_preprocessed_low_ink_image(
    hil_ble_transport: PrinterTransport,
    printing_allowed: None,
) -> None:
    source = Image.new("RGB", (192, 48), "white")
    draw = ImageDraw.Draw(source)
    for index, tone in enumerate((224, 192, 160, 128)):
        left = 8 + index * 44
        draw.rectangle((left, 8, left + 34, 29), fill=(tone, tone, tone))
    draw.rectangle((4, 4, 187, 43), outline="black", width=1)
    draw.line((8, 38, 183, 34), fill="black", width=1)

    prepared = prepare_image(
        source,
        ImagePreparationConfig(
            width=384,
            dither=DitherMode.ORDERED_4X4,
            effects=(
                EffectSpec.parse("autocontrast:cutoff=1"),
                EffectSpec.parse("contrast:factor=1.1"),
            ),
        ),
        registry=build_effect_registry(discover_plugins=False),
    )
    assert prepared.raster.height == 96
    assert prepared.black_percent < 30

    result = build_application(hil_ble_transport).commands.execute(
        PrintRaster(prepared.raster, feed_dots=160)
    )

    assert result.completion[0] == 0xAA or result.completion.startswith(b"OK")

