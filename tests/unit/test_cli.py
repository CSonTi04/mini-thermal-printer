import json
from pathlib import Path

import pytest
from PIL import Image, ImageFont

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


def test_image_effects_lists_builtin_plugins(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["image-effects"]) == 0

    names = {item["name"] for item in json.loads(capsys.readouterr().out)}
    assert {"autocontrast", "contrast", "edge", "gamma", "invert"} <= names


def test_prepare_image_writes_exact_preview_without_hardware(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    preview = tmp_path / "preview.png"
    pixels = Image.new("L", (2, 1))
    pixels.putdata([0, 255])
    pixels.save(source)
    monkeypatch.setattr(
        cli,
        "BleTransport",
        lambda *_args, **_kwargs: pytest.fail("prepare-image opened Bluetooth"),
    )

    result = cli.main(
        [
            "prepare-image",
            str(source),
            "--output",
            str(preview),
            "--width",
            "2",
            "--effect",
            "invert",
            "--dither",
            "ordered-4x4",
        ]
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["preview"] == str(preview)
    assert output["effects"] == ["invert"]
    assert output["code_esc_frame_bytes"] > 10
    with Image.open(preview) as rendered:
        assert rendered.size == (2, 1)
        assert set(rendered.tobytes()) <= {0, 255}


def test_prepare_showcase_writes_four_labeled_pages_without_hardware(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    output_dir = tmp_path / "showcase"
    Image.new("RGB", (16, 16), "gray").save(source)
    monkeypatch.setattr(
        cli,
        "BleTransport",
        lambda *_args, **_kwargs: pytest.fail("prepare-showcase opened Bluetooth"),
    )

    assert cli.main(["prepare-showcase", str(source), "-o", str(output_dir)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert [page["slug"] for page in output] == [
        "floyd-photo",
        "ordered-newsprint",
        "gritty-noir",
        "outline-sketch",
    ]
    assert len(list(output_dir.glob("*.png"))) == 4


def test_prepare_text_renders_unicode_font_preview_without_hardware(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    preview = tmp_path / "text.png"
    font_path = Path(ImageFont.truetype("DejaVuSans.ttf", 12).path)
    monkeypatch.setattr(
        cli,
        "BleTransport",
        lambda *_args, **_kwargs: pytest.fail("prepare-text opened Bluetooth"),
    )

    assert (
        cli.main(
            [
                "prepare-text",
                "Pergel Dávid\nTóth András",
                "--font-file",
                str(font_path),
                "--font-size",
                "24",
                "--align",
                "center",
                "--output",
                str(preview),
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["font"]["family"] == "DejaVu Sans"
    assert output["line_count"] == 2
    assert output["align"] == "center"
    assert preview.is_file()


def test_prepare_text_reads_utf8_file_and_rejects_conflicting_sources(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    source = tmp_path / "message.txt"
    preview = tmp_path / "text.png"
    source.write_text("Árvíztűrő tükörfúrógép", encoding="utf-8")

    assert cli.main(["prepare-text", "--text-file", str(source), "-o", str(preview)]) == 0
    assert json.loads(capsys.readouterr().out)["black_pixels"] > 0

    with pytest.raises(SystemExit, match="either inline text"):
        cli.main(
            [
                "prepare-text",
                "inline",
                "--text-file",
                str(source),
                "-o",
                str(preview),
            ]
        )


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


def test_ble_print_image_requires_both_consent_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "sample.png"
    Image.new("L", (2, 1), color=0).save(image)
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "BleTransport", lambda *_args, **_kwargs: printer)

    with pytest.raises(SystemExit, match="--live"):
        cli.main(["ble-print-image", "mock", str(image)])
    with pytest.raises(SystemExit, match="--allow-printing"):
        cli.main(["ble-print-image", "mock", str(image), "--live"])

    assert printer.writes == []


def test_ble_print_image_uses_shared_application(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    image = tmp_path / "sample.png"
    pixels = Image.new("L", (2, 1))
    pixels.putdata([0, 255])
    pixels.save(image)
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "BleTransport", lambda *_args, **_kwargs: printer)

    result = cli.main(
        [
            "ble-print-image",
            "mock",
            str(image),
            "--width",
            "2",
            "--live",
            "--allow-printing",
        ]
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["completion"] == "aa 0d 0a"
    assert output["image"]["width"] == 2
    assert output["image"]["height"] == 1
    assert len(printer.completed_jobs) == 1
    assert printer.completed_jobs[0][2].startswith(bytes.fromhex("1F 10"))


def test_ble_print_image_rejects_invalid_image_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    opened = False

    def open_transport(*_args: object, **_kwargs: object) -> EmulatedPrinterTransport:
        nonlocal opened
        opened = True
        return EmulatedPrinterTransport()

    monkeypatch.setattr(cli, "BleTransport", open_transport)

    with pytest.raises(SystemExit, match="cannot prepare image"):
        cli.main(
            [
                "ble-print-image",
                "mock",
                str(tmp_path / "missing.png"),
                "--live",
                "--allow-printing",
            ]
        )

    assert not opened


def test_ble_print_text_requires_consent_and_uses_shared_application(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = EmulatedPrinterTransport()
    monkeypatch.setattr(cli, "BleTransport", lambda *_args, **_kwargs: printer)

    with pytest.raises(SystemExit, match="--live"):
        cli.main(["ble-print-text", "mock", "hello"])
    with pytest.raises(SystemExit, match="--allow-printing"):
        cli.main(["ble-print-text", "mock", "hello", "--live"])
    assert printer.writes == []

    assert (
        cli.main(
            [
                "ble-print-text",
                "mock",
                "Pergel Dávid",
                "--font-size",
                "20",
                "--live",
                "--allow-printing",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["completion"] == "aa 0d 0a"
    assert output["text"]["font_size"] == 20
    assert len(printer.completed_jobs) == 1


def test_ble_print_text_rejects_invalid_font_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    opened = False

    def open_transport(*_args: object, **_kwargs: object) -> EmulatedPrinterTransport:
        nonlocal opened
        opened = True
        return EmulatedPrinterTransport()

    monkeypatch.setattr(cli, "BleTransport", open_transport)
    with pytest.raises(SystemExit, match="cannot prepare text"):
        cli.main(
            [
                "ble-print-text",
                "mock",
                "hello",
                "--font-file",
                str(tmp_path / "missing.ttf"),
                "--live",
                "--allow-printing",
            ]
        )
    assert not opened


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
