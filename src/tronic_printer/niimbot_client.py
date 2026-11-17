"""NIIMBOT B1 client: device queries and the print-job lifecycle over any byte transport.

The wire framing and row primitives live in :mod:`tronic_printer.niimbot`. This
module adds the request/response layer on top of the same synchronous
:class:`~tronic_printer.ports.PrinterTransport` port used by the other printers,
so it works over USB CDC serial (verified for queries and print jobs) or any other
transport that carries NIIMBOT frames.

Evidence labels follow the rest of the project: the query commands and print-job
lifecycle were *Verified* against a physical B1 over USB at 115200 baud and over
BLE. Some details (for example long-job BLE pacing) remain *Recovered* / *Unknown*.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import IntEnum
from typing import Literal

from tronic_printer.domain import PrinterError, ProtocolError, RasterImage
from tronic_printer.niimbot import (
    B1_PROFILE,
    NIIMBOT_PRINTHEAD_PIXELS,
    NiimbotFrameBuffer,
    NiimbotPacket,
    PrinterProfile,
    encode_empty_row,
    encode_print_start,
    encode_set_page_size,
)
from tronic_printer.ports import PrinterTransport

MAX_DENSITY = 5
MAX_ROW_REPEAT = 0xFF
WRITE_CHUNK_BYTES = 4096
FIRST_RESPONSE_TIMEOUT = 3.0
RESPONSE_IDLE_TIMEOUT = 0.15


class NiimbotError(PrinterError):
    """The printer rejected a command or the job could not complete."""


class RequestCode(IntEnum):
    START_PRINT = 0x01
    START_PAGE = 0x03
    SET_DIMENSION = 0x13
    SET_DENSITY = 0x21
    SET_LABEL_TYPE = 0x23
    GET_INFO = 0x40
    ROW_EMPTY = 0x84
    ROW_BITMAP = 0x85
    PRINT_STATUS = 0xA3
    HEARTBEAT = 0xDC
    PAGE_END = 0xE3
    PRINT_END = 0xF3


class InfoKey(IntEnum):
    DENSITY = 1
    LABEL_TYPE = 3
    AUTO_SHUTDOWN = 7
    DEVICE_TYPE = 8
    SOFTWARE_VERSION = 9
    BATTERY = 10
    SERIAL_NUMBER = 11
    HARDWARE_VERSION = 12


class LabelType(IntEnum):
    """Paper types reported by the printer (``3`` is continuous paper)."""

    WITH_GAPS = 1
    BLACK_MARK = 2
    CONTINUOUS = 3
    PERFORATED = 4
    TRANSPARENT = 5


# Response command = request command + 1, except where the printer answers differently.
# 0x21 -> 0x31 is *Verified* on hardware; the others are *Recovered* from upstream.
_RESPONSE_CODES = {
    RequestCode.SET_DENSITY: 0x31,
    RequestCode.SET_LABEL_TYPE: 0x33,
    RequestCode.PRINT_STATUS: 0xB3,
}
_PRINT_STATUS_RESPONSE = 0xB3
_HEARTBEAT_RESPONSE = 0xDD
ERROR_RESPONSE = 0xDB  # the printer reports a failed command with this packet

StartVariant = Literal["legacy", "v3"]


@dataclass(frozen=True, slots=True)
class NiimbotInfo:
    device_type: int
    software_version: str  # "major.minor", e.g. "6.19"
    hardware_version: str
    serial_number: str
    battery_level: int
    density: int
    label_type: int
    auto_shutdown: int | None

    @property
    def model(self) -> str:
        return B1_PROFILE.name if self.device_type == B1_PROFILE.model_id else "unknown"


@dataclass(frozen=True, slots=True)
class NiimbotHeartbeat:
    """Raw heartbeat payload with the 13-byte B1 layout decoded.

    Byte 9 is ``0`` when the cover is closed, byte 10 the battery level, byte 11 is ``0``
    when paper is present and byte 12 is ``1`` when an RFID-tagged roll is detected
    (third-party observation on hardware 6.01 / firmware 6.19, consistent with this
    project's own readings). An untagged roll reads ``0`` there and still prints on
    firmware that skips the tag check.
    """

    raw: bytes
    lid_state: int | None
    power_level: int | None
    paper_state: int | None
    rfid_state: int | None

    @property
    def cover_closed(self) -> bool | None:
        return None if self.lid_state is None else self.lid_state == 0

    @property
    def paper_present(self) -> bool | None:
        return None if self.paper_state is None else self.paper_state == 0


@dataclass(frozen=True, slots=True)
class NiimbotPrintResult:
    rows: int
    packets: int
    bytes_sent: int


def _be(payload: bytes) -> int:
    return int.from_bytes(payload, "big")


def _version(payload: bytes) -> str:
    """Two bytes ``major, minor``: ``06 13`` is 6.19 (not the decimal 1555)."""
    if len(payload) != 2:
        raise ProtocolError(f"version payload must be 2 bytes, got {payload.hex(' ')}")
    return f"{payload[0]}.{payload[1]:02d}"


def _split_black_counts(row: bytes) -> tuple[int, int, int]:
    """Black-pixel counts for the three equal slices of a row (16 bytes each for 384 dots)."""
    step = -(-len(row) // 3)
    parts = (row[:step], row[step : 2 * step], row[2 * step :])
    return tuple(sum(byte.bit_count() for byte in part) for part in parts)  # type: ignore[return-value]


def encode_raster_rows(rows: list[bytes]) -> Iterator[bytes]:
    """Encode rows as NIIMBOT row packets, collapsing identical neighbours into repeats."""
    index = 0
    while index < len(rows):
        row = rows[index]
        repeat = 1
        while (
            index + repeat < len(rows) and rows[index + repeat] == row and repeat < MAX_ROW_REPEAT
        ):
            repeat += 1
        if not any(row):
            yield encode_empty_row(index, repeat)
        else:
            payload = (
                index.to_bytes(2, "big") + bytes(_split_black_counts(row)) + bytes((repeat,)) + row
            )
            yield NiimbotPacket(RequestCode.ROW_BITMAP, payload).to_bytes()
        index += repeat


class NiimbotClient:
    def __init__(
        self,
        transport: PrinterTransport,
        *,
        profile: PrinterProfile = B1_PROFILE,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.transport = transport
        self.profile = profile
        self._sleep = sleep
        self._monotonic = monotonic

    # -- request/response ------------------------------------------------------------------

    def _transceive(
        self, command: int, payload: bytes = b"", *, expect: int | None = None
    ) -> NiimbotPacket:
        wanted = _RESPONSE_CODES.get(command, command + 1) if expect is None else expect
        raw = self.transport.exchange(
            NiimbotPacket(command, payload).to_bytes(),
            timeout=FIRST_RESPONSE_TIMEOUT,
            idle_timeout=RESPONSE_IDLE_TIMEOUT,
        )
        packets = NiimbotFrameBuffer().feed(raw)
        for packet in packets:
            if packet.command == ERROR_RESPONSE:
                raise NiimbotError(
                    f"printer reported an error for 0x{command:02X}: {packet.payload.hex(' ')}"
                )
            if packet.command == wanted:
                return packet
        seen = ", ".join(f"0x{p.command:02X}" for p in packets) or "nothing"
        raise ProtocolError(f"expected response 0x{wanted:02X} to 0x{command:02X}, got {seen}")

    def _acknowledge(self, command: int, payload: bytes, name: str) -> None:
        response = self._transceive(command, payload)
        if not response.payload or response.payload[0] != 1:
            raise NiimbotError(f"printer rejected {name}: {response.payload.hex(' ') or 'empty'}")

    # -- queries -----------------------------------------------------------------------------

    def _info_payload(self, key: InfoKey) -> bytes | None:
        """Payload for an info key, or None when the firmware does not implement it."""
        try:
            return self._transceive(RequestCode.GET_INFO, bytes((key,)), expect=0x40 + key).payload
        except ProtocolError:
            return None

    def device_info(self) -> NiimbotInfo:
        def need(key: InfoKey) -> bytes:
            payload = self._info_payload(key)
            if payload is None:
                raise ProtocolError(f"printer did not answer info query {key.name}")
            return payload

        serial = need(InfoKey.SERIAL_NUMBER)
        auto_shutdown = self._info_payload(InfoKey.AUTO_SHUTDOWN)
        return NiimbotInfo(
            device_type=_be(need(InfoKey.DEVICE_TYPE)),
            software_version=_version(need(InfoKey.SOFTWARE_VERSION)),
            hardware_version=_version(need(InfoKey.HARDWARE_VERSION)),
            serial_number=serial.decode("ascii") if serial.isascii() else serial.hex(),
            battery_level=_be(need(InfoKey.BATTERY)),
            density=_be(need(InfoKey.DENSITY)),
            label_type=_be(need(InfoKey.LABEL_TYPE)),
            auto_shutdown=_be(auto_shutdown) if auto_shutdown else None,
        )

    def heartbeat(self) -> NiimbotHeartbeat:
        data = self._transceive(RequestCode.HEARTBEAT, b"\x01", expect=_HEARTBEAT_RESPONSE).payload
        if len(data) == 13:
            return NiimbotHeartbeat(data, data[9], data[10], data[11], data[12])
        return NiimbotHeartbeat(data, None, None, None, None)

    # -- printing ----------------------------------------------------------------------------

    def print_raster(
        self,
        raster: RasterImage,
        *,
        density: int = 3,
        label_type: int | None = None,
        feed_rows: int = 96,
        start_variant: StartVariant = "v3",
        progress_timeout: float | None = None,
    ) -> NiimbotPrintResult:
        """Print one page.

        ``label_type=None`` re-sends the paper type the printer already reports, so a
        continuous-paper firmware setting is preserved. ``feed_rows`` blank rows are
        appended so the printed content clears the tear bar.
        """
        if raster.width != NIIMBOT_PRINTHEAD_PIXELS:
            raise ValueError(f"raster must be exactly {NIIMBOT_PRINTHEAD_PIXELS} dots wide")
        if not 1 <= density <= MAX_DENSITY:
            raise ValueError(f"density must be between 1 and {MAX_DENSITY}")
        if feed_rows < 0:
            raise ValueError("feed_rows cannot be negative")

        row_bytes = raster.row_bytes
        rows = [raster.data[i * row_bytes : (i + 1) * row_bytes] for i in range(raster.height)]
        rows.extend(bytes(row_bytes) for _ in range(feed_rows))
        packets = list(encode_raster_rows(rows))
        if label_type is None:
            label_type = _be(self._info_payload_required(InfoKey.LABEL_TYPE))

        self._acknowledge(RequestCode.SET_DENSITY, bytes((density,)), "set density")
        self._acknowledge(RequestCode.SET_LABEL_TYPE, bytes((label_type,)), "set label type")
        started = False
        try:
            self._start_print(start_variant)
            started = True
            self._acknowledge(RequestCode.START_PAGE, b"\x01", "start page")
            self._set_dimension(len(rows), raster.width, start_variant)
            sent = self._send_packets(packets)
            self._acknowledge(RequestCode.PAGE_END, b"\x01", "end page")
            self._wait_until_printed(len(rows), progress_timeout)
        except BaseException:
            if started:
                self._abort_quietly()
            raise
        self._acknowledge(RequestCode.PRINT_END, b"\x01", "end print")
        return NiimbotPrintResult(rows=len(rows), packets=len(packets), bytes_sent=sent)

    def _info_payload_required(self, key: InfoKey) -> bytes:
        payload = self._info_payload(key)
        if payload is None:
            raise ProtocolError(f"printer did not answer info query {key.name}")
        return payload

    def _start_print(self, variant: StartVariant) -> None:
        if variant == "legacy":
            self._acknowledge(RequestCode.START_PRINT, b"\x01", "start print")
            return
        frame = encode_print_start(1)
        packet = NiimbotPacket.from_bytes(frame)
        self._acknowledge(packet.command, packet.payload, "start print")

    def _set_dimension(self, rows: int, cols: int, variant: StartVariant) -> None:
        if variant == "legacy":
            payload = rows.to_bytes(2, "big") + cols.to_bytes(2, "big")
        else:
            payload = NiimbotPacket.from_bytes(encode_set_page_size(rows, cols, 1)).payload
        self._acknowledge(RequestCode.SET_DIMENSION, payload, "set page size")

    def _send_packets(self, packets: list[bytes]) -> int:
        total = 0
        chunk = bytearray()
        for packet in packets:
            if chunk and len(chunk) + len(packet) > WRITE_CHUNK_BYTES:
                self.transport.write(bytes(chunk))
                total += len(chunk)
                chunk.clear()
            chunk.extend(packet)
        if chunk:
            self.transport.write(bytes(chunk))
            total += len(chunk)
        return total

    def _wait_until_printed(self, rows: int, timeout: float | None) -> None:
        deadline = self._monotonic() + (timeout if timeout is not None else 30.0 + rows * 0.05)
        while True:
            payload = self._transceive(
                RequestCode.PRINT_STATUS, b"\x01", expect=_PRINT_STATUS_RESPONSE
            ).payload
            if len(payload) >= 4 and _be(payload[:2]) >= 1 and payload[2] == 100 == payload[3]:
                return
            if self._monotonic() > deadline:
                raise TimeoutError("printer did not report the page as finished in time")
            self._sleep(0.2)

    def _abort_quietly(self) -> None:
        with contextlib.suppress(OSError, TimeoutError, PrinterError):
            self._transceive(RequestCode.PRINT_END, b"\x01")
