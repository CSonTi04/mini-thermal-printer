"""Ports implemented by infrastructure adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PrinterTransport(Protocol):
    """Synchronous byte transport used by all application handlers."""

    def write(self, payload: bytes) -> None: ...

    def exchange(
        self,
        payload: bytes,
        *,
        timeout: float = 3.0,
        idle_timeout: float = 0.10,
        min_bytes: int = 1,
    ) -> bytes: ...

    def close(self) -> None: ...
