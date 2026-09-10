"""This file contains definition of the TQS4 device."""

import logging
from dataclasses import dataclass
from typing import Any, override

from ..client import PapouchSerialClient
from .base import PapouchConfiguration, PapouchDevice

_LOGGER = logging.getLogger(__name__)


@dataclass
class TQS4Configuration(PapouchConfiguration):
    """Configuration for TQS4."""

    address: int = 0
    unit: str = ""


class TQS4(PapouchDevice):
    """Represents TH2E device."""

    @override
    @property
    def conf(self) -> TQS4Configuration:
        return self._conf

    def __init__(
        self,
        api_client: PapouchSerialClient,
        device_name: str,
        location: str,
        serial_number: str,
        address: int,
    ) -> None:
        """Constructor for TQS4 device."""

        self.api_client = api_client

        self._conf = TQS4Configuration(
            name=device_name,
            location=location,
            identifier=serial_number,
            context=f"{device_name} - SN: {serial_number}",
            address=address,
        )

        self._conf.unit = self._get_unit(self.TEMPERATURE_SNS_TYPE, "0")

    async def _update_data(self) -> bytes:
        """Fetch raw bytes of the fresh data from the serial device."""
        packet = await self.api_client.write_command(
            self.conf.address,
            0x51,
            self.conf.context,
        )
        return packet.data

    def _parse_raw_data(self, data: bytes) -> dict:
        """Parse raw bytes into dictionary )."""
        parsed_data: dict[str, dict[str, Any]] = {"sensor": {}}

        raw_value = int.from_bytes(data, byteorder="big", signed=True)

        semantic_key = self._generate_semantic_key(self.TEMPERATURE_SNS_TYPE, "1")

        parsed_data["sensor"][semantic_key] = raw_value / 32

        return parsed_data

    @override
    async def parse_fresh_data(self, xml_data: str = "") -> dict:
        """Fetch and parse fresh data."""
        raw_bytes = await self._update_data()
        return self._parse_raw_data(raw_bytes)

    @override
    def get_supported_buttons(self) -> list[dict[str, Any]]:
        """Unused in TQS4."""
        return []

    @override
    def get_supported_binary_sensors(self) -> list[dict[str, Any]]:
        """Unused in TQS4."""
        return []

    @override
    def get_supported_numbers(self) -> list[dict[str, Any]]:
        """Unused in TQS4."""
        return []

    @override
    def get_supported_sensors(self) -> list[dict[str, Any]]:

        semantic_key = self._generate_semantic_key(self.TEMPERATURE_SNS_TYPE, "1")

        return [
            {
                "item_id": "1",
                "value_key": semantic_key,
                "type": "sensor",
                "data_type": "temperature",
                "name": None,
                "unit": self.conf.unit,
            }
        ]

    @override
    def get_supported_switches(self) -> list[dict[str, Any]]:
        """Unused in TQS4."""
        return []

    @override
    def get_supported_selects(self) -> list[dict[str, Any]]:
        """Unused in TQS4."""
        return []

    @override
    async def execute_button_command(self, cmd_type: str) -> None:
        """Unused in TQS4."""

    @override
    async def turn_on_switch(self, item_id: str) -> None:
        """Unused in TQS4."""

    @override
    async def turn_off_switch(self, item_id: str) -> None:
        """Unused in TQS4."""

    @override
    async def set_number_value(self, category: str, item_id: str, value: float) -> None:
        """Unused in TQS4."""

    @override
    def get_select_option(self, category: str, item_id: str) -> str | None:
        """Unused in TQS4."""

    @override
    async def set_select_option(self, category: str, item_id: str, option: str) -> None:
        """Unused in TQS4."""

    @override
    async def switch_to_web_mode(self) -> None:
        """TQS4 is a serial device."""

    @override
    def _parse_initial_settings(self) -> None:
        """Unused in TQS4."""


async def async_setup_serial_tqs4(
    client: PapouchSerialClient,
    address: int,
    serial_number: str,
    device_name: str,
    location: str,
) -> TQS4:
    """Async factory for TQS4 device."""

    return TQS4(client, device_name, location, serial_number, address)
