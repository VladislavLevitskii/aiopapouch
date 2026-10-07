"""This file contains definition of the TH2E device."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, override

import defusedxml.ElementTree as defused_ET

from ..client import PapouchHTTPClient
from ..const import UNKNOWN_LOCATION, UNKNOWN_NAME
from ..exceptions import DeviceLogicError, DeviceParseError, DeviceResponseError
from ..utils import find_tag, require_attr
from .base import PapouchNetworkConfiguration, PapouchNetworkDevice

_LOGGER = logging.getLogger(__name__)


@dataclass
class TH2EConfiguration(PapouchNetworkConfiguration):
    """Configuration for TH2E."""

    sensors: dict[str, dict[str, str]] = field(default_factory=dict)
    sensor_type: int = 0


class TH2E(PapouchNetworkDevice):
    """Represents TH2E device."""

    @property
    @override
    def conf(self) -> TH2EConfiguration:
        return self._conf

    def __init__(
        self,
        api_client: PapouchHTTPClient,
        settings: str,
        device_name: str,
        location: str,
        mac_address: str,
    ) -> None:
        """Constructor for TH2E device."""

        super().__init__()

        self.api_client = api_client

        try:
            self.settings_root = defused_ET.fromstring(settings)
        except defused_ET.ParseError as err:
            raise DeviceParseError(
                f"Invalid XML passed to TH2E initialization: {err}"
            ) from err

        context_str = f"{device_name} ({location}) - {self.api_client.ip_address}"

        self._conf = TH2EConfiguration(
            name=device_name,
            location=location,
            identifier=mac_address,
            context=context_str,
        )

    @override
    async def get_fresh_data(self) -> dict:
        """Parse XML data into dictionary to feed the coordinator.

        Note that it also sets the type of the sensor. (Global one)
        """

        xml_data = await self.api_client.fetch_data()

        try:
            root = defused_ET.fromstring(xml_data)
        except defused_ET.ParseError as err:
            raise DeviceParseError(
                f"Unable to parse fresh data in {self.conf.context}"
            ) from err

        parsed_data: dict[str, dict[str, Any]] = {"sensor": {}}

        status_tag = find_tag(root, "status")

        if status_tag is None:
            raise DeviceParseError(
                f"The device doesn't have box status tag in fresh.xml, device: {self.conf.context}"
            )

        _sensor_type = require_attr(
            status_tag, "typesens", f"status tag {status_tag.tag}", self.conf.context
        )

        try:
            self.conf.sensor_type = int(_sensor_type)
        except ValueError as err:
            raise DeviceParseError(
                f"Sensor type '{_sensor_type}' is not int in the device {self.conf.context}"
            ) from err

        for element in root.iter():
            if not element.tag.endswith("sns"):
                continue

            item_id = require_attr(
                element, "id", f"sensor {element.tag}", self.conf.context
            )
            sns_type = require_attr(
                element, "type", f"sensor {item_id}", self.conf.context
            )
            unit_code = require_attr(
                element, "unit", f"sensor {item_id}", self.conf.context
            )

            if sns_type not in self.TYPE_MAPPING:
                _LOGGER.warning(
                    "Unknown sensor type '%s' ignored in %s.",
                    sns_type,
                    self.conf.context,
                )
                continue

            semantic_key = self._generate_semantic_key(sns_type, item_id)

            # unit 3 means percentage but in global unit map it would be 1
            if unit_code == "3":
                unit_code = "0"

            status = require_attr(
                element, "status", f"sensor {item_id}", self.conf.context
            )

            self.conf.sensors[item_id] = {
                "id": item_id,
                "type": sns_type,
                "unit": unit_code,
            }

            if status in ("1", "4"):
                parsed_data["sensor"][semantic_key] = None
            else:
                raw_val = require_attr(
                    element, "val", f"sensor {item_id}", self.conf.context
                )
                try:
                    parsed_data["sensor"][semantic_key] = float(raw_val)
                except ValueError:
                    parsed_data["sensor"][semantic_key] = None

        return parsed_data

    @override
    def get_supported_buttons(self) -> list[dict[str, Any]]:
        return [{"translation": "set_sensor", "cmd": "set_sensor"}]

    @override
    def get_supported_binary_sensors(self) -> list[dict[str, Any]]:
        """Unused in TH2E."""
        return []

    @override
    def get_supported_numbers(self) -> list[dict[str, Any]]:
        """Unused in TH2E."""
        return []

    @override
    def get_supported_sensors(self) -> list[dict[str, Any]]:
        sensors = []

        for sns in self.conf.sensors.values():
            item_id = sns["id"]
            sns_type = sns["type"]
            unit_code = sns["unit"]

            sensors.append({
                "item_id": item_id,
                "value_key": self._generate_semantic_key(sns_type, item_id),
                "type": "sensor",
                "data_type": self.TYPE_MAPPING[sns_type],
                "name": None,
                "unit": self._get_unit(sns_type, unit_code),
            })

        return sensors

    @override
    def get_supported_switches(self) -> list[dict[str, Any]]:
        """Unused in TH2E."""
        return []

    @override
    def get_supported_selects(self) -> list[dict[str, Any]]:
        return [
            {
                "item_id": "1",
                "category": "sensor_type",
                "name": None,
                "options": self.SENSOR_TYPES,
            }
        ]

    @override
    async def execute_button_command(self, cmd_type: str) -> None:
        if cmd_type != "set_sensor":
            raise DeviceLogicError(
                f"Unsupported command: {cmd_type}, in the device: {self.conf.context}"
            )

        self.conf.sensor_type = await self.get_sensor_type()
        await self.set_sensor_type(self.conf.sensor_type)

    async def get_sensor_type(self) -> int:
        """Get the type of the sensor."""

        request = '<root><set box="19" num1="00001" /></root>'
        response = await self.api_client.write_command(
            request, f"{self.conf.name} ({self.conf.location})"
        )

        parsed_type = self._check_sensor_response(
            response,
            expected_status="4",
            action_msg="fetching the type of the sensor",
        )

        if parsed_type is None:
            raise DeviceParseError(
                f"Missing required attribute 'typesens' in response in {self.conf.context}"
            )

        return parsed_type

    async def set_sensor_type(self, type_idx: int) -> None:
        """Set the type of the sensor."""

        settings = await self.api_client.fetch_settings()

        try:
            settings_root = defused_ET.fromstring(settings)
        except defused_ET.ParseError as exception:
            raise DeviceParseError(
                f"Invalid settings XML: {exception}, in the device: {self.conf.context}"
            ) from exception

        def format_str_val(val: str) -> str:
            clean_val = val.removesuffix(".0")
            return clean_val.rjust(10, " ")

        set_attrs = {
            "box": "9",
            "num1": str(type_idx),
            "num2": "0",
            "str1": format_str_val("-40"),
            "str2": format_str_val("125"),
            "str3": format_str_val("0"),
            "num3": "00020",
            "str4": format_str_val("0"),
            "str5": format_str_val("100"),
            "str6": format_str_val("0"),
            "num4": "00001",
            "str7": format_str_val("-40"),
            "str8": format_str_val("125"),
            "str9": format_str_val("0"),
            "num5": "00001",
        }

        num2_val = 0

        for i in range(1, 4):
            item = None
            for element in settings_root.iter():
                if element.tag.endswith("sns") and element.attrib.get("id") == str(i):
                    item = element
                    break

            if item is None:
                continue

            if item.get("sns2mem", "0") == "1":
                num2_val += 1 << (i + 3)

            str_base = (i - 1) * 3

            if "min" in item.attrib:
                set_attrs[f"str{str_base + 1}"] = format_str_val(item.attrib["min"])
            if "max" in item.attrib:
                set_attrs[f"str{str_base + 2}"] = format_str_val(item.attrib["max"])
            if "hyst" in item.attrib:
                set_attrs[f"str{str_base + 3}"] = format_str_val(item.attrib["hyst"])
            if "memhyst" in item.attrib:
                set_attrs[f"num{i + 2}"] = item.attrib["memhyst"].zfill(5)

        set_attrs["num2"] = str(num2_val)

        save_root = ET.Element("root", xmlns="http://www.papouch.com/xml/th2e/save")
        ET.SubElement(save_root, "set", attrib=set_attrs)

        xml_payload = ET.tostring(save_root, encoding="unicode")

        final_response = await self.api_client.write_command(
            xml_payload, f"{self.conf.name} ({self.conf.location})"
        )

        self._check_sensor_response(
            final_response,
            expected_status="2",
            action_msg="setting the type of the sensor",
        )

    def _check_sensor_response(
        self, response_text: str, expected_status: str, action_msg: str
    ) -> int | None:
        try:
            root = defused_ET.fromstring(response_text)
        except defused_ET.ParseError as exception:
            raise DeviceParseError(
                f"Invalid XML response from device: {exception}, in the device: {self.conf.context}"
            ) from exception

        result_tag = find_tag(root, "result")

        if result_tag is None:
            raise DeviceParseError(
                f"Response doesn't have result tag!, in the device: {self.conf.context}"
            )

        status_val = require_attr(result_tag, "status", "result tag", self.conf.context)

        if status_val != expected_status:
            raise DeviceResponseError(
                f"{self.conf.context} returned an error while {action_msg}, whole response: {response_text}"
            )

        typesens_str = result_tag.attrib.get("typesens")

        if typesens_str is None:
            return None

        try:
            return int(typesens_str)
        except ValueError as exception:
            raise DeviceParseError(
                f"Invalid 'typesens' value '{typesens_str}' in device: {self.conf.context}"
            ) from exception

    @override
    async def turn_on_switch(self, item_id: str) -> None:
        """Unused in TH2E."""
        raise DeviceLogicError(
            f"Calling not implemented method in {self.conf.context}."
        )

    @override
    async def turn_off_switch(self, item_id: str) -> None:
        """Unused in TH2E."""
        raise DeviceLogicError(
            f"Calling not implemented method in {self.conf.context}."
        )

    @override
    async def set_number_value(self, category: str, item_id: str, value: float) -> None:
        """Unused in TH2E."""
        raise DeviceLogicError(
            f"Calling not implemented method in {self.conf.context}."
        )

    @override
    def get_select_option(self, category: str, item_id: str) -> str | None:
        if category != "sensor_type":
            raise DeviceLogicError(
                f"Unknown select category '{category}' requested for device: {self.conf.context}"
            )

        if item_id != "1":
            raise DeviceLogicError(
                f"Unknown item_id '{item_id}' requested for device: {self.conf.context}"
            )

        if 0 <= self.conf.sensor_type < len(self.SENSOR_TYPES):
            return self.SENSOR_TYPES[self.conf.sensor_type]

        raise DeviceLogicError(
            f"Invalid sensor_type index '{self.conf.sensor_type}' in device: {self.conf.context}"
        )

    @override
    async def set_select_option(self, category: str, item_id: str, option: str) -> None:
        if category != "sensor_type":
            raise DeviceLogicError(
                f"Unknown select category '{category}' requested for device: {self.conf.context}"
            )

        if item_id != "1":
            raise DeviceLogicError(
                f"Unknown item_id '{item_id}' requested for device: {self.conf.context}"
            )

        try:
            type_idx = self.SENSOR_TYPES.index(option)
        except ValueError as err:
            raise DeviceLogicError(
                f"Unknown option '{option}' for category '{category}' in device: {self.conf.context}"
            ) from err

        await self.set_sensor_type(type_idx)
        self.conf.sensor_type = type_idx

    @override
    async def switch_to_web_mode(self) -> None:
        """Switch the device network mode to WEB using its current settings."""
        box = self.settings_root.find(".//set[@box='1']")
        if box is None:
            raise DeviceParseError(
                f"Box for network mode is not found, in the device: {self.conf.context}"
            )

        def pad_ip(ip_str: str) -> str:
            return ".".join(part.zfill(3) for part in ip_str.split("."))

        ctx = self.conf.context
        save_root = ET.Element("root")

        ET.SubElement(
            save_root,
            "set",
            box="1",
            ip1=pad_ip(require_attr(box, "ip", "box 1", ctx)),
            ip2=pad_ip(require_attr(box, "mask", "box 1", ctx)),
            ip3=pad_ip(require_attr(box, "gate", "box 1", ctx)),
            ip5=pad_ip(require_attr(box, "dip", "box 1", ctx)),
            num2=require_attr(box, "wport", "box 1", ctx).zfill(5),
            num4="3",
            num5=require_attr(box, "com", "box 1", ctx),
            num7=require_attr(box, "mport", "box 1", ctx).zfill(5),
            num1=require_attr(box, "lport", "box 1", ctx).zfill(5),
            ip4=pad_ip(require_attr(box, "rip", "box 1", ctx)),
            num3=require_attr(box, "rport", "box 1", ctx).zfill(5),
        )

        xml_payload = ET.tostring(save_root, encoding="unicode")
        response = await self.api_client.write_command(
            xml_payload, f"{self.conf.name} ({self.conf.location})"
        )

        self._check_sensor_response(response, "2", "setting to WEB mode")

        await asyncio.sleep(15)


async def async_setup_network_th2e(client: PapouchHTTPClient) -> TH2E:
    """Async factory for TH2E device."""
    settings = await client.fetch_settings()

    device_name, location = await client.get_device_info()
    device_name = device_name or UNKNOWN_NAME
    location = location or UNKNOWN_LOCATION

    mac_address = await client.get_device_mac()

    return TH2E(client, settings, device_name, location, mac_address)
