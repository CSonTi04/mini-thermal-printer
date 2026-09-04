from collections.abc import Callable

import pytest

from tronic_printer.application import build_application
from tronic_printer.messages import (
    GetBootInfo,
    GetSerialNumber,
    GetShutdownTime,
    GetSpeed,
    GetTimeFormat,
    SetShutdownTime,
)
from tronic_printer.ports import PrinterTransport


@pytest.mark.hil
def test_live_optional_read_only_queries(hil_transport: PrinterTransport) -> None:
    queries = build_application(hil_transport).queries

    assert queries.ask(GetSerialNumber())
    assert queries.ask(GetBootInfo())
    assert queries.ask(GetShutdownTime()) in {5, 10, 20, 30, 60}
    with pytest.raises((OSError, TimeoutError)):
        queries.ask(GetSpeed())
    with pytest.raises((OSError, TimeoutError)):
        queries.ask(GetTimeFormat())


@pytest.mark.hil
def test_live_ble_optional_read_only_queries(hil_ble_transport: PrinterTransport) -> None:
    queries = build_application(hil_ble_transport).queries

    assert queries.ask(GetSerialNumber())
    assert queries.ask(GetBootInfo())
    assert queries.ask(GetShutdownTime()) in {5, 10, 20, 30, 60}
    with pytest.raises((OSError, TimeoutError)):
        queries.ask(GetSpeed())
    with pytest.raises((OSError, TimeoutError)):
        queries.ask(GetTimeFormat())


@pytest.mark.hil
def test_live_shutdown_time_round_trip(
    hil_transport_factory: Callable[[], PrinterTransport],
    settings_allowed: None,
) -> None:
    with hil_transport_factory() as transport:
        original = build_application(transport).queries.ask(GetShutdownTime())
    if original not in {5, 10, 20, 30, 60}:
        pytest.fail(f"refusing to change unrecognized shutdown time {original}")
    temporary = 30 if original != 30 else 20

    restore_needed = False
    try:
        restore_needed = True
        with hil_transport_factory() as transport:
            build_application(transport).commands.execute(SetShutdownTime(temporary))
        with hil_transport_factory() as transport:
            assert build_application(transport).queries.ask(GetShutdownTime()) == temporary
    finally:
        if restore_needed:
            with hil_transport_factory() as transport:
                build_application(transport).commands.execute(SetShutdownTime(original))
            with hil_transport_factory() as transport:
                assert build_application(transport).queries.ask(GetShutdownTime()) == original
