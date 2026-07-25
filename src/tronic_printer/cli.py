"""Command-line adapter over the same CQRS application used by other UIs."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from typing import NoReturn

from tronic_printer.application import build_application
from tronic_printer.domain import RasterImage
from tronic_printer.infrastructure.ble import BleTransport, discover, inspect_gatt
from tronic_printer.infrastructure.serial import SerialTransport, available_ports
from tronic_printer.messages import FeedPaper, GetDeviceInfo, PrintRaster, RasterEncoding


def _require(flag: bool, message: str) -> None:
    if not flag:
        raise SystemExit(message)


def _serial_transport(args: argparse.Namespace) -> SerialTransport:
    _require(args.live, "refusing hardware access without --live")
    return SerialTransport(args.port, baudrate=args.baudrate)


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tronic-printer")
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("ports", help="list operating-system serial ports")

    scan = subparsers.add_parser("ble-scan", help="scan for matching BLE advertisements")
    scan.add_argument("--timeout", type=float, default=5.0)

    gatt = subparsers.add_parser(
        "ble-gatt",
        help="enumerate GATT metadata without value reads/writes",
    )
    gatt.add_argument("address")
    gatt.add_argument("--live", action="store_true", help="confirm physical Bluetooth access")

    ble_info = subparsers.add_parser("ble-info", help="query identity and telemetry over BLE")
    ble_info.add_argument("address")
    ble_info.add_argument("--live", action="store_true", help="confirm physical Bluetooth access")

    ble_print = subparsers.add_parser("ble-print-test", help="print a test pattern over BLE")
    ble_print.add_argument("address")
    ble_print.add_argument("--live", action="store_true", help="confirm physical Bluetooth access")
    ble_print.add_argument(
        "--allow-printing",
        action="store_true",
        help="confirm that activating the head and moving paper is allowed",
    )
    ble_print.add_argument("--height", type=int, default=32)
    ble_print.add_argument("--line-width", type=int, default=1)
    ble_print.add_argument("--feed-dots", type=int, default=80)
    ble_print.add_argument(
        "--encoding",
        choices=[encoding.value for encoding in RasterEncoding],
        default=RasterEncoding.CODE_ESC.value,
    )

    ble_feed = subparsers.add_parser("ble-feed", help="advance paper over BLE")
    ble_feed.add_argument("address")
    ble_feed.add_argument("--dots", type=int, default=80)
    ble_feed.add_argument("--live", action="store_true", help="confirm physical Bluetooth access")
    ble_feed.add_argument(
        "--allow-printing",
        action="store_true",
        help="confirm that moving paper is allowed",
    )

    for name in ("info", "print-test"):
        command = subparsers.add_parser(name)
        command.add_argument("--port", required=True)
        command.add_argument("--baudrate", type=int, default=115_200)
        command.add_argument("--live", action="store_true", help="confirm physical printer access")
        if name == "print-test":
            command.add_argument(
                "--allow-printing",
                action="store_true",
                help="confirm that activating the head and moving paper is allowed",
            )
            command.add_argument("--height", type=int, default=32)
            command.add_argument("--line-width", type=int, default=1)
            command.add_argument("--feed-dots", type=int, default=80)
            command.add_argument(
                "--encoding",
                choices=[encoding.value for encoding in RasterEncoding],
                default=RasterEncoding.CODE_ESC.value,
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "ports":
        _print_json(available_ports())
        return 0
    if args.action == "ble-scan":
        try:
            devices = asyncio.run(discover(args.timeout))
        except OSError as error:
            raise SystemExit(f"BLE scan failed: {error}") from error
        _print_json([asdict(item) for item in devices])
        return 0
    if args.action == "ble-gatt":
        _require(args.live, "refusing Bluetooth connection without --live")
        try:
            metadata = asyncio.run(inspect_gatt(args.address))
        except OSError as error:
            raise SystemExit(f"BLE GATT inspection failed: {error}") from error
        _print_json(metadata)
        return 0
    if args.action == "ble-info":
        _require(args.live, "refusing Bluetooth connection without --live")
        try:
            with BleTransport(args.address) as transport:
                info = build_application(transport).queries.ask(GetDeviceInfo())
                result = asdict(info)
                result["status"] = asdict(info.status)
                result["ble"] = transport.connection_info
        except (OSError, TimeoutError) as error:
            raise SystemExit(f"BLE query failed: {error}") from error
        _print_json(result)
        return 0
    if args.action == "ble-print-test":
        _require(args.live, "refusing Bluetooth connection without --live")
        _require(args.allow_printing, "refusing to print without --allow-printing")
        try:
            with BleTransport(args.address) as transport:
                pattern = RasterImage.test_pattern(
                    height=args.height,
                    line_width=args.line_width,
                )
                result = build_application(transport).commands.execute(
                    PrintRaster(
                        pattern,
                        feed_dots=args.feed_dots,
                        encoding=RasterEncoding(args.encoding),
                    )
                )
        except (OSError, TimeoutError) as error:
            raise SystemExit(f"BLE print failed: {error}") from error
        _print_json(asdict(result) | {"completion": result.completion.hex(" ")})
        return 0
    if args.action == "ble-feed":
        _require(args.live, "refusing Bluetooth connection without --live")
        _require(args.allow_printing, "refusing to move paper without --allow-printing")
        try:
            with BleTransport(args.address) as transport:
                build_application(transport).commands.execute(FeedPaper(args.dots))
        except (OSError, TimeoutError) as error:
            raise SystemExit(f"BLE feed failed: {error}") from error
        _print_json({"fed_dots": args.dots, "fed_mm": args.dots / 8})
        return 0

    with _serial_transport(args) as transport:
        app = build_application(transport)
        if args.action == "info":
            info = app.queries.ask(GetDeviceInfo())
            result = asdict(info)
            result["status"] = asdict(info.status)
            _print_json(result)
            return 0
        if args.action == "print-test":
            _require(args.allow_printing, "refusing to print without --allow-printing")
            pattern = RasterImage.test_pattern(
                height=args.height,
                line_width=args.line_width,
            )
            result = app.commands.execute(
                PrintRaster(
                    pattern,
                    feed_dots=args.feed_dots,
                    encoding=RasterEncoding(args.encoding),
                )
            )
            _print_json(asdict(result) | {"completion": result.completion.hex(" ")})
            return 0
    return _unreachable(args.action)


def _unreachable(action: str) -> NoReturn:
    raise AssertionError(f"unhandled action: {action}")
