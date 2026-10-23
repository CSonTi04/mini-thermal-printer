"""NIIMBOT B1 frame parsing, stream buffering, and row primitives.

This module is intentionally narrow and transport-independent: it validates the
upstream-derived packet framing, yields synthetic support for the B1 job model,
and keeps the deterministic raster logic separate from the higher-level TRONIC
application.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from tronic_printer.domain import ProtocolError

NIIMBOT_HEAD: Final[bytes] = b"\x55\x55"
NIIMBOT_TAIL: Final[bytes] = b"\xaa\xaa"
NIIMBOT_CONNECT_PREFIX: Final[bytes] = b"\x03"
NIIMBOT_MODEL_ID: Final[int] = 4096
NIIMBOT_DPI: Final[int] = 203
NIIMBOT_PRINTHEAD_PIXELS: Final[int] = 384
NIIMBOT_ROW_BYTES: Final[int] = 48


@dataclass(frozen=True, slots=True)
class PrinterProfile:
    """A compact capability description for a specific printer model."""

    name: str
    model_id: int
    dpi: int
    printhead_pixels: int
    row_bytes: int
    paper_types: tuple[int, ...]
    continuous_supported: bool = False


B1_PROFILE = PrinterProfile(
    name="NIIMBOT B1",
    model_id=NIIMBOT_MODEL_ID,
    dpi=NIIMBOT_DPI,
    printhead_pixels=NIIMBOT_PRINTHEAD_PIXELS,
    row_bytes=NIIMBOT_ROW_BYTES,
    paper_types=(1, 2, 5),
    continuous_supported=False,
)


def _xor_checksum(command: int, payload: bytes) -> int:
    checksum = command ^ len(payload)
    for byte in payload:
        checksum ^= byte
    return checksum


@dataclass(frozen=True, slots=True)
class NiimbotPacket:
    """A validated NIIMBOT command frame carrying a command and payload."""

    command: int
    payload: bytes
    prefix: bytes = b""

    @property
    def length(self) -> int:
        return len(self.payload)

    @classmethod
    def from_bytes(cls, frame: bytes) -> NiimbotPacket:
        if not frame:
            raise ProtocolError("empty NIIMBOT frame")

        prefix = b""
        if frame.startswith(NIIMBOT_CONNECT_PREFIX):
            prefix = NIIMBOT_CONNECT_PREFIX
            frame = frame[1:]

        if len(frame) < 7:
            raise ProtocolError(f"frame too short for a NIIMBOT packet: {frame.hex(' ')}")
        if not frame.startswith(NIIMBOT_HEAD):
            raise ProtocolError(f"missing NIIMBOT frame head: {frame.hex(' ')}")
        if not frame.endswith(NIIMBOT_TAIL):
            raise ProtocolError(f"missing NIIMBOT frame tail: {frame.hex(' ')}")

        command = frame[2]
        payload_length = frame[3]
        expected_length = 7 + payload_length
        if len(frame) != expected_length:
            raise ProtocolError(
                "frame length mismatch: "
                f"expected {expected_length}, got {len(frame)} ({frame.hex(' ')})"
            )

        payload = frame[4:-3]
        checksum = frame[-3]
        actual = _xor_checksum(command, payload)
        if checksum != actual:
            raise ProtocolError(
                "invalid NIIMBOT checksum: "
                f"expected {checksum:02X}, got {actual:02X} ({frame.hex(' ')})"
            )

        return cls(command=command, payload=bytes(payload), prefix=prefix)

    def to_bytes(self, *, include_connect_prefix: bool = False) -> bytes:
        packet = bytearray()
        packet.extend(NIIMBOT_HEAD)
        packet.append(self.command)
        packet.append(self.length)
        packet.extend(self.payload)
        packet.append(_xor_checksum(self.command, self.payload))
        packet.extend(NIIMBOT_TAIL)
        if include_connect_prefix:
            return NIIMBOT_CONNECT_PREFIX + bytes(packet)
        return bytes(packet)


class NiimbotFrameBuffer:
    """Accumulate raw stream bytes and yield complete NIIMBOT frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    @property
    def buffer(self) -> bytes:
        return bytes(self._buffer)

    def feed(self, chunk: bytes) -> list[NiimbotPacket]:
        if not chunk:
            return []
        self._buffer.extend(chunk)
        packets: list[NiimbotPacket] = []
        while True:
            if len(self._buffer) < 7:
                break

            start = 0
            if self._buffer.startswith(NIIMBOT_CONNECT_PREFIX):
                start = 1
                if len(self._buffer) < 8:
                    break

            if self._buffer[start : start + 2] != NIIMBOT_HEAD:
                search_index = self._buffer.find(NIIMBOT_HEAD, start)
                if search_index < 0:
                    self._buffer.clear()
                    break
                del self._buffer[:search_index]
                continue

            frame_length = 7 + self._buffer[start + 3]
            if len(self._buffer[start:]) < frame_length:
                break

            frame_bytes = bytes(self._buffer[start : start + frame_length])
            if self._buffer.startswith(NIIMBOT_CONNECT_PREFIX):
                packet = NiimbotPacket.from_bytes(NIIMBOT_CONNECT_PREFIX + frame_bytes)
            else:
                packet = NiimbotPacket.from_bytes(frame_bytes)
            packets.append(packet)
            del self._buffer[: start + frame_length]
        return packets


def encode_row(
    *,
    row_index: int,
    row_bits: Iterable[int] | bytes,
    repeat: int = 1,
    page_cols: int = NIIMBOT_PRINTHEAD_PIXELS,
    black_count_mode: str = "split",
) -> bytes:
    """Encode a B1 print row payload with the upstream split/total black-count scheme."""

    if not 0 <= row_index <= 0xFFFF:
        raise ValueError("row_index must fit in unsigned 16 bits")
    if not 1 <= repeat <= 0xFF:
        raise ValueError("repeat must fit in one byte")
    if page_cols <= 0 or page_cols > NIIMBOT_PRINTHEAD_PIXELS:
        raise ValueError("page_cols must fit in the 384-dot B1 head")

    if black_count_mode not in {"split", "total"}:
        raise ValueError("black_count_mode must be 'split' or 'total'")

    row_data = bytes(row_bits)

    expected_bytes = (page_cols + 7) // 8
    if len(row_data) != expected_bytes:
        raise ValueError(
            "row data length must be "
            f"{expected_bytes} bytes for {page_cols} columns, got {len(row_data)}"
        )

    black_total = 0
    for byte in row_data:
        black_total += byte.bit_count()

    counts = [black_total, 0, 0] if black_count_mode == "split" else [0, black_total, 0]

    payload = bytearray()
    payload.extend(row_index.to_bytes(2, "big"))
    for count in counts:
        payload.append(count)
    payload.append(repeat)
    payload.extend(row_data)
    return bytes(payload)


def decode_row(payload: bytes) -> dict[str, object]:
    """Parse a single row packet payload and return its row metadata."""

    if len(payload) < 7:
        raise ProtocolError(f"row payload is too short: {len(payload)} bytes")
    row_index = int.from_bytes(payload[:2], "big")
    count_segment = list(payload[2:5])
    repeat = payload[5]
    row_bytes = payload[6:]
    black_total = sum(count_segment)
    return {
        "row_index": row_index,
        "count_segment": count_segment,
        "repeat": repeat,
        "row_bytes": row_bytes,
        "black_total": black_total,
    }


def encode_print_start(total_pages: int, *, page_color: int = 0) -> bytes:
    if not 0 <= total_pages <= 0xFFFF:
        raise ValueError("total_pages must fit in an unsigned 16-bit integer")
    if not 0 <= page_color <= 0xFF:
        raise ValueError("page_color must fit in one byte")
    payload = total_pages.to_bytes(2, "big") + b"\x00\x00\x00\x00" + bytes((page_color,))
    return NiimbotPacket(0x01, payload).to_bytes()


def encode_set_page_size(rows: int, cols: int, copies: int = 1) -> bytes:
    if not 0 <= rows <= 0xFFFF or not 0 <= cols <= 0xFFFF or not 0 <= copies <= 0xFFFF:
        raise ValueError("page-size values must fit in unsigned 16-bit integers")
    payload = rows.to_bytes(2, "big") + cols.to_bytes(2, "big") + copies.to_bytes(2, "big")
    return NiimbotPacket(0x13, payload).to_bytes()


def encode_empty_row(row_index: int, repeat: int = 1) -> bytes:
    if not 0 <= row_index <= 0xFFFF:
        raise ValueError("row_index must fit in unsigned 16 bits")
    if not 1 <= repeat <= 0xFF:
        raise ValueError("repeat must fit in one byte")
    payload = row_index.to_bytes(2, "big") + repeat.to_bytes(1, "big")
    return NiimbotPacket(0x84, payload).to_bytes()
