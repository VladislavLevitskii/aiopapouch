"""This file is used as a hub for imports."""

import logging
from collections.abc import Callable
from typing import NamedTuple

from ..client import PapouchHTTPClient, PapouchSerialClient
from ..utils import parse_device_location, parse_device_name, parse_device_serial_number
from .base import PapouchDevice
from .papago import async_setup_papago
from .quido import async_setup_quido
from .th2e import async_setup_th2e
from .tht2 import async_setup_tht2
from .tme import async_setup_tme

SERIAL = "serial"
NETWORK = "network"

_LOGGER = logging.getLogger()


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


async def create_serial_device(
    api_client: PapouchSerialClient, address: int
) -> PapouchDevice | None:
    """Create a proper serial device instance dynamically based on the fetched info.

    Returns None if the device is not supported.

    Raises DeviceConnectionError.
    """

    pkt_man_data = await api_client.get_man_data(
        address, f"Unknown device with {address} address"
    )

    serial_number = parse_device_serial_number(pkt_man_data.data)

    pkt_info = await api_client.get_info(address, serial_number)
    device_name = parse_device_name(pkt_info.data)

    raw_location = await api_client.get_location(
        address, f"{device_name} - SN: {serial_number}"
    )
    location = parse_device_location(raw_location.data)

    handler = _get_device_handler(device_name, SERIAL)
    if not handler:
        return None

    return await handler.setup_func(api_client, address, serial_number, location)


__all__ = [
    "PapouchDevice",
    "create_network_device",
    "create_serial_device",
    "is_device_supported",
]
