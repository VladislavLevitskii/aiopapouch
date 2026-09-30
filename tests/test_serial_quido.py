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
    client = AsyncMock()
    return client


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


@pytest.mark.asyncio
async def test_get_number_io_invalid_payload(serial_client):
    """Test DeviceParseError when get_number_io receives malformed data."""
    serial_client.write_command.return_value = MockPacket(b"\x04\x04")
    with pytest.raises(DeviceParseError):
        await QuidoRS485.get_number_io(serial_client, 1, "ctx")


@pytest.mark.asyncio
async def test_get_modes_counters_invalid_payload(serial_client, mock_quido):
    """Test DeviceParseError when get_modes_counters receives less bytes than inputs."""
    serial_client.write_command.return_value = MockPacket(b"\x00\x40")

    with pytest.raises(DeviceParseError):
        await QuidoRS485.get_modes_counters(serial_client, mock_quido.conf)


@pytest.mark.asyncio
async def test_get_state_coils_success(mock_quido, serial_client):
    """Test parsing bits for output coils."""
    serial_client.write_command.return_value = MockPacket(b"\x0a")
    result = await mock_quido._get_state_coils()
    assert result == {"1": 0, "2": 1, "3": 0, "4": 1}


@pytest.mark.asyncio
async def test_get_state_coils_short_payload(mock_quido, serial_client):
    """Test _get_state_coils raises error on empty payload."""
    serial_client.write_command.return_value = MockPacket(b"")
    with pytest.raises(DeviceParseError):
        await mock_quido._get_state_coils()


@pytest.mark.asyncio
async def test_get_inputs_success(mock_quido, serial_client):
    """Test parsing bits for inputs."""
    serial_client.write_command.return_value = MockPacket(b"\x05")
    result = await mock_quido._get_inputs()
    assert result == {"1": 1, "2": 0, "3": 1, "4": 0}


@pytest.mark.asyncio
async def test_get_inputs_short_payload(mock_quido, serial_client):
    """Test _get_inputs raises error on empty payload."""
    serial_client.write_command.return_value = MockPacket(b"")
    with pytest.raises(DeviceParseError):
        await mock_quido._get_inputs()


@pytest.mark.asyncio
async def test_get_temp_success(mock_quido, serial_client):
    """Test parsing temperature including negative values (signed bytes)."""
    serial_client.write_command.return_value = MockPacket(b"\x00\x00\xfa")
    assert await mock_quido._get_temp() == 25.0

    serial_client.write_command.return_value = MockPacket(b"\x00\xff\x9c")
    assert await mock_quido._get_temp() == -10.0


@pytest.mark.asyncio
async def test_get_temp_disconnected(mock_quido, serial_client):
    """Test disconnected thermometer returns None."""

    serial_client.write_command.return_value = MockPacket(b"", ack=ACK_FAILURE)
    assert await mock_quido._get_temp() is None


@pytest.mark.asyncio
async def test_get_temp_short_payload(mock_quido, serial_client):
    """Test _get_temp raises error on short payload."""

    serial_client.write_command.return_value = MockPacket(b"\x00")

    with pytest.raises(DeviceParseError):
        await mock_quido._get_temp()


@pytest.mark.asyncio
async def test_get_counters_success(mock_quido, serial_client):
    """Test parsing 16-bit counters."""
    data = b"\x10" + b"\x00\x0a" + b"\x00\x14" + b"\x00\x1e" + b"\x00\x28"
    serial_client.write_command.return_value = MockPacket(data)

    counters = await mock_quido._get_counters()

    assert counters["pulses_1"] == 10
    assert counters["pulses_2"] == 20
    assert counters["pulses_3"] == 30
    assert counters["pulses_4"] == 40


@pytest.mark.asyncio
async def test_get_counters_empty_and_short(mock_quido, serial_client):
    """Test _get_counters errors for bad payloads."""
    serial_client.write_command.return_value = MockPacket(b"")
    with pytest.raises(DeviceParseError):
        await mock_quido._get_counters()

    data = b"\x10" + b"\x00\x0a" + b"\x00\x14" + b"\x00\x1e"
    serial_client.write_command.return_value = MockPacket(data)
    with pytest.raises(DeviceParseError):
        await mock_quido._get_counters()


@pytest.mark.asyncio
async def test_get_fresh_data_aggregation(mock_quido, serial_client):
    """Test get_fresh_data aggregates coils, inputs, counters, and temp."""

    mock_quido._get_state_coils = AsyncMock(return_value={"1": 1})
    mock_quido._get_inputs = AsyncMock(return_value={"1": 0})
    mock_quido._get_counters = AsyncMock(return_value={"pulses_1": 10})
    mock_quido._get_temp = AsyncMock(return_value=22.5)

    serial_client.write_command.return_value = MockPacket(b"\x01\x01")

    data = await mock_quido.get_fresh_data()

    assert data["switch"] == {"1": 1}
    assert data["input"] == {"1": 0}
    assert data["counter"] == {"pulses_1": 10}
    assert data["temperature"]["temperature_1"] == 22.5
    assert mock_quido.conf.temperature_unit == "1"


@pytest.mark.parametrize(
    "unit",
    [b"\xff", b"\x03", b"\x42"],
)
@pytest.mark.asyncio
async def test_process_invalid_units(mock_quido, serial_client, unit):
    """Test get_fresh_data aggregates coils, inputs, counters, and temp."""

    return_packet = b"\x01" + unit

    serial_client.write_command.return_value = MockPacket(return_packet)

    with pytest.raises(DeviceLogicError):
        await mock_quido._process_unit()


@pytest.mark.parametrize(
    "unit_packet",
    [b"\xff", b"\x00", b"", b"\x00\x00\x00"],
)
@pytest.mark.asyncio
async def test_process_invalid_length_unit(mock_quido, serial_client, unit_packet):
    """Test get_fresh_data aggregates coils, inputs, counters, and temp."""

    serial_client.write_command.return_value = MockPacket(unit_packet)

    with pytest.raises(DeviceParseError):
        await mock_quido._process_unit()


@pytest.mark.asyncio
async def test_switch_and_coil_commands(mock_quido, serial_client):
    """Test turning on/off individual and all coils."""

    await mock_quido.turn_on_switch("2")
    # 0x80 | 2 = 0x82 (130) -> 0-based for output writes isn't clear from documentation,
    # but based on your ETH code it seems they might be 1-based. We test as is.
    serial_client.write_command.assert_called_with(
        1, INST_WRITE_OUTPUT, mock_quido.conf.context, b"\x82"
    )

    await mock_quido.turn_off_switch("3")
    serial_client.write_command.assert_called_with(
        1, INST_WRITE_OUTPUT, mock_quido.conf.context, b"\x03"
    )

    mock_quido._get_state_coils = AsyncMock(return_value={"1": 0, "2": 1})
    mock_quido.turn_on_switch = AsyncMock()
    await mock_quido._connect_all_coils()
    mock_quido.turn_on_switch.assert_called_once_with("1")

    mock_quido.turn_off_switch = AsyncMock()
    await mock_quido._disconnect_all_coils()
    mock_quido.turn_off_switch.assert_called_once_with("2")


@pytest.mark.asyncio
async def test_number_values(mock_quido, serial_client):
    """Test decreasing counters and setting duration."""

    serial_client.write_command.return_value = MockPacket(ack=0)

    await mock_quido.set_number_value("decrease_counter", "2", 15)

    expected_payload = b"\x02\x00\x0f"
    serial_client.write_command.assert_called_with(
        1, INST_SUBTRACT_COUNTER, mock_quido.conf.context, expected_payload
    )

    await mock_quido.set_number_value("output_on_duration", "3", 10.0)
    serial_client.write_command.assert_called_with(
        1, INST_WRITE_OUTPUT_TIME, mock_quido.conf.context, b"\x14\x83"
    )

    await mock_quido.set_number_value("output_off_duration", "3", 500.0)
    serial_client.write_command.assert_called_with(
        1, INST_WRITE_OUTPUT_TIME, mock_quido.conf.context, b"\xff\x03"
    )

    with pytest.raises(DeviceLogicError):
        await mock_quido.set_number_value("invalid", "1", 10.0)


@pytest.mark.asyncio
async def test_decrease_counter_error_ack(mock_quido, serial_client):
    """Test decrease counter raises error when ACK is non-zero."""
    serial_client.write_command.return_value = MockPacket(ack=2)
    with pytest.raises(DeviceLogicError):
        await mock_quido.set_number_value("decrease_counter", "1", 50)


@pytest.mark.asyncio
async def test_select_options_logic(mock_quido, serial_client):
    """Test select options for counter modes."""

    serial_client.write_command.return_value = MockPacket(ack=0)

    assert (
        mock_quido.get_select_option("counter_mode", "2") == "counts_descending_edges"
    )
    with pytest.raises(DeviceLogicError):
        mock_quido.get_select_option("invalid", "1")

    await mock_quido.set_select_option("counter_mode", "1", "counts_descending_edges")
    serial_client.write_command.assert_called_with(
        1, INST_COUNTER_MODE_WRITE, mock_quido.conf.context, b"\x41"
    )
    assert mock_quido.conf.counter_states["1"] == "counts_descending_edges"

    with pytest.raises(DeviceLogicError):
        await mock_quido.set_select_option("invalid", "1", "off")


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
    mock_quido._get_counters = AsyncMock(return_value=counters)

    await mock_quido._reset_all_counters()

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
    mock_quido._get_counters = AsyncMock(return_value=incomplete_counters)

    with pytest.raises(DeviceLogicError):
        await mock_quido._reset_all_counters()
