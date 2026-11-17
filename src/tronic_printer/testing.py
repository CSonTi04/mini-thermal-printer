"""Reusable mocks and an in-memory printer emulator."""

from __future__ import annotations

from collections import defaultdict, deque

from tronic_printer import protocol
from tronic_printer.niimbot import NiimbotFrameBuffer, NiimbotPacket


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
        serial_number: str = "TEST-SERIAL",
        boot_info: str = "TEST-BOOT",
        shutdown_time: int = 30,
        speed: int = 2,
        time_format: int = 0,
    ) -> None:
        self.model = model
        self.firmware = firmware
        self.battery = battery
        self.density = density
        self.status = status
        self.serial_number = serial_number
        self.boot_info = boot_info
        self.shutdown_time = shutdown_time
        self.speed = speed
        self.time_format = time_format
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
        if request == protocol.QUERY_SERIAL:
            return self.serial_number.encode("ascii")
        if request == protocol.QUERY_BOOT_INFO:
            return self.boot_info.encode("ascii")
        if request == protocol.QUERY_SHUTDOWN_TIME:
            return bytes((0, self.shutdown_time))
        if request == protocol.QUERY_SPEED:
            return bytes((self.speed,))
        if request == protocol.QUERY_TIME_FORMAT:
            return bytes((self.time_format,))
        if request.startswith(bytes.fromhex("10 FF 10 00")) and len(request) == 5:
            self.density = request[-1]
            return b"OK"
        if request.startswith(bytes.fromhex("10 FF 12")) and len(request) == 5:
            self.shutdown_time = int.from_bytes(request[-2:], "big")
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


class EmulatedNiimbotTransport:
    """Stateful NIIMBOT B1 emulator.

    Query answers mirror a physical B1 observed over USB. The print flow follows the
    upstream protocol and is strict: it rebuilds the page from row packets and checks
    each row's black-pixel counts, so encoding mistakes fail in tests.
    """

    _INFO_KEYS = (1, 3, 7, 8, 9, 10, 11, 12)

    def __init__(
        self,
        *,
        device_type: int = 4096,
        software: int = 0x0613,
        hardware: int = 0x0601,
        serial_number: str = "I612120126",
        battery: int = 4,
        density: int = 3,
        label_type: int = 3,
        rejected: frozenset[int] = frozenset(),
        errors: frozenset[int] = frozenset(),
        lid_open: bool = False,
        paper_out: bool = False,
        status_polls_until_done: int = 2,
    ) -> None:
        self._info = {
            1: bytes((density,)),
            3: bytes((label_type,)),
            7: b"\x03",
            8: device_type.to_bytes(2, "big"),
            9: software.to_bytes(2, "big"),
            10: bytes((battery,)),
            11: serial_number.encode("ascii"),
            12: hardware.to_bytes(2, "big"),
        }
        self.rejected = rejected
        self.errors = errors  # commands the printer answers with an 0xDB error packet
        self.lid_open = lid_open
        self.paper_out = paper_out
        self.status_polls_until_done = status_polls_until_done
        self.commands: list[int] = []
        self.payloads: dict[int, bytes] = {}
        self.rows: dict[int, bytes] = {}
        self.row_packets: list[NiimbotPacket] = []
        self.page_rows = 0
        self.page_cols = 0
        self.closed = False
        self._status_polls = 0
        self._stream = NiimbotFrameBuffer()
        self._replies = bytearray()

    # -- transport port ----------------------------------------------------------------------

    def write(self, payload: bytes) -> None:
        if self.closed:
            raise OSError("transport is closed")
        for packet in self._stream.feed(bytes(payload)):
            self._handle(packet)

    def exchange(self, payload: bytes, **_options: object) -> bytes:
        self._replies.clear()  # like reset_input_buffer() on the real serial transport
        self.write(payload)
        if not self._replies:
            raise TimeoutError("printer response timed out")
        return bytes(self._replies)

    def drain_replies(self) -> bytes:
        """Bytes the printer has answered since the last call (emulates BLE notifications)."""
        replies = bytes(self._replies)
        self._replies.clear()
        return replies

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> EmulatedNiimbotTransport:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- emulation ---------------------------------------------------------------------------

    @property
    def bitmap(self) -> bytes:
        """The page reconstructed from row packets; fails if any row is missing."""
        missing = [i for i in range(self.page_rows) if i not in self.rows]
        assert not missing, f"rows never sent: {missing[:5]}"
        return b"".join(self.rows[i] for i in range(self.page_rows))

    def _reply(self, command: int, payload: bytes) -> None:
        self._replies.extend(NiimbotPacket(command, payload).to_bytes())

    def _handle(self, packet: NiimbotPacket) -> None:
        command, payload = packet.command, packet.payload
        if command in (0x84, 0x85):
            self._store_row(packet)
            return
        self.commands.append(command)
        self.payloads[command] = payload
        if command in self.errors:
            self._reply(0xDB, b"\x01")
        elif command == 0x40:
            key = payload[0]
            if key in self._INFO_KEYS:
                self._reply(0x40 + key, self._info[key])
            else:
                self._reply(0x00, b"\x01")  # unsupported key, as on hardware
        elif command == 0xDC:
            beat = bytearray.fromhex("207d0064006400004a00040000")
            beat[9], beat[11] = int(self.lid_open), int(self.paper_out)
            self._reply(0xDD, bytes(beat))
        elif command == 0xA3:
            self._status_polls += 1
            done = self._status_polls > self.status_polls_until_done
            progress = (0, 1, 100, 100) if done else (0, 0, 40, 40)
            self._reply(0xB3, bytes(progress))
        elif command in (0x01, 0x03, 0x13, 0x21, 0x23, 0xE3, 0xF3):
            if command == 0x13:
                self.page_rows = int.from_bytes(payload[0:2], "big")
                self.page_cols = int.from_bytes(payload[2:4], "big")
            self._reply(
                {0x21: 0x31, 0x23: 0x33}.get(command, command + 1),
                b"\x00" if command in self.rejected else b"\x01",
            )
        else:
            raise AssertionError(f"unsupported NIIMBOT emulator command: 0x{command:02X}")

    def _store_row(self, packet: NiimbotPacket) -> None:
        self.row_packets.append(packet)
        payload = packet.payload
        index = int.from_bytes(payload[0:2], "big")
        row_bytes = self.page_cols // 8
        if packet.command == 0x84:
            repeat, data = payload[2], bytes(row_bytes)
        else:
            repeat, data = payload[5], payload[6:]
            assert len(data) == row_bytes, f"row {index} has {len(data)} bytes, want {row_bytes}"
            step = -(-row_bytes // 3)
            expected = [
                sum(b.bit_count() for b in data[i : i + step]) for i in range(0, row_bytes, step)
            ]
            assert list(payload[2:5]) == expected, f"row {index} black counts are wrong"
            assert any(data), f"blank row {index} must use the empty-row command"
        for offset in range(repeat):
            self.rows[index + offset] = data
