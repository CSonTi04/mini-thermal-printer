"""Verified and statically recovered printer protocol encoding."""

from __future__ import annotations

import zlib

from tronic_printer.domain import ProtocolError, RasterImage

QUERY_MODEL = bytes.fromhex("10 FF 20 F0")
QUERY_FIRMWARE = bytes.fromhex("10 FF 20 F1")
QUERY_SERIAL = bytes.fromhex("10 FF 20 F2")
QUERY_BOOT_INFO = bytes.fromhex("10 FF 20 EF")
QUERY_BATTERY = bytes.fromhex("10 FF 50 F1")
QUERY_DENSITY = bytes.fromhex("10 FF 11")
QUERY_STATUS = bytes.fromhex("10 FF 40")
QUERY_SHUTDOWN_TIME = bytes.fromhex("10 FF 13")
QUERY_SPEED = bytes.fromhex("10 FF 20 A0")
QUERY_TIME_FORMAT = bytes.fromhex("10 FF B0")

START_JOB = bytes.fromhex("10 FF F1 03")
WAKE_PREFIX = bytes(12)
STOP_JOB = bytes.fromhex("10 FF F1 45")
MAX_PRINT_WIDTH = 384


def decode_ascii(response: bytes, field: str) -> str:
    if not response:
        raise ProtocolError(f"empty {field} response")
    try:
        return response.rstrip(b"\x00\r\n").decode("ascii")
    except UnicodeDecodeError as error:
        raise ProtocolError(f"non-ASCII {field} response: {response.hex(' ')}") from error


def decode_battery(response: bytes) -> int:
    if len(response) < 2:
        raise ProtocolError(f"battery response is too short: {response.hex(' ')}")
    value = response[1]
    if value > 100:
        raise ProtocolError(f"invalid battery percentage: {value}")
    return value


def decode_density(response: bytes) -> int:
    if not response:
        raise ProtocolError("empty density response")
    value = response[0]
    if value > 2:
        raise ProtocolError(f"invalid density: {value}")
    return value


def decode_status(response: bytes) -> int:
    if not response:
        raise ProtocolError("empty status response")
    return response[0]


def decode_shutdown_time(response: bytes) -> int:
    """Decode the SDK's one- or two-byte shutdown-time response."""
    if not response:
        raise ProtocolError("empty shutdown-time response")
    return response[1] if len(response) == 2 else response[0]


def decode_speed(response: bytes) -> int:
    if not response:
        raise ProtocolError("empty speed response")
    return response[0]


def decode_time_format(response: bytes) -> int:
    if len(response) != 1:
        raise ProtocolError(
            f"time-format response must contain exactly one byte: {response.hex(' ')}"
        )
    return response[0]


def set_density(level: int) -> bytes:
    if level not in range(3):
        raise ValueError("density must be 0, 1, or 2")
    return bytes((0x10, 0xFF, 0x10, 0x00, level))


def set_shutdown_time(minutes: int) -> bytes:
    if minutes not in {5, 10, 20, 30, 60}:
        raise ValueError("shutdown time must be 5, 10, 20, 30, or 60 minutes")
    return bytes((0x10, 0xFF, 0x12)) + minutes.to_bytes(2, "big")


def start_job(mode: int = 3) -> bytes:
    if not 0 <= mode <= 0xFF:
        raise ValueError("job mode must fit in one byte")
    return bytes((0x10, 0xFF, 0xF1, mode))


def feed_dots(dots: int) -> bytes:
    if not 0 <= dots <= 0xFF:
        raise ValueError("feed must be between 0 and 255 dots")
    return bytes((0x1B, 0x4A, dots))


def encode_uncompressed_raster(raster: RasterImage, mode: int = 0) -> bytes:
    if mode not in range(4):
        raise ValueError("raster mode must be between 0 and 3")
    if raster.width > MAX_PRINT_WIDTH:
        raise ValueError(f"raster exceeds the {MAX_PRINT_WIDTH}-dot print head")
    if raster.row_bytes > 0xFFFF or raster.height > 0xFFFF:
        raise ValueError("raster dimensions exceed the protocol envelope")
    x = raster.row_bytes.to_bytes(2, "little")
    y = raster.height.to_bytes(2, "little")
    return bytes((0x1D, 0x76, 0x30, mode)) + x + y + raster.data


def compress_code_esc(data: bytes) -> bytes:
    """Reproduce the native codeESC zlib stream exactly."""
    compressor = zlib.compressobj(
        level=zlib.Z_DEFAULT_COMPRESSION,
        method=zlib.DEFLATED,
        wbits=10,
        memLevel=8,
        strategy=zlib.Z_DEFAULT_STRATEGY,
    )
    return compressor.compress(data) + compressor.flush(zlib.Z_FINISH)


def encode_compressed_raster(raster: RasterImage) -> bytes:
    if raster.width > MAX_PRINT_WIDTH:
        raise ValueError(f"raster exceeds the {MAX_PRINT_WIDTH}-dot print head")
    if raster.row_bytes > 0xFFFF or raster.height > 0xFFFF:
        raise ValueError("raster dimensions exceed the protocol envelope")
    payload = compress_code_esc(raster.data)
    return (
        bytes((0x1F, 0x10))
        + raster.row_bytes.to_bytes(2, "big")
        + raster.height.to_bytes(2, "big")
        + len(payload).to_bytes(4, "big")
        + payload
    )


def is_success(response: bytes) -> bool:
    return bool(response) and (response[0] == 0xAA or response.startswith(b"OK"))
