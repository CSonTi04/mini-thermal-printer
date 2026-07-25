import pytest

from tronic_printer.application import CommandBus, QueryBus, build_application
from tronic_printer.domain import PrinterNotReady, RasterImage
from tronic_printer.messages import GetDeviceInfo, PrintRaster, SetDensity
from tronic_printer.testing import EmulatedPrinterTransport


def test_device_info_query_uses_emulated_captured_values() -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)

    info = app.queries.ask(GetDeviceInfo())

    assert info.model == "A2Y"
    assert info.firmware == "V1.06LY"
    assert info.battery_percent == 92
    assert info.density == 1
    assert info.status.raw == 0


def test_set_density_changes_emulated_device_state() -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)

    app.commands.execute(SetDensity(2))

    assert transport.density == 2


def test_print_command_builds_complete_continuous_roll_job() -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)
    raster = RasterImage.test_pattern(width=384, height=16)

    result = app.commands.execute(PrintRaster(raster, feed_dots=80))

    assert result.completion == b"\xAA\r\n"
    assert result.raster_bytes == 8 + 48 * 16
    assert len(transport.completed_jobs) == 1
    job = transport.completed_jobs[0]
    assert job[0] == bytes.fromhex("10 FF F1 03")
    assert job[1] == bytes(12)
    assert job[2].startswith(bytes.fromhex("1D 76 30 00 30 00 10 00"))
    assert job[3] == bytes.fromhex("1B 4A 50")
    assert job[4] == bytes.fromhex("10 FF F1 45")


def test_print_command_honors_job_mode() -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)

    app.commands.execute(PrintRaster(RasterImage.test_pattern(), job_mode=7))

    assert transport.writes[0] == bytes.fromhex("10 FF F1 07")


@pytest.mark.parametrize("unsafe_status", [0x02, 0x04, 0x10, 0x40])
def test_print_command_refuses_unsafe_status(unsafe_status: int) -> None:
    transport = EmulatedPrinterTransport(status=unsafe_status)
    app = build_application(transport)

    with pytest.raises(PrinterNotReady):
        app.commands.execute(PrintRaster(RasterImage.test_pattern()))

    assert transport.writes == []
    assert transport.completed_jobs == []


def test_unregistered_messages_fail_explicitly() -> None:
    with pytest.raises(LookupError, match="no query handler"):
        QueryBus().ask(object())
    with pytest.raises(LookupError, match="no command handler"):
        CommandBus().execute(object())
