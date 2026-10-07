# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for base device methods."""

from unittest.mock import AsyncMock, patch

import pytest
from aiopapouch.devices.base import (
    ERROR_STATUS,
    PapouchDevice,
    PapouchNetworkDevice,
    PapouchSerialDevice,
)
from aiopapouch.exceptions import (
    DeviceConnectionError,
    DeviceLogicError,
    DeviceParseError,
    DeviceResponseError,
)


class DummyConf:
    """Dummy configuration for testing."""

    context = "Dummy Context"
    address = 1


class DummyAbstractMixin(PapouchDevice):
    """Mixin to satisfy all PapouchDevice abstract methods."""

    async def get_fresh_data(self):
        return {}

    def get_supported_buttons(self):
        return []

    def get_supported_binary_sensors(self):
        return []

    def get_supported_numbers(self):
        return []

    def get_supported_sensors(self):
        return []

    def get_supported_switches(self):
        return []

    def get_supported_selects(self):
        return []

    async def execute_button_command(self, cmd_type):
        pass

    async def turn_on_switch(self, item_id):
        pass

    async def turn_off_switch(self, item_id):
        pass

    async def set_number_value(self, category, item_id, value):
        pass

    def get_select_option(self, category, item_id):
        return None

    async def set_select_option(self, category, item_id, option):
        pass

    async def switch_to_web_mode(self):
        pass


class DummyNetworkDevice(DummyAbstractMixin, PapouchNetworkDevice):
    """Mock network device that inherits from base.py."""

    def __init__(self, api_client):
        self.api_client = api_client
        self._conf = DummyConf()

    @property
    def conf(self):
        return self._conf


class DummySerialDevice(DummyAbstractMixin, PapouchSerialDevice):
    """Mock serial device that inherits from base.py."""

    def __init__(self, api_client):
        self.api_client = api_client
        self._conf = DummyConf()

    @property
    def conf(self):
        return self._conf


class MockSerialResponse:
    """Mock packet response for serial communication."""

    def __init__(self, ack):
        self._ack = ack

    def ack_code(self):
        """Mock acknowledgement code."""
        return self._ack


@pytest.fixture
def net_device():
    """Fixture providing a dummy network device with mocked client."""
    client = AsyncMock()

    device = DummyNetworkDevice(client)
    return device


@pytest.fixture
def serial_device():
    """Fixture providing a dummy serial device with mocked client."""
    client = AsyncMock()
    return DummySerialDevice(client)


@pytest.mark.asyncio
async def test_send_command_filters_none_values(net_device):
    """Test that _send_command removes None values before sending."""
    net_device.api_client.read_command.return_value = (
        '<root><result status="1" /></root>'
    )

    await net_device._send_command(cmd_type="s", item_id="1", value=None)

    expected_params = {"type": "s", "id": "1"}
    net_device.api_client.read_command.assert_called_once_with(
        expected_params, "Dummy Context"
    )


@pytest.mark.asyncio
async def test_send_command_calls_check_response(net_device):
    """Test that _send_command automatically verifies the response."""

    net_device.api_client.read_command.return_value = (
        f'<root><result status="{ERROR_STATUS}" /></root>'
    )

    with pytest.raises(DeviceResponseError):
        await net_device._send_command("r")


def test_check_response_success(net_device):
    """Test that _check_response passes silently on successful status."""
    response_xml = '<root><result status="1" /></root>'
    net_device._check_response(response_xml, "Request")


def test_check_response_error_status(net_device):
    """Test that DeviceResponseError is raised when status matches ERROR_STATUS."""
    response_xml = f'<root><result status="{ERROR_STATUS}" /></root>'

    with pytest.raises(DeviceResponseError):
        net_device._check_response(response_xml, "Request")


def test_check_response_missing_result_tag(net_device):
    """Test that DeviceResponseError is raised when result tag is completely missing."""
    response_xml = "<root><other_tag/></root>"

    with pytest.raises(DeviceResponseError):
        net_device._check_response(response_xml, "Request")


def test_check_response_invalid_xml(net_device):
    """Test that DeviceParseError is raised when response XML is invalid (ParseError)."""
    response_xml = "NOT_XML_DATA"

    with pytest.raises(DeviceParseError):
        net_device._check_response(response_xml, "Request")


def test_base_get_unit_error(net_device):
    """Test inherited _get_unit raises DeviceLogicError on missing dictionary keys."""
    with pytest.raises(DeviceLogicError):
        net_device._get_unit("nonexistent_sns_type", "0")

    with pytest.raises(DeviceLogicError):
        net_device._get_unit("1", "nonexistent_code")


def test_base_generate_semantic_key_error(net_device):
    """Test inherited _generate_semantic_key raises DeviceLogicError on missing type."""
    with pytest.raises(DeviceLogicError):
        net_device._generate_semantic_key("nonexistent_type", "1")


@pytest.mark.asyncio
async def test_network_device_ping(net_device):
    """Test ping behavior of base network device."""
    net_device.api_client.fetch_info.return_value = True
    assert await net_device.ping() is True

    net_device.api_client.fetch_info.side_effect = DeviceConnectionError()
    assert await net_device.ping() is False


@pytest.mark.asyncio
async def test_network_device_restart(net_device):
    """Test restart behavior of base network device."""

    net_device.api_client.write_command.return_value = "response"

    with patch.object(net_device, "_check_response") as mock_check:
        await net_device.restart()

        net_device.api_client.write_command.assert_called_once_with(
            '<root><set box="14" num1="00001" /></root>', "Dummy Context"
        )
        mock_check.assert_called_once_with(
            "response", '<root><set box="14" num1="00001" /></root>'
        )


@pytest.mark.asyncio
async def test_serial_device_ping(serial_device):
    """Test ping behavior of base serial device."""

    serial_device.api_client.get_info.return_value = True
    assert await serial_device.ping() is True

    serial_device.api_client.get_info.side_effect = DeviceConnectionError()
    assert await serial_device.ping() is False


@pytest.mark.asyncio
async def test_serial_device_restart(serial_device):
    """Test restart behavior of base serial device."""

    serial_device.api_client.write_command.return_value = MockSerialResponse(0)
    await serial_device.restart()


@pytest.mark.asyncio
async def test_serial_device_restart_failed(serial_device):
    """Test restart behavior when ack is not 0."""

    serial_device.api_client.write_command.return_value = MockSerialResponse(6)

    with pytest.raises(DeviceLogicError):
        await serial_device.restart()
