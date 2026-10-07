# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for Papouch device hubs."""

from unittest.mock import AsyncMock, patch

import pytest
from aiopapouch.exceptions import DeviceConnectionError, DeviceLogicError
from aiopapouch.hub import Hub, NetworkHub, NetworkSpinelHub, SerialHub

from pap_spinel import SpinelTransportError


class MockConfiguration:
    """Mock for Papouch configuration."""

    def __init__(self, identifier, context, address=None, host=None):
        self.identifier = identifier
        self.context = context
        self.address = address
        self.host = host


class MockDevice:
    """Mock for Papouch device."""

    def __init__(self, identifier="sn123", context="ctx", address=1, host=None):
        self.conf = MockConfiguration(identifier, context, address, host)
        self.api_client = AsyncMock()
        self.get_fresh_data = AsyncMock(return_value={"data": True})
        self.ping = AsyncMock(return_value=True)
        self.restart = AsyncMock()


@pytest.fixture
def base_hub():
    """Return a plain Hub instance."""

    return Hub()


@pytest.fixture
def serial_hub():
    """Return a SerialHub instance with mock client."""

    client = AsyncMock()
    return SerialHub(client)


@pytest.fixture
def network_hub():
    """Return a NetworkHub instance with mock aiohttp session."""

    session = AsyncMock()
    return NetworkHub(session)


@pytest.mark.asyncio
async def test_base_hub_add_remove(base_hub):
    """Test adding and removing devices in base hub."""

    device1 = MockDevice("sn1", "ctx1")
    device2 = MockDevice("sn2", "ctx2")

    await base_hub.add_device(device1)
    await base_hub.add_device(device2)

    assert len(base_hub) == 2
    assert device1 in base_hub

    device_count = 0
    for _ in base_hub:
        device_count += 1

    assert len(base_hub) == device_count

    with pytest.raises(DeviceLogicError):
        await base_hub.add_device(device1)

    await base_hub.remove_device(device1)
    assert len(base_hub) == 1

    with pytest.raises(DeviceLogicError):
        await base_hub.remove_device(device1)

    await base_hub.remove_all_devices()
    assert len(base_hub) == 0


@pytest.mark.asyncio
async def test_base_hub_getters(base_hub):
    """Test getting devices by ID or context."""
    device = MockDevice("sn_test", "ctx_test")
    await base_hub.add_device(device)

    assert base_hub.get_device_by_identifier("sn_test") == device

    with pytest.raises(DeviceLogicError):
        base_hub.get_device_by_identifier("unknown_sn")


@pytest.mark.asyncio
async def test_base_hub_batch_operations(base_hub):
    """Test batch operations (health, data, restart) catching exceptions correctly."""

    device_good = MockDevice("sn1", "ctx_good")
    device_bad = MockDevice("sn2", "ctx_bad")

    device_bad.get_fresh_data.side_effect = DeviceConnectionError("Fetch failed")
    device_bad.ping.return_value = False
    device_bad.restart.side_effect = DeviceConnectionError("Restart failed")

    await base_hub.add_device(device_good)
    await base_hub.add_device(device_bad)

    data = await base_hub.get_fresh_data()
    assert "ctx_good" in data
    assert "ctx_bad" not in data

    health = await base_hub.check_health()
    assert health["ctx_good"] is True
    assert health["ctx_bad"] is False

    await base_hub.restart_all_devices()


@pytest.mark.asyncio
async def test_base_hub_empty_batch(base_hub):
    """Test batch operations return empty if no devices."""

    assert await base_hub.get_fresh_data() == {}
    assert await base_hub.check_health() == {}
    await base_hub.restart_all_devices()


@pytest.mark.asyncio
async def test_serial_hub_context_manager(serial_hub):
    """Test async context manager usage on serial hub."""

    async with serial_hub as sh:
        assert sh == serial_hub
    serial_hub.client.close.assert_called_once()


@pytest.mark.asyncio
@patch("aiopapouch.hub.create_serial_device")
async def test_serial_hub_create_add_device(mock_create, serial_hub):
    """Test serial hub creation and logic handling."""

    mock_device = MockDevice("sn1", "ctx1", address=5)
    mock_create.return_value = mock_device

    await serial_hub.create_and_add_device(5)
    assert len(serial_hub) == 1
    assert 5 in serial_hub.used_addresses

    mock_create.return_value = None
    with pytest.raises(DeviceLogicError):
        await serial_hub.create_and_add_device(10)


@pytest.mark.asyncio
@patch("aiopapouch.hub.get_device_details")
@patch("aiopapouch.hub.create_serial_device")
async def test_serial_hub_discover_single_device(
    mock_create, mock_get_details, serial_hub
):
    """Test discovery pipeline on a serial bus."""

    mock_get_details.return_value = ("Name", "sn_new", 3)
    mock_create.return_value = MockDevice("sn_new", "ctx_new", address=3)

    await serial_hub.discover_and_add_single_device()
    assert 3 in serial_hub.used_addresses

    with pytest.raises(DeviceLogicError):
        await serial_hub.discover_and_add_single_device()

    mock_get_details.side_effect = DeviceConnectionError()
    with pytest.raises(DeviceConnectionError):
        await serial_hub.discover_and_add_single_device()


@pytest.mark.asyncio
async def test_serial_hub_remove_and_get_by_address(serial_hub):
    """Test searching and removing by rs485 address."""

    device = MockDevice("sn", "ctx", address=10)
    await serial_hub.add_device(device)

    assert serial_hub.get_device_by_address(10) == device

    with pytest.raises(DeviceLogicError):
        serial_hub.get_device_by_address(99)

    serial_hub.remove_device_by_address(10)
    assert len(serial_hub) == 0

    with pytest.raises(DeviceLogicError):
        serial_hub.remove_device_by_address(10)


@pytest.mark.asyncio
@patch("aiopapouch.hub.assign_next_available_address")
@patch("aiopapouch.hub.create_serial_device")
async def test_serial_hub_create_by_sn(mock_create, mock_assign, serial_hub):
    """Test address assignment logic via serial number."""
    mock_assign.return_value = (5, "NewDevice")
    mock_create.return_value = MockDevice(address=5)

    await serial_hub.create_device_by_serial_number("SN123")
    assert 5 in serial_hub.used_addresses

    # Error: Found address but no name
    mock_assign.return_value = (6, None)
    with pytest.raises(DeviceLogicError):
        await serial_hub.create_device_by_serial_number("SN123")

    # Error: Full bus
    mock_assign.return_value = (None, None)
    with pytest.raises(DeviceLogicError):
        await serial_hub.create_device_by_serial_number("SN123")

    # Error: Unreachable code
    mock_assign.return_value = (None, "SomeName")
    with pytest.raises(DeviceLogicError):
        await serial_hub.create_device_by_serial_number("SN123")


@pytest.mark.asyncio
async def test_serial_hub_get_fresh_data(serial_hub):
    """Test serial fresh data does not use asyncio.gather due to lock."""
    device = MockDevice("sn", "ctx")
    await serial_hub.add_device(device)

    device.get_fresh_data = AsyncMock(side_effect=DeviceConnectionError("Port locked"))
    data = await serial_hub.get_fresh_data()
    assert data == {}


@pytest.mark.asyncio
@patch("aiopapouch.hub.create_network_device")
async def test_network_hub_create_device(mock_create, network_hub):
    """Test creating a device via HTTP IP."""

    mock_device = MockDevice("sn1", "ctx", host="1.1.1.1")
    mock_device.api_client.ip_address = "1.1.1.1"
    mock_create.return_value = mock_device

    await network_hub.create_and_add_device("1.1.1.1")
    assert "1.1.1.1" in network_hub.used_ips

    mock_create.return_value = None
    with pytest.raises(DeviceLogicError):
        await network_hub.create_and_add_device("2.2.2.2")


@pytest.mark.asyncio
@patch("aiopapouch.hub.async_discover_papouch_devices")
@patch.object(NetworkHub, "create_and_add_device")
async def test_network_hub_discover_devices(
    mock_create_add, mock_discover, network_hub
):
    """Test network discovery handles multiple IPs and errors safely."""

    existing_mock = MockDevice()
    existing_mock.api_client.ip_address = "10.0.0.1"
    await network_hub.add_device(existing_mock)

    mock_discover.return_value = ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    async def mock_create_effect(ip, **kwargs):
        if ip == "10.0.0.3":
            raise DeviceConnectionError("Failed")

    mock_create_add.side_effect = mock_create_effect

    await network_hub.discover_and_add_all_devices()
    assert mock_create_add.call_count == 2


@pytest.mark.asyncio
async def test_network_hub_get_and_remove_by_ip(network_hub):
    """Test getting and removing network device via IP."""

    device = MockDevice()
    device.api_client.ip_address = "10.10.10.10"
    await network_hub.add_device(device)

    assert network_hub.get_device_by_ip("10.10.10.10") == device

    with pytest.raises(DeviceLogicError):
        network_hub.get_device_by_ip("9.9.9.9")

    network_hub.remove_device_by_ip("10.10.10.10")
    assert len(network_hub) == 0

    with pytest.raises(DeviceLogicError):
        network_hub.remove_device_by_ip("10.10.10.10")


@pytest.fixture
def spinel_hub():
    """Return a NetworkSpinelHub."""
    return NetworkSpinelHub()


@pytest.mark.asyncio
async def test_spinel_hub_context_manager(spinel_hub):
    """Test context manager wipes all devices on exit."""
    device = MockDevice("sn", "ctx", host="10.0.0.1")
    await spinel_hub.add_device(device)

    with pytest.raises(DeviceLogicError):
        await spinel_hub.add_device(device)

    async with spinel_hub as sh:
        assert len(sh) == 1

    assert len(spinel_hub) == 0
    device.api_client.close.assert_called()


@pytest.mark.asyncio
async def test_spinel_hub_add_device(spinel_hub):
    """Test TCP port opening upon adding device."""

    device = MockDevice("sn", "ctx", host="10.0.0.1")

    await spinel_hub.add_device(device)
    device.api_client.open.assert_called_once()

    device2 = MockDevice("sn2", "ctx2", host="10.0.0.2")

    device2.api_client.open.side_effect = SpinelTransportError()
    with pytest.raises(DeviceConnectionError):
        await spinel_hub.add_device(device2)


@pytest.mark.asyncio
async def test_spinel_hub_used_ips_property(spinel_hub):
    """Test gathering used IPs safely."""

    device = MockDevice("sn", "ctx", host="10.0.0.1")
    await spinel_hub.add_device(device)

    assert "10.0.0.1" in spinel_hub.used_ips

    device.conf.host = None
    with pytest.raises(DeviceLogicError):
        _ = spinel_hub.used_ips


@pytest.mark.asyncio
@patch("aiopapouch.hub.PapouchSerialClient")
@patch("aiopapouch.hub.create_serial_device")
async def test_spinel_hub_create_add_device(mock_create, mock_client, spinel_hub):
    """Test Spinel TCP network device creation lifecycle."""

    mock_client_instance = AsyncMock()
    mock_client.return_value = mock_client_instance

    mock_device = MockDevice()
    mock_create.return_value = mock_device

    await spinel_hub.create_and_add_device("192.168.1.50", 10001)
    assert len(spinel_hub) == 1
    assert mock_device.conf.host == "192.168.1.50"

    mock_client_instance.open.side_effect = SpinelTransportError()
    with pytest.raises(DeviceConnectionError):
        await spinel_hub.create_and_add_device("192.168.1.51")

    mock_client_instance.open.side_effect = None
    mock_create.return_value = None

    with pytest.raises(DeviceLogicError):
        await spinel_hub.create_and_add_device("192.168.1.52")

    assert mock_client_instance.close.call_count >= 1


@pytest.mark.asyncio
async def test_spinel_hub_remove_device(spinel_hub):
    """Test TCP port is closed on removal."""
    device = MockDevice("sn", "ctx", host="10.0.0.1")
    await spinel_hub.add_device(device)

    await spinel_hub.remove_device(device)
    with pytest.raises(DeviceLogicError):
        await spinel_hub.remove_device(device)

    device.api_client.close.assert_called_once()
    assert len(spinel_hub) == 0

    await spinel_hub.add_device(device)
    device.api_client.close.side_effect = DeviceConnectionError()
    with pytest.raises(DeviceConnectionError):
        await spinel_hub.remove_device(device)


@pytest.mark.asyncio
async def test_spinel_hub_remove_all(spinel_hub):
    """Test remove_all swallows closing errors safely."""
    device1 = MockDevice("sn1", "ctx1", host="10.0.0.1")
    device2 = MockDevice("sn2", "ctx2", host="10.0.0.2")

    device2.api_client.close.side_effect = SpinelTransportError()

    await spinel_hub.add_device(device1)
    await spinel_hub.add_device(device2)

    await spinel_hub.remove_all_devices()

    assert len(spinel_hub) == 0
    device1.api_client.close.assert_called()
    device2.api_client.close.assert_called()
