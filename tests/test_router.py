# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for the device factory and hub (devices/__init__.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiopapouch.devices import (
    CONVERTER_SETUP_HANDLERS,
    DEVICE_SETUP_HANDLERS,
    NETWORK,
    SERIAL,
    ConverterHandler,
    create_converter,
    create_network_device,
    create_serial_device,
)
from aiopapouch.exceptions import DeviceConnectionError

from aiopapouch import (
    is_converter_supported,
    is_device_supported,
)


@pytest.fixture
def http_client():
    """Mock HTTP client."""

    return AsyncMock()


@pytest.fixture
def serial_client():
    """Mock Serial client."""

    return AsyncMock()


@pytest.mark.parametrize(
    "device_name, device_type, expected",
    [
        ("Quido 4/4", NETWORK, True),
        ("Quido 10/1", SERIAL, True),
        ("TH2E", NETWORK, True),
        ("TH2E", SERIAL, False),
        ("Papago Meteo ETH", NETWORK, True),
        ("THT2", SERIAL, True),
        ("Unknown Device", NETWORK, False),
        (None, NETWORK, False),
    ],
)
def test_is_device_supported(device_name, device_type, expected):
    """Test device support resolving based on name and connection type."""

    assert is_device_supported(device_name, device_type) is expected


@pytest.mark.parametrize(
    "converter_name, expected",
    [
        ("EDGAR", True),
        ("GNOME", True),
        ("GNOME232", True),
        ("Unknown", False),
        (None, False),
    ],
)
def test_is_converter_supported(converter_name, expected):
    """Test converter support resolving based on name."""

    assert is_converter_supported(converter_name) is expected


async def test_create_network_device_success(http_client, monkeypatch):
    """Test successful routing and creation of a network device."""

    http_client.get_device_info.return_value = ("Quido 4/4", "Living Room")

    mock_setup = AsyncMock()

    monkeypatch.setitem(DEVICE_SETUP_HANDLERS["Quido"].setup_funcs, NETWORK, mock_setup)

    device = await create_network_device(http_client)

    assert device is not None

    mock_setup.assert_called_once_with(http_client)


async def test_create_network_device_unsupported(http_client):
    """Test creating network device returns None if device is unknown."""

    http_client.get_device_info.return_value = ("NonExistentDevice", "Living Room")

    device = await create_network_device(http_client)

    assert device is None


async def test_create_network_device_missing_name(http_client):
    """Test creating network device returns None if get_device_info fails to return a name."""

    http_client.get_device_info.return_value = (None, None)

    device = await create_network_device(http_client)

    assert device is None


async def test_create_converter_success(http_client, monkeypatch):
    """Test successful routing and creation of a converter."""

    http_client.get_device_info.return_value = ("EDGAR", "Hall")

    mock_setup = AsyncMock()

    monkeypatch.setitem(CONVERTER_SETUP_HANDLERS, "EDGAR", ConverterHandler(mock_setup))

    converter = await create_converter(http_client)

    assert converter is not None
    mock_setup.assert_called_once_with(http_client, "EDGAR")


async def test_create_converter_unsupported(http_client):
    """Test creating converter returns None if name is unknown."""

    http_client.get_device_info.return_value = ("Unknown", "Hall")

    converter = await create_converter(http_client)

    assert converter is None


@patch("aiopapouch.devices.async_setup_converter_gnome")
async def test_create_converter_gnome_fallback_success(mock_gnome_setup, http_client):
    """Test GNOME fallback logic when get_device_info raises connection error."""

    http_client.get_device_info.side_effect = DeviceConnectionError()
    mock_gnome_setup.return_value = AsyncMock()

    converter = await create_converter(http_client)

    assert converter is not None
    mock_gnome_setup.assert_called_once_with(http_client)


@patch("aiopapouch.devices.async_setup_converter_gnome")
async def test_create_converter_gnome_fallback_failure(mock_gnome_setup, http_client):
    """Test that connection error is re-raised if GNOME fallback also fails (returns None)."""

    http_client.get_device_info.side_effect = DeviceConnectionError()
    mock_gnome_setup.return_value = None

    with pytest.raises(DeviceConnectionError):
        await create_converter(http_client)


@patch("aiopapouch.devices.parse_device_location")
@patch("aiopapouch.devices.parse_device_name")
@patch("aiopapouch.devices.parse_device_serial_number")
async def test_create_serial_device_success(
    mock_parse_sn, mock_parse_name, mock_parse_loc, serial_client, monkeypatch
):
    """Test successful orchestration of serial device creation."""

    mock_parse_sn.return_value = "0123/45678"
    mock_parse_name.return_value = "Quido 10/1"
    mock_parse_loc.return_value = "Boiler Room"

    mock_packet = AsyncMock()
    mock_packet.data = b"dummy_data"
    serial_client.get_man_data.return_value = mock_packet
    serial_client.get_info.return_value = mock_packet
    serial_client.get_location.return_value = mock_packet

    mock_setup = AsyncMock()

    monkeypatch.setitem(DEVICE_SETUP_HANDLERS["Quido"].setup_funcs, SERIAL, mock_setup)

    device = await create_serial_device(serial_client, address=5)

    assert device is not None
    mock_setup.assert_called_once_with(
        serial_client, 5, "0123/45678", "Quido 10/1", "Boiler Room"
    )


@patch("aiopapouch.devices.parse_device_location")
@patch("aiopapouch.devices.parse_device_name")
@patch("aiopapouch.devices.parse_device_serial_number")
async def test_create_serial_device_unsupported(
    mock_parse_sn, mock_parse_name, mock_parse_loc, serial_client
):
    """Test serial device creation returns None for unsupported devices."""

    mock_parse_sn.return_value = "0123/45678"
    mock_parse_name.return_value = "NonExistentDevice"
    mock_parse_loc.return_value = "Boiler Room"

    mock_packet = MagicMock()
    mock_packet.data = b"dummy_data"
    serial_client.get_man_data.return_value = mock_packet
    serial_client.get_info.return_value = mock_packet
    serial_client.get_location.return_value = mock_packet

    device = await create_serial_device(serial_client, address=5)

    assert device is None
