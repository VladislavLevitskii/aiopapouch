"""This file contains definition of the HTTP converters device."""

import logging
from dataclasses import dataclass
from typing import override

import defusedxml.ElementTree as defused_ET

from aiopapouch.exceptions import DeviceParseError, DeviceResponseError

from ..client import SAVE_SETTINGS_ENDPOINT, PapouchHTTPClient
from .base import PapouchConfiguration, PapouchHTTPConverter, find_tag

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
class EdgarConfiguration(PapouchConfiguration):
    """Represent Edgar configuration"""


class Edgar(PapouchHTTPConverter):
    """Represent Edgar ETH and WIFI converter to RS485."""

    def __init__(
        self,
        client: PapouchHTTPClient,
        identifier: str,
        name: str,
        location: str | None,
    ):
        _location = location or "NONAME"
        self._conf = EdgarConfiguration(
            identifier,
            name,
            _location,
            f"{name} - ({_location})",
        )
        self._client = client

    @override
    @property
    def conf(self) -> EdgarConfiguration:
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

    return Edgar(client, identifier, name, location)
