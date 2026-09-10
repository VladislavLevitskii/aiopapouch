"""This file contains definition of the Papago device family."""

import logging
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, cast, override

import defusedxml.ElementTree as defused_ET

from ..client import PapouchHTTPClient
from ..exceptions import (
    DeviceLogicError,
    DeviceParseError,
    DeviceResponseError,
)
from .base import HTTPMixin, PapouchConfiguration, PapouchDevice, find_tag

_LOGGER = logging.getLogger(__name__)


@dataclass
class InputSettings:
    """Contains information about 1 input of Papago."""

    name: str
    unit: str
    decimal_count: str
    trigger_impulse_count: str  # how much impulses are needed to increase counter
    value_to_add: str  # and by how many
    type_cnt: str
    box_num: int


@dataclass
class OutputSettings:
    """Contains information about 1 output of Papago."""

    name: str


@dataclass
class PapagoConfiguration(PapouchConfiguration):
    """Configuration for Papago devices."""

    size_counter_bits: int = 32

    inputs: dict[str, InputSettings] = field(default_factory=dict)
    outputs: dict[str, OutputSettings] = field(default_factory=dict)
    sensors: dict[str, dict[str, Any]] = field(default_factory=dict)
    sensors_types: dict[str, str] = field(default_factory=dict)


class PapagoETH(PapouchDevice, HTTPMixin, ABC):
    """Represents Papago device family.

    Note that it uses unified code that
    will be applicable to all of Papago devices.
    """

    api_client: PapouchHTTPClient

    BOX_SENSOR_BASE: int | None = None

    SAVE_ENDPOINT = "savesettings.xml"

    SENSOR_SETTINGS_KEYS: ClassVar[list[tuple[str, str]]]

    # This constant is used for distinguishing IDs for select entries
    INPUT_ID_INCREMENT = 1000

    @property
    @override
    def conf(self) -> PapagoConfiguration:
        """Return the device configuration."""
        return self._conf

    def __init__(
        self,
        api_client: PapouchHTTPClient,
        settings: str,
        device_name: str,
        location: str,
    ) -> None:
        """Constructor for Papago device."""

        super().__init__()

        self.api_client = cast(PapouchHTTPClient, api_client)
        self.settings_root = defused_ET.fromstring(settings)

        _mac_address = self._get_identifier()

        context_str = f"{device_name} ({location}) - {self.api_client.ip_address}"
        self._conf = PapagoConfiguration(
            identifier=_mac_address,
            name=device_name,
            location=location,
            context=context_str,
        )

        self._parse_initial_settings()

    @override
    async def parse_fresh_data(self, xml_data: str) -> dict:
        root = defused_ET.fromstring(xml_data)

        parsed_data: dict[str, dict[str, Any]] = {
            "sensor": {},
            "input": {},
            "counter": {},
            "switch": {},
        }

        for element in root.iter():
            tag = element.tag

            match tag:
                case "sns":
                    await self._parse_sns_element(element, parsed_data)
                case "din":
                    await self._parse_din_element(element, parsed_data)
                case "dout":  # codespell:ignore dout
                    await self._parse_dout_element(element, parsed_data)
                case _:
                    continue

        return parsed_data

    async def _parse_sns_element(
        self, element: ET.Element, parsed_data: dict[str, dict[str, Any]]
    ) -> None:
        """Parse XML element containing sensor data (temperature, humidity...)."""
        base_item_id = element.attrib.get("id")
        base_name = element.attrib.get("name", "Unknown")

        if not base_item_id:
            return

        if base_item_id not in self.conf.sensors:
            self.conf.sensors[base_item_id] = {
                "name": base_name,
                "sub_sensors": dict[str, str](),
            }

        idx = 1
        while True:
            suffix = "" if idx == 1 else str(idx)
            sns_type = element.attrib.get(f"type{suffix}")

            if sns_type is None:
                break

            item_id = base_item_id if idx == 1 else f"{base_item_id}_{idx}"
            unit_code = element.attrib.get(f"unit{suffix}", "0")
            status = element.attrib.get(f"status{suffix}", "0")

            self.conf.sensors[base_item_id]["sub_sensors"][item_id] = {
                "type": sns_type,
                "unit": unit_code,
            }

            semantic_key = self._generate_semantic_key(sns_type, item_id)

            if status in ("1", "4"):
                parsed_data["sensor"][semantic_key] = None
            else:
                raw_val = element.attrib.get(f"val{suffix}", "0")
                try:
                    parsed_data["sensor"][semantic_key] = float(raw_val)
                except ValueError:
                    # In case there is wind direction e.g. NW
                    parsed_data["sensor"][semantic_key] = raw_val

            idx += 1

    async def _parse_din_element(
        self, element: ET.Element, parsed_data: dict[str, dict[str, Any]]
    ) -> None:
        """Parse XML element containing digital input and counter data."""
        item_id = element.attrib.get("id")
        if not item_id:
            return

        name = element.attrib.get("name")
        if name and item_id in self.conf.inputs:
            self.conf.inputs[item_id].name = name

        bin_val = element.attrib.get("bin")
        if bin_val is not None:
            parsed_data["input"][item_id] = bin_val == "1"

        val_str = element.attrib.get("val")
        semantic_key = self._generate_semantic_key(self.PULSES, item_id)

        if val_str is not None:
            try:
                parts = val_str.split()
                clean_val = parts[0]
                parsed_data["counter"][semantic_key] = float(clean_val)
            except (ValueError, IndexError):
                parsed_data["counter"][semantic_key] = None

    async def _parse_dout_element(
        self, element: ET.Element, parsed_data: dict[str, dict[str, Any]]
    ) -> None:
        """Parse XML element containing digital output data."""
        item_id = element.attrib.get("id")
        if not item_id:
            return

        bin_val = element.attrib.get("bin")

        if bin_val is not None:
            parsed_data["switch"][item_id] = int(bin_val)

        name_val = element.attrib.get("name")

        if name_val is not None and item_id in self.conf.outputs:
            self.conf.outputs[item_id].name = name_val

    def _get_identifier(self) -> str:
        """Return the identifier of the device."""
        box = self.settings_root.find(".//set[@box='12']")

        if box is not None:
            return str(box.attrib.get("mac", ""))

        raise DeviceParseError(
            f"The device doesn't have box 12 with MAC address, device: {self.conf.context}"
        )

    @override
    def get_supported_buttons(self) -> list[dict[str, Any]]:
        buttons = []
        for item_id in self.conf.sensors_types:
            sensor_name = self.conf.sensors.get(item_id, {}).get(
                "name", f"Sensor {item_id}"
            )
            buttons.append({
                "cmd": f"set_sensor_{item_id}",
                "name": sensor_name,
            })
        return buttons

    @override
    def get_supported_binary_sensors(self) -> list[dict[str, Any]]:
        return [
            {
                "item_id": item_id,
                "type": "input",
                "name": item_data.name,
            }
            for item_id, item_data in self.conf.inputs.items()
        ]

    @override
    def get_supported_numbers(self) -> list[dict[str, Any]]:
        result = []
        for item_id, input_data in self.conf.inputs.items():
            result.extend([
                {
                    "item_id": item_id,
                    "category": "decrease_counter",
                    "type": "counter",
                    "name": input_data.name,
                    "min_value": 0,
                    "max_value": (2**self.conf.size_counter_bits) - 1,
                    "step": 10 ** (-int(input_data.decimal_count)),
                },
                {
                    "item_id": str(item_id),
                    "category": "set_counter",
                    "type": "counter",
                    "name": input_data.name,
                    "min_value": 0,
                    "max_value": (2**self.conf.size_counter_bits) - 1,
                    "step": 10 ** (-int(input_data.decimal_count)),
                },
            ])
        return result

    @override
    def get_supported_sensors(self) -> list[dict[str, Any]]:
        sensors = []

        for item_id, item_data in self.conf.inputs.items():
            sensors.append({
                "item_id": item_id,
                "value_key": self._generate_semantic_key(self.PULSES, item_id),
                "type": "counter",
                "data_type": "counter",
                "name": item_data.name,
                "use_custom_name": True,
                "unit": item_data.unit,
            })

        for sensor_data in self.conf.sensors.values():
            sensor_name = sensor_data["name"]

            for sub_id, sub_data in sensor_data["sub_sensors"].items():
                sns_type = sub_data["type"]
                unit_code = sub_data["unit"]

                if sns_type not in self.TYPE_MAPPING:
                    continue

                semantic_key = self._generate_semantic_key(sns_type, sub_id)
                data_type = self.TYPE_MAPPING[sns_type]
                unit_str = self._get_unit(sns_type, unit_code)
                final_name = sensor_name

                if sns_type == self.WIND_DIRECTION_SNS_TYPE:
                    if unit_str != "°":
                        data_type = "wind_direction_text"
                        unit_str = None
                elif sns_type == self.RAIN_SNS_TYPE:
                    if unit_code == "0":
                        final_name = f"{sensor_name} 15 Min"
                        data_type = "rain"
                    elif unit_code == "1":
                        final_name = f"{sensor_name} Hourly"
                        data_type = "precipitation_intensity"
                    elif unit_code == "2":
                        final_name = f"{sensor_name} Daily"
                        data_type = "precipitation_intensity"

                sensors.append({
                    "item_id": sub_id,
                    "value_key": semantic_key,
                    "type": "sensor",
                    "data_type": data_type,
                    "name": final_name,
                    "unit": unit_str,
                })

        return sensors

    @override
    def get_supported_switches(self) -> list[dict[str, Any]]:
        return [
            {
                "item_id": item_id,
                "name": item_data.name,
            }
            for item_id, item_data in self.conf.outputs.items()
        ]

    @override
    def get_supported_selects(self) -> list[dict[str, Any]]:
        selects = []
        for item_id in self.conf.sensors_types:
            sensor_name = self.conf.sensors.get(item_id, {}).get(
                "name", f"Sensor {item_id}"
            )
            selects.append({
                "item_id": item_id,
                "category": "sensor_type",
                "name": sensor_name,
                "options": self.SENSOR_TYPES,
            })

        for item_id, input_data in self.conf.inputs.items():
            selects.append({
                "item_id": str(int(item_id) + self.INPUT_ID_INCREMENT),
                "category": "counter_mode",
                "name": input_data.name,
                "options": self.COUNTER_MODES,
            })
        return selects

    @override
    async def turn_on_switch(self, item_id: str) -> None:
        """Command for turning the coil on by its id."""
        await self._send_command("s", item_id)

    @override
    async def turn_off_switch(self, item_id: str) -> None:
        """Command for turning the coil off by its id."""
        await self._send_command("r", item_id)

    async def _update_settings(self) -> None:
        settings = await self.api_client.fetch_settings()

        try:
            self.settings_root = defused_ET.fromstring(settings)
        except defused_ET.ParseError as exception:
            raise DeviceParseError(
                f"Invalid settings XML: {exception}, in the device: {self.conf.context}"
            ) from exception

        self._parse_initial_settings()

    @override
    async def execute_button_command(self, cmd_type: str) -> None:
        if "set_sensor" not in cmd_type:
            raise DeviceLogicError(
                f"Unsupported command: {cmd_type}, in the device: {self.conf.context}"
            )

        sensor_id = cmd_type.split("_")[2]
        await self._auto_detect_sensor(sensor_id)

    async def _auto_detect_sensor(self, sensor_id: str) -> None:
        """Send command to automatically detect the connected sensor."""
        result_id = str(int(sensor_id) + 3)
        payload = f'<root><set box="98" num01="{result_id}" /></root>'

        response = await self.api_client.write_command(
            payload, f"{self.name} ({self.location})", self.SAVE_ENDPOINT
        )

        if not response:
            return

        await self._check_auto_detect_sensor_response(response)

    async def _check_auto_detect_sensor_response(self, response: str) -> None:
        root = defused_ET.fromstring(response)

        result_tag = find_tag(root, "result")
        if result_tag is not None and result_tag.attrib.get("status") not in ("1", "4"):
            raise DeviceResponseError(
                f"{self.conf.context} returned an error while auto-detecting sensor, whole response: {response}"
            )

        for element in root.iter("set"):
            box_id = element.attrib.get("box")
            sns_type = element.attrib.get("type")

            if box_id and box_id.isdigit() and sns_type is not None:
                box_num = int(box_id)

                base = self.BOX_SENSOR_BASE

                if base is not None and base <= box_num <= base + 1:
                    s_id = str(box_num - base + 1)
                    self.conf.sensors_types[s_id] = sns_type

    async def _set_sensor_type(self, item_id: str, type_idx: str) -> None:
        """Set sensor type by sensor id and type index (exact number that will be send to Meteo)."""

        await self._update_settings()

        def format_val(val: str) -> str:
            return val.removesuffix(".0")

        if self.BOX_SENSOR_BASE is None:
            return

        box_num = int(item_id) - 1 + self.BOX_SENSOR_BASE
        target_box = None

        for element in self.settings_root.iter("set"):
            if element.attrib.get("box") == str(box_num):
                target_box = element
                break

        if target_box is None:
            raise DeviceParseError(
                f"Box {box_num} not found in settings, in the device: {self.conf.context}"
            )

        safe_defaults = {
            "name": f"Sensor {item_id}",
            "tunit": "0",
            "watch": "0",
            "watch2": "0",
            "watch3": "0",
            "min": "-40",
            "max": "125",
            "hyst": "0",
            "min2": "0",
            "max2": "100",
            "hyst2": "0",
            "min3": "-40",
            "max3": "125",
            "hyst3": "0",
        }

        payload_parts = [f'<set box="{box_num}"']

        for post_key, read_key in self.SENSOR_SETTINGS_KEYS:
            if read_key == "type":
                val = str(type_idx)
            else:
                raw_val = target_box.attrib.get(
                    read_key, safe_defaults.get(read_key, "0")
                )
                val = format_val(raw_val)

            payload_parts.append(f'{post_key}="{val}"')

        payload_parts.append("/>")

        xml_payload = f'<?xml version="1.0" encoding="iso-8859-2"?>\n<root>{" ".join(payload_parts)}</root>'

        await self._save_setting(xml_payload)

        self.conf.sensors_types[item_id] = str(type_idx)

    def _check_sensor_response(
        self, response_text: str, expected_status: str, action_msg: str
    ) -> None:
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

    async def _save_setting(self, xml_payload: str) -> None:
        resp_start = await self.api_client.write_command(
            '<root><set box="0" /></root>',
            f"{self.name} ({self.location})",
            self.SAVE_ENDPOINT,
        )

        self._check_sensor_response(
            resp_start,
            expected_status="1",
            action_msg="opening configuration transaction",
        )

        resp_data = await self.api_client.write_command(
            xml_payload, f"{self.name} ({self.location})", self.SAVE_ENDPOINT
        )

        self._check_sensor_response(
            resp_data, expected_status="1", action_msg="setting the type of the sensor"
        )

        resp_save = await self.api_client.write_command(
            '<root><set box="99" /></root>',
            f"{self.name} ({self.location})",
            self.SAVE_ENDPOINT,
        )
        self._check_sensor_response(
            resp_save,
            expected_status="2",
            action_msg="saving and restarting the device",
        )

    async def _set_input_type(self, item_id: str, type_idx: str) -> None:
        """Set the counter mode for a specific input."""

        await self._update_settings()

        try:
            real_input_id = str(int(item_id) - self.INPUT_ID_INCREMENT)
        except ValueError as err:
            raise DeviceLogicError(
                f"Invalid item_id format for input: {item_id}device: {self.conf.context}"
            ) from err

        input_item = self.conf.inputs.get(real_input_id)
        if not input_item:
            raise DeviceLogicError(
                f"Input with ID {real_input_id} not found in parsed data, "
                f"device: {self.conf.context}"
            )

        box_num = input_item.box_num

        if type_idx == "0":
            payload_content = (
                f'<set box="{box_num}" num01="0" str01="{input_item.name}" />'
            )
        else:
            payload_content = (
                f'<set box="{box_num}" '
                f'num01="{type_idx}" '
                f'num02="{input_item.decimal_count}" '
                f'str01="{input_item.name}" '
                f'str02="{input_item.trigger_impulse_count}" '
                f'str03="{input_item.value_to_add}" '
                f'str04="{input_item.unit}" />'
            )

        xml_payload = f'<?xml version="1.0" encoding="iso-8859-2"?>\n<root>{payload_content}</root>'

        await self._save_setting(xml_payload)

        input_item.type_cnt = type_idx

    @override
    async def set_number_value(
        self, category: str, _item_id: str, _value: float
    ) -> None:

        formatted_value = str(_value).removesuffix(".0")

        match category:
            case "decrease_counter":
                await self._send_command(
                    "m", item_id=_item_id, value=str(formatted_value)
                )
            case "set_counter":
                await self._send_command(
                    "n", item_id=_item_id, value=str(formatted_value)
                )
            case _:
                raise DeviceLogicError(
                    f"Unknown number category '{category}' requested for device: {self.conf.context}"
                )

    @override
    def get_select_option(self, category: str, item_id: str) -> str | None:
        if category == "sensor_type":
            sns_type = self.conf.sensors_types.get(item_id)
            if sns_type is not None and sns_type.isdigit():
                type_idx = int(sns_type)
                if 0 <= type_idx < len(self.SENSOR_TYPES):
                    return self.SENSOR_TYPES[type_idx]
            return None

        if category == "counter_mode":
            real_input_id = str(int(item_id) - self.INPUT_ID_INCREMENT)
            input_item = self.conf.inputs.get(real_input_id)
            if input_item and str(input_item.type_cnt).isdigit():
                mode_idx = int(input_item.type_cnt)
                if 0 <= mode_idx < len(self.COUNTER_MODES):
                    return self.COUNTER_MODES[mode_idx]
            return None

        raise DeviceLogicError(
            f"Unknown select category '{category}' requested for device: {self.conf.context}"
        )

    @override
    async def set_select_option(self, category: str, item_id: str, option: str) -> None:
        if category == "sensor_type":
            try:
                type_idx = str(self.SENSOR_TYPES.index(option))
            except ValueError:
                return

            await self._set_sensor_type(item_id, type_idx)
            return

        if category == "counter_mode":
            try:
                type_idx = str(self.COUNTER_MODES.index(option))
            except ValueError:
                return

            await self._set_input_type(item_id, type_idx)
            return

        raise DeviceLogicError(
            f"Unknown select category '{category}' requested for device: {self.conf.context}"
        )

    @override
    async def switch_to_web_mode(self) -> None:
        """Unused in Papago."""
        raise DeviceLogicError("Calling not implemented method.")

    @override
    def _parse_initial_settings(self) -> None:
        """Base method for other devices to parse their settings."""
        for element in self.settings_root.iter():
            if element.tag != "set":
                continue

            box_id = element.attrib.get("box")
            if not box_id or not box_id.isdigit():
                continue

            self._process_box(int(box_id), element)

    @abstractmethod
    def _process_box(self, box_num: int, element: ET.Element) -> None:
        """Should be overridden in children to process specific boxes."""

    def _parse_standard_input(
        self, box_num: int, element: ET.Element, input_base: int
    ) -> None:
        """Helper for parsing standard digital inputs and counters."""

        counter_id = str(box_num - input_base + 1)
        name = element.attrib.get("name", f"Input {counter_id}")
        unit = element.attrib.get("unit", "")
        dec = element.attrib.get("dec", "0")
        trigger_impulse_count = element.attrib.get("src", "1")
        value_to_add = element.attrib.get("dst", "1")
        type_cnt = element.attrib.get("enb", "0")

        self.conf.inputs[counter_id] = InputSettings(
            name,
            unit,
            dec,
            trigger_impulse_count,
            value_to_add,
            type_cnt,
            box_num,
        )

    def _parse_standard_sensor_setting(
        self, box_num: int, element: ET.Element, sensor_base: int
    ) -> None:
        """Helper for parsing standard sensor ports from settings.xml."""
        sensor_id = str(box_num - sensor_base + 1)
        sns_type = element.attrib.get("type", "0")
        sensor_name = element.attrib.get("name", f"Sensor {sensor_id}")

        self.conf.sensors_types[sensor_id] = sns_type

        if sensor_id not in self.conf.sensors:
            self.conf.sensors[sensor_id] = {
                "name": sensor_name,
                "sub_sensors": {},
            }
        else:
            self.conf.sensors[sensor_id]["name"] = sensor_name


class PapagoETH_2TH(PapagoETH):
    """Represents Papago 2TH ETH."""

    BOX_SENSOR_BASE = 30

    SENSOR_SETTINGS_KEYS: ClassVar[list[tuple[str, str]]] = [
        ("num01", "type"),
        ("num02", "watch"),
        ("num03", "watch2"),
        ("num04", "watch3"),
        ("str00", "name"),
        ("str01", "min"),
        ("str02", "max"),
        ("str03", "hyst"),
        ("str04", "min2"),
        ("str05", "max2"),
        ("str06", "hyst2"),
        ("str07", "min3"),
        ("str08", "max3"),
        ("str09", "hyst3"),
    ]

    @override
    def _process_box(self, box_num: int, element: ET.Element) -> None:
        if self.BOX_SENSOR_BASE <= box_num <= self.BOX_SENSOR_BASE + 1:
            self._parse_standard_sensor_setting(box_num, element, self.BOX_SENSOR_BASE)


class PapagoETH_1TH_2DI_1DO(PapagoETH):
    """Represents Papago 1TH 2DI 1DO ETH."""

    BOX_OUTPUT_BASE = 30
    BOX_INPUT_BASE = 31
    BOX_SENSOR_BASE = 40

    SENSOR_SETTINGS_KEYS: ClassVar[list[tuple[str, str]]] = [
        ("num00", "tunit"),
        ("num01", "type"),
        ("num02", "watch"),
        ("num03", "watch2"),
        ("num04", "watch3"),
        ("str01", "min"),
        ("str02", "max"),
        ("str03", "hyst"),
        ("str04", "min2"),
        ("str05", "max2"),
        ("str06", "hyst2"),
        ("str07", "min3"),
        ("str08", "max3"),
        ("str09", "hyst3"),
    ]

    @override
    def _process_box(self, box_num: int, element: ET.Element) -> None:
        match box_num:
            case self.BOX_SENSOR_BASE:
                self._parse_standard_sensor_setting(
                    box_num, element, self.BOX_SENSOR_BASE
                )

            case self.BOX_OUTPUT_BASE:
                self.conf.outputs["1"] = OutputSettings("")

            case x if self.BOX_INPUT_BASE <= x < self.BOX_SENSOR_BASE:
                self._parse_standard_input(box_num, element, self.BOX_INPUT_BASE)


class PapagoETH_5HDI_1DO(PapagoETH):
    """Represents Papago 5HDI 1DO ETH."""

    BOX_OUTPUT_BASE = 30
    BOX_INPUT_BASE = 31

    @override
    def _process_box(self, box_num: int, element: ET.Element) -> None:
        match box_num:
            case self.BOX_OUTPUT_BASE:
                self.conf.outputs["1"] = OutputSettings("")

            case x if self.BOX_INPUT_BASE <= x < self.BOX_INPUT_BASE + 1000:
                self._parse_standard_input(box_num, element, self.BOX_INPUT_BASE)


class PapagoETH_METEO(PapagoETH):
    """Represents Papago Meteo ETH."""

    BOX_SENSOR_BASE = 30

    SENSOR_SETTINGS_KEYS: ClassVar[list[tuple[str, str]]] = [
        ("num01", "type"),
        ("num02", "watch"),
        ("num03", "watch2"),
        ("num04", "watch3"),
        ("str00", "name"),
        ("str01", "min"),
        ("str02", "max"),
        ("str03", "hyst"),
        ("str04", "min2"),
        ("str05", "max2"),
        ("str06", "hyst2"),
        ("str07", "min3"),
        ("str08", "max3"),
        ("str09", "hyst3"),
    ]

    SENSOR_TYPES_AB: ClassVar[dict] = {
        "0": "unused",
        "2": "temperature_ds",
        "3": "temperature_humidity_th3x",
        "4": "temperature_tmp",
        "5": "co2_concentration_t6713",
        "7": "atmospheric_pressure",
        "9": "co2_concentration_sd4x",
        "10": "rain_gauge",
    }

    SENSOR_TYPES_C: ClassVar[dict] = {
        "0": "unused",
        "6": "davis",
    }

    @override
    def _process_box(self, box_num: int, element: ET.Element) -> None:
        if self.BOX_SENSOR_BASE <= box_num <= self.BOX_SENSOR_BASE + 2:
            self._parse_standard_sensor_setting(box_num, element, self.BOX_SENSOR_BASE)

    @override
    def get_supported_buttons(self) -> list[dict[str, Any]]:
        buttons = []
        for item_id in self.conf.sensors_types:
            if item_id == "3":
                continue
            sensor_name = self.conf.sensors.get(item_id, {}).get(
                "name", f"Sensor {item_id}"
            )
            buttons.append({
                "cmd": f"set_sensor_{item_id}",
                "name": sensor_name,
            })
        return buttons

    @override
    def get_supported_selects(self) -> list[dict[str, Any]]:
        selects = []
        for item_id in self.conf.sensors_types:
            sensor_name = self.conf.sensors.get(item_id, {}).get(
                "name", f"Sensor {item_id}"
            )
            options_dict = (
                self.SENSOR_TYPES_C if item_id == "3" else self.SENSOR_TYPES_AB
            )
            selects.append({
                "item_id": item_id,
                "category": "sensor_type_meteo_c"
                if item_id == "3"
                else "sensor_type_meteo_ab",
                "name": sensor_name,
                "options": list(options_dict.values()),
            })
        return selects

    @override
    def get_select_option(self, category: str, item_id: str) -> str | None:
        if category in ("sensor_type", "sensor_type_meteo_ab", "sensor_type_meteo_c"):
            sns_type_code = self.conf.sensors_types.get(item_id)
            if sns_type_code is not None:
                options_dict = (
                    self.SENSOR_TYPES_C if item_id == "3" else self.SENSOR_TYPES_AB
                )
                return options_dict.get(sns_type_code)
        return None

    @override
    async def set_select_option(self, category: str, item_id: str, option: str) -> None:
        if category in ("sensor_type", "sensor_type_meteo_ab", "sensor_type_meteo_c"):
            options_dict = (
                self.SENSOR_TYPES_C if item_id == "3" else self.SENSOR_TYPES_AB
            )

            type_idx = None
            for code, text in options_dict.items():
                if text == option:
                    type_idx = code
                    break

            if type_idx is not None:
                await self._set_sensor_type(item_id, type_idx)


async def async_setup_network_papago(client: PapouchHTTPClient) -> PapagoETH | None:
    """Async factory for Papago devices."""
    settings = await client.fetch_settings()
    info = await client.fetch_info()

    root_info = defused_ET.fromstring(info)
    heartbeat_tag = find_tag(root_info, "heartbeat")

    if heartbeat_tag is None:
        raise DeviceParseError("This Papago doesn't have heartbeat tag.")

    device_name = heartbeat_tag.attrib.get("device")
    location = heartbeat_tag.attrib.get("location", "NONAME")

    if device_name == "Papago 2TH ETH":
        return PapagoETH_2TH(client, settings, device_name, location)
    if device_name == "Papago 1TH 2DI 1DO ETH":
        return PapagoETH_1TH_2DI_1DO(client, settings, device_name, location)
    if device_name == "Papago 5HDI 1DO ETH":
        return PapagoETH_5HDI_1DO(client, settings, device_name, location)
    if device_name == "Papago METEO ETH":
        return PapagoETH_METEO(client, settings, device_name, location)

    _LOGGER.warning("Unsupported Papago: %s, location: %s", device_name, location)
    return None
