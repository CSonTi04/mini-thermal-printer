import pytest

from tronic_printer.application import build_application
from tronic_printer.domain import RasterImage
from tronic_printer.messages import PrintRaster
from tronic_printer.ports import PrinterTransport


@pytest.mark.hil
@pytest.mark.printing
def test_live_ble_uncompressed_test_pattern(
    hil_ble_transport: PrinterTransport,
    printing_allowed: None,
) -> None:
    result = build_application(hil_ble_transport).commands.execute(
        PrintRaster(RasterImage.test_pattern(384, 32))
    )

    assert result.completion[0] == 0xAA or result.completion.startswith(b"OK")
