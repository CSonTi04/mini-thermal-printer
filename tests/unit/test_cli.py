import json

import pytest

from tronic_printer import cli
from tronic_printer.infrastructure.ble import BleDevice
from tronic_printer.testing import EmulatedPrinterTransport


def test_ports_is_read_only_and_json_formatted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "available_ports",
        lambda: [{"device": "COM7", "description": "Bluetooth", "hwid": "mock"}],
    )

    assert cli.main(["ports"]) == 0

    assert json.loads(capsys.readouterr().out)[0]["device"] == "COM7"


def test_info_refuses_hardware_without_live() -> None:
    with pytest.raises(SystemExit, match="--live"):
        cli.main(["info", "--port", "COM7"])


def test_info_uses_cqrs_application(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "SerialTransport", lambda *_args, **_kwargs: printer)

    assert cli.main(["info", "--port", "COM7", "--live"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["model"] == "A2Y"
    assert output["firmware"] == "V1.06LY"
    assert output["status"]["raw"] == 0


def test_print_requires_separate_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "SerialTransport", lambda *_args, **_kwargs: printer)

    with pytest.raises(SystemExit, match="--allow-printing"):
        cli.main(["print-test", "--port", "COM7", "--live"])

    assert printer.writes == []


def test_print_with_both_flags_uses_mock_printer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "SerialTransport", lambda *_args, **_kwargs: printer)

    result = cli.main(
        [
            "print-test",
            "--port",
            "COM7",
            "--live",
            "--allow-printing",
            "--height",
            "16",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["completion"] == "aa 0d 0a"
    assert len(printer.completed_jobs) == 1
    assert printer.completed_jobs[0][2].startswith(bytes.fromhex("1F 10"))


def test_ble_print_can_select_uncompressed_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "BleTransport", lambda *_args, **_kwargs: printer)

    cli.main(
        [
            "ble-print-test",
            "mock",
            "--live",
            "--allow-printing",
            "--encoding",
            "uncompressed",
        ]
    )

    assert printer.completed_jobs[0][2].startswith(bytes.fromhex("1D 76 30"))


def test_ble_scan_formats_discovered_devices(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_discover(_timeout: float) -> list[object]:
        return [BleDevice(name="Mini Pocket Printer_BLE", address="mock", rssi=-42)]

    monkeypatch.setattr(cli, "discover", fake_discover)

    assert cli.main(["ble-scan", "--timeout", "0.1"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["rssi"] == -42


def test_ble_scan_reports_unavailable_radio(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failed_discover(_timeout: float) -> list[object]:
        raise OSError("radio unavailable")

    monkeypatch.setattr(cli, "discover", failed_discover)

    with pytest.raises(SystemExit, match="BLE scan failed: radio unavailable"):
        cli.main(["ble-scan"])


def test_gatt_requires_live(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_gatt(_address: str) -> list[dict[str, object]]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(cli, "inspect_gatt", fake_gatt)
    with pytest.raises(SystemExit, match="--live"):
        cli.main(["ble-gatt", "mock"])
    assert not called


def test_gatt_live_formats_metadata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_gatt(_address: str) -> list[dict[str, object]]:
        return [{"service": "ff00", "characteristic": "ff01", "properties": ["notify"]}]

    monkeypatch.setattr(cli, "inspect_gatt", fake_gatt)

    assert cli.main(["ble-gatt", "mock", "--live"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["service"] == "ff00"


def test_gatt_reports_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failed_gatt(_address: str) -> list[dict[str, object]]:
        raise OSError("connection unavailable")

    monkeypatch.setattr(cli, "inspect_gatt", failed_gatt)

    with pytest.raises(SystemExit, match="GATT inspection failed: connection unavailable"):
        cli.main(["ble-gatt", "mock", "--live"])


def test_ble_info_requires_live() -> None:
    with pytest.raises(SystemExit, match="--live"):
        cli.main(["ble-info", "mock"])


def test_ble_info_uses_shared_application(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = EmulatedPrinterTransport()
    printer.connection_info = {  # type: ignore[attr-defined]
        "packet_size": 20,
        "host_write_limit": 100,
        "credits": 5,
    }
    monkeypatch.setattr(cli, "BleTransport", lambda *_args, **_kwargs: printer)

    assert cli.main(["ble-info", "mock", "--live"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["model"] == "A2Y"
    assert output["ble"]["packet_size"] == 20


def test_ble_print_requires_both_consent_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "BleTransport", lambda *_args, **_kwargs: printer)

    with pytest.raises(SystemExit, match="--live"):
        cli.main(["ble-print-test", "mock"])
    with pytest.raises(SystemExit, match="--allow-printing"):
        cli.main(["ble-print-test", "mock", "--live"])

    assert printer.writes == []


def test_ble_print_with_both_flags_uses_shared_application(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "BleTransport", lambda *_args, **_kwargs: printer)

    result = cli.main(
        [
            "ble-print-test",
            "mock",
            "--live",
            "--allow-printing",
            "--height",
            "16",
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["completion"] == "aa 0d 0a"
    assert len(printer.completed_jobs) == 1


def test_ble_feed_requires_both_consent_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "BleTransport", lambda *_args, **_kwargs: printer)

    with pytest.raises(SystemExit, match="--live"):
        cli.main(["ble-feed", "mock"])
    with pytest.raises(SystemExit, match="--allow-printing"):
        cli.main(["ble-feed", "mock", "--live"])

    assert printer.writes == []


def test_ble_feed_uses_white_raster_workaround(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "BleTransport", lambda *_args, **_kwargs: printer)

    assert (
        cli.main(
            [
                "ble-feed",
                "mock",
                "--dots",
                "160",
                "--live",
                "--allow-printing",
            ]
        )
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {"fed_dots": 160, "fed_mm": 20.0}
    assert printer.completed_jobs[0][2][8:] == bytes(48)
