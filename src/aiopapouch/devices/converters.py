"""This file contains definition of the HTTP converters device."""

from dataclasses import dataclass
from typing import override

import defusedxml.ElementTree as defused_ET

from aiopapouch.exceptions import DeviceParseError

from ..client import PapouchHTTPClient
from .base import PapouchConfiguration, PapouchHTTPConverter


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


async def async_setup_converter_edgar(client: PapouchHTTPClient, name: str) -> Edgar:
    """Async factory for Edgar converter."""

    identifier = await client.get_device_mac()
    _, location = await client.get_device_info()

    return Edgar(client, identifier, name, location)
