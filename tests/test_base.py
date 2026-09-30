# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for base device methods."""

from unittest.mock import AsyncMock

import pytest
from aiopapouch.devices.base import ERROR_STATUS
from aiopapouch.exceptions import DeviceParseError, DeviceResponseError

from aiopapouch import PapouchNetworkDevice


class DummyConf:
    """Dummy configuration for testing."""

    context = "Dummy Context"


class DummyDevice(PapouchNetworkDevice):
    """Mock device, that inherits from base.py."""

    def __init__(self, api_client):
        self.api_client = api_client
        self._conf = DummyConf()

    @property
    def conf(self):
        return self._conf

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


@pytest.fixture
def dummy_device():
    """Fixture providing a dummy device with mocked client."""

    client = AsyncMock()
    return DummyDevice(client)


async def test_send_command_filters_none_values(dummy_device):
    """Test that _send_command removes None values before sending."""

    dummy_device.api_client.read_command.return_value = (
        '<root><result status="1" /></root>'
    )

    await dummy_device._send_command(cmd_type="s", item_id="1", value=None)

    expected_params = {"type": "s", "id": "1"}
    dummy_device.api_client.read_command.assert_called_once_with(
        expected_params, "Dummy Context"
    )


async def test_send_command_calls_check_response(dummy_device):
    """Test that _send_command automatically verifies the response."""

    dummy_device.api_client.read_command.return_value = (
        f'<root><result status="{ERROR_STATUS}" /></root>'
    )

    with pytest.raises(DeviceResponseError):
        await dummy_device._send_command("r")


def test_check_response_success(dummy_device):
    """Test that _check_response passes silently on successful status."""

    response_xml = '<root><result status="1" /></root>'

    dummy_device._check_response(response_xml, "Request")


def test_check_response_error_status(dummy_device):
    """Test that DeviceResponseError is raised when status matches ERROR_STATUS."""

    response_xml = f'<root><result status="{ERROR_STATUS}" /></root>'

    with pytest.raises(DeviceResponseError):
        dummy_device._check_response(response_xml, "Request")


def test_check_response_missing_result_tag(dummy_device):
    """Test that DeviceResponseError is raised when result tag is completely missing."""

    response_xml = "<root><other_tag/></root>"

    with pytest.raises(DeviceResponseError):
        dummy_device._check_response(response_xml, "Request")


def test_check_response_invalid_xml(dummy_device):
    """Test that DeviceParseError is raised when response XML is invalid (ParseError)."""

    response_xml = "NOT_XML_DATA"

    with pytest.raises(DeviceParseError):
        dummy_device._check_response(response_xml, "Request")
