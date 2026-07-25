from collections.abc import Iterator

import pytest

from tronic_printer.infrastructure.ble import BleTransport
from tronic_printer.infrastructure.serial import SerialTransport


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("printer hardware-in-the-loop")
    group.addoption("--live", action="store_true", help="allow access to a physical printer")
    group.addoption("--allow-printing", action="store_true", help="allow paper/head activation")
    group.addoption(
        "--allow-four-image-showcase",
        action="store_true",
        help="allow the long four-page labeled image showcase",
    )
    group.addoption(
        "--showcase-pause-seconds",
        type=float,
        default=20.0,
        help="cooling pause between showcase pages",
    )
    group.addoption("--printer-port", help="Bluetooth SPP serial port, for example COM7")
    group.addoption("--printer-address", help="Bluetooth address used by the BLE HIL transport")
    group.addoption("--printer-baudrate", type=int, default=115_200)


@pytest.fixture
def hil_transport(request: pytest.FixtureRequest) -> Iterator[SerialTransport]:
    if not request.config.getoption("--live"):
        pytest.skip("requires explicit --live consent")
    port = request.config.getoption("--printer-port")
    if not port:
        pytest.skip("requires --printer-port")
    transport = SerialTransport(
        port,
        baudrate=request.config.getoption("--printer-baudrate"),
    )
    try:
        yield transport
    finally:
        transport.close()


@pytest.fixture
def printing_allowed(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--allow-printing"):
        pytest.skip("requires separate --allow-printing consent")


@pytest.fixture
def four_image_showcase_allowed(
    request: pytest.FixtureRequest,
    printing_allowed: None,
) -> float:
    if not request.config.getoption("--allow-four-image-showcase"):
        pytest.skip("requires separate --allow-four-image-showcase consent")
    pause = request.config.getoption("--showcase-pause-seconds")
    if pause < 0:
        pytest.fail("--showcase-pause-seconds cannot be negative")
    return pause


@pytest.fixture
def hil_ble_transport(request: pytest.FixtureRequest) -> Iterator[BleTransport]:
    if not request.config.getoption("--live"):
        pytest.skip("requires explicit --live consent")
    address = request.config.getoption("--printer-address")
    if not address:
        pytest.skip("requires --printer-address")
    transport = BleTransport(address)
    try:
        yield transport
    finally:
        transport.close()
