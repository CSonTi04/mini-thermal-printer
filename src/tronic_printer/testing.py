"""Reusable mocks and an in-memory printer emulator."""

from __future__ import annotations

from collections import defaultdict, deque

from tronic_printer import protocol


class ScriptedTransport:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.exchanges: list[bytes] = []
        self._responses: dict[bytes, deque[bytes]] = defaultdict(deque)
        self.closed = False

    def respond(self, request: bytes, *responses: bytes) -> ScriptedTransport:
        self._responses[request].extend(responses)
        return self

    def write(self, payload: bytes) -> None:
        if self.closed:
            raise OSError("transport is closed")
        self.writes.append(bytes(payload))

    def exchange(self, payload: bytes, **_options: object) -> bytes:
        if self.closed:
            raise OSError("transport is closed")
        request = bytes(payload)
        self.exchanges.append(request)
        try:
            return self._responses[request].popleft()
        except (KeyError, IndexError) as error:
            raise AssertionError(f"unexpected exchange: {request.hex(' ')}") from error

    def close(self) -> None:
        self.closed = True


class EmulatedPrinterTransport:
    """Stateful protocol emulator for adapter-independent test scenarios."""

    def __init__(
        self,
        *,
        model: str = "A2Y",
        firmware: str = "V1.06LY",
        battery: int = 92,
        density: int = 1,
        status: int = 0,
    ) -> None:
        self.model = model
        self.firmware = firmware
        self.battery = battery
        self.density = density
        self.status = status
        self.writes: list[bytes] = []
        self.exchanges: list[bytes] = []
        self.completed_jobs: list[list[bytes]] = []
        self._active_job: list[bytes] | None = None
        self.closed = False

    def write(self, payload: bytes) -> None:
        if self.closed:
            raise OSError("transport is closed")
        frame = bytes(payload)
        self.writes.append(frame)
        if frame.startswith(bytes.fromhex("10 FF F1")) and len(frame) == 4:
            self._active_job = [frame]
        elif self._active_job is not None:
            self._active_job.append(frame)

    def exchange(self, payload: bytes, **_options: object) -> bytes:
        if self.closed:
            raise OSError("transport is closed")
        request = bytes(payload)
        self.exchanges.append(request)
        if request == protocol.QUERY_MODEL:
            return self.model.encode("ascii")
        if request == protocol.QUERY_FIRMWARE:
            return self.firmware.encode("ascii")
        if request == protocol.QUERY_BATTERY:
            return bytes((0, self.battery))
        if request == protocol.QUERY_DENSITY:
            return bytes((self.density, 0x0C, 0x10))
        if request == protocol.QUERY_STATUS:
            return bytes((self.status,))
        if request.startswith(bytes.fromhex("10 FF 10 00")) and len(request) == 5:
            self.density = request[-1]
            return b"OK"
        if request == protocol.STOP_JOB:
            if self._active_job is None:
                return b"ERR"
            self._active_job.append(request)
            self.completed_jobs.append(self._active_job)
            self._active_job = None
            return b"\xAA\r\n"
        raise AssertionError(f"unsupported emulator request: {request.hex(' ')}")

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> EmulatedPrinterTransport:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
