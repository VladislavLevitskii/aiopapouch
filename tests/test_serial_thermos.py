# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for simple serial thermometers (THCO2, THT2, TQS4)."""

from inspect import iscoroutinefunction
from unittest.mock import AsyncMock

import pytest
from aiopapouch.devices.thco2 import THCO2, async_setup_serial_thco2
from aiopapouch.devices.tht2 import THT2, async_setup_serial_tht2
from aiopapouch.devices.tqs4 import TQS4, async_setup_serial_tqs4
from aiopapouch.exceptions import DeviceLogicError, DeviceParseError


class MockPacket:
    """Mock for Spinel packet returned by serial client."""

    def __init__(self, data=b""):
        self.data = data


@pytest.fixture
def serial_client():
    """Serial client mock"""
    return AsyncMock()


# THCO2 TESTS


@pytest.mark.asyncio
async def test_thco2_parsing(serial_client):
    """Test setup and parsing of THCO2 device."""

    serial_client.write_command.return_value = MockPacket(
        b"\x00\x01\x6f\x01\x04\x00\xdd\x00\x1a\x00\x38"
    )

    device = await async_setup_serial_thco2(serial_client, 1, "SN123", "THCO2", "Loc")
    data = await device.get_fresh_data()

    print(data)

    assert data["sensor"] == {
        "co2_1": 367,
        "temperature_2": 26.0,
        "humidity_3": 22.1,
        "dew_point_4": 2.6,
    }

    sensors = device.get_supported_sensors()
    assert len(sensors) == 4


@pytest.mark.parametrize(
    "payload, expected_error",
    [
        (b"", DeviceLogicError),
        (b"\x00\x03", DeviceLogicError),
        (
            b"\x00" + (b"\x00\x00" * 10),
            DeviceLogicError,
        ),
    ],
)
@pytest.mark.asyncio
async def test_thco2_parsing_errors(serial_client, payload, expected_error):
    """Test raising exception during parsing THCO2 data."""

    serial_client.write_command.return_value = MockPacket(payload)
    device = THCO2(serial_client, "N", "L", "SN", 1)
    with pytest.raises(expected_error):
        await device.get_fresh_data()


@pytest.mark.asyncio
async def test_thco2_status_not_zero(serial_client):
    """Test status different from 0."""

    serial_client.write_command.return_value = MockPacket(
        b"\x01\x03\x20\x00\x00\x00\x00\x00\x00\x00\x00"
    )
    device = THCO2(serial_client, "N", "L", "SN", 1)
    data = await device.get_fresh_data()
    assert data == {"sensor": {}}


# THT2 TESTS


@pytest.mark.parametrize(
    "side_effect_write_command",
    [MockPacket(b"\x00\x00"), MockPacket(b"")],
)
@pytest.mark.asyncio
async def test_tht2_parsing(serial_client, side_effect_write_command):
    """Test setup and parsing of THT2 device."""

    serial_client.write_command.side_effect = [
        side_effect_write_command,
        MockPacket(b"\x01\x80\x00\xfa\x02\x00\x00\x00"),
    ]

    device = await async_setup_serial_tht2(serial_client, 1, "SN", "THT2", "Loc")
    data = await device.get_fresh_data()

    assert data["sensor"]["temperature_1"] == 25.0
    assert data["sensor"]["humidity_2"] is None

    sensors = device.get_supported_sensors()
    assert len(sensors) == 2


@pytest.mark.parametrize(
    "payload, is_unit_call",
    [
        (b"\x00", True),
        (b"\x01\x80\x00", False),
    ],
)
@pytest.mark.asyncio
async def test_tht2_parsing_errors(serial_client, payload, is_unit_call):
    """Test raising exception during parsing THT2 data."""

    serial_client.write_command.return_value = MockPacket(payload)
    if is_unit_call:
        with pytest.raises(DeviceParseError):
            await async_setup_serial_tht2(serial_client, 1, "SN", "THT2", "Loc")
    else:
        device = THT2(serial_client, "N", "L", "SN", 1, None)
        with pytest.raises(DeviceLogicError):
            await device.get_fresh_data()


# TQS4 TESTS


@pytest.mark.asyncio
async def test_tqs4_parsing(serial_client):
    """Test setup and parsing of TQS4 device."""

    serial_client.write_command.return_value = MockPacket(b"\x01\x40")

    device = await async_setup_serial_tqs4(serial_client, 1, "SN", "TQS4", "Loc")
    data = await device.get_fresh_data()

    assert data["sensor"]["temperature_1"] == 10.0

    sensors = device.get_supported_sensors()
    assert len(sensors) == 1


# COMMON UNUSED METHODS TEST


@pytest.mark.parametrize(
    "method_name, args",
    [
        ("get_supported_buttons", ()),
        ("get_supported_binary_sensors", ()),
        ("get_supported_numbers", ()),
        ("get_supported_switches", ()),
        ("get_supported_selects", ()),
        ("execute_button_command", ("cmd",)),
        ("turn_on_switch", ("1",)),
        ("turn_off_switch", ("1",)),
        ("set_number_value", ("cat", "1", 1.0)),
        ("get_select_option", ("cat", "1")),
        ("set_select_option", ("cat", "1", "opt")),
        ("switch_to_web_mode", ()),
    ],
)
@pytest.mark.asyncio
async def test_unimplemented_methods(serial_client, method_name, args):
    """Test that all three simple devices raise or return empty on unimplemented methods."""

    devices = [
        THCO2(serial_client, "N", "L", "SN", 1),
        THT2(serial_client, "N", "L", "SN", 1, None),
        TQS4(serial_client, "N", "L", "SN", 1),
    ]

    for device in devices:
        func = getattr(device, method_name)
        if method_name.startswith("get_supported_"):
            if method_name != "get_supported_sensors":
                assert func(*args) == []
        else:
            with pytest.raises(DeviceLogicError):
                if iscoroutinefunction(func):
                    await func(*args)
                else:
                    func(*args)
