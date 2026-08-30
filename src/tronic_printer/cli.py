"""Command-line adapter over the same CQRS application used by other UIs."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

from tronic_printer import protocol
from tronic_printer.application import build_application
from tronic_printer.domain import RasterImage
from tronic_printer.infrastructure.ble import BleTransport, discover, inspect_gatt
from tronic_printer.infrastructure.serial import SerialTransport, available_ports
from tronic_printer.messages import (
    FeedPaper,
    GetDeviceInfo,
    PrintRaster,
    PrintResult,
    RasterEncoding,
)
from tronic_printer.preprocessing import (
    DitherMode,
    EffectSpec,
    ImagePreparationConfig,
    PreparedImage,
    build_effect_registry,
    load_prepared_image,
)
from tronic_printer.showcase import load_showcase_pages
from tronic_printer.text import (
    FontCatalog,
    FontSpec,
    PreparedText,
    TextAlign,
    TextLayoutConfig,
    prepare_text,
)


def _require(flag: bool, message: str) -> None:
    if not flag:
        raise SystemExit(message)


def _serial_transport(args: argparse.Namespace) -> SerialTransport:
    _require(args.live, "refusing hardware access without --live")
    return SerialTransport(args.port, baudrate=args.baudrate)


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _add_print_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--feed-dots", type=int, default=80)
    parser.add_argument(
        "--encoding",
        choices=[encoding.value for encoding in RasterEncoding],
        default=RasterEncoding.CODE_ESC.value,
    )


def _add_preparation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("image", help="PNG, JPEG, BMP, or another Pillow-readable image")
    parser.add_argument("--width", type=int, default=384, help="output width in dots")
    parser.add_argument("--threshold", type=int, default=128, help="black threshold from 0 to 255")
    parser.add_argument(
        "--dither",
        choices=[mode.value for mode in DitherMode],
        default=DitherMode.THRESHOLD.value,
    )
    parser.add_argument(
        "--effect",
        action="append",
        default=[],
        metavar="NAME[:KEY=VALUE,...]",
        help="apply a registered effect; repeat to build an ordered chain",
    )


def _add_image_print_options(parser: argparse.ArgumentParser) -> None:
    _add_preparation_options(parser)
    parser.add_argument("--preview", help="save the exact one-bit raster PNG before connecting")
    _add_print_options(parser)


def _add_text_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("text", nargs="?", help="Unicode text to render")
    parser.add_argument(
        "--text-file",
        help="read UTF-8 text from a file, or use '-' for standard input",
    )
    font_source = parser.add_mutually_exclusive_group()
    font_source.add_argument("--font-family", help="installed font family name")
    font_source.add_argument("--font-file", type=Path, help="TTF, OTF, or TTC font file")
    parser.add_argument("--font-size", type=int, default=28, help="font size in printer dots")
    parser.add_argument("--bold", action="store_true", help="request a bold family face")
    parser.add_argument("--italic", action="store_true", help="request an italic family face")
    parser.add_argument(
        "--align",
        choices=[alignment.value for alignment in TextAlign],
        default=TextAlign.LEFT.value,
    )
    parser.add_argument("--width", type=int, default=384, help="output width in dots")
    parser.add_argument("--margin", type=int, default=12, help="left/right/top/bottom margin")
    parser.add_argument("--line-spacing", type=int, default=4, help="extra dots between lines")
    parser.add_argument("--threshold", type=int, default=180, help="black threshold from 0 to 255")


def _add_text_print_options(parser: argparse.ArgumentParser) -> None:
    _add_text_options(parser)
    parser.add_argument("--preview", help="save the exact one-bit raster PNG before connecting")
    _add_print_options(parser)


def _prepare_image_or_exit(args: argparse.Namespace) -> PreparedImage:
    try:
        config = ImagePreparationConfig(
            width=args.width,
            threshold=args.threshold,
            dither=DitherMode(args.dither),
            effects=tuple(EffectSpec.parse(value) for value in args.effect),
        )
        prepared = load_prepared_image(
            args.image,
            config,
            registry=build_effect_registry(),
        )
        if getattr(args, "preview", None):
            prepared.save_preview(args.preview)
        return prepared
    except (ImportError, OSError, TypeError, ValueError) as error:
        raise SystemExit(f"cannot prepare image: {error}") from error


def _read_text_or_exit(args: argparse.Namespace) -> str:
    if args.text is not None and args.text_file is not None:
        raise SystemExit("choose either inline text or --text-file, not both")
    if args.text_file == "-":
        value = sys.stdin.read()
    elif args.text_file is not None:
        try:
            value = Path(args.text_file).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise SystemExit(f"cannot read text file: {error}") from error
    elif args.text is not None:
        value = args.text
    else:
        raise SystemExit("text is required (inline or via --text-file)")
    return value


def _prepare_text_or_exit(args: argparse.Namespace) -> PreparedText:
    try:
        prepared = prepare_text(
            _read_text_or_exit(args),
            FontSpec(
                size=args.font_size,
                family=args.font_family,
                path=args.font_file,
                bold=args.bold,
                italic=args.italic,
            ),
            TextLayoutConfig(
                width=args.width,
                margin=args.margin,
                line_spacing=args.line_spacing,
                align=TextAlign(args.align),
            ),
            threshold=args.threshold,
        )
        if getattr(args, "preview", None):
            prepared.prepared.save_preview(args.preview)
        return prepared
    except (OSError, TypeError, ValueError) as error:
        raise SystemExit(f"cannot prepare text: {error}") from error


def _print_result(result: PrintResult, raster: RasterImage) -> None:
    values = asdict(result)
    values["completion"] = result.completion.hex(" ")
    values["width"] = raster.width
    values["height"] = raster.height
    _print_json(values)


def _prepared_summary(prepared: PreparedImage) -> dict[str, object]:
    return prepared.summary() | {
        "code_esc_frame_bytes": len(protocol.encode_compressed_raster(prepared.raster))
    }


def _prepared_print_result(result: PrintResult, prepared: PreparedImage) -> None:
    values = asdict(result)
    values["completion"] = result.completion.hex(" ")
    values["image"] = _prepared_summary(prepared)
    _print_json(values)


def _prepared_text_summary(prepared: PreparedText) -> dict[str, object]:
    return prepared.summary() | {
        "code_esc_frame_bytes": len(protocol.encode_compressed_raster(prepared.prepared.raster))
    }


def _prepared_text_print_result(result: PrintResult, prepared: PreparedText) -> None:
    values = asdict(result)
    values["completion"] = result.completion.hex(" ")
    values["text"] = _prepared_text_summary(prepared)
    _print_json(values)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tronic-printer")
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("ports", help="list operating-system serial ports")
    subparsers.add_parser("image-effects", help="list built-in and installed image effects")

    fonts = subparsers.add_parser("fonts", help="list discoverable system font faces")
    fonts.add_argument("--family", help="filter by family name")

    prepare = subparsers.add_parser(
        "prepare-image",
        help="prepare and preview the exact raster without hardware access",
    )
    _add_preparation_options(prepare)
    prepare.add_argument("--output", "-o", required=True, help="destination PNG preview")

    prepare_text_parser = subparsers.add_parser(
        "prepare-text",
        help="render Unicode text to an exact print preview without hardware access",
    )
    _add_text_options(prepare_text_parser)
    prepare_text_parser.add_argument("--output", "-o", required=True, help="destination PNG")

    showcase = subparsers.add_parser(
        "prepare-showcase",
        help="build the four labeled style pages without hardware access",
    )
    showcase.add_argument("image", help="source image used for all four recipes")
    showcase.add_argument("--output-dir", "-o", required=True)

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
    _add_print_options(ble_print)

    ble_image = subparsers.add_parser("ble-print-image", help="print an image over BLE")
    ble_image.add_argument("address")
    ble_image.add_argument("--live", action="store_true", help="confirm physical Bluetooth access")
    ble_image.add_argument(
        "--allow-printing",
        action="store_true",
        help="confirm that activating the head and moving paper is allowed",
    )
    _add_image_print_options(ble_image)

    ble_text = subparsers.add_parser(
        "ble-print-text",
        help="render and print Unicode text over BLE",
    )
    ble_text.add_argument("address")
    ble_text.add_argument("--live", action="store_true", help="confirm physical Bluetooth access")
    ble_text.add_argument(
        "--allow-printing",
        action="store_true",
        help="confirm that activating the head and moving paper is allowed",
    )
    _add_text_print_options(ble_text)

    ble_feed = subparsers.add_parser("ble-feed", help="advance paper over BLE")
    ble_feed.add_argument("address")
    ble_feed.add_argument("--dots", type=int, default=80)
    ble_feed.add_argument("--live", action="store_true", help="confirm physical Bluetooth access")
    ble_feed.add_argument(
        "--allow-printing",
        action="store_true",
        help="confirm that moving paper is allowed",
    )

    for name in ("info", "print-test", "print-image", "print-text"):
        command = subparsers.add_parser(name)
        command.add_argument("--port", required=True)
        command.add_argument("--baudrate", type=int, default=115_200)
        command.add_argument("--live", action="store_true", help="confirm physical printer access")
        if name in {"print-test", "print-image", "print-text"}:
            command.add_argument(
                "--allow-printing",
                action="store_true",
                help="confirm that activating the head and moving paper is allowed",
            )
        if name == "print-test":
            command.add_argument("--height", type=int, default=32)
            command.add_argument("--line-width", type=int, default=1)
            _add_print_options(command)
        elif name == "print-image":
            _add_image_print_options(command)
        elif name == "print-text":
            _add_text_print_options(command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "ports":
        _print_json(available_ports())
        return 0
    if args.action == "image-effects":
        try:
            _print_json(build_effect_registry().describe())
        except (ImportError, TypeError, ValueError) as error:
            raise SystemExit(f"cannot load image effects: {error}") from error
        return 0
    if args.action == "fonts":
        try:
            _print_json(FontCatalog().describe(args.family))
        except OSError as error:
            raise SystemExit(f"cannot discover fonts: {error}") from error
        return 0
    if args.action == "prepare-image":
        prepared = _prepare_image_or_exit(args)
        try:
            prepared.save_preview(Path(args.output))
        except OSError as error:
            raise SystemExit(f"cannot save preview: {error}") from error
        _print_json(_prepared_summary(prepared) | {"preview": str(Path(args.output))})
        return 0
    if args.action == "prepare-text":
        prepared_text = _prepare_text_or_exit(args)
        try:
            prepared_text.prepared.save_preview(Path(args.output))
        except OSError as error:
            raise SystemExit(f"cannot save preview: {error}") from error
        _print_json(
            _prepared_text_summary(prepared_text) | {"preview": str(Path(args.output))}
        )
        return 0
    if args.action == "prepare-showcase":
        output_dir = Path(args.output_dir)
        try:
            pages = load_showcase_pages(args.image)
            output_dir.mkdir(parents=True, exist_ok=True)
            summaries: list[dict[str, object]] = []
            for index, page in enumerate(pages, start=1):
                destination = output_dir / f"{index:02d}-{page.recipe.slug}.png"
                page.preview.save(destination)
                summaries.append(page.summary() | {"preview": str(destination)})
        except (OSError, TypeError, ValueError) as error:
            raise SystemExit(f"cannot prepare showcase: {error}") from error
        _print_json(summaries)
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
        _print_result(result, pattern)
        return 0
    if args.action == "ble-print-image":
        _require(args.live, "refusing Bluetooth connection without --live")
        _require(args.allow_printing, "refusing to print without --allow-printing")
        prepared = _prepare_image_or_exit(args)
        try:
            with BleTransport(args.address) as transport:
                result = build_application(transport).commands.execute(
                    PrintRaster(
                        prepared.raster,
                        feed_dots=args.feed_dots,
                        encoding=RasterEncoding(args.encoding),
                    )
                )
        except (OSError, TimeoutError) as error:
            raise SystemExit(f"BLE print failed: {error}") from error
        _prepared_print_result(result, prepared)
        return 0
    if args.action == "ble-print-text":
        _require(args.live, "refusing Bluetooth connection without --live")
        _require(args.allow_printing, "refusing to print without --allow-printing")
        prepared_text = _prepare_text_or_exit(args)
        try:
            with BleTransport(args.address) as transport:
                result = build_application(transport).commands.execute(
                    PrintRaster(
                        prepared_text.prepared.raster,
                        feed_dots=args.feed_dots,
                        encoding=RasterEncoding(args.encoding),
                    )
                )
        except (OSError, TimeoutError) as error:
            raise SystemExit(f"BLE print failed: {error}") from error
        _prepared_text_print_result(result, prepared_text)
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

    if args.action == "print-image":
        _require(args.live, "refusing hardware access without --live")
        _require(args.allow_printing, "refusing to print without --allow-printing")
        prepared = _prepare_image_or_exit(args)
        with SerialTransport(args.port, baudrate=args.baudrate) as transport:
            result = build_application(transport).commands.execute(
                PrintRaster(
                    prepared.raster,
                    feed_dots=args.feed_dots,
                    encoding=RasterEncoding(args.encoding),
                )
            )
        _prepared_print_result(result, prepared)
        return 0

    if args.action == "print-text":
        _require(args.live, "refusing hardware access without --live")
        _require(args.allow_printing, "refusing to print without --allow-printing")
        prepared_text = _prepare_text_or_exit(args)
        with SerialTransport(args.port, baudrate=args.baudrate) as transport:
            result = build_application(transport).commands.execute(
                PrintRaster(
                    prepared_text.prepared.raster,
                    feed_dots=args.feed_dots,
                    encoding=RasterEncoding(args.encoding),
                )
            )
        _prepared_text_print_result(result, prepared_text)
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
            _print_result(result, pattern)
            return 0
    return _unreachable(args.action)


def _unreachable(action: str) -> NoReturn:
    raise AssertionError(f"unhandled action: {action}")
