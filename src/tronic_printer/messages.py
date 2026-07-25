"""CQRS messages shared by every presentation adapter."""

from __future__ import annotations

from dataclasses import dataclass

from tronic_printer.domain import RasterImage


@dataclass(frozen=True, slots=True)
class GetModel:
    pass


@dataclass(frozen=True, slots=True)
class GetFirmware:
    pass


@dataclass(frozen=True, slots=True)
class GetBattery:
    pass


@dataclass(frozen=True, slots=True)
class GetDensity:
    pass


@dataclass(frozen=True, slots=True)
class GetStatus:
    pass


@dataclass(frozen=True, slots=True)
class GetDeviceInfo:
    pass


@dataclass(frozen=True, slots=True)
class SetDensity:
    level: int


@dataclass(frozen=True, slots=True)
class FeedPaper:
    dots: int


@dataclass(frozen=True, slots=True)
class PrintRaster:
    raster: RasterImage
    feed_dots: int = 80
    job_mode: int = 3


@dataclass(frozen=True, slots=True)
class PrintResult:
    raster_bytes: int
    total_bytes: int
    completion: bytes
