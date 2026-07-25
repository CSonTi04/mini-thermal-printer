from tronic_printer.application import build_application
from tronic_printer.domain import RasterImage
from tronic_printer.messages import GetDeviceInfo, PrintRaster, SetDensity
from tronic_printer.testing import EmulatedPrinterTransport


def test_complete_mocked_operator_workflow() -> None:
    printer = EmulatedPrinterTransport(battery=90)
    app = build_application(printer)

    before = app.queries.ask(GetDeviceInfo())
    app.commands.execute(SetDensity(2))
    printed = app.commands.execute(PrintRaster(RasterImage.test_pattern(384, 32)))
    after = app.queries.ask(GetDeviceInfo())

    assert before.battery_percent == 90
    assert before.density == 1
    assert after.density == 2
    assert printed.total_bytes == 4 + 12 + (8 + 48 * 32) + 3 + 4
    assert len(printer.completed_jobs) == 1
