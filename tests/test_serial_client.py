# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Test serial client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiopapouch.client import PapouchSerialClient
from aiopapouch.const import INST_NEW_ADDR, SERIAL_BROADCAST_ADDRESS
from aiopapouch.exceptions import (
    DeviceConnectionError,
    DeviceLogicError,
    DeviceParseError,
)
from pap_spinel.packet import INST_INFO, INST_LOC, INST_SN

from pap_spinel import SpinelError, SpinelTransportError


@pytest.fixture
def serial_client():
    """Fixture to provide PapouchSerialClient with a mocked transport."""
    transport_mock = MagicMock()
    return PapouchSerialClient(transport=transport_mock)


async def test_serial_open_success(serial_client):
    """Test successful port opening."""

    serial_client._spinel_client.open = AsyncMock()
    await serial_client.open()
    serial_client._spinel_client.open.assert_called_once()


async def test_serial_open_error(serial_client):
    """Test connection error translation when opening port."""

    serial_client._spinel_client.open = AsyncMock(side_effect=SpinelTransportError())
    with pytest.raises(DeviceConnectionError):
        await serial_client.open()


async def test_serial_close_success(serial_client):
    """Test successful port closing."""

    serial_client._spinel_client.close = AsyncMock()
    await serial_client.close()
    serial_client._spinel_client.close.assert_called_once()


async def test_serial_close_error(serial_client):
    """Test connection error translation when closing port."""

    serial_client._spinel_client.close = AsyncMock(side_effect=SpinelTransportError())
    with pytest.raises(DeviceConnectionError):
        await serial_client.close()


async def test_write_command_success(serial_client):
    """Test successful write command execution."""

    serial_client._spinel_client.request = AsyncMock(return_value="mocked_packet")

    result = await serial_client.write_command(addr=1, inst=2, context="Test")

    assert result == "mocked_packet"
    serial_client._spinel_client.request.assert_called_once_with(
        addr=1, inst=2, data=b"", timeout=2.0
    )


async def test_write_command_error(serial_client):
    """Test SpinelError is translated to DeviceConnectionError in write_command."""

    serial_client._spinel_client.request = AsyncMock(side_effect=SpinelError())

    with pytest.raises(DeviceConnectionError):
        await serial_client.write_command(addr=1, inst=2, context="Test")


async def test_write_command_lock_concurrency(serial_client):
    """Test that asyncio.Lock prevents concurrent requests."""

    concurrent_executions = 0
    max_concurrent_executions = 0

    async def slow_mock_request(*args, **kwargs):
        """A mock request that simulates network delay and tracks concurrency."""

        nonlocal concurrent_executions, max_concurrent_executions

        concurrent_executions += 1
        max_concurrent_executions = max(
            max_concurrent_executions, concurrent_executions
        )

        # Hard work
        await asyncio.sleep(0.5)

        concurrent_executions -= 1
        return "packet"

    serial_client._spinel_client.request = AsyncMock(side_effect=slow_mock_request)

    tasks = [
        serial_client.write_command(addr=1, inst=2, context="Test1"),
        serial_client.write_command(addr=1, inst=2, context="Test2"),
        serial_client.write_command(addr=1, inst=2, context="Test3"),
    ]

    results = await asyncio.gather(*tasks)

    assert results == ["packet", "packet", "packet"]
    assert serial_client._spinel_client.request.call_count == 3

    # If the lock works, the max concurrent executions will be exactly 1.
    # If the lock was missing, max_concurrent_executions would be 3.
    assert max_concurrent_executions == 1


async def test_get_info(serial_client):
    """Test get_info calls write_command with correct instruction."""

    serial_client.write_command = AsyncMock(return_value="info_packet")
    result = await serial_client.get_info(address=1, context="Test")

    assert result == "info_packet"
    serial_client.write_command.assert_called_once_with(1, INST_INFO, "Test")


async def test_get_man_data(serial_client):
    """Test get_man_data calls write_command with correct instruction."""

    serial_client.write_command = AsyncMock(return_value="man_packet")
    result = await serial_client.get_man_data(address=1, context="Test")

    assert result == "man_packet"
    serial_client.write_command.assert_called_once_with(1, INST_SN, "Test")


async def test_get_location(serial_client):
    """Test get_location calls write_command with correct instruction."""

    serial_client.write_command = AsyncMock(return_value="loc_packet")
    result = await serial_client.get_location(address=1, context="Test")

    assert result == "loc_packet"
    serial_client.write_command.assert_called_once_with(1, INST_LOC, "Test")


async def test_set_address_success(serial_client):
    """Test correct byte parsing and execution of set_address."""
    serial_client.write_command = AsyncMock()

    await serial_client.set_address(5, "0123/45678", "Test")

    serial_client.write_command.assert_called_once_with(
        SERIAL_BROADCAST_ADDRESS, INST_NEW_ADDR, "Test", data=b"\x05\x00\x7b\xb2\x6e"
    )


@pytest.mark.parametrize(
    "new_address, serial_number, exception",
    [
        ("5", "0123/45678", DeviceLogicError),
        (5, 12345678, DeviceLogicError),
        (5, None, DeviceLogicError),
        (-1, "0123/45678", DeviceLogicError),
        (256, "0123/45678", DeviceLogicError),
        (5, "0123-45678", DeviceParseError),
        (5, "0123/456/78", DeviceParseError),
        (5, "abcd/efgh", DeviceParseError),
        (5, "/45678", DeviceParseError),
        (5, "0123/", DeviceParseError),
        (5, "", DeviceParseError),
    ],
)
async def test_set_address_invalid_args(
    serial_client, new_address, serial_number, exception
):
    """Test validation of arguments and formats in set_address."""

    serial_client.write_command = AsyncMock()

    with pytest.raises(exception):
        await serial_client.set_address(new_address, serial_number, "Test context")

    serial_client.write_command.assert_not_called()
