"""This file contains definition of the THCO2 device."""

import logging
from dataclasses import dataclass, field
from typing import Any, override

from aiopapouch.exceptions import DeviceParseError

from ..client import PapouchSerialClient
from .base import PapouchConfiguration, PapouchDevice

_LOGGER = logging.getLogger(__name__)


@dataclass
class THCO2Configuration(PapouchConfiguration):
    """Configuration for THCO2."""

    address: int = 0
    sensors: dict[str, dict[str, str]] = field(default_factory=dict)


class THCO2(PapouchDevice):
    """Represents TH2E device."""

    @override
    @property
    def conf(self) -> THCO2Configuration:
        return self._conf

    def __init__(
        self,
        api_client: PapouchSerialClient,
        device_name: str,
        location: str,
        serial_number: str,
        address: int,
    ) -> None:
        """Constructor for THCO2 device. Default unit is C"""

        self.api_client = api_client

        self._conf = THCO2Configuration(
            name=device_name,
            location=location,
            identifier=serial_number,
            context=f"{device_name} - SN: {serial_number}",
            address=address,
        )

        self.MAPPING_SENSORS = {
            1: self.CO2_SNS_TYPE,
            2: self.TEMPERATURE_SNS_TYPE,
            3: self.HUMIDITY_SNS_TYPE,
            4: self.DEW_POINT_SNS_TYPE,
        }

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

        status = data[0]
        if status != 0:
            return parsed_data

        type_idx = 1

        for i in range(1, len(data) - 2, 2):
            chunk = data[i : i + 2]
            if len(chunk) < 2:
                raise DeviceParseError(
                    f"Chunk doesn't have 2 bytes, in {self.conf.context}"
                )

            if type_idx == 5:
                raise DeviceParseError(
                    f"Too much data received, in {self.conf.context}"
                )

            item_id = str(type_idx)

            sns_type = self.MAPPING_SENSORS[type_idx]

            self.conf.sensors[item_id] = {
                "id": item_id,
                "type": sns_type,
                "unit": "0",
            }

            raw_value = int.from_bytes(chunk, byteorder="big", signed=True)

            semantic_key = self._generate_semantic_key(sns_type, item_id)

            parsed_data["sensor"][semantic_key] = (
                raw_value / 10 if type_idx != 1 else raw_value
            )

            type_idx += 1

        return parsed_data

    @override
    async def parse_fresh_data(self, xml_data: str = "") -> dict:
        """Fetch and parse fresh data."""
        raw_bytes = await self._update_data()
        return self._parse_raw_data(raw_bytes)

    @override
    def get_supported_buttons(self) -> list[dict[str, Any]]:
        """Unused in THCO2."""
        return []

    @override
    def get_supported_binary_sensors(self) -> list[dict[str, Any]]:
        """Unused in THCO2."""
        return []

    @override
    def get_supported_numbers(self) -> list[dict[str, Any]]:
        """Unused in THCO2."""
        return []

    @override
    def get_supported_sensors(self) -> list[dict[str, Any]]:
        sensors = []

        for sns in self.conf.sensors.values():
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

                case self.CO2_SNS_TYPE:
                    sensors.append({
                        "item_id": item_id,
                        "value_key": semantic_key,
                        "type": "sensor",
                        "data_type": "co2",
                        "name": None,
                        "unit": self._get_unit(sns_type, unit_code),
                    })

        return sensors

    @override
    def get_supported_switches(self) -> list[dict[str, Any]]:
        """Unused in THCO2."""
        return []

    @override
    def get_supported_selects(self) -> list[dict[str, Any]]:
        """Unused in THCO2."""
        return []

    @override
    async def execute_button_command(self, cmd_type: str) -> None:
        """Unused in THCO2."""

    @override
    async def turn_on_switch(self, item_id: str) -> None:
        """Unused in THCO2."""

    @override
    async def turn_off_switch(self, item_id: str) -> None:
        """Unused in THCO2."""

    @override
    async def set_number_value(self, category: str, item_id: str, value: float) -> None:
        """Unused in THCO2."""

    @override
    def get_select_option(self, category: str, item_id: str) -> str | None:
        """Unused in THCO2."""

    @override
    async def set_select_option(self, category: str, item_id: str, option: str) -> None:
        """Unused in THCO2."""

    @override
    async def switch_to_web_mode(self) -> None:
        """THCO2 is a serial device."""

    @override
    def _parse_initial_settings(self) -> None:
        """Unused in THCO2."""


async def async_setup_serial_thco2(
    client: PapouchSerialClient,
    address: int,
    serial_number: str,
    device_name: str,
    location: str,
) -> THCO2:
    """Async factory for THCO2 device."""

    return THCO2(client, device_name, location, serial_number, address)
