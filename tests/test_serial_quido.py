# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for QuidoRS485 (serial) device."""

from unittest.mock import AsyncMock

import pytest
from aiopapouch.devices.quido import (
    INST_COUNTER_MODE_READ,
    INST_COUNTER_MODE_WRITE,
    INST_INFO_DATA_QUIDO,
    INST_SUBTRACT_COUNTER,
    INST_WRITE_OUTPUT,
    INST_WRITE_OUTPUT_TIME,
    QuidoRS485,
    QuidoSerialConfiguration,
    async_setup_serial_quido,
)
from aiopapouch.exceptions import DeviceLogicError, DeviceParseError

from pap_spinel import ACK_FAILURE


class MockPacket:
    """Mock for Spinel packet returned by serial client."""

    def __init__(self, data=b"", ack=0):
        self.data = data
        self._ack = ack

    def ack_code(self):
        """Get mocked ACK."""
        return self._ack


@pytest.fixture
def serial_client():
    """Mock serial client."""
    return AsyncMock()


@pytest.fixture
def mock_quido(serial_client):
    """Fixture providing an initialized QuidoRS485 with 4 I/Os."""
    conf = QuidoSerialConfiguration(
        number_inputs=4,
        number_outputs=4,
        location="Serial Loc",
        name="Quido RS",
        identifier="SN123",
        context="Quido RS - SN: SN123",
        address=1,
        counter_states={
            "1": "off",
            "2": "counts_descending_edges",
            "3": "counts_ascending_edges",
            "4": "counts_ascending_and_descending_edges",
        },
    )
    return QuidoRS485(serial_client, conf)


@pytest.mark.asyncio
async def test_async_setup_serial_quido_success(serial_client):
    """Test full setup pipeline for serial Quido."""

    def mock_write_command(addr, inst, ctx, payload=b""):
        if inst == INST_INFO_DATA_QUIDO:
            return MockPacket(b"\x04\x04\x00")
        if inst == INST_COUNTER_MODE_READ:
            return MockPacket(b"\x00\x40\x80\xc0")
        raise DeviceLogicError("Neumíš psat testy?")

    serial_client.write_command.side_effect = mock_write_command

    device = await async_setup_serial_quido(
        serial_client,
        address=1,
        serial_number="0123/4567",
        device_name="Quido 4/4",
        location="Rozvadeč",
    )

    assert isinstance(device, QuidoRS485)
    assert device.conf.number_outputs == 4
    assert device.conf.number_inputs == 4
    assert device.conf.counter_states["1"] == "off"
    assert device.conf.counter_states["2"] == "counts_descending_edges"
    assert device.conf.counter_states["3"] == "counts_ascending_edges"
    assert device.conf.counter_states["4"] == "counts_ascending_and_descending_edges"


@pytest.mark.parametrize(
    "method, payload, expected_error",
    [
        (QuidoRS485.get_number_io, b"\x04\x04", DeviceParseError),  # short payload
        (QuidoRS485.get_modes_counters, b"\x00\x40", DeviceParseError),  # short payload
    ],
)
@pytest.mark.asyncio
async def test_static_setup_methods_invalid_payload(
    serial_client, mock_quido, method, payload, expected_error
):
    """Test DeviceParseError when setup methods receive malformed data."""
    serial_client.write_command.return_value = MockPacket(payload)

    with pytest.raises(expected_error):
        if method == QuidoRS485.get_number_io:
            await method(serial_client, 1, "ctx")
        else:
            await method(serial_client, mock_quido.conf)


@pytest.mark.parametrize(
    "method_name, payload, expected, expected_exc",
    [
        ("get_state_coils", b"\x0a", {"1": 0, "2": 1, "3": 0, "4": 1}, None),
        ("get_state_coils", b"", None, DeviceParseError),
        ("_get_inputs", b"\x05", {"1": 1, "2": 0, "3": 1, "4": 0}, None),
        ("_get_inputs", b"", None, DeviceParseError),
        (
            "get_counters",
            b"\x10\x00\x0a\x00\x14\x00\x1e\x00\x28",
            {"pulses_1": 10, "pulses_2": 20, "pulses_3": 30, "pulses_4": 40},
            None,
        ),
        ("get_counters", b"", None, DeviceParseError),
        ("get_counters", b"\x10\x00\x0a\x00\x14\x00\x1e", None, DeviceParseError),
    ],
)
@pytest.mark.asyncio
async def test_io_parsing(
    mock_quido, serial_client, method_name, payload, expected, expected_exc
):
    """Test parsing logic for coils, inputs, and counters."""
    serial_client.write_command.return_value = MockPacket(payload)
    func = getattr(mock_quido, method_name)

    if expected_exc:
        with pytest.raises(expected_exc):
            await func()
    else:
        assert await func() == expected


@pytest.mark.parametrize(
    "payload, ack, expected, expected_exc",
    [
        (b"\x00\x00\xfa", 0, 25.0, None),
        (b"\x00\xff\x9c", 0, -10.0, None),
        (b"", ACK_FAILURE, None, None),
        (b"\x00", 0, None, DeviceParseError),
    ],
)
@pytest.mark.asyncio
async def test_get_temp(
    mock_quido, serial_client, payload, ack, expected, expected_exc
):
    """Test parsing temperature including negative values and errors."""
    serial_client.write_command.return_value = MockPacket(payload, ack=ack)

    if expected_exc:
        with pytest.raises(expected_exc):
            await mock_quido._get_temp()
    else:
        assert await mock_quido._get_temp() == expected


@pytest.mark.asyncio
async def test_get_fresh_data_aggregation(mock_quido, serial_client):
    """Test get_fresh_data aggregates coils, inputs, counters, and temp."""
    mock_quido.get_state_coils = AsyncMock(return_value={"1": 1})
    mock_quido._get_inputs = AsyncMock(return_value={"1": 0})
    mock_quido.get_counters = AsyncMock(return_value={"pulses_1": 10})
    mock_quido._get_temp = AsyncMock(return_value=22.5)

    serial_client.write_command.return_value = MockPacket(b"\x00\x01")

    data = await mock_quido.get_fresh_data()

    assert data["switch"] == {"1": 1}
    assert data["input"] == {"1": 0}
    assert data["counter"] == {"pulses_1": 10}
    assert data["temperature"]["temperature_1"] == 22.5
    assert mock_quido.conf.temperature_unit == "1"


@pytest.mark.parametrize(
    "unit_packet, expected_exc",
    [
        (b"\x01\xff", DeviceLogicError),
        (b"\x01\x03", DeviceLogicError),
        (b"\xff", DeviceParseError),
        (b"", DeviceParseError),
        (b"\x00\x00\x00", DeviceParseError),
    ],
)
@pytest.mark.asyncio
async def test_process_invalid_units(
    mock_quido, serial_client, unit_packet, expected_exc
):
    """Test _process_unit handles invalid packets correctly."""
    serial_client.write_command.return_value = MockPacket(unit_packet)

    with pytest.raises(expected_exc):
        await mock_quido._process_unit()


@pytest.mark.parametrize(
    "method_name, item_id, expected_payload",
    [
        ("turn_on_switch", "2", b"\x82"),
        ("turn_off_switch", "3", b"\x03"),
    ],
)
@pytest.mark.asyncio
async def test_turn_on_off_commands(
    mock_quido, serial_client, method_name, item_id, expected_payload
):
    """Test individual switch turning on and off."""

    func = getattr(mock_quido, method_name)
    await func(item_id)

    serial_client.write_command.assert_called_with(
        1, INST_WRITE_OUTPUT, mock_quido.conf.context, expected_payload
    )


@pytest.mark.asyncio
async def test_connect_disconnect_all_coils(mock_quido):
    """Test logic evaluating current states to turn on/off all coils."""
    mock_quido.get_state_coils = AsyncMock(return_value={"1": 0, "2": 1})

    mock_quido.turn_on_switch = AsyncMock()
    await mock_quido.connect_all_coils()
    mock_quido.turn_on_switch.assert_called_once_with("1")

    mock_quido.turn_off_switch = AsyncMock()
    await mock_quido.disconnect_all_coils()
    mock_quido.turn_off_switch.assert_called_once_with("2")


@pytest.mark.parametrize(
    "category, item_id, value, ack, expected_inst, expected_payload, expected_exc",
    [
        ("decrease_counter", "2", 15, 0, INST_SUBTRACT_COUNTER, b"\x02\x00\x0f", None),
        (
            "decrease_counter",
            "1",
            50,
            2,
            INST_SUBTRACT_COUNTER,
            b"\x01\x00\x32",
            DeviceLogicError,
        ),  # ACK error
        ("output_on_duration", "3", 10.0, 0, INST_WRITE_OUTPUT_TIME, b"\x14\x83", None),
        (
            "output_off_duration",
            "3",
            500.0,
            0,
            INST_WRITE_OUTPUT_TIME,
            b"\xff\x03",
            None,
        ),  # max limit clamp
        (
            "output_on_duration",
            "1",
            0.1,
            0,
            INST_WRITE_OUTPUT_TIME,
            b"\x01\x81",
            None,
        ),  # min limit clamp
        ("invalid", "1", 10.0, 0, None, None, DeviceLogicError),
    ],
)
@pytest.mark.asyncio
async def test_set_number_values(
    mock_quido,
    serial_client,
    category,
    item_id,
    value,
    ack,
    expected_inst,
    expected_payload,
    expected_exc,
):
    """Test setting diverse number values, including bounding boxes and errors."""
    serial_client.write_command.return_value = MockPacket(ack=ack)

    if expected_exc:
        with pytest.raises(expected_exc):
            await mock_quido.set_number_value(category, item_id, value)
    else:
        await mock_quido.set_number_value(category, item_id, value)
        serial_client.write_command.assert_called_with(
            1, expected_inst, mock_quido.conf.context, expected_payload
        )


@pytest.mark.parametrize(
    "category, item_id, option, expected_payload, expected_exc",
    [
        ("counter_mode", "1", "counts_descending_edges", b"\x41", None),
        ("counter_mode", "invalid_item", "off", None, DeviceLogicError),
        ("counter_mode", "1", "invalid_mode", None, DeviceLogicError),
        ("invalid", "1", "off", None, DeviceLogicError),
    ],
)
@pytest.mark.asyncio
async def test_set_select_options_logic(
    mock_quido, serial_client, category, item_id, option, expected_payload, expected_exc
):
    """Test setting options for counter modes."""
    serial_client.write_command.return_value = MockPacket(ack=0)

    if expected_exc:
        with pytest.raises(expected_exc):
            await mock_quido.set_select_option(category, item_id, option)
    else:
        await mock_quido.set_select_option(category, item_id, option)
        serial_client.write_command.assert_called_with(
            1, INST_COUNTER_MODE_WRITE, mock_quido.conf.context, expected_payload
        )
        assert mock_quido.conf.counter_states[item_id] == option


@pytest.mark.asyncio
async def test_get_select_option_errors(mock_quido):
    """Test getting invalid select options."""

    assert (
        mock_quido.get_select_option("counter_mode", "2") == "counts_descending_edges"
    )

    with pytest.raises(DeviceLogicError):
        mock_quido.get_select_option("invalid", "1")

    with pytest.raises(DeviceLogicError):
        mock_quido.get_select_option("counter_mode", "1999")


@pytest.mark.asyncio
async def test_switch_to_web_mode(mock_quido):
    """Test switch to web mode raises logic error for serial device."""

    with pytest.raises(DeviceLogicError):
        await mock_quido.switch_to_web_mode()


@pytest.mark.asyncio
async def test_reset_all_counters_chunking(mock_quido, serial_client):
    """Test that resetting counters splits payload correctly into max 12-item chunks."""

    serial_client.write_command.return_value = MockPacket(ack=0)
    mock_quido.conf.number_inputs = 14
    counters = {f"pulses_{i}": 10 for i in range(1, 15)}
    mock_quido.get_counters = AsyncMock(return_value=counters)

    await mock_quido.reset_all_counters()

    assert serial_client.write_command.call_count == 2

    payload1 = serial_client.write_command.call_args_list[0][0][3]
    payload2 = serial_client.write_command.call_args_list[1][0][3]

    assert len(payload1) == 36
    assert len(payload2) == 6

    assert payload1[0:3] == b"\x01\x00\x0a"
    assert payload2[0:3] == b"\x0d\x00\x0a"


@pytest.mark.asyncio
async def test_reset_all_counters_missing_key(mock_quido):
    """Test defensive check when a counter is inexplicably missing from the dictionary."""

    incomplete_counters = {"pulses_1": 10}
    mock_quido.get_counters = AsyncMock(return_value=incomplete_counters)

    with pytest.raises(DeviceLogicError):
        await mock_quido.reset_all_counters()
