"""This file is used as a hub for imports."""

from collections.abc import Callable
from typing import NamedTuple

from ..client import PapouchHTTPClient, PapouchSerialClient
from .base import PapouchDevice
from .papago import async_setup_papago
from .quido import async_setup_quido
from .th2e import async_setup_th2e
from .tht2 import async_setup_tht2
from .tme import async_setup_tme

SERIAL = "serial"
NETWORK = "network"


class DeviceHandler(NamedTuple):
    """Represents device handler with async setup and supported types."""

    setup_func: Callable
    supported_types: set[str]


DEVICE_SETUP_HANDLERS = {
    "Quido": DeviceHandler(async_setup_quido, {NETWORK}),
    "TH2E": DeviceHandler(async_setup_th2e, {NETWORK}),
    "TME": DeviceHandler(async_setup_tme, {NETWORK}),
    "Papago": DeviceHandler(async_setup_papago, {NETWORK}),
    "THT2": DeviceHandler(async_setup_tht2, {SERIAL}),
}


def _get_device_handler(
    device_name: str | None, device_type: str
) -> DeviceHandler | None:
    if not device_name:
        return None

    for prefix, handler in DEVICE_SETUP_HANDLERS.items():
        if prefix in device_name and device_type in handler.supported_types:
            return handler

    return None


def is_device_supported(device_name: str | None, device_type: str) -> bool:
    """Check if the extracted device name matches any supported prefix and type of the communication."""
    return _get_device_handler(device_name, device_type) is not None


async def create_network_device(api_client: PapouchHTTPClient) -> PapouchDevice | None:
    """Create a proper device instance dynamically based on the fetched info.

    Returns None if the device is not supported.
    """

    device_name, _ = await api_client.get_device_info()

    handler = _get_device_handler(device_name, NETWORK)
    if not handler:
        return None

    return await handler.setup_func(api_client)


async def create_serial_device(api_client: PapouchSerialClient) -> PapouchDevice | None:
    """Create a proper serial device instance dynamically based on the fetched info.

    Returns None if the device is not supported.
    """

    pkt = await api_client.get_info()
    raw_name = pkt.data
    result = raw_name.decode("ascii")
    device_name = result.split(";")[0]

    handler = _get_device_handler(device_name, SERIAL)
    if not handler:
        return None

    return await handler.setup_func(api_client)


__all__ = [
    "PapouchDevice",
    "create_network_device",
    "create_serial_device",
    "is_device_supported",
]
