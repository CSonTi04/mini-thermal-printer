import pytest

from tronic_printer.application import build_application
from tronic_printer.messages import GetDeviceInfo
from tronic_printer.ports import PrinterTransport


@pytest.mark.hil
def test_live_ble_identity_and_safe_telemetry(hil_ble_transport: PrinterTransport) -> None:
    info = build_application(hil_ble_transport).queries.ask(GetDeviceInfo())

    assert info.model
    assert info.firmware
    assert 0 <= info.battery_percent <= 100
    assert 0 <= info.density <= 2
    assert 0 <= info.status.raw <= 0xFF
