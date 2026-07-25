import pytest

from tronic_printer.application import build_application
from tronic_printer.messages import FeedPaper
from tronic_printer.ports import PrinterTransport


@pytest.mark.hil
@pytest.mark.printing
def test_live_ble_white_raster_feed(
    hil_ble_transport: PrinterTransport,
    printing_allowed: None,
) -> None:
    build_application(hil_ble_transport).commands.execute(FeedPaper(160))
