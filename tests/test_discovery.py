"""Test device discovery."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiopapouch.const import UNKNOWN_LOCATION
from aiopapouch.devices.converters import ConverterConfiguration
from aiopapouch.discovery import (
    ACTIVE_DISCOVERY_TIMEOUT,
    MAGIC_PACKET,
    TARGET_PORT,
    PapouchDiscoveryProtocol,
    async_discover_papouch_devices,
)
from aiopapouch.exceptions import DeviceAuthError, DeviceConnectionError

from aiopapouch import PapouchHTTPClient


@pytest.fixture
def mock_udp_discovery(mocker) -> MagicMock:
    """Mock discovery UDP protocol."""
    mock_protocol = MagicMock()
    mock_protocol.discovered_ips = {}

    mock_transport = MagicMock()
    mock_loop = MagicMock()
    mock_loop.create_datagram_endpoint = AsyncMock(
        return_value=(mock_transport, mock_protocol)
    )

    mocker.patch("asyncio.get_running_loop", return_value=mock_loop)
    return mock_protocol


@pytest.mark.parametrize(
    "discovered_ips, client_behavior, expected_results",
    [
        (["192.168.1.50"], [("TME", "Store")], {"192.168.1.50": ("TME", "Store")}),
        (["192.168.1.50"], [("UNSUPPORTED", "Store")], {}),
        (["192.168.1.50"], [("TME", "")], {"192.168.1.50": ("TME", UNKNOWN_LOCATION)}),
        ([], [], {}),
        (["192.168.1.50", "192.168.1.51"], [(None, None), (None, None)], {}),
        (
            ["192.168.1.50", "192.168.1.51"],
            [("TME", "Store"), (None, None)],
            {"192.168.1.50": ("TME", "Store")},
        ),
        ([], [("TME", "Store"), (None, None)], {}),
        (["192.168.1.50"], DeviceConnectionError, {}),
        (["192.168.1.50"], DeviceAuthError, {}),
        (
            ["192.168.1.50", "192.168.1.51"],
            [DeviceConnectionError, ("TME", "Store")],
            {"192.168.1.51": ("TME", "Store")},
        ),
    ],
)
async def test_async_discovery_network(
    mocker,
    mock_udp_discovery,  # pylint: disable=redefined-outer-name
    discovered_ips,
    client_behavior,
    expected_results,
):
    """Test device discovery for standard network connections."""
    mock_udp_discovery.discovered_ips = discovered_ips

    mock_client = AsyncMock(spec=PapouchHTTPClient)
    mock_client.get_device_info.side_effect = client_behavior

    mocker.patch("aiopapouch.discovery.PapouchHTTPClient", return_value=mock_client)

    session = AsyncMock()
    results = await async_discover_papouch_devices(session, "network")
    assert results == expected_results


@pytest.mark.parametrize(
    "discovered_ips, client_behavior, expected_results, converter_conf",
    [
        (
            ["192.168.1.50", "192.168.1.51", "192.168.1.52"],
            [
                DeviceConnectionError,
                ("EDGAR", UNKNOWN_LOCATION),
                ("UNSUPPORTED_CONVERTER", UNKNOWN_LOCATION),
            ],
            {
                "192.168.1.50": ("Gnome", UNKNOWN_LOCATION),
                "192.168.1.51": ("EDGAR", UNKNOWN_LOCATION),
            },
            ConverterConfiguration(name="Gnome", location=UNKNOWN_LOCATION),
        ),
    ],
)
async def test_async_discovery_network_hub(
    mocker,
    mock_udp_discovery,  # pylint: disable=redefined-outer-name
    discovered_ips,
    client_behavior,
    expected_results,
    converter_conf,
):
    """Test device discovery specifically for network hubs with converters."""
    mock_udp_discovery.discovered_ips = discovered_ips

    mock_client = AsyncMock(spec=PapouchHTTPClient)
    mock_client.get_device_info.side_effect = client_behavior
    mocker.patch("aiopapouch.discovery.PapouchHTTPClient", return_value=mock_client)

    mock_converter = AsyncMock()
    mock_converter.conf = converter_conf
    mocker.patch(
        "aiopapouch.discovery.async_setup_converter_gnome",
        return_value=mock_converter,
    )

    session = AsyncMock()
    results = await async_discover_papouch_devices(session, "network_hub")
    assert results == expected_results


async def test_async_discovery_network_hub_converter_none(
    mocker,
    mock_udp_discovery,  # pylint: disable=redefined-outer-name
):
    """Test discovery when async_setup_converter_gnome fails and returns None."""
    mock_udp_discovery.discovered_ips = ["192.168.1.50"]

    mock_client = AsyncMock(spec=PapouchHTTPClient)
    mock_client.get_device_info.side_effect = DeviceConnectionError
    mocker.patch("aiopapouch.discovery.PapouchHTTPClient", return_value=mock_client)

    mocker.patch(
        "aiopapouch.discovery.async_setup_converter_gnome",
        return_value=None,
    )

    session = AsyncMock()
    results = await async_discover_papouch_devices(session, "network_hub")

    assert results == {}


async def test_async_discovery_timeout_exception(
    mocker,
    mock_udp_discovery,  # pylint: disable=redefined-outer-name
):
    """Test discovery when get_device_info."""
    mock_udp_discovery.discovered_ips = ["192.168.1.50"]

    mock_client = AsyncMock(spec=PapouchHTTPClient)
    mocker.patch("aiopapouch.discovery.PapouchHTTPClient", return_value=mock_client)

    async def slow_get_device_info():
        """Simulate sleep."""
        await asyncio.sleep(ACTIVE_DISCOVERY_TIMEOUT + 0.1)
        return ("TME", "Store")

    mock_client.get_device_info.side_effect = slow_get_device_info

    session = AsyncMock()
    results = await async_discover_papouch_devices(session, "network")

    assert results == {}


def test_papouch_discovery_protocol():
    """Test the UDP discovery protocol behavior."""

    protocol = PapouchDiscoveryProtocol()
    assert not protocol.discovered_ips
    assert protocol.transport is None

    mock_transport = MagicMock()
    protocol.connection_made(mock_transport)

    mock_transport.sendto.assert_called_once_with(
        MAGIC_PACKET, ("255.255.255.255", TARGET_PORT)
    )
    assert protocol.transport == mock_transport

    protocol.datagram_received(b"SOMETHING", ("192.168.1.55", 5465))
    protocol.datagram_received(b"SOMETHING ELSE", ("192.168.1.56", 123))

    assert protocol.discovered_ips == {"192.168.1.55", "192.168.1.56"}
