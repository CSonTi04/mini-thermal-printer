"""CQRS dispatch and printer use-case handlers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from tronic_printer import protocol
from tronic_printer.domain import (
    DeviceInfo,
    PrinterNotReady,
    PrinterStatus,
    ProtocolError,
    RasterImage,
)
from tronic_printer.messages import (
    FeedPaper,
    GetBattery,
    GetDensity,
    GetDeviceInfo,
    GetFirmware,
    GetModel,
    GetStatus,
    PrintRaster,
    PrintResult,
    RasterEncoding,
    SetDensity,
)
from tronic_printer.ports import PrinterTransport

Message = TypeVar("Message")
Result = TypeVar("Result")
Handler = Callable[[Any], Any]


class QueryBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Any], Handler] = {}

    def register(self, message_type: type[Message], handler: Callable[[Message], Result]) -> None:
        self._handlers[message_type] = cast(Handler, handler)

    def ask(self, query: Message) -> Any:
        try:
            handler = self._handlers[type(query)]
        except KeyError as error:
            raise LookupError(f"no query handler for {type(query).__name__}") from error
        return handler(query)


class CommandBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Any], Handler] = {}

    def register(self, message_type: type[Message], handler: Callable[[Message], Result]) -> None:
        self._handlers[message_type] = cast(Handler, handler)

    def execute(self, command: Message) -> Any:
        try:
            handler = self._handlers[type(command)]
        except KeyError as error:
            raise LookupError(f"no command handler for {type(command).__name__}") from error
        return handler(command)


@dataclass(slots=True)
class PrinterApplication:
    queries: QueryBus
    commands: CommandBus


class PrinterQueryHandlers:
    def __init__(self, transport: PrinterTransport) -> None:
        self.transport = transport

    def model(self, _query: GetModel) -> str:
        return protocol.decode_ascii(self.transport.exchange(protocol.QUERY_MODEL), "model")

    def firmware(self, _query: GetFirmware) -> str:
        return protocol.decode_ascii(self.transport.exchange(protocol.QUERY_FIRMWARE), "firmware")

    def battery(self, _query: GetBattery) -> int:
        return protocol.decode_battery(self.transport.exchange(protocol.QUERY_BATTERY, min_bytes=2))

    def density(self, _query: GetDensity) -> int:
        return protocol.decode_density(self.transport.exchange(protocol.QUERY_DENSITY))

    def status(self, _query: GetStatus) -> PrinterStatus:
        raw = protocol.decode_status(self.transport.exchange(protocol.QUERY_STATUS))
        return PrinterStatus.from_byte(raw)

    def device_info(self, _query: GetDeviceInfo) -> DeviceInfo:
        return DeviceInfo(
            model=self.model(GetModel()),
            firmware=self.firmware(GetFirmware()),
            battery_percent=self.battery(GetBattery()),
            density=self.density(GetDensity()),
            status=self.status(GetStatus()),
        )


class PrinterCommandHandlers:
    def __init__(self, transport: PrinterTransport, queries: PrinterQueryHandlers) -> None:
        self.transport = transport
        self.queries = queries

    def set_density(self, command: SetDensity) -> None:
        response = self.transport.exchange(protocol.set_density(command.level))
        if not protocol.is_success(response):
            raise ProtocolError(f"set-density rejected: {response.hex(' ')}")

    def feed_paper(self, command: FeedPaper) -> None:
        # Firmware V1.06LY ignores feed outside a raster job and leaves a
        # raster-less job unfinished. One all-white row satisfies the job
        # lifecycle without activating any print-head dots.
        blank_row = RasterImage(protocol.MAX_PRINT_WIDTH, 1, bytes(48))
        self.print_raster(
            PrintRaster(
                blank_row,
                feed_dots=command.dots,
                encoding=RasterEncoding.UNCOMPRESSED,
            )
        )

    def print_raster(self, command: PrintRaster) -> PrintResult:
        status = self.queries.status(GetStatus())
        if not status.can_print:
            raise PrinterNotReady(f"printer status 0x{status.raw:02X} prevents printing")

        if command.encoding is RasterEncoding.CODE_ESC:
            raster_frame = protocol.encode_compressed_raster(command.raster)
        elif command.encoding is RasterEncoding.UNCOMPRESSED:
            raster_frame = protocol.encode_uncompressed_raster(command.raster)
        else:
            raise ValueError(f"unsupported raster encoding: {command.encoding}")
        chunks = (
            protocol.start_job(command.job_mode),
            protocol.WAKE_PREFIX,
            raster_frame,
            protocol.feed_dots(command.feed_dots),
        )
        for chunk in chunks:
            self.transport.write(chunk)
        completion = self.transport.exchange(protocol.STOP_JOB, timeout=70.0)
        if not protocol.is_success(completion):
            raise ProtocolError(f"print completion rejected: {completion.hex(' ')}")
        return PrintResult(
            raster_bytes=len(raster_frame),
            total_bytes=sum(map(len, chunks)) + len(protocol.STOP_JOB),
            completion=completion,
        )


def build_application(transport: PrinterTransport) -> PrinterApplication:
    query_bus = QueryBus()
    command_bus = CommandBus()
    queries = PrinterQueryHandlers(transport)
    commands = PrinterCommandHandlers(transport, queries)

    query_bus.register(GetModel, queries.model)
    query_bus.register(GetFirmware, queries.firmware)
    query_bus.register(GetBattery, queries.battery)
    query_bus.register(GetDensity, queries.density)
    query_bus.register(GetStatus, queries.status)
    query_bus.register(GetDeviceInfo, queries.device_info)
    command_bus.register(SetDensity, commands.set_density)
    command_bus.register(FeedPaper, commands.feed_paper)
    command_bus.register(PrintRaster, commands.print_raster)
    return PrinterApplication(queries=query_bus, commands=command_bus)
