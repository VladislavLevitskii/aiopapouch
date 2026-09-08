"""This file contains definition of the QuidoETH device."""

import logging
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, cast, override

import defusedxml.ElementTree as defused_ET

from pap_spinel import ACK_FAILURE

from ..client import PapouchHTTPClient, PapouchSerialClient
from ..exceptions import DeviceLogicError, DeviceParseError
from .base import HTTPMixin, PapouchDevice, find_tag

_LOGGER = logging.getLogger(__name__)


@dataclass
class QuidoConfiguration:
    """Configuration of the Quido"""

    number_inputs: int = -1
    number_outputs: int = -1
    number_temp: int = 1
    counter_states: dict[str, str] = field(default_factory=dict)
    temperature_unit: str = "°C"
    size_counter_bits: int = 16
    name: str = ""
    location: str = ""
    identifier: str = ""


class QuidoBase(PapouchDevice, ABC):
    """Base class for all Quido devices containing shared entity logic."""

    def __init__(self) -> None:
        """Constructor for the base of the Quido."""

        self.api_client: PapouchHTTPClient

        # That variable should be populated by the subclasses:

        self.conf = QuidoConfiguration()

    # These methods are the same for every Quido device:

    @override
    @property
    def name(self) -> str:
        """Return device's name."""
        return self.conf.name

    @override
    @property
    def location(self) -> str:
        """Return device's location."""
        return self.conf.location

    @override
    @property
    def manufacturer(self) -> str:
        """Return device's manufacturer."""
        return "Papouch s.r.o."

    @override
    @property
    def identifier(self) -> str:
        """Return device's identifier."""
        return self.conf.identifier

    @override
    def get_supported_buttons(self) -> list[dict[str, Any]]:
        return [
            {"cmd": "connect_all_coils", "name": None},
            {"cmd": "disconnect_all_coils", "name": None},
            {"cmd": "reset_all_counters", "name": None},
        ]

    @override
    def get_supported_binary_sensors(self) -> list[dict[str, Any]]:
        return [
            {
                "item_id": str(i),
                "type": "input",
                "name": str(i),
            }
            for i in range(1, self.conf.number_inputs + 1)
        ]

    @override
    def get_supported_numbers(self) -> list[dict[str, Any]]:
        result = [
            {
                "item_id": str(i),
                "category": "decrease_counter",
                "name": str(i),
                "min_value": 0,
                "max_value": (2**self.conf.size_counter_bits) - 1,
                "step": 1,
            }
            for i in range(1, self.conf.number_inputs + 1)
        ]
        result.extend(
            {
                "item_id": str(i),
                "category": f"output_{action}_duration",
                "name": str(i),
                "min_value": 0.5,
                "max_value": 127.5,
                "step": 0.5,
            }
            for i in range(1, self.conf.number_outputs + 1)
            for action in ("on", "off")
        )
        return result

    @override
    def get_supported_sensors(self) -> list[dict[str, Any]]:
        sensors: list[dict[str, Any]] = [
            {
                "item_id": str(i),
                "value_key": self._generate_semantic_key(
                    self.TEMPERATURE_SNS_TYPE, str(i)
                ),
                "type": "temperature",
                "data_type": "temperature",
                "name": None,
                "unit": self.conf.temperature_unit,
            }
            for i in range(1, self.conf.number_temp + 1)
        ]

        sensors.extend([
            {
                "item_id": str(i),
                "value_key": self._generate_semantic_key(self.PULSES, str(i)),
                "type": "counter",
                "data_type": "counter",
                "name": str(i),
                "unit": "pulses",
            }
            for i in range(1, self.conf.number_inputs + 1)
        ])

        return sensors

    @override
    def get_supported_switches(self) -> list[dict[str, Any]]:
        return [
            {
                "item_id": str(i),
                "name": str(i),
            }
            for i in range(1, self.conf.number_outputs + 1)
        ]

    @override
    def get_supported_selects(self) -> list[dict[str, Any]]:
        return [
            {
                "item_id": str(i),
                "category": "counter_mode",
                "name": str(i),
                "options": self.COUNTER_MODES,
            }
            for i in range(1, self.conf.number_inputs + 1)
        ]

    @override
    async def execute_button_command(self, cmd_type: str) -> None:
        """Route the button press to the correct method."""
        match cmd_type:
            case "connect_all_coils":
                await self._connect_all_coils()
            case "disconnect_all_coils":
                await self._disconnect_all_coils()
            case "reset_all_counters":
                await self._reset_all_counters()
            case _:
                raise DeviceLogicError(
                    f"Unsupported command: {cmd_type}, in the device: {self.name} ({self.location})"
                )

    @override
    async def turn_on_switch(self, item_id: str) -> None:
        """Turn on the switch by its id."""
        await self._turn_on_coil(item_id)

    @override
    async def turn_off_switch(self, item_id: str) -> None:
        """Turn off the switch by its id."""
        await self._turn_off_coil(item_id)

    # These are the methods all of the children should implement

    @abstractmethod
    async def _connect_all_coils(self) -> None:
        pass

    @abstractmethod
    async def _disconnect_all_coils(self) -> None:
        pass

    @abstractmethod
    async def _reset_all_counters(self) -> None:
        pass

    @abstractmethod
    async def _turn_on_coil(self, item_id: str) -> None:
        pass

    @abstractmethod
    async def _turn_off_coil(self, item_id: str) -> None:
        pass

    @abstractmethod
    async def _decrease_value_counter(self, item_id: str, value: int) -> None:
        pass


class QuidoETH(QuidoBase, HTTPMixin):
    """Represents devices of Quido family."""

    api_client: PapouchHTTPClient

    def __init__(self, api_client: PapouchHTTPClient, settings: str, info: str) -> None:
        """Constructor for Quido device."""

        super().__init__()
        self.api_client = cast(PapouchHTTPClient, api_client)

        self.info_root = defused_ET.fromstring(info)
        self.settings_root = defused_ET.fromstring(settings)

        name = self.get_name()
        location = self.get_location()
        mac_address = self.get_identifier()

        self.conf = QuidoConfiguration(
            name=name, location=location, identifier=mac_address
        )

        self._parse_initial_settings()

    @override
    @property
    def context(self) -> str:
        return f"{self.name} ({self.location}) - {self.api_client.ip_address}"

    @override
    async def parse_fresh_data(self, xml_data: str) -> dict:
        """Defines parser method for QuidoETH."""
        root = defused_ET.fromstring(xml_data)
        parsed_data: dict[str, dict[str, Any]] = {
            "temperature": {},
            "input": {},
            "switch": {},
            "counter": {},
        }

        for element in root:
            item_id = element.attrib.get("id")

            match element.tag:
                case "temp":
                    semantic_key = self._generate_semantic_key(
                        self.TEMPERATURE_SNS_TYPE, item_id
                    )
                    val_str = element.attrib.get("val", "0")
                    if val_str == "":
                        val_str = 0
                    parsed_data["temperature"][semantic_key] = float(val_str)

                case "dout":  # codespell:ignore dout
                    val_str = element.attrib.get("val", "0")
                    parsed_data["switch"][item_id] = int(val_str)

                case "din":
                    parsed_data["input"][item_id] = int(element.attrib.get("val", "0"))
                    semantic_key = self._generate_semantic_key(self.PULSES, item_id)
                    parsed_data["counter"][semantic_key] = int(
                        element.attrib.get("cnt", "0")
                    )

        return parsed_data

    @override
    async def set_number_value(self, category: str, item_id: str, value: float) -> None:
        match category:
            case "decrease_counter":
                await self._decrease_value_counter(item_id, int(value))
            case "output_on_duration" | "output_off_duration":
                time_units = max(1, min(255, int(value * 2)))
                await self._send_command(
                    "s" if category == "output_on_duration" else "r",
                    item_id=item_id,
                    time=str(time_units),
                )
            case _:
                raise DeviceLogicError(
                    f"Unknown number category '{category}' requested for device: {self.context}"
                )

    @override
    def get_select_option(self, category: str, item_id: str) -> str | None:
        """Return selected option by its id."""
        if category == "counter_mode":
            return self._get_counter_mode(item_id)
        else:
            raise DeviceLogicError(
                f"Unknown select category '{category}' requested for device: {self.context}"
            )

    @override
    async def set_select_option(self, category: str, item_id: str, option: str) -> None:
        """Set selected option by its id."""
        if category == "counter_mode":
            await self._set_counter_mode(item_id, option)
        else:
            raise DeviceLogicError(
                f"Unknown select category '{category}' requested for device: {self.context}"
            )

    @override
    async def switch_to_web_mode(self) -> None:
        """Switch the device network mode to WEB using its current settings."""
        box = self.settings_root.find(".//set[@box='1']")
        if box is None:
            raise DeviceParseError(
                f"Box for network mode is not found, in the device: {self.context}"
            )

        def pad_ip(ip_str: str) -> str:
            return ".".join(part.zfill(3) for part in ip_str.split("."))

        save_root = ET.Element("root")
        ET.SubElement(
            save_root,
            "set",
            box="1",
            ip1=pad_ip(box.get("ip", "0.0.0.0")),
            ip2=pad_ip(box.get("mask", "0.0.0.0")),
            ip3=pad_ip(box.get("gate", "0.0.0.0")),
            ip4=pad_ip(box.get("dip", "0.0.0.0")),
            ip5=pad_ip(box.get("rip", "0.0.0.0")),
            num1=box.get("wport", "80").zfill(5),
            num2=box.get("lport", "10001").zfill(5),
            num3="3",
            num4=box.get("rport", "0").zfill(5),
            num5=box.get("mport", "502").zfill(5),
            num6=box.get("dhcp", "0"),
            num7=box.get("single", "0"),
            num8=box.get("tcpto", "0").zfill(5),
        )

        xml_payload = ET.tostring(save_root, encoding="unicode")
        response = await self.api_client.write_command(
            xml_payload, f"{self.name} ({self.location})"
        )
        self._check_response(response, xml_payload)

    @override
    async def _connect_all_coils(self) -> None:
        """Command for connecting all the coils."""
        await self._send_command("S")

    @override
    async def _disconnect_all_coils(self) -> None:
        """Command for disconnecting all the coils."""
        await self._send_command("R")

    @override
    async def _reset_all_counters(self) -> None:
        """Command for resetting all the counters."""
        await self._send_command("C")

    @override
    async def _decrease_value_counter(self, item_id: str, value: int) -> None:
        """Command for decreasing specific counter."""
        await self._send_command("c", item_id, str(value))

    def _get_counter_mode(self, item_id: str) -> str:
        """Get the current mode of the counter."""
        result = self.conf.counter_states.get(item_id, self.COUNTER_MODES[0])
        return str(result)

    async def _set_counter_mode(self, item_id: str, mode: str) -> None:
        """Set the new mode of the counter."""
        current_settings = await self.api_client.fetch_settings()

        root = defused_ET.fromstring(current_settings)

        item = root.find(f".//set[@box='10']/item[@id='{item_id}']")
        if item is None:
            raise DeviceParseError(
                f"Item {item_id} not found in settings in the device: {self.context}"
            )

        try:
            mode_index = self.COUNTER_MODES.index(mode)
        except ValueError as err:
            raise DeviceLogicError(
                f"Invalid counter mode: {mode}, in the device: {self.context}"
            ) from err

        on_val = item.get("on", "0")
        off_val = item.get("off", "0")
        hide_val = item.get("hide", "0")
        change_val = item.get("change", "0")

        sampl_val = item.get("sampl", "20").zfill(5)
        name_val = item.get("name", "")

        save_root = ET.Element("root")
        ET.SubElement(
            save_root,
            "set",
            box="10",
            num1=str(item_id),
            num2=on_val,
            num3=off_val,
            num4=str(mode_index),
            num5=hide_val,
            num6=change_val,
            num7=sampl_val,
            str1=name_val,
        )

        xml_payload = ET.tostring(save_root, encoding="unicode")

        response = await self.api_client.write_command(
            xml_payload, f"{self.name} ({self.location})"
        )
        self._check_response(response, xml_payload)

        self.conf.counter_states[item_id] = mode

    @override
    def _parse_initial_settings(self) -> None:
        """Parse the initial settings XML to configure device properties.

        This method counts the total number of hardware inputs and outputs,
        initializes the states for all counter modes, and determines the
        global temperature unit used by the device.
        """

        if self.settings_root is None:
            return

        try:
            input_items = self.settings_root.findall(".//set[@box='10']/item")
            output_items = self.settings_root.findall(".//set[@box='11']/item")

            self.conf.number_inputs = len(input_items)
            self.conf.number_outputs = len(output_items)

            for item in input_items:
                if (item_id := item.get("id")) is None:
                    continue

                mode_index_str = item.get("cnt", "0")

                try:
                    mode_index = int(mode_index_str)
                    if 0 <= mode_index < len(self.COUNTER_MODES):
                        self.conf.counter_states[item_id] = self.COUNTER_MODES[
                            mode_index
                        ]
                except ValueError as err:
                    raise DeviceLogicError(
                        f"Invalid mode index for item {item_id}: {mode_index_str}, in the device: {self.context}"
                    ) from err

            box_elem = self.settings_root.find(".//set[@box='8']")
            if box_elem is not None:
                unit = box_elem.get("units")
                match unit:
                    case "C":
                        self.temperature_unit = "°C"
                    case "F":
                        self.temperature_unit = "°F"
                    case _:
                        self.temperature_unit = "K"

        except (defused_ET.ParseError, ValueError, TypeError) as err:
            raise DeviceParseError(
                f"Failed to parse initial settings: {err}, in the device: {self.context}"
            ) from err

    @override
    def get_location(self) -> str:
        """Return the location of the device."""
        heartbeat = find_tag(self.info_root, "heartbeat")
        if heartbeat is not None:
            return heartbeat.attrib.get("location", "")
        return ""

    @override
    def get_name(self) -> str:
        """Return the name of the device."""
        heartbeat = find_tag(self.info_root, "heartbeat")
        if heartbeat is not None:
            return heartbeat.attrib.get("device", "")
        return ""

    @override
    def get_identifier(self) -> str:
        """Return the identifier of the device."""
        box = self.settings_root.find(".//set[@box='12']")
        if box is not None:
            return str(box.attrib.get("mac", ""))

        raise DeviceParseError(
            f"The device doesn't have box 12 with MAC address, device: {self.context}"
        )

    @override
    async def _turn_on_coil(self, item_id: str) -> None:
        """Command for turning on the coil by its id."""
        await self._send_command("s", item_id)

    @override
    async def _turn_off_coil(self, item_id: str) -> None:
        """Command for turning off the coil by its id."""
        await self._send_command("r", item_id)


class QuidoRS485(QuidoBase):
    """Represents serial Quido."""

    api_client: PapouchSerialClient

    def __init__(
        self,
        api_client: PapouchSerialClient,
        address: int,
        configuration: QuidoConfiguration,
    ) -> None:
        """Constructor for Quido device."""

        super().__init__()
        self.api_client = api_client
        self.conf = configuration

        self.address = address

    @override
    def get_location(self) -> str:
        return self.conf.location

    @override
    def get_name(self) -> str:
        return self.conf.name

    @override
    def get_identifier(self) -> str:
        return self.conf.identifier

    @override
    @property
    def context(self) -> str:
        return f"{self.conf.name} - SN: {self.conf.identifier}"

    async def _get_state_coils(self) -> dict:
        result_pkt = await self.api_client.write_command(
            self.address, 0x30, self.context
        )
        result_int = int.from_bytes(result_pkt.data)

        result: dict = {}

        for i in range(1, self.conf.number_outputs + 1):
            result[str(i)] = result_int & 1
            result_int >>= 1

        return result

    async def _get_inputs(self) -> dict:
        result_pkt = await self.api_client.write_command(
            self.address, 0x31, self.context
        )
        result_int = int.from_bytes(result_pkt.data)

        result: dict = {}

        for i in range(1, self.conf.number_inputs + 1):
            result[str(i)] = result_int & 1
            result_int >>= 1

        return result

    async def _get_temp(self) -> float | None:
        result_pkt = await self.api_client.write_command(
            self.address, 0x51, self.context, b"\x01"
        )

        # for some reason if there is no temp sensor it returns ACK 5
        if result_pkt.ack_code() == ACK_FAILURE:
            return None

        data_part = result_pkt.data[1:]

        result = int.from_bytes(data_part, signed=True)
        return result / 10

    async def _get_counters(self) -> dict:
        result: dict = {}

        result_pkt = await self.api_client.write_command(
            self.address, 0x60, self.context, b"\x00"
        )

        bits = result_pkt.data[0]
        bytes_per_counter = bits // 8
        result_data_bytes = result_pkt.data[1:]

        for i in range(1, self.conf.number_inputs + 1):
            start = (i - 1) * bytes_per_counter
            end = start + bytes_per_counter
            counter_bytes = result_data_bytes[start:end]
            semantic_key = self._generate_semantic_key(self.PULSES, str(i))
            result[semantic_key] = int.from_bytes(counter_bytes)

        return result

    @override
    async def parse_fresh_data(self, xml_data: str) -> dict:
        parsed_data: dict[str, dict[str, Any]] = {
            "temperature": {},
            "input": {},
            "switch": {},
            "counter": {},
        }

        parsed_data["switch"] = await self._get_state_coils()
        parsed_data["input"] = await self._get_inputs()
        parsed_data["counter"] = await self._get_counters()

        semantic_key = self._generate_semantic_key(self.TEMPERATURE_SNS_TYPE, "1")
        parsed_data["temperature"][semantic_key] = await self._get_temp()

        return parsed_data

    def _get_counter_mode(self, item_id: str) -> str:
        result = self.conf.counter_states.get(item_id, self.COUNTER_MODES[0])
        return str(result)

    async def _set_counter_mode(self, item_id: str, mode: str) -> None:
        mode_index = self.COUNTER_MODES.index(mode)

        result_int = mode_index << 6
        result_int |= int(item_id)

        payload = result_int.to_bytes(1)

        await self.api_client.write_command(self.address, 0x6A, self.context, payload)
        self.conf.counter_states[item_id] = mode

    @override
    def get_select_option(self, category: str, item_id: str) -> str | None:
        """Return selected option by its id."""
        if category == "counter_mode":
            return self._get_counter_mode(item_id)
        raise DeviceLogicError(
            f"Unknown select category '{category}' requested for device: {self.context}"
        )

    @override
    async def set_select_option(self, category: str, item_id: str, option: str) -> None:
        if category == "counter_mode":
            await self._set_counter_mode(item_id, option)
        else:
            raise DeviceLogicError(
                f"Unknown select category '{category}' requested for device: {self.context}"
            )

    @override
    async def _decrease_value_counter(self, item_id: str, value: int) -> None:
        payload = int(item_id).to_bytes(1) + value.to_bytes(2)
        response = await self.api_client.write_command(
            self.address, 0x61, self.context, payload
        )

        ack_code = response.ack_code()

        if ack_code and ack_code != 0:
            _LOGGER.error(
                "Error during decreasing counter, in the device: %s, probably you are subtracting more then counter has.",
                self.context,
            )
            raise DeviceLogicError(
                f"Error during decreasing counter, in the device: {self.context}"
            )

    @override
    async def set_number_value(self, category: str, item_id: str, value: float) -> None:
        match category:
            case "decrease_counter":
                await self._decrease_value_counter(item_id, int(value))
            case "output_on_duration" | "output_off_duration":
                time_units = max(1, min(255, int(value * 2)))
                output_num = int(item_id)

                set_byte = (
                    (1 << 7 | output_num)
                    if category == "output_on_duration"
                    else output_num
                )
                payload = time_units.to_bytes(1) + set_byte.to_bytes(1)

                await self.api_client.write_command(
                    self.address, 0x23, self.context, payload
                )

            case _:
                raise DeviceLogicError(
                    f"Unknown number category '{category}' requested for device: {self.context}"
                )

    @override
    async def switch_to_web_mode(self) -> None:
        """Unused in QuidoRS485."""

    @override
    async def _connect_all_coils(self) -> None:
        state_coils = await self._get_state_coils()
        for coil_id, coil_value in state_coils.items():
            if coil_value == 0:
                await self.turn_on_switch(coil_id)

    @override
    async def _disconnect_all_coils(self) -> None:
        state_coils = await self._get_state_coils()
        for coil_id, coil_value in state_coils.items():
            if coil_value == 1:
                await self.turn_off_switch(coil_id)

    @override
    async def _reset_all_counters(self) -> None:
        counters = await self._get_counters()

        pairs = []
        for i in range(1, self.conf.number_inputs + 1):
            semantic_key = self._generate_semantic_key(self.PULSES, str(i))
            val = counters.get(semantic_key, 0)
            if val > 0:
                pairs.append((i, val))

        for j in range(0, len(pairs), 12):
            chunk = pairs[j : j + 12]
            payload = bytearray()

            for counter_num, val in chunk:
                payload.append(counter_num)
                payload.extend(val.to_bytes(2, "big"))

            if payload:
                await self.api_client.write_command(
                    self.address, 0x61, self.context, bytes(payload)
                )

    @override
    async def _turn_on_coil(self, item_id: str) -> None:
        output_num = int(item_id)
        payload = (0x80 | output_num).to_bytes(1)
        await self.api_client.write_command(self.address, 0x20, self.context, payload)

    @override
    async def _turn_off_coil(self, item_id: str) -> None:
        output_num = int(item_id)
        payload = output_num.to_bytes(1, "big")
        await self.api_client.write_command(self.address, 0x20, self.context, payload)

    @override
    def _parse_initial_settings(self) -> None:
        """Unused."""

    @staticmethod
    async def get_number_io(
        client: PapouchSerialClient, address: int, context: str
    ) -> tuple[int, int]:
        """Resolving number of inputs and outputs."""
        pkt = await client.write_command(address, 0xF3, context, b"\x01")
        number_outputs = pkt.data[0]
        number_inputs = pkt.data[1]
        return number_outputs, number_inputs

    @staticmethod
    async def get_modes_counters(
        api_client: PapouchSerialClient,
        address: int,
        conf: QuidoConfiguration,
        context: str,
    ) -> None:
        """Assignes proper mode of the counters in the configuration."""

        result_pkt = await api_client.write_command(address, 0x6B, context, b"\x00")

        result_data_bytes = result_pkt.data

        for i in range(1, conf.number_inputs + 1):
            counter_mode_int_data = result_data_bytes[i - 1]

            # here we need only 2 first bits
            mode = counter_mode_int_data >> 6
            conf.counter_states[str(i)] = QuidoBase.COUNTER_MODES[mode]


async def async_setup_network_quido(client: PapouchHTTPClient) -> QuidoBase | None:
    """Async factory for network Quido."""
    settings = await client.fetch_settings()
    info = await client.fetch_info()
    return QuidoETH(client, settings, info)


async def async_setup_serial_quido(
    client: PapouchSerialClient,
    address: int,
    serial_number: str,
    device_name: str,
    location: str,
) -> QuidoBase | None:
    """Async factory for serial Quido."""

    temp_context = f"{device_name} - SN: {serial_number}"

    number_outputs, number_inputs = await QuidoRS485.get_number_io(
        client, address, temp_context
    )

    configuration = QuidoConfiguration(
        number_inputs=number_inputs,
        number_outputs=number_outputs,
        location=location,
        name=device_name,
        identifier=serial_number,
    )

    await QuidoRS485.get_modes_counters(client, address, configuration, temp_context)

    return QuidoRS485(client, address, configuration)
