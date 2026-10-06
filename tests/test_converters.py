# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for HTTP converters (Edgar and Gnome)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from aiopapouch.client import (
    TCP_CLIENT_MODE_INDEX,
    TCP_SERVER_MODE_INDEX,
    UDP_MODE_INDEX,
)
from aiopapouch.const import UNKNOWN_LOCATION
from aiopapouch.devices.converters import (
    Edgar,
    Gnome,
    _async_download_gnome_config,
    _async_is_gnome_device,
    _parse_gnome_config,
    async_setup_converter_edgar,
    async_setup_converter_gnome,
)
from aiopapouch.exceptions import (
    DeviceConnectionError,
    DeviceParseError,
    DeviceResponseError,
)

VALID_EDGAR_SETTINGS = """
<root>
    <set box="1" dhcp="0" ip="192.168.3.32" mask="255.255.0.0" gate="192.168.1.201" dip="0.0.0.0" wport="80" lport="10001" comm="1" rip="192.168.1.30" rport="10001" mtu="1400" keep="45"/>
    <set box="2" admset="0"/>
    <set box="5" domain="" ip="192.168.1.102" port="8811" dir="" getscr="" guid="" keyset="0"/>
    <set box="14" port="RS485" speed="2" mode="0" flow="0" timeout="1" byte="00"/>
    <set box="8" name="" lang="e" pwrout="0"/>
    <set box="12" type="Edgar ETH" mac="00:80:A3:B5:D9:1E" fw="1.2"/>
</root>
"""


@pytest.fixture
def http_client():
    """Mock HTTP client for Edgar converter."""

    client = AsyncMock()
    client.ip_address = "192.168.3.32"
    client.get_device_mac.return_value = "00:80:A3:B5:D9:1E"
    client.get_device_info.return_value = ("Edgar", UNKNOWN_LOCATION)
    client.get_device_tcp_port.return_value = 10001
    client.fetch_settings.return_value = VALID_EDGAR_SETTINGS
    return client


@pytest.mark.asyncio
async def test_async_setup_edgar_success(http_client):
    """Test successful initialization of Edgar."""

    edgar = await async_setup_converter_edgar(http_client, "Edgar ETH")

    assert isinstance(edgar, Edgar)
    assert edgar.conf.name == "Edgar ETH"
    assert edgar.conf.location == UNKNOWN_LOCATION
    assert edgar.conf.identifier == "00:80:A3:B5:D9:1E"
    assert edgar.conf.tcp_port == 10001


@pytest.mark.asyncio
async def test_edgar_get_mode_success(http_client):
    """Test retrieving mode from Edgar settings."""

    edgar = await async_setup_converter_edgar(http_client, "Edgar")
    mode = await edgar.get_mode()

    assert mode == 1


@pytest.mark.parametrize(
    "xml_content, expected_error",
    [
        ("NOT_XML", DeviceParseError),
        (
            '<root><set box="1" num05="invalid" /></root>',
            DeviceParseError,
        ),
        ('<root><set box="2" num05="2" /></root>', DeviceParseError),
    ],
)
@pytest.mark.asyncio
async def test_edgar_get_mode_errors(http_client, xml_content, expected_error):
    """Test get_mode handles invalid XML gracefully."""

    edgar = await async_setup_converter_edgar(http_client, "Edgar")
    http_client.fetch_settings.return_value = xml_content

    with pytest.raises(expected_error):
        await edgar.get_mode()


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_edgar_switch_to_tcp_server_success(mock_sleep, http_client):
    """Test Edgar switching to TCP server mode."""

    edgar = await async_setup_converter_edgar(http_client, "Edgar")

    http_client.write_command.side_effect = [
        '<root><result status="1" /></root>',  # open config
        '<root><result status="1" /></root>',  # save XML
        '<root><result status="2" /></root>',  # save and restart
    ]

    await edgar.switch_to_tcp_server()

    assert http_client.write_command.call_count == 3

    payload = http_client.write_command.call_args_list[1][0][0]
    assert 'num05="0"' in payload
    assert 'ip01="192.168.3.32"' in payload
    assert 'num01="10001"' in payload


@pytest.mark.parametrize(
    "xml_settings, responses, expected_error",
    [
        ("NOT_XML", None, DeviceParseError),
        ("<root></root>", None, DeviceParseError),
        (
            VALID_EDGAR_SETTINGS,
            ['<root><result status="5" /></root>'],
            DeviceResponseError,
        ),
        (VALID_EDGAR_SETTINGS, ["NOT_XML"], DeviceParseError),
    ],
)
@pytest.mark.asyncio
async def test_edgar_switch_to_tcp_server_errors(
    http_client, xml_settings, responses, expected_error
):
    """Test Edgar switch to TCP server error handling."""

    edgar = await async_setup_converter_edgar(http_client, "Edgar")
    http_client.fetch_settings.return_value = xml_settings

    if responses:
        http_client.write_command.side_effect = responses

    with pytest.raises(expected_error):
        await edgar.switch_to_tcp_server()


GNOME_INIT_TEXT = b"""
MAC address 00204A112233
Software version V6.8.0.1 (100125)
"""

GNOME_CONFIG_TEXT_SERVER = b"""
*** Channel 1
Baudrate 9600, I/F Mode 4C, Flow 00
Port 10001
Connect Mode : C0
"""

GNOME_CONFIG_TEXT_CLIENT = b"""
*** Channel 1
Baudrate 9600, I/F Mode 00, Flow 00
Port 10001
Connect Mode : 05
"""

GNOME_CONFIG_TEXT_UDP = b"""
*** Channel 1
Baudrate 9600, I/F Mode 00, Flow 00
Port 10001
Connect Mode : 0C
"""


@pytest.mark.asyncio
async def test_async_is_gnome_device(http_client):
    """Test checking if device is a Gnome."""

    http_client.read_command.return_value = "var ver = 'Gnome 4.0';"
    assert await _async_is_gnome_device(http_client) is True

    http_client.read_command.return_value = "var ver = 'Quido 4.0';"
    assert await _async_is_gnome_device(http_client) is False

    http_client.read_command.side_effect = DeviceConnectionError("HTTP error")
    assert await _async_is_gnome_device(http_client) is False


@pytest.mark.parametrize(
    "config_text, expected_iface, expected_mode",
    [
        (GNOME_CONFIG_TEXT_SERVER, "RS485", TCP_SERVER_MODE_INDEX),
        (GNOME_CONFIG_TEXT_CLIENT, "RS232/RS422", TCP_CLIENT_MODE_INDEX),
        (GNOME_CONFIG_TEXT_UDP, "RS232/RS422", UDP_MODE_INDEX),
    ],
)
def test_parse_gnome_config_success(config_text, expected_iface, expected_mode):
    """Test parsing Telnet text output into Gnome properties."""

    mac, iface, port, mode = _parse_gnome_config(GNOME_INIT_TEXT, config_text)

    assert mac == "00:20:4A:11:22:33"
    assert port == 10001
    assert iface == expected_iface
    assert mode == expected_mode


def test_parse_gnome_config_missing_mac():
    """Test raising parse error if MAC address is not found in init text."""

    with pytest.raises(DeviceParseError):
        _parse_gnome_config(b"Invalid Init Text", GNOME_CONFIG_TEXT_SERVER)


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters._async_is_gnome_device", return_value=True)
@patch("aiopapouch.devices.converters._async_download_gnome_config")
async def test_async_setup_gnome_success(mock_download, mock_is_gnome, http_client):
    """Test Gnome initialization pipeline."""

    mock_download.return_value = (GNOME_INIT_TEXT, GNOME_CONFIG_TEXT_SERVER)

    gnome = await async_setup_converter_gnome(http_client)

    assert isinstance(gnome, Gnome)
    assert gnome.conf.name == "Gnome RS485"
    assert gnome.conf.identifier == "00:20:4A:11:22:33"
    assert gnome.conf.tcp_port == 10001
    assert await gnome.get_mode() == TCP_SERVER_MODE_INDEX


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters._async_is_gnome_device", return_value=True)
@patch(
    "aiopapouch.devices.converters._async_download_gnome_config",
    side_effect=DeviceConnectionError("Telnet closed"),
)
async def test_async_setup_gnome_telnet_fail(mock_download, mock_is_gnome, http_client):
    """Test Gnome initialization returns None if Telnet download fails."""

    gnome = await async_setup_converter_gnome(http_client)
    assert gnome is None


class MockStreamReader:
    """Mock for asyncio.StreamReader."""

    def __init__(self, data_chunks):
        self.data_chunks = data_chunks
        self.index = 0

    async def read(self, n=-1):
        """Mock read function"""
        if self.index < len(self.data_chunks):
            chunk = self.data_chunks[self.index]
            self.index += 1
            if isinstance(chunk, Exception):
                raise chunk
            return chunk

        await asyncio.sleep(10)
        return b""


class MockStreamWriter:
    """Mock for asyncio.StreamWriter."""

    def __init__(self):
        self.writes = []

    def write(self, data):
        """Mocked"""
        self.writes.append(data)

    async def drain(self):
        """Mocked"""

    def close(self):
        """Mocked"""

    async def wait_closed(self):
        """Mocked"""


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_async_download_gnome_config(mock_sleep, mock_open_connection):
    """Test Telnet config download loop."""

    mock_reader = MockStreamReader([
        GNOME_INIT_TEXT,
        b"Press Enter...",
        b"Your choice ?",
    ])
    mock_writer = MockStreamWriter()
    mock_open_connection.return_value = (mock_reader, mock_writer)

    init, config = await _async_download_gnome_config("192.168.1.50")

    assert init == GNOME_INIT_TEXT
    assert b"Your choice ?" in config
    assert b"\r\n" in mock_writer.writes
    assert b"8\r\n" in mock_writer.writes


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_async_download_gnome_config_oserror(mock_sleep, mock_open_connection):
    """Test Telnet config download retries 4 times on OSError and then raises."""

    mock_open_connection.side_effect = OSError("Connection refused")

    with pytest.raises(DeviceConnectionError):
        await _async_download_gnome_config("192.168.1.50")

    assert mock_open_connection.call_count == 4


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_async_set_gnome_tcp_server(
    mock_sleep, mock_open_connection, http_client
):
    """Test Gnome Telnet loop to change ConnectMode."""

    chunks = [
        GNOME_INIT_TEXT,
        b"Press Enter...",
        b"Your choice ?",
        b"Baudrate:",
        asyncio.TimeoutError(),
        b"I/F Mode:",
        asyncio.TimeoutError(),
        b"ConnectMode :",
        asyncio.TimeoutError(),
        b"Your choice ?",
    ]
    mock_reader = MockStreamReader(chunks)
    mock_writer = MockStreamWriter()
    mock_open_connection.return_value = (mock_reader, mock_writer)

    gnome = Gnome(http_client, "MAC", "Gnome RS232", 10001, TCP_CLIENT_MODE_INDEX)
    await gnome.switch_to_tcp_server()

    assert gnome.conf.tcp_port == 10001
    assert await gnome.get_mode() == TCP_SERVER_MODE_INDEX

    assert b"1\r\n" in mock_writer.writes
    assert b"\r\n" in mock_writer.writes
    assert b"C0\r\n" in mock_writer.writes
    assert b"9\r\n" in mock_writer.writes


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_async_set_gnome_tcp_server_menu_timeout(
    mock_sleep, mock_open_connection, http_client
):
    """Test Gnome throws error if it never reaches 'Your choice ?'."""

    chunks = [GNOME_INIT_TEXT, asyncio.TimeoutError()]
    mock_reader = MockStreamReader(chunks)
    mock_writer = MockStreamWriter()
    mock_open_connection.return_value = (mock_reader, mock_writer)

    gnome = Gnome(http_client, "MAC", "Gnome", 10001, 1)

    with pytest.raises(DeviceConnectionError):
        await gnome.switch_to_tcp_server()


def test_edgar_check_response_missing_result(http_client):
    """No tag <result> in the response."""

    edgar = Edgar(http_client, "mac", "name", "loc", 80)
    with pytest.raises(DeviceParseError):
        edgar._check_response("<root><other/></root>", "1", "testing")


@pytest.mark.asyncio
async def test_edgar_get_mode_value_error(http_client):
    """Mode value isn't covertible to int."""

    edgar = Edgar(http_client, "mac", "name", "loc", 80)
    http_client.fetch_settings.return_value = (
        '<root><set box="1" comm="invalid_int" /></root>'
    )
    with pytest.raises(DeviceParseError):
        await edgar.get_mode()


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters._async_is_gnome_device", return_value=False)
async def test_setup_gnome_not_gnome(mock_is_gnome, http_client):
    """Setup returns None if it isn't Gnome."""

    assert await async_setup_converter_gnome(http_client) is None


def test_parse_gnome_config_unknown_interface():
    """Test telnetu doesn't return I/F Mode."""

    config_text = b"*** Channel 1\nPort 10001\nConnect Mode : C0\n"
    _, iface, _, _ = _parse_gnome_config(GNOME_INIT_TEXT, config_text)
    assert iface == "Unknown"


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_gnome_open_connection_returns_none(
    mock_sleep, mock_open_connection, http_client
):
    """Test open_connection returns None without an exception."""

    mock_open_connection.return_value = (None, None)

    with pytest.raises(DeviceConnectionError):
        await _async_download_gnome_config("1.2.3.4")

    gnome = Gnome(http_client, "MAC", "Gnome", 10001, 1)
    with pytest.raises(DeviceConnectionError):
        await gnome.switch_to_tcp_server()


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_gnome_telnet_oserror_loop(mock_sleep, mock_open_connection, http_client):
    """Simulation of error socket in retry loop."""

    mock_open_connection.side_effect = OSError("Connection refused")

    gnome = Gnome(http_client, "MAC", "Gnome", 10001, 1)
    with pytest.raises(DeviceConnectionError):
        await gnome.switch_to_tcp_server()

    assert mock_open_connection.call_count == 4


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_gnome_telnet_empty_chunks(mock_sleep, mock_open_connection, http_client):
    """Reader return empty data."""

    mock_reader = MockStreamReader([b""])
    mock_writer = MockStreamWriter()
    mock_open_connection.return_value = (mock_reader, mock_writer)

    gnome = Gnome(http_client, "MAC", "Gnome", 10001, 1)
    with pytest.raises(DeviceConnectionError):
        await gnome.switch_to_tcp_server()

    mock_reader.index = 0
    init, conf = await _async_download_gnome_config("1.2.3.4")
    assert init == b""
    assert conf == b""


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_gnome_telnet_timeouts(mock_sleep, mock_open_connection, http_client):
    """Check Timeouts are suppressed."""

    mock_reader = MockStreamReader([
        b"init",
        asyncio.TimeoutError(),
        asyncio.TimeoutError(),
    ])
    mock_writer = MockStreamWriter()
    mock_open_connection.return_value = (mock_reader, mock_writer)

    init, conf = await _async_download_gnome_config("1.2.3.4")
    assert init == b"init"
    assert conf == b""

    mock_reader = MockStreamReader([
        GNOME_INIT_TEXT,
        b"Your choice ?",
        b"Baudrate",
        asyncio.TimeoutError(),
        b"Your choice ?",
        asyncio.TimeoutError(),
    ])
    mock_open_connection.return_value = (mock_reader, mock_writer)
    gnome = Gnome(http_client, "MAC", "Gnome", 10001, 1)

    await gnome.switch_to_tcp_server()


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_gnome_telnet_extra_prompt_reading(
    mock_sleep, mock_open_connection, http_client
):
    """Reading extra data after ":"."""

    chunks = [
        GNOME_INIT_TEXT,
        b"Press Enter...",
        b"Your choice ?",
        b"ConnectMode :",
        b" ",
        b"Your choice ?",
    ]
    mock_reader = MockStreamReader(chunks)
    mock_writer = MockStreamWriter()
    mock_open_connection.return_value = (mock_reader, mock_writer)

    gnome = Gnome(http_client, "MAC", "Gnome", 10001, 1)
    await gnome.switch_to_tcp_server()


@pytest.mark.asyncio
@patch("aiopapouch.devices.converters.asyncio.open_connection")
@patch("aiopapouch.devices.converters.asyncio.sleep", new_callable=AsyncMock)
async def test_gnome_telnet_unreachable_lines(
    mock_sleep, mock_open_connection, http_client
):
    """Test sudden disconnect and timeout at the end."""

    chunks = [
        GNOME_INIT_TEXT,
        b"Press Enter...",
        b"Your choice ?",
        b"",
        asyncio.TimeoutError(),
    ]
    mock_reader = MockStreamReader(chunks)
    mock_writer = MockStreamWriter()
    mock_open_connection.return_value = (mock_reader, mock_writer)

    gnome = Gnome(http_client, "MAC", "Gnome RS232", 10001, 1)

    await gnome.switch_to_tcp_server()
