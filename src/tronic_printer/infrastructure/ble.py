"""Read-only BLE discovery helpers; no printer writes are implemented here."""

from __future__ import annotations

import asyncio
import math
import threading
import time
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, TypeVar

from bleak import BleakClient, BleakScanner

FF01_RESPONSE = "0000ff01-0000-1000-8000-00805f9b34fb"
FF02_WRITE = "0000ff02-0000-1000-8000-00805f9b34fb"
FF03_CONTROL = "0000ff03-0000-1000-8000-00805f9b34fb"

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class BleDevice:
    name: str | None
    address: str
    rssi: int | None


async def discover(
    timeout: float = 5.0,
    name_prefix: str = "Mini Pocket Printer",
) -> list[BleDevice]:
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    matches: list[BleDevice] = []
    for device, advertisement in devices.values():
        name = advertisement.local_name or device.name
        if name and name.startswith(name_prefix):
            matches.append(BleDevice(name=name, address=device.address, rssi=advertisement.rssi))
    return sorted(matches, key=lambda item: item.address)


async def inspect_gatt(address: str) -> list[dict[str, object]]:
    """Connect and enumerate GATT metadata without reading or writing values."""
    async with BleakClient(address) as client:
        result = []
        for service in client.services:
            for characteristic in service.characteristics:
                item: dict[str, object] = {
                    "service": service.uuid,
                    "characteristic": characteristic.uuid,
                    "properties": sorted(characteristic.properties),
                }
                if "write-without-response" in characteristic.properties:
                    item["max_write_without_response_size"] = (
                        characteristic.max_write_without_response_size
                    )
                result.append(item)
        return result


class BleTransport:
    """Synchronous CQRS transport backed by the printer's BLE GATT service."""

    def __init__(
        self,
        address: str,
        *,
        connect_timeout: float = 12.0,
        setup_timeout: float = 15.0,
        client_factory: Callable[..., Any] = BleakClient,
    ) -> None:
        self._address = address
        self._connect_timeout = connect_timeout
        self._setup_timeout = setup_timeout
        self._client_factory = client_factory
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._response_changed = threading.Condition()
        self._response = bytearray()
        self._credits = 0
        self._packet_size = 20
        self._host_write_limit = 20
        self._closed = False
        self._client: Any = None
        self._credit_event: asyncio.Event | None = None
        self._mtu_event: asyncio.Event | None = None
        self._thread.start()
        try:
            self._submit(self._connect()).result(
                timeout=connect_timeout + setup_timeout + 2.0
            )
        except BaseException:
            self._stop_loop()
            raise

    @property
    def connection_info(self) -> dict[str, int]:
        return {
            "packet_size": self._packet_size,
            "host_write_limit": self._host_write_limit,
            "credits": self._credits,
        }

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coroutine: Coroutine[Any, Any, T]) -> Future[T]:
        if self._closed:
            coroutine.close()
            raise OSError("transport is closed")
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    async def _connect(self) -> None:
        self._credit_event = asyncio.Event()
        self._mtu_event = asyncio.Event()
        self._client = self._client_factory(self._address, timeout=self._connect_timeout)
        await self._client.connect()
        write_characteristic = self._client.services.get_characteristic(FF02_WRITE)
        if write_characteristic is None:
            raise OSError("printer FF02 write characteristic is missing")
        self._host_write_limit = write_characteristic.max_write_without_response_size
        await self._client.start_notify(FF01_RESPONSE, self._on_response)
        await self._client.start_notify(FF03_CONTROL, self._on_control)
        try:
            await asyncio.wait_for(
                asyncio.gather(self._credit_event.wait(), self._mtu_event.wait()),
                timeout=self._setup_timeout,
            )
        except TimeoutError as error:
            raise TimeoutError(
                "printer did not provide initial BLE credit and MTU control messages"
            ) from error

    def _on_response(self, _sender: object, data: bytearray) -> None:
        with self._response_changed:
            self._response.extend(data)
            self._response_changed.notify_all()

    def _on_control(self, _sender: object, data: bytearray) -> None:
        payload = bytes(data)
        if len(payload) >= 2 and payload[0] == 0x01:
            self._credits += payload[1]
            if self._credits > 0 and self._credit_event is not None:
                self._credit_event.set()
        elif len(payload) >= 3 and payload[0] == 0x02:
            requested = int.from_bytes(payload[1:3], "little")
            if requested > 0:
                self._packet_size = min(requested, self._host_write_limit, 509)
                if self._mtu_event is not None:
                    self._mtu_event.set()

    async def _wait_for_credit(self, timeout: float = 30.0) -> None:
        if self._credit_event is None:
            raise OSError("BLE transport is not initialized")
        deadline = self._loop.time() + timeout
        while self._credits <= 0:
            self._credit_event.clear()
            remaining = deadline - self._loop.time()
            if remaining <= 0:
                raise TimeoutError("BLE transmit credit timed out")
            await asyncio.wait_for(self._credit_event.wait(), timeout=remaining)

    async def _write(self, payload: bytes) -> None:
        offset = 0
        while offset < len(payload):
            await self._wait_for_credit()
            usable_credits = self._credits - 1 if self._credits >= 3 else self._credits
            packet_count = min(
                math.ceil((len(payload) - offset) / self._packet_size),
                usable_credits,
            )
            for _index in range(packet_count):
                chunk = payload[offset : offset + self._packet_size]
                await self._client.write_gatt_char(FF02_WRITE, chunk, response=False)
                offset += len(chunk)
                self._credits -= 1
                if self._credits <= 0 and self._credit_event is not None:
                    self._credit_event.clear()

    def write(self, payload: bytes) -> None:
        if not payload:
            return
        packets = math.ceil(len(payload) / self._packet_size)
        self._submit(self._write(bytes(payload))).result(timeout=35.0 + packets * 5.0)

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
        with self._response_changed:
            self._response.clear()
        self.write(payload)

        deadline = time.monotonic() + timeout
        last_size = 0
        last_change: float | None = None
        with self._response_changed:
            while time.monotonic() < deadline:
                if len(self._response) != last_size:
                    last_size = len(self._response)
                    last_change = time.monotonic()
                if (
                    len(self._response) >= min_bytes
                    and last_change is not None
                    and time.monotonic() - last_change >= idle_timeout
                ):
                    return bytes(self._response)
                remaining = min(0.02, max(0.0, deadline - time.monotonic()))
                self._response_changed.wait(timeout=remaining)
        raise TimeoutError(
            f"printer response timed out after {timeout:.1f}s "
            f"({len(self._response)}/{min_bytes} bytes)"
        )

    async def _disconnect(self) -> None:
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()

    def _stop_loop(self) -> None:
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._loop.close()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._submit(self._disconnect()).result(timeout=5.0)
        finally:
            self._closed = True
            self._stop_loop()

    def __enter__(self) -> BleTransport:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
