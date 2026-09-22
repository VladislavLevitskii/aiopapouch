"""File contains helper functions that are used in various places."""

import asyncio
import contextlib
import xml.etree.ElementTree as ET

from pap_spinel import INST_INFO

from .client import PapouchSerialClient
from .exceptions import DeviceConnectionError

MAX_ATTEMPTS_ASSIGNING = 3


def find_tag(root: ET.Element, tag_name: str) -> ET.Element | None:
    """Find element and ignore the namespace."""
    for element in root.iter():
        if element.tag.endswith(tag_name):
            return element
    return None


def parse_device_name(raw_name: bytes) -> str:
    """Parse device name from raw Spinel bytes."""

    result = raw_name.decode("ascii", errors="ignore")
    result = result.split(";")[0]
    return result.replace("\x00", "").strip()


def parse_device_location(raw_location: bytes) -> str:
    """Parse device location from raw Spinel bytes."""

    result = raw_location.decode("ascii", errors="ignore")
    return result.replace("\x00", "").strip()


def parse_device_serial_number(raw_serial_number: bytes) -> str:
    """Parse device serial number from raw Spinel bytes."""

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

            device_name, _, _ = await _get_device_details(api_client, addr)

            return addr, device_name

        except DeviceConnectionError:
            pass

        failed_attempts += 1
        if failed_attempts >= MAX_ATTEMPTS_ASSIGNING:
            return addr, None

    return None, None


async def _get_device_details(
    api_client: PapouchSerialClient, address: int
) -> tuple[str, str, int]:
    """Test device connection and return errors, name, and serial number."""

    pkt_man_data = await api_client.get_man_data(
        address, f"Unknown device with {address} address"
    )

    _address = pkt_man_data.adr

    serial_number = parse_device_serial_number(pkt_man_data.data)

    pkt_info = await api_client.get_info(address, f"Device at address {address}")
    device_name = parse_device_name(pkt_info.data)

    return device_name, serial_number, _address
