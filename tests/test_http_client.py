# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Test HTTP client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiopapouch.client import (
    DATA_URL,
    INFO_URL,
    SAVE_URL,
    SET_URL,
    SETTINGS_URL,
    WEB_MODE_INDEX,
)
from aiopapouch.exceptions import (
    DeviceAuthError,
    DeviceConnectionError,
    DeviceLogicError,
    DeviceParseError,
)

from aiopapouch import PapouchHTTPClient, PapouchSerialClient


class FakeIP:
    """Mock representing IP object."""

    ip_address: str = "192.168.1.50"


class MockAiohttpResponse:
    """Mock class for aiohttp responses (async context manager)."""

    def __init__(self, text="<xml></xml>", status=200):
        self._text = text
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def text(self, encoding="utf-8"):
        """Return its fake text representation"""
        return self._text


@pytest.fixture
def http_client():
    """Fixture for basic HTTP client."""
    session = AsyncMock()
    return PapouchHTTPClient(
        ip_address="192.168.1.50", session=session, password="heslo"
    )


def mock_aiohttp_request(http_client, text="<xml></xml>", status=200, exception=None):
    """Mock aiohttp async with request."""
    if exception:
        http_client.session.request = MagicMock(side_effect=exception)
        return

    response_mock = AsyncMock()
    response_mock.status = status
    response_mock.text.return_value = text

    ctx_mock = MagicMock()
    ctx_mock.__aenter__.return_value = response_mock

    http_client.session.request = MagicMock(return_value=ctx_mock)


@pytest.fixture
def serial_client():
    """Fixture to provide PapouchSerialClient with a mocked transport."""
    transport_mock = MagicMock()
    return PapouchSerialClient(transport=transport_mock)


@pytest.mark.parametrize(
    "password",
    ["", "password", "pass word", "રšřžýáÜ"],
)
def test_http_client_constructor_password(password):
    """Test creating HTTP client with different password"""

    session = AsyncMock()
    PapouchHTTPClient("192.168.1.50", session, password, 80)


@pytest.mark.parametrize(
    "ip_address, password, web_port",
    [
        ("192.168.1.50", "123", "80"),
        ("192.168.1.50", 123, 80),
        (FakeIP(), "123", "80"),
        ("192.168.1.50", "123", -1),
        ("192.168.1.50", "123", 1222222),
    ],
)
def test_http_client_constructor_invalid_args(
    ip_address,
    password,
    web_port,
):
    """Test creating HTTP client with invalid args."""

    session = AsyncMock()

    with pytest.raises(DeviceLogicError):
        PapouchHTTPClient(
            ip_address=ip_address, session=session, password=password, web_port=web_port
        )


async def test_send_request_success(http_client):
    """Test successful HTTP request."""
    mock_aiohttp_request(http_client, text="OK", status=200)

    response = await http_client._send_request("GET", "test.xml", "Test context")
    assert response == "OK"
    http_client.session.request.assert_called_once()


async def test_send_request_auth_error(http_client):
    """Test status 401 raises DeviceAuthError."""
    mock_aiohttp_request(http_client, status=401)

    with pytest.raises(DeviceAuthError):
        await http_client._send_request("GET", "test.xml", "Test context")


async def test_send_request_connection_error(http_client):
    """Test status 500 and TimeoutError raises DeviceConnectionError."""
    mock_aiohttp_request(http_client, status=500)
    with pytest.raises(DeviceConnectionError):
        await http_client._send_request("GET", "test.xml", "Test context")

    mock_aiohttp_request(http_client, exception=asyncio.TimeoutError())
    with pytest.raises(DeviceConnectionError):
        await http_client._send_request("GET", "test.xml", "Test context")


async def test_fetch_removes_xml_namespace(http_client):
    """Test _fetch remove xmlns."""
    xml_with_ns = '<root xmlns="http://example.com"><data/></root>'
    mock_aiohttp_request(http_client, text=xml_with_ns)

    result = await http_client._fetch("test.xml")
    assert result == "<root><data/></root>"


async def test_fetch_info(http_client):
    """Test the fetch_info method."""
    http_client._fetch = AsyncMock(return_value="<xml>info</xml>")

    result = await http_client.fetch_info()

    assert result == "<xml>info</xml>"
    http_client._fetch.assert_called_once_with(INFO_URL)


async def test_fetch_data(http_client):
    """Test the fetch_data method."""
    http_client._fetch = AsyncMock(return_value="<xml>data</xml>")

    result = await http_client.fetch_data()

    assert result == "<xml>data</xml>"
    http_client._fetch.assert_called_once_with(DATA_URL)


async def test_fetch_settings(http_client):
    """Test the fetch_settings method."""
    http_client._fetch = AsyncMock(return_value="<xml>settings</xml>")

    result = await http_client.fetch_settings()

    assert result == "<xml>settings</xml>"
    http_client._fetch.assert_called_once_with(SETTINGS_URL)


@pytest.mark.parametrize(
    "xml_content, expected_device, expected_location",
    [
        (
            '<root><heartbeat device="TH2E" location="Sklep" /></root>',
            "TH2E",
            "Sklep",
        ),
        (
            '<root><heartbeat device="TME" /></root>',
            "TME",
            None,
        ),
        (
            '<root><heartbeat location="Sklep" /></root>',
            None,
            "Sklep",
        ),
        (
            "<root><heartbeat /></root>",
            None,
            None,
        ),
        (
            "<root><other_tag>data</other_tag></root>",
            None,
            None,
        ),
    ],
)
async def test_get_device_info_structure(
    http_client, xml_content, expected_device, expected_location
):
    """Test get_device_info with different XMLs."""
    http_client.fetch_info = AsyncMock(return_value=xml_content)

    device, location = await http_client.get_device_info()

    assert device == expected_device
    assert location == expected_location


async def test_get_device_info_invalid_xml(http_client):
    """Test invalid XML (ParseError) return (None, None)."""
    http_client.fetch_info = AsyncMock(return_value="Test text (NOT XML)")

    device, location = await http_client.get_device_info()

    assert device is None
    assert location is None


async def test_get_device_mac_success(http_client):
    """Test successful retrieving MAC adress (box 12 exists and has atribut mac)."""
    xml_content = '<root><set box="12" mac="00:11:22:33:44:55" /></root>'
    http_client.fetch_settings = AsyncMock(return_value=xml_content)

    mac = await http_client.get_device_mac()

    assert mac == "00:11:22:33:44:55"


async def test_get_device_mac_missing_attribute(http_client):
    """Test that DeviceLogicError is raised when box 12 exists but mac attribute is missing."""

    xml_content = '<root><set box="12" /></root>'
    http_client.fetch_settings = AsyncMock(return_value=xml_content)

    with pytest.raises(DeviceParseError):
        await http_client.get_device_mac()


async def test_get_device_mac_empty_attribute(http_client):
    """Test that DeviceLogicError is raised when mac attribute is empty."""

    xml_content = '<root><set box="12" mac="" /></root>'
    http_client.fetch_settings = AsyncMock(return_value=xml_content)

    with pytest.raises(DeviceParseError):
        await http_client.get_device_mac()


async def test_get_device_mac_missing_box(http_client):
    """Test that DeviceLogicError is raised when box 12 is entirely missing from XML."""

    xml_content = '<root><set box="1" mac="00:11:22:33:44:55" /></root>'
    http_client.fetch_settings = AsyncMock(return_value=xml_content)

    with pytest.raises(DeviceParseError):
        await http_client.get_device_mac()


async def test_get_device_tcp_port_success(http_client):
    """Test successful retrieval of TCP port and correct conversion to integer."""

    xml_content = '<root><set box="1" lport="8080" /></root>'
    http_client.fetch_settings = AsyncMock(return_value=xml_content)

    port = await http_client.get_device_tcp_port()

    assert port == 8080
    assert isinstance(port, int)


async def test_get_device_tcp_port_missing_attribute(http_client):
    """Test that DeviceLogicError is raised when box 1 exists but lport attribute is missing."""

    xml_content = '<root><set box="1" /></root>'
    http_client.fetch_settings = AsyncMock(return_value=xml_content)

    with pytest.raises(DeviceParseError):
        await http_client.get_device_tcp_port()


async def test_get_device_tcp_port_empty_attribute(http_client):
    """Test that DeviceLogicError is raised when lport attribute is empty."""

    xml_content = '<root><set box="1" lport="" /></root>'
    http_client.fetch_settings = AsyncMock(return_value=xml_content)

    with pytest.raises(DeviceParseError):
        await http_client.get_device_tcp_port()


async def test_get_device_tcp_port_missing_box(http_client):
    """Test that DeviceLogicError is raised when box 1 is entirely missing from XML."""

    xml_content = '<root><set box="2" lport="8080" /></root>'
    http_client.fetch_settings = AsyncMock(return_value=xml_content)

    with pytest.raises(DeviceParseError):
        await http_client.get_device_tcp_port()


async def test_read_command(http_client):
    """Test that read_command passes correct arguments to _send_request."""

    http_client._send_request = AsyncMock(return_value="OK")
    params = {"val": "1"}

    result = await http_client.read_command(params=params, context="Test Context")

    assert result == "OK"
    http_client._send_request.assert_called_once_with(
        "GET", SET_URL, "Test Context", params=params
    )


async def test_read_command_custom_endpoint(http_client):
    """Test read_command with a custom endpoint."""

    http_client._send_request = AsyncMock(return_value="OK")

    await http_client.read_command({}, "Context", endpoint="custom.xml")

    http_client._send_request.assert_called_once_with(
        "GET", "custom.xml", "Context", params={}
    )


async def test_write_command(http_client):
    """Test that write_command passes correct arguments to _send_request."""

    http_client._send_request = AsyncMock(return_value="OK")
    payload = "<data>123</data>"

    result = await http_client.write_command(payload=payload, context="Test Context")

    assert result == "OK"
    http_client._send_request.assert_called_once_with(
        "POST", SAVE_URL, "Test Context", data=payload
    )


async def test_get_device_mode_success(http_client):
    """Test successful extraction of device mode."""

    xml_content = '<root><heartbeat mode="2" /></root>'
    http_client.fetch_info = AsyncMock(return_value=xml_content)

    mode = await http_client.get_device_mode()

    assert mode == 2


@pytest.mark.parametrize(
    "exception_device",
    ["TME", "Papago ETH"],
)
async def test_get_device_mode_exception_devices(http_client, exception_device):
    """Test that mode falls back to WEB_MODE_INDEX for exception devices."""

    xml_content = f'<root><heartbeat device="{exception_device}" /></root>'
    http_client.fetch_info = AsyncMock(return_value=xml_content)

    mode = await http_client.get_device_mode()

    assert mode == WEB_MODE_INDEX


async def test_get_device_mode_missing_mode_unknown_device(http_client):
    """Test that missing mode returns -1."""

    xml_content = '<root><heartbeat device="Unknown_Device" /></root>'
    http_client.fetch_info = AsyncMock(return_value=xml_content)

    mode = await http_client.get_device_mode()

    assert mode == -1


async def test_get_device_mode_missing_heartbeat(http_client):
    """Test that missing heartbeat tag returns -1 and logs an error."""

    xml_content = "<root><some_other_tag /></root>"
    http_client.fetch_info = AsyncMock(return_value=xml_content)

    mode = await http_client.get_device_mode()

    assert mode == -1


@pytest.mark.parametrize(
    "device_name, expected",
    [
        ("TME", True),
        ("Papago 2TH ETH", True),
        ("Papago Meteo ETH", True),
        ("Papago 2TH WIFI", True),
        ("TH2E", False),
        ("Unknown", False),
    ],
)
def test_check_exceptions_device_web_mode(http_client, device_name, expected):
    """Test matching logic for devices requiring web mode fallback."""

    result = http_client._check_exceptions_device_web_mode(device_name)
    assert result is expected


async def test_get_device_mode_invalid_xml(http_client):
    """Test that DeviceParseError is raised when info XML is invalid (ParseError)."""

    http_client.fetch_info = AsyncMock(return_value="NOT_XML_DATA")

    with pytest.raises(DeviceParseError):
        await http_client.get_device_mode()


async def test_get_box_attribute_invalid_xml(http_client):
    """Test that DeviceParseError is raised when settings XML is invalid (ParseError)."""

    http_client.fetch_settings = AsyncMock(return_value="NOT_XML_DATA")

    with pytest.raises(DeviceParseError):
        await http_client._get_box_attribute("1", "comm", "Error Context")
