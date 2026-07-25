"""Classic Bluetooth SPP adapter through an operating-system serial port."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import serial
from serial.tools import list_ports


def available_ports() -> list[dict[str, str | None]]:
    return [
        {
            "device": port.device,
            "description": port.description,
            "hwid": port.hwid,
        }
        for port in list_ports.comports()
    ]


class SerialTransport:
    """Serial transport with inactivity-delimited responses."""

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 115_200,
        write_chunk_size: int = 16_384,
        serial_factory: Callable[..., Any] = serial.Serial,
    ) -> None:
        if write_chunk_size <= 0:
            raise ValueError("write_chunk_size must be positive")
        self._write_chunk_size = write_chunk_size
        self._serial = serial_factory(
            port=port,
            baudrate=baudrate,
            timeout=0.02,
            write_timeout=3.0,
        )

    def write(self, payload: bytes) -> None:
        written = 0
        while written < len(payload):
            chunk = payload[written : written + self._write_chunk_size]
            chunk_written = self._serial.write(chunk)
            if chunk_written != len(chunk):
                raise OSError(f"short serial write: {chunk_written}/{len(chunk)} bytes")
            written += chunk_written
        self._serial.flush()

    def exchange(
        self,
        payload: bytes,
        *,
        timeout: float = 3.0,
        idle_timeout: float = 0.10,
        min_bytes: int = 1,
    ) -> bytes:
        if timeout <= 0 or idle_timeout <= 0 or min_bytes <= 0:
            raise ValueError("timeouts and min_bytes must be positive")
        self._serial.reset_input_buffer()
        self.write(payload)

        response = bytearray()
        deadline = time.monotonic() + timeout
        last_received: float | None = None
        while time.monotonic() < deadline:
            waiting = self._serial.in_waiting
            chunk = self._serial.read(max(waiting, 1))
            if chunk:
                response.extend(chunk)
                last_received = time.monotonic()
            elif (
                len(response) >= min_bytes
                and last_received is not None
                and time.monotonic() - last_received >= idle_timeout
            ):
                break
        if len(response) < min_bytes:
            raise TimeoutError(
                f"printer response timed out after {timeout:.1f}s "
                f"({len(response)}/{min_bytes} bytes)"
            )
        return bytes(response)

    def close(self) -> None:
        self._serial.close()

    def __enter__(self) -> SerialTransport:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
