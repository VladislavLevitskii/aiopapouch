"""This file contains definition of the HTTP converters device."""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import override

import defusedxml.ElementTree as defused_ET

from aiopapouch.exceptions import (
    DeviceConnectionError,
    DeviceLogicError,
    DeviceParseError,
    DeviceResponseError,
)

from ..client import (
    SAVE_SETTINGS_ENDPOINT,
    TCP_CLIENT_MODE_INDEX,
    TCP_SERVER_MODE_INDEX,
    UDP_MODE_INDEX,
    PapouchHTTPClient,
)
from .base import PapouchConfiguration, find_tag

_LOGGER = logging.getLogger()

EDGAR_BOX_1_MAP = {
    "ip": "ip01",
    "mask": "ip02",
    "gate": "ip03",
    "rip": "ip04",
    "dip": "ip05",
    "lport": "num01",
    "wport": "num02",
    "mtu": "num04",
    "comm": "num05",
    "dhcp": "num06",
    "keep": "num07",
    "rport": "num09",
}


@dataclass
class ConverterConfiguration(PapouchConfiguration):
    """Represent Edgar configuration"""

    tcp_port: int = -1


class PapouchHTTPConverter(ABC):
    """Represent HTTP Converters."""

    @property
    @abstractmethod
    def conf(self) -> ConverterConfiguration:
        """Return the device configuration."""

    @abstractmethod
    async def get_mode(self) -> int:
        """Return converter mode."""

    @abstractmethod
    async def switch_to_tcp_server(self) -> None:
        """Switch the converter to WEB mode"""


class Edgar(PapouchHTTPConverter):
    """Represent Edgar ETH and WIFI converter to RS485."""

    def __init__(
        self,
        client: PapouchHTTPClient,
        identifier: str,
        name: str,
        location: str | None,
        tcp_port: int,
    ):
        _location = location or "NONAME"
        self._conf = ConverterConfiguration(
            identifier, name, _location, f"{name} - ({_location})", tcp_port=tcp_port
        )
        self._client = client

    @override
    @property
    def conf(self) -> ConverterConfiguration:
        return self._conf

    @override
    async def get_mode(self) -> int:
        settings_xml = await self._client.fetch_settings()
        root = defused_ET.fromstring(settings_xml)

        box = root.find(".//set[@box='1']")

        if box is not None:
            return int(box.attrib.get("comm", "-1"))

        raise DeviceParseError(
            f"Box 1 wasn't found in settings.xml, in: {self.conf.context}"
        )

    def _check_response(
        self, response_text: str, expected_status: str, action_msg: str
    ) -> None:
        """Verify that the device responded correctly to a command."""
        try:
            root = defused_ET.fromstring(response_text)
            result_tag = find_tag(root, "result")

            if result_tag is None:
                raise DeviceParseError(
                    f"Response doesn't have result tag!, in the device: {self.conf.context}"
                )

            if result_tag.attrib.get("status") != expected_status:
                raise DeviceResponseError(
                    f"{self.conf.context} returned an error while {action_msg}, whole response: {response_text}"
                )

        except defused_ET.ParseError as exception:
            raise DeviceParseError(
                f"Invalid XML response from device: {exception}, in the device: {self.conf.context}"
            ) from exception

    @override
    async def switch_to_tcp_server(self) -> None:
        """Switch the converter to TCP server mode"""

        settings_xml = await self._client.fetch_settings()
        root = defused_ET.fromstring(settings_xml)
        box1 = root.find(".//set[@box='1']")

        if box1 is None:
            raise DeviceParseError(
                f"Box 1 wasn't found in settings.xml, in: {self.conf.context}"
            )

        payload_parts = ['<set box="1"']

        for get_key, post_key in EDGAR_BOX_1_MAP.items():
            if get_key == "comm":
                val = "0"
            else:
                val = box1.attrib.get(get_key, "0")

            payload_parts.append(f'{post_key}="{val}"')

        payload_parts.append("/>")
        xml_payload = f'<?xml version="1.0" encoding="iso-8859-2"?>\n<root>{" ".join(payload_parts)}</root>'

        resp_start = await self._client.write_command(
            '<root><set box="0" /></root>',
            self.conf.context,
            SAVE_SETTINGS_ENDPOINT,
        )
        self._check_response(
            resp_start,
            expected_status="1",
            action_msg="opening configuration transaction",
        )

        resp_data = await self._client.write_command(
            xml_payload, self.conf.context, SAVE_SETTINGS_ENDPOINT
        )
        self._check_response(
            resp_data, expected_status="1", action_msg="setting TCP server mode"
        )

        resp_save = await self._client.write_command(
            '<root><set box="99" /></root>',
            self.conf.context,
            SAVE_SETTINGS_ENDPOINT,
        )
        self._check_response(
            resp_save,
            expected_status="2",
            action_msg="saving and restarting the device",
        )


async def async_setup_converter_edgar(client: PapouchHTTPClient, name: str) -> Edgar:
    """Async factory for Edgar converter."""

    identifier = await client.get_device_mac()
    _, location = await client.get_device_info()
    tcp_port = await client.get_device_tcp_port()

    return Edgar(client, identifier, name, location, tcp_port)


class Gnome(PapouchHTTPConverter):
    """Represent Gnome converters."""

    def __init__(self, identifier: str, name: str, tcp_port: int, device_mode: int):
        self._conf = ConverterConfiguration(
            identifier, name, "Serial", name, tcp_port=tcp_port
        )
        self._device_mode = device_mode

    @override
    @property
    def conf(self) -> ConverterConfiguration:
        return self._conf

    @override
    async def get_mode(self) -> int:
        return self._device_mode

    @override
    async def switch_to_tcp_server(self) -> None:
        """Unused."""
        raise DeviceLogicError("Gnome shouldn't use this method.")


async def _async_is_gnome_device(client: PapouchHTTPClient) -> bool:
    """Check via HTTP if the device is a Gnome."""
    try:
        version_js = await client.read_command(
            {}, "Trying to create Gnome", "papouch-version.js"
        )
        return "gnome" in version_js.lower()
    except DeviceConnectionError:
        return False


async def _async_download_gnome_config(ip_address: str) -> tuple[bytes, bytes]:
    """Connect to Telnet, safely download configuration and disconnect."""
    reader = None
    writer = None
    for attempt in range(4):
        try:
            reader, writer = await asyncio.open_connection(ip_address, 9999)
            break
        except OSError as err:
            if attempt == 3:
                raise DeviceConnectionError(
                    f"Cannot connect to Gnome Telnet port: {err}"
                ) from err
            await asyncio.sleep(2.0)

    if reader is None or writer is None:
        raise DeviceConnectionError("Failed to open connection to Gnome Telnet port")

    init_data = await reader.read(1024)
    writer.write(b"\r\n")
    await asyncio.wait_for(writer.drain(), timeout=5.0)

    buffer = bytearray()
    while True:
        try:
            chunk = await asyncio.wait_for(reader.read(1024), timeout=0.3)
            if not chunk:
                break
            buffer.extend(chunk)

            if b"Your choice ?" in buffer:
                break
        except TimeoutError:
            break

    writer.write(b"8\r\n")
    await asyncio.wait_for(writer.drain(), timeout=5.0)

    try:
        while True:
            exit_chunk = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            if not exit_chunk:
                break
    except (TimeoutError, ConnectionResetError, EOFError):
        pass

    config_data = bytes(buffer)
    writer.close()
    await writer.wait_closed()

    return init_data, config_data


def _parse_gnome_config(
    init_data: bytes, config_data: bytes
) -> tuple[str, str, int, int]:
    """Parse raw bytes from Telnet into MAC address, interface type, and TCP port."""
    init_text = init_data.decode("ascii", errors="ignore")
    config_text = config_data.decode("ascii", errors="ignore")

    mac_match = re.search(r"MAC address\s+([0-9A-Fa-f]{12})", init_text)
    if not mac_match:
        raise DeviceParseError("MAC of the GNOME wasn't found")

    mac_raw = mac_match.group(1)
    mac_address = ":".join(mac_raw[i : i + 2] for i in range(0, 12, 2))

    port_match = re.search(
        r"\*\*\* Channel 1.*?\n.*?Port\s+(\d+)", config_text, re.DOTALL
    )
    tcp_port = int(port_match.group(1)) if port_match else 10001

    if_mode_match = re.search(r"I/F Mode\s+([0-9A-Fa-f]+)", config_text)
    if if_mode_match:
        if_mode_hex = if_mode_match.group(1)
        if_mode_byte = int(if_mode_hex, 16)

        is_rs485 = (if_mode_byte & 0x40) != 0 or (if_mode_byte & 0xC0) == 0xC0
        interface_type = "RS485" if is_rs485 else "RS232/RS422"
    else:
        interface_type = "Unknown"

    device_mode_index = 0
    connect_mode_match = re.search(r"Connect Mode\s*:\s*([0-9A-Fa-f]{2})", config_text)

    if connect_mode_match:
        connect_mode_byte = int(connect_mode_match.group(1), 16)

        is_server = ((connect_mode_byte >> 5) & 0x07) == 0x06

        active_mode = connect_mode_byte & 0x0F

        if active_mode == 0x0C:
            device_mode_index = UDP_MODE_INDEX
        elif active_mode == 0x05 and not is_server:
            device_mode_index = TCP_CLIENT_MODE_INDEX
        elif is_server:
            device_mode_index = TCP_SERVER_MODE_INDEX

    return mac_address, interface_type, tcp_port, device_mode_index


async def async_setup_converter_gnome(client: PapouchHTTPClient) -> Gnome | None:
    """Async factory for Gnome converter."""
    if not await _async_is_gnome_device(client):
        return None

    try:
        init_data, config_data = await _async_download_gnome_config(client.ip_address)
    except DeviceConnectionError:
        return None

    mac_address, interface_type, tcp_port, device_mode = _parse_gnome_config(
        init_data, config_data
    )

    return Gnome(mac_address, f"Gnome {interface_type}", tcp_port, device_mode)
