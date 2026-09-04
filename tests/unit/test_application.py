import pytest

from tronic_printer.application import CommandBus, QueryBus, build_application
from tronic_printer.domain import PrinterNotReady, RasterImage
from tronic_printer.messages import (
    FeedPaper,
    GetBootInfo,
    GetDeviceInfo,
    GetSerialNumber,
    GetShutdownTime,
    GetSpeed,
    GetTimeFormat,
    PrintRaster,
    RasterEncoding,
    SetDensity,
    SetShutdownTime,
)
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


def test_extended_info_uses_only_optional_read_queries() -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)

    assert app.queries.ask(GetSerialNumber()) == "TEST-SERIAL"
    assert app.queries.ask(GetBootInfo()) == "TEST-BOOT"
    assert app.queries.ask(GetShutdownTime()) == 30
    assert app.queries.ask(GetSpeed()) == 2
    assert app.queries.ask(GetTimeFormat()) == 0
    assert transport.exchanges == [
        bytes.fromhex("10 FF 20 F2"),
        bytes.fromhex("10 FF 20 EF"),
        bytes.fromhex("10 FF 13"),
        bytes.fromhex("10 FF 20 A0"),
        bytes.fromhex("10 FF B0"),
    ]
    assert transport.writes == []


def test_shutdown_time_can_be_changed_and_restored() -> None:
    transport = EmulatedPrinterTransport(shutdown_time=20)
    app = build_application(transport)

    app.commands.execute(SetShutdownTime(30))
    assert transport.shutdown_time == 30

    app.commands.execute(SetShutdownTime(20))
    assert transport.shutdown_time == 20


def test_print_command_builds_complete_continuous_roll_job() -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)
    raster = RasterImage.test_pattern(width=384, height=16)

    result = app.commands.execute(PrintRaster(raster, feed_dots=80))

    assert result.completion == b"\xAA\r\n"
    assert result.raster_bytes < 8 + 48 * 16
    assert len(transport.completed_jobs) == 1
    job = transport.completed_jobs[0]
    assert job[0] == bytes.fromhex("10 FF F1 03")
    assert job[1] == bytes(12)
    assert job[2].startswith(bytes.fromhex("1F 10 00 30 00 10"))
    assert job[3] == bytes.fromhex("1B 4A 50")
    assert job[4] == bytes.fromhex("10 FF F1 45")


def test_print_command_honors_job_mode() -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)

    app.commands.execute(PrintRaster(RasterImage.test_pattern(), job_mode=7))

    assert transport.writes[0] == bytes.fromhex("10 FF F1 07")


def test_uncompressed_encoding_remains_available_for_regression_probes() -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)

    app.commands.execute(
        PrintRaster(
            RasterImage.test_pattern(),
            encoding=RasterEncoding.UNCOMPRESSED,
        )
    )

    assert transport.completed_jobs[0][2].startswith(bytes.fromhex("1D 76 30 00"))


def test_feed_uses_verified_all_white_raster_lifecycle() -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)

    app.commands.execute(FeedPaper(160))

    job = transport.completed_jobs[0]
    assert job[2][:8] == bytes.fromhex("1D 76 30 00 30 00 01 00")
    assert job[2][8:] == bytes(48)
    assert job[3] == bytes.fromhex("1B 4A A0")


@pytest.mark.parametrize("unsafe_status", [0x02, 0x04, 0x10, 0x40])
def test_print_command_refuses_unsafe_status(unsafe_status: int) -> None:
    transport = EmulatedPrinterTransport(status=unsafe_status)
    app = build_application(transport)

    with pytest.raises(PrinterNotReady):
        app.commands.execute(PrintRaster(RasterImage.test_pattern()))

    assert transport.writes == []
    assert transport.completed_jobs == []


@pytest.mark.parametrize(
    "command, message",
    [
        (PrintRaster(RasterImage(385, 1, bytes(49))), "384-dot"),
        (PrintRaster(RasterImage.test_pattern(), feed_dots=256), "feed"),
        (PrintRaster(RasterImage.test_pattern(), job_mode=256), "job mode"),
    ],
)
def test_print_command_validates_entire_job_before_transport_access(
    command: PrintRaster,
    message: str,
) -> None:
    transport = EmulatedPrinterTransport()
    app = build_application(transport)

    with pytest.raises(ValueError, match=message):
        app.commands.execute(command)

    assert transport.exchanges == []
    assert transport.writes == []


def test_unregistered_messages_fail_explicitly() -> None:
    with pytest.raises(LookupError, match="no query handler"):
        QueryBus().ask(object())
    with pytest.raises(LookupError, match="no command handler"):
        CommandBus().execute(object())
