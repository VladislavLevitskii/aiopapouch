"""This file contains definition of the THT2 device."""

import logging
from typing import Any, override

from ..client import PapouchSerialClient
from .base import PapouchDevice

_LOGGER = logging.getLogger(__name__)


class THT2(PapouchDevice):
    """Represents TH2E device."""

    @override
    @property
    def name(self) -> str:
        """Return device's name."""
        return self._name

    @override
    @property
    def location(self) -> str:
        """Return device's location."""
        return self._location

    @override
    @property
    def manufacturer(self) -> str:
        """Return device's manufacturer."""
        return "Papouch s.r.o."

    @override
    @property
    def identifier(self) -> str:
        """Return device's identifier."""
        return self._serial_number

    def __init__(
        self,
        api_client: PapouchSerialClient,
        location: str,
        serial_number: str,
        address: int,
        unit: str = "0",
    ) -> None:
        """Constructor for THT2 device. Default unit is C"""

        self.api_client = api_client
        self._name = "THT2"
        self._location = location
        self._serial_number = serial_number
        self._address = address
        self._unit = unit

        self.sensors: dict[str, dict[str, str]] = {}

    async def _update_data(self) -> bytes:
        """Fetch raw bytes of the fresh data from the serial device."""
        packet = await self.api_client.write_command(
            self._address, 0x51, f"{self.name} - {self.location}", b"\x00"
        )
        return packet.data

    def _parse_raw_data(self, data: bytes) -> dict:
        """Parse raw bytes into dictionary )."""
        parsed_data: dict[str, dict[str, Any]] = {"sensor": {}}

        type_idx = 1

        for i in range(0, len(data), 4):
            chunk = data[i : i + 4]
            if len(chunk) < 4:
                break

            item_id = str(type_idx)
            sns_type = str(type_idx)
            type_idx += 1

            self.sensors[item_id] = {
                "id": item_id,
                "type": sns_type,
                "unit": self._unit
                if item_id != "2"
                else "0",  # humidity ("2") has always 0
            }

            dev_index = chunk[0]
            status = chunk[1]
            raw_value = int.from_bytes(chunk[2:4], byteorder="big", signed=True)

            item_id = str(dev_index)
            sns_type = str(dev_index)
            semantic_key = self._generate_semantic_key(sns_type, item_id)

            if status >> 7 != 1:
                parsed_data["sensor"][semantic_key] = None
            else:
                parsed_data["sensor"][semantic_key] = raw_value / 10

        return parsed_data

    @override
    async def parse_fresh_data(self, xml_data: str = "") -> dict:
        """Fetch and parse fresh data."""
        raw_bytes = await self._update_data()
        return self._parse_raw_data(raw_bytes)

    @override
    def get_location(self) -> str:
        """Return the location of the device."""
        return self._location

    @override
    def get_name(self) -> str:
        """Return the name of the device."""
        return self._name

    @override
    def get_identifier(self) -> str:
        """Return the identifier of the device."""
        return self._serial_number

    @override
    def get_supported_buttons(self) -> list[dict[str, Any]]:
        """Unused in THT2."""
        return []

    @override
    def get_supported_binary_sensors(self) -> list[dict[str, Any]]:
        """Unused in THT2."""
        return []

    @override
    def get_supported_numbers(self) -> list[dict[str, Any]]:
        """Unused in THT2."""
        return []

    @override
    def get_supported_sensors(self) -> list[dict[str, Any]]:
        sensors = []

        for sns in self.sensors.values():
            item_id = sns["id"]
            sns_type = sns["type"]
            unit_code = sns["unit"]

            semantic_key = self._generate_semantic_key(sns_type, item_id)

            match sns_type:
                case self.TEMPERATURE_SNS_TYPE:
                    sensors.append({
                        "item_id": item_id,
                        "value_key": semantic_key,
                        "type": "sensor",
                        "data_type": "temperature",
                        "name": None,
                        "unit": self._get_unit(sns_type, unit_code),
                    })

                case self.HUMIDITY_SNS_TYPE:
                    sensors.append({
                        "item_id": item_id,
                        "value_key": semantic_key,
                        "type": "sensor",
                        "data_type": "humidity",
                        "name": None,
                        "unit": self._get_unit(sns_type, unit_code),
                    })

                case self.DEW_POINT_SNS_TYPE:
                    sensors.append({
                        "item_id": item_id,
                        "value_key": semantic_key,
                        "type": "sensor",
                        "data_type": "dew_point",
                        "name": None,
                        "unit": self._get_unit(sns_type, unit_code),
                    })

        return sensors

    @override
    def get_supported_switches(self) -> list[dict[str, Any]]:
        """Unused in THT2."""
        return []

    @override
    def get_supported_selects(self) -> list[dict[str, Any]]:
        """Unused in THT2."""
        return []

    @override
    async def execute_button_command(self, cmd_type: str) -> None:
        """Unused in THT2."""

    @override
    async def turn_on_switch(self, item_id: str) -> None:
        """Unused in THT2."""

    @override
    async def turn_off_switch(self, item_id: str) -> None:
        """Unused in THT2."""

    @override
    async def set_number_value(self, category: str, item_id: str, value: float) -> None:
        """Unused in THT2."""

    @override
    def get_select_option(self, category: str, item_id: str) -> str | None:
        """Unused in THT2."""

    @override
    async def set_select_option(self, category: str, item_id: str, option: str) -> None:
        """Unused in THT2."""

    @override
    async def switch_to_web_mode(self) -> None:
        """THT2 is a serial device."""

    @override
    def _parse_initial_settings(self) -> None:
        """Unused in THT2."""


async def _get_unit(
    transport: PapouchSerialClient, address: int, serial_number: str
) -> str:
    pkt_unit = await transport.write_command(
        address, 0x1B, f"THT2 on address {address} - SN: {serial_number}"
    )

    data = pkt_unit.data

    # first channel value because setting can happen only on every channel
    chunk = data[1]

    return str(chunk)


async def async_setup_tht2(
    client: PapouchSerialClient, address: int, serial_number: str, location: str
) -> THT2:
    """Async factory for THT2 device."""

    unit = await _get_unit(client, address, serial_number)

    return THT2(client, location, serial_number, address, unit)
