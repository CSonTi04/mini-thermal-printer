"""Command-line adapter over the same CQRS application used by other UIs."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from typing import NoReturn

from tronic_printer.application import build_application
from tronic_printer.domain import RasterImage
from tronic_printer.infrastructure.ble import discover, inspect_gatt
from tronic_printer.infrastructure.serial import SerialTransport, available_ports
from tronic_printer.messages import GetDeviceInfo, PrintRaster


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "ports":
        _print_json(available_ports())
        return 0
    if args.action == "ble-scan":
        _print_json([asdict(item) for item in asyncio.run(discover(args.timeout))])
        return 0
    if args.action == "ble-gatt":
        _require(args.live, "refusing Bluetooth connection without --live")
        _print_json(asyncio.run(inspect_gatt(args.address)))
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
            pattern = RasterImage.test_pattern(height=args.height)
            result = app.commands.execute(PrintRaster(pattern))
            _print_json(asdict(result) | {"completion": result.completion.hex(" ")})
            return 0
    return _unreachable(args.action)


def _unreachable(action: str) -> NoReturn:
    raise AssertionError(f"unhandled action: {action}")
