"""Transport-independent domain values."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


class PrinterError(Exception):
    """Base error raised by the driver."""


class ProtocolError(PrinterError):
    """A device response or encoded command is invalid."""


class PrinterNotReady(PrinterError):
    """Printing was rejected because the printer reports an unsafe state."""


@dataclass(frozen=True, slots=True)
class PrinterStatus:
    raw: int
    printing: bool
    cover_open: bool
    paper_absent: bool
    low_battery: bool
    overheated: bool
    charging: bool

    @classmethod
    def from_byte(cls, value: int) -> PrinterStatus:
        if not 0 <= value <= 0xFF:
            raise ValueError("status must fit in one byte")
        return cls(
            raw=value,
            printing=bool(value & 0x01),
            cover_open=bool(value & 0x02),
            paper_absent=bool(value & 0x04),
            low_battery=bool(value & 0x08),
            overheated=bool(value & 0x10 or value & 0x40),
            charging=bool(value & 0x20),
        )

    @property
    def can_print(self) -> bool:
        return not (self.cover_open or self.paper_absent or self.overheated)


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    model: str
    firmware: str
    battery_percent: int
    density: int
    status: PrinterStatus


@dataclass(frozen=True, slots=True)
class RasterImage:
    """A row-major, one-bit image with black pixels represented by set bits."""

    width: int
    height: int
    data: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("raster dimensions must be positive")
        expected = self.row_bytes * self.height
        if len(self.data) != expected:
            raise ValueError(f"expected {expected} raster bytes, got {len(self.data)}")

    @property
    def row_bytes(self) -> int:
        return (self.width + 7) // 8

    @classmethod
    def from_rows(cls, rows: Sequence[Sequence[bool]]) -> RasterImage:
        if not rows or not rows[0]:
            raise ValueError("raster requires at least one pixel")
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise ValueError("all raster rows must have equal width")

        packed = bytearray(((width + 7) // 8) * len(rows))
        row_bytes = (width + 7) // 8
        for y, row in enumerate(rows):
            for x, is_black in enumerate(row):
                if is_black:
                    packed[y * row_bytes + x // 8] |= 0x80 >> (x % 8)
        return cls(width=width, height=len(rows), data=bytes(packed))

    @classmethod
    def test_pattern(cls, width: int = 384, height: int = 32) -> RasterImage:
        """Create a deterministic border/crosshatch pattern for physical tests."""
        if width < 8 or height < 8:
            raise ValueError("test pattern must be at least 8 by 8 pixels")
        rows: list[list[bool]] = []
        for y in range(height):
            row = []
            for x in range(width):
                border = x in (0, width - 1) or y in (0, height - 1)
                crosshair = x == width // 2 or y == height // 2
                ticks = y < 8 and x % 16 == 0
                row.append(border or crosshair or ticks)
            rows.append(row)
        return cls.from_rows(rows)


def pack_black_pixels(rows: Iterable[Iterable[bool]]) -> RasterImage:
    """Convenience wrapper accepting arbitrary finite iterables."""
    materialized = [list(row) for row in rows]
    return RasterImage.from_rows(materialized)
