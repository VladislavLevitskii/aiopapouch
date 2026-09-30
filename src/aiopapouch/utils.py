"""File contains helper functions that are used in various places."""

from __future__ import annotations

import asyncio
import contextlib
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from pap_spinel import INST_INFO

from .exceptions import DeviceConnectionError, DeviceLogicError, DeviceParseError

if TYPE_CHECKING:
    from .client import PapouchSerialClient

MAX_ATTEMPTS_ASSIGNING = 3


def find_tag(root: ET.Element | None, tag_name: str) -> ET.Element | None:
    """Find element and ignore the namespace."""

    if root is None:
        return None

    for element in root.iter():
        if element.tag.endswith(tag_name):
            return element
    return None


def get_box_attribute(
    root: ET.Element, box_num: str, attr_name: str, context: str, error_context: str
) -> str:
    """Helper to extract a specific attribute from a specific box in settings XML."""

    box = root.find(f".//set[@box='{box_num}']")

    if box is not None:
        value = box.attrib.get(attr_name)
        if value:
            return str(value)

        raise DeviceParseError(
            f"Device: {context} does have a box {box_num} but without {error_context}"
        )

    raise DeviceParseError(
        f"Device: {context} doesn't have a box {box_num} with {error_context}"
    )


def parse_device_name(raw_name: bytes) -> str:
    """Parse device name from raw Spinel bytes."""

    if not isinstance(raw_name, bytes):
        raise DeviceLogicError("Invalid payload type, expected bytes.")

    result = raw_name.decode("ascii", errors="ignore")

    if len(result) < 1:
        raise DeviceParseError("Invalid length of the data, expected more than 0 byte.")

    result = result.split(";")[0]
    return result.replace("\x00", "").strip()


def parse_device_location(raw_location: bytes) -> str:
    """Parse device location from raw Spinel bytes."""

    if not isinstance(raw_location, bytes):
        raise DeviceLogicError("Invalid payload type, expected bytes.")

    result = raw_location.decode("ascii", errors="ignore")
    return result.replace("\x00", "").strip()


def parse_device_serial_number(raw_serial_number: bytes) -> str:
    """Parse device serial number from raw Spinel bytes."""

    if not isinstance(raw_serial_number, bytes):
        raise DeviceLogicError("Invalid payload type, expected bytes.")

    if len(raw_serial_number) != 8:
        raise DeviceParseError(
            f"Invalid payload length for serial number,"
            f"expected: 8, got {len(raw_serial_number)}"
        )

    product_number = int.from_bytes(raw_serial_number[0:2], "big")
    serial_number_num = int.from_bytes(raw_serial_number[2:4], "big")
    return f"{product_number:04d}/{serial_number_num}"


async def assign_next_available_address(
    api_client: PapouchSerialClient,
    used_addresses: list[int],
    serial_number: str,
) -> tuple[int | None, str | None]:
    """Finds, sets, and verifies the next available address. Returns (new_address, device_name)."""

    failed_attempts = 0

    for addr in range(250, -1, -1):
        if addr in used_addresses:
            continue

        with contextlib.suppress(DeviceConnectionError):
            await api_client.write_command(addr, INST_INFO, context="", timeout=0.3)
            continue

        try:
            await api_client.set_address(
                addr, serial_number, f"device with {addr} for SN {serial_number}"
            )

            await asyncio.sleep(2)

            device_name, _, _ = await get_device_details(api_client, addr)

            return addr, device_name

        except DeviceConnectionError:
            pass

        failed_attempts += 1
        if failed_attempts >= MAX_ATTEMPTS_ASSIGNING:
            return addr, None

    return None, None


async def get_device_details(
    api_client: PapouchSerialClient, address: int
) -> tuple[str, str, int]:
    """Test device connection and return name, serial number and device's address (if broadcast was used)."""

    pkt_man_data = await api_client.get_man_data(
        address, f"Unknown device with {address} address"
    )

    _address = pkt_man_data.adr

    serial_number = parse_device_serial_number(pkt_man_data.data)

    pkt_info = await api_client.get_info(address, f"Device at address {address}")
    device_name = parse_device_name(pkt_info.data)

    return device_name, serial_number, _address


def require_attr(
    element: ET.Element, attr_name: str, tag_context: str, context: str
) -> str:
    """Strictly get an attribute from XML element or raise DeviceParseError."""
    val = element.attrib.get(attr_name)
    if val is None:
        raise DeviceParseError(
            f"Missing required attribute '{attr_name}' in <{element.tag}> ({tag_context}) "
            f"for device: {context}"
        )
    return val
