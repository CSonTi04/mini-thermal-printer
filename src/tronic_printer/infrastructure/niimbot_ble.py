"""BLE transport for the NIIMBOT B1.

The B1 exposes one characteristic with ``notify`` and ``write-without-response`` inside
the vendor service below; the packets are the same ones used over USB serial, so
:class:`~tronic_printer.niimbot_client.NiimbotClient` runs unchanged on top of this
transport. This is not the credit-controlled protocol of the TRONIC printer, so it does
not share code with :mod:`tronic_printer.infrastructure.ble`.

Evidence: service and characteristic layout, the 237-byte write limit and the
``B1-<serial>`` advertising name are *Verified* against a physical B1 (the advertisement
carries no service UUID, so discovery matches on the name). The write pacing follows the
reference client at https://github.com/vkolarik/niimbot-b1 and is *Recovered*.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

NIIMBOT_SERVICE = "e7810a71-73ae-499d-8c15-faa9aef0c3f2"
NAME_PREFIX = "B1-"
# One row packet is about 55 bytes; keeping writes near that size with a short pause
# mirrors the reference client and avoids overrunning the printer's receive buffer.
DEFAULT_WRITE_CHUNK = 64
PACKET_INTERVAL = 0.01

T = TypeVar("T")
DeviceFinder = Callable[[str | None, str, float], Awaitable[Any]]


async def find_device(address: str | None, name_prefix: str, timeout: float) -> Any:
    """The BLE device with *address*, or the first one advertising a B1 name or the service."""
    if address:
        return await BleakScanner.find_device_by_address(address, timeout=timeout)

    def is_b1(device: Any, advertisement: Any) -> bool:
        name = advertisement.local_name or device.name or ""
        return name.startswith(name_prefix) or NIIMBOT_SERVICE in (
            advertisement.service_uuids or []
        )

    return await BleakScanner.find_device_by_filter(is_b1, timeout=timeout)


class NiimbotBleTransport:
    """Synchronous byte transport over the B1's BLE characteristic.

    Connects in the constructor and raises :class:`OSError` (not a Bleak exception) when the
    printer is off, out of range, or already connected to another client such as the phone
    app, so callers can treat BLE and USB failures alike.
    """

    def __init__(
        self,
        address: str | None = None,
        *,
        name_prefix: str = NAME_PREFIX,
        connect_timeout: float = 15.0,
        write_chunk: int = DEFAULT_WRITE_CHUNK,
        packet_interval: float = PACKET_INTERVAL,
        client_factory: Callable[..., Any] = BleakClient,
        device_finder: DeviceFinder = find_device,
    ) -> None:
        if write_chunk <= 0 or packet_interval < 0:
            raise ValueError("write_chunk must be positive and packet_interval not negative")
        self._requested_address = None if address in (None, "", "auto") else address
        self._name_prefix = name_prefix
        self._connect_timeout = connect_timeout
        self._write_chunk_limit = write_chunk
        self._packet_interval = packet_interval
        self._client_factory = client_factory
        self._device_finder = device_finder
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._changed = threading.Condition()
        self._rx = bytearray()
        self._closed = False
        self._client: Any = None
        self._characteristic: Any = None
        self._chunk = write_chunk
        self.address: str | None = self._requested_address
        self._thread.start()
        try:
            self._call(self._connect(), timeout=2 * connect_timeout + 5.0)
        except BaseException:
            self._closed = True
            self._stop_loop()
            raise

    # -- event loop plumbing ---------------------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _call(self, coroutine: Coroutine[Any, Any, T], *, timeout: float) -> T:
        if self._closed:
            coroutine.close()
            raise OSError("transport is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout)
        except BleakError as error:
            raise OSError(f"BLE error: {error}") from error
        except TimeoutError:
            future.cancel()
            raise

    # -- connection ------------------------------------------------------------------------

    async def _connect(self) -> None:
        device = await self._device_finder(
            self._requested_address, self._name_prefix, self._connect_timeout
        )
        if device is None:
            raise OSError(
                "NIIMBOT B1 not found over BLE (is it on, in range, and not connected to "
                "another app?)"
            )
        self.address = getattr(device, "address", None) or str(device)
        self._client = self._client_factory(device, timeout=self._connect_timeout)
        try:
            await self._client.connect()
            self._characteristic = self._find_characteristic()
            limit = getattr(self._characteristic, "max_write_without_response_size", None)
            self._chunk = max(1, min(self._write_chunk_limit, limit or self._write_chunk_limit))
            await self._client.start_notify(self._characteristic, self._on_notify)
        except BaseException:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
            raise

    def _find_characteristic(self) -> Any:
        fallback = None
        for service in self._client.services:
            for characteristic in service.characteristics:
                props = characteristic.properties
                if "notify" in props and "write-without-response" in props:
                    if str(service.uuid).lower() == NIIMBOT_SERVICE:
                        return characteristic
                    fallback = fallback or characteristic
        if fallback is None:
            raise OSError("no notify + write-without-response characteristic: not a NIIMBOT B1?")
        return fallback

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        with self._changed:
            self._rx.extend(data)
            self._changed.notify_all()

    # -- transport port --------------------------------------------------------------------

    async def _write(self, payload: bytes) -> None:
        for offset in range(0, len(payload), self._chunk):
            await self._client.write_gatt_char(
                self._characteristic, payload[offset : offset + self._chunk], response=False
            )
            await asyncio.sleep(self._packet_interval)

    def write(self, payload: bytes) -> None:
        if not payload:
            return
        chunks = -(-len(payload) // self._chunk)
        timeout = 10.0 + chunks * (self._packet_interval + 0.25)
        self._call(self._write(bytes(payload)), timeout=timeout)

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
        with self._changed:
            self._rx.clear()
        self.write(payload)

        deadline = time.monotonic() + timeout
        last_size = 0
        last_change: float | None = None
        with self._changed:
            while time.monotonic() < deadline:
                if len(self._rx) != last_size:
                    last_size = len(self._rx)
                    last_change = time.monotonic()
                if (
                    len(self._rx) >= min_bytes
                    and last_change is not None
                    and time.monotonic() - last_change >= idle_timeout
                ):
                    return bytes(self._rx)
                self._changed.wait(timeout=min(0.02, max(0.0, deadline - time.monotonic())))
        raise TimeoutError(
            f"printer response timed out after {timeout:.1f}s ({len(self._rx)}/{min_bytes} bytes)"
        )

    # -- shutdown --------------------------------------------------------------------------

    async def _disconnect(self) -> None:
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()

    def _stop_loop(self) -> None:
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if not self._loop.is_running():
            self._loop.close()

    def close(self) -> None:
        if self._closed:
            return
        try:
            with contextlib.suppress(OSError, TimeoutError):
                self._call(self._disconnect(), timeout=8.0)
        finally:
            self._closed = True
            self._stop_loop()

    def __enter__(self) -> NiimbotBleTransport:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
