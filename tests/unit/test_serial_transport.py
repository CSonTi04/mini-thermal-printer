from collections import deque

import pytest

from tronic_printer.infrastructure.serial import SerialTransport


class FakeSerial:
    def __init__(self, chunks: list[bytes] | None = None, **options: object) -> None:
        self.options = options
        self.chunks = deque(chunks or [])
        self.writes: list[bytes] = []
        self.flushed = False
        self.reset = False
        self.closed = False

    @property
    def in_waiting(self) -> int:
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, _size: int) -> bytes:
        return self.chunks.popleft() if self.chunks else b""

    def write(self, payload: bytes) -> int:
        self.writes.append(bytes(payload))
        return len(payload)

    def flush(self) -> None:
        self.flushed = True

    def reset_input_buffer(self) -> None:
        self.reset = True

    def close(self) -> None:
        self.closed = True


def test_serial_exchange_collects_fragmented_response() -> None:
    fake = FakeSerial([b"V1.", b"06LY"])
    transport = SerialTransport("COM42", serial_factory=lambda **_options: fake)

    response = transport.exchange(b"query", timeout=0.1, idle_timeout=0.001)

    assert response == b"V1.06LY"
    assert fake.writes == [b"query"]
    assert fake.reset
    assert fake.flushed


def test_serial_exchange_times_out_without_minimum_response() -> None:
    fake = FakeSerial()
    transport = SerialTransport("COM42", serial_factory=lambda **_options: fake)

    with pytest.raises(TimeoutError):
        transport.exchange(b"query", timeout=0.001, idle_timeout=0.001)


def test_serial_writes_use_official_app_chunk_limit() -> None:
    fake = FakeSerial()
    transport = SerialTransport("COM42", serial_factory=lambda **_options: fake)

    transport.write(bytes(16_385))

    assert [len(chunk) for chunk in fake.writes] == [16_384, 1]
