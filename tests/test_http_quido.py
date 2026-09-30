# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for QuidoETH device."""

import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch

import pytest
from aiopapouch.devices.quido import QuidoETH, async_setup_network_quido
from aiopapouch.exceptions import (
    DeviceLogicError,
    DeviceParseError,
)

VALID_QUIDO_INFO = """
<root><heartbeat level="1" location="NONAME" ver="85" lang="e" unit="C" device="Quido ETH 4/4" mode="3" mobile="1"/></root>
"""

VALID_QUIDO_SETTINGS = """
<root>
<set box="1" dhcp="0" ip="192.168.3.40" mask="255.255.240.0" gate="192.168.1.201" dip="192.168.1.201" wport="80" lport="10001" rip="192.168.1.50" rport="19999" mport="502" mode="3" single="0" sx_aut="0" tcpto="0"/>
<set box="2" telnet="1" upd="1" mobile="0" usrset="0" admset="0"/>
<set box="3" enbmail="0" domain="" ip="0.0.0.0" sport="25" from="" to="" enbwatch="0" enbch="0" enbauth="0"/>
<set box="4" enb="1" ip="0.0.0.0" enbtrap="0" enbwatch="0" enbch="0" readcom="public" writecom="private"/>
<set box="5" domain="" ip="192.168.1.21" port="8090" changes="1" per="0" path="/change"/>
<set box="8" name="NONAME" units="C"/>
<set box="10">
<item id="1" name="" hide="0" change="0" sampl="20" cnt="0" on="2" off="4"/>
<item id="2" name="asd" hide="0" change="1" sampl="20" cnt="0" on="10" off="12"/>
<item id="3" name="" hide="0" change="0" sampl="20" cnt="0" on="9" off="5"/>
<item id="4" name="" hide="0" change="1" sampl="20" cnt="3" on="3" off="4"/>
</set>
<set box="11">
<item id="1" name="" hide="0" change="0" on="3" off="4" mde="0" len="1" tx="1250" ty="-550" tend="0" nosns="0"/>
<item id="2" name="" hide="0" change="1" on="3" off="4" mde="0" len="0" tx="1250" ty="-550" tend="0" nosns="0"/>
<item id="3" name="" hide="0" change="1" on="3" off="4" mde="0" len="0" tx="1250" ty="-550" tend="0" nosns="0"/>
<item id="4" name="" hide="0" change="1" on="3" off="4" mde="0" len="0" tx="1250" ty="-550" tend="0" nosns="0"/>
</set>
<set box="13">
<item id="1" hide="0" enbw="1" th="40.0" tl="5.0" hys="1.0" snd="0"/>
</set>
<set box="12" mac="00:80:A3:F7:60:FB" sn="00254/05881" info="Quido ETH 4/4; v0254.04.51; f66 97; t1"/>
</root>
"""

VALID_QUIDO_DATA = """
<root>
<din id="1" name="" sts="0" val="0" pic="4" cmo="0" cnt="0"/>
<din id="2" name="asd" sts="0" val="0" pic="12" cmo="0" cnt="0"/>
<din id="3" name="" sts="0" val="0" pic="5" cmo="0" cnt="0"/>
<din id="4" name="" sts="0" val="1" pic="4" cmo="3" cnt="5"/>
<dout id="1" name="" sts="0" val="1" pic="4" mde="0" pars="1;0;1250;-550;1"/>
<dout id="2" name="" sts="0" val="0" pic="4" mde="0" pars="1;0;1250;-550;0"/>
<dout id="3" name="" sts="0" val="0" pic="4" mde="0" pars="1;0;1250;-550;0"/>
<dout id="4" name="" sts="0" val="0" pic="4" mde="0" pars="1;0;1250;-550;0"/>
<temp id="1" sts="0" val="31.6" tenb="1" th="40.0" tl="5.0"/>
<status location="NONAME"/>
</root>
"""

DISCONNECTED_TEMP_DATA = """
<root>
<din id="1" name="" sts="0" val="0" pic="4" cmo="0" cnt="0"/>
<dout id="1" name="" sts="0" val="0" pic="4" mde="0" pars="1;0;1250;-550;1"/>
<temp id="1" sts="4" val="" tenb="1" th="40.0" tl="5.0"/>
<status location="NONAME"/>
</root>
"""


@pytest.fixture
def http_client():
    """Mock HTTP client returning real valid base XMLs."""

    client = AsyncMock()
    client.fetch_settings.return_value = VALID_QUIDO_SETTINGS
    client.fetch_info.return_value = VALID_QUIDO_INFO
    client.fetch_data.return_value = VALID_QUIDO_DATA
    client.ip_address = "192.168.3.40"
    client.get_device_info.return_value = ("Quido ETH 4/4", "NONAME")
    return client


@pytest.mark.asyncio
async def test_async_setup_network_quido_success(http_client):
    """Test successful initialization of QuidoETH using real XML."""

    device = await async_setup_network_quido(http_client)

    assert isinstance(device, QuidoETH)
    assert device.conf.name == "Quido ETH 4/4"
    assert device.conf.location == "NONAME"
    assert device.conf.identifier == "00:80:A3:F7:60:FB"
    assert device.conf.number_inputs == 4
    assert device.conf.number_outputs == 4
    assert device.conf.temperature_unit == "0"

    assert device.conf.counter_states["4"] == "counts_ascending_and_descending_edges"


@pytest.mark.asyncio
async def test_async_setup_network_quido_invalid_xml(http_client):
    """Test DeviceParseError is raised when settings.xml is invalid."""

    http_client.fetch_settings.return_value = "INVALID_XML"

    with pytest.raises(DeviceParseError):
        await async_setup_network_quido(http_client)


@pytest.mark.asyncio
async def test_parse_initial_settings_errors(http_client):
    """Test various errors during initial settings parsing."""

    http_client.fetch_settings.return_value = '<root><set box="12" /></root>'
    with pytest.raises(DeviceParseError):
        await async_setup_network_quido(http_client)

    http_client.fetch_settings.return_value = """
    <root>
        <set box="10"><item id="1" cnt="invalid" /></set>
        <set box="12" mac="00:11:22:33:44:55" />
    </root>
    """

    with pytest.raises(DeviceLogicError):
        await async_setup_network_quido(http_client)

    http_client.fetch_settings.return_value = """
    <root>
        <set box="10"><item cnt="0" /></set>
        <set box="12" mac="00:11:22:33:44:55" />
    </root>
    """
    with pytest.raises(DeviceParseError):
        await async_setup_network_quido(http_client)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unit, expected",
    [
        ("C", "0"),
        ("F", "1"),
        ("K", "2"),
    ],
)
async def test_temperature_units_parsing(http_client, unit, expected):
    """Test that temperature units are resolved correctly."""

    http_client.fetch_settings.return_value = f"""
    <root>
        <set box="8" units="{unit}" />
        <set box="12" mac="00:11:22:33:44:55" />
    </root>
    """
    device = await async_setup_network_quido(http_client)
    assert device.conf.temperature_unit == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unit",
    ["", "invalid", "0", "1"],
)
async def test_temperature_invalid_unit(http_client, unit):
    """Test that invalid temperature units lead to DeviceLogicError exception."""

    http_client.fetch_settings.return_value = f"""
    <root>
        <set box="8" units="{unit}" />
        <set box="12" mac="00:11:22:33:44:55" />
    </root>
    """

    with pytest.raises(DeviceLogicError):
        await async_setup_network_quido(http_client)


@pytest.mark.asyncio
async def test_get_supported_entities(http_client):
    """Test base mappings for buttons, sensors, switches, numbers and selects."""

    device = await async_setup_network_quido(http_client)

    buttons = device.get_supported_buttons()
    assert len(buttons) == 3
    assert buttons[0]["cmd"] == "connect_all_coils"

    bins = device.get_supported_binary_sensors()
    assert len(bins) == 4
    assert bins[0]["item_id"] == "1"

    nums = device.get_supported_numbers()
    assert len(nums) == 12
    assert nums[0]["category"] == "decrease_counter"
    assert nums[4]["category"] == "output_on_duration"

    sensors = device.get_supported_sensors()
    assert len(sensors) == 5
    assert sensors[0]["type"] == "temperature"
    assert sensors[1]["type"] == "counter"

    switches = device.get_supported_switches()
    assert len(switches) == 4

    selects = device.get_supported_selects()
    assert len(selects) == 4
    assert selects[0]["category"] == "counter_mode"


@pytest.mark.asyncio
async def test_execute_button_command(http_client):
    """Test routing of execute_button_command."""
    device = await async_setup_network_quido(http_client)
    device._send_command = AsyncMock()

    await device.execute_button_command("connect_all_coils")
    device._send_command.assert_called_with("S")

    await device.execute_button_command("disconnect_all_coils")
    device._send_command.assert_called_with("R")

    await device.execute_button_command("reset_all_counters")
    device._send_command.assert_called_with("C")

    with pytest.raises(DeviceLogicError):
        await device.execute_button_command("invalid")


@pytest.mark.asyncio
async def test_turn_on_off_switch(http_client):
    """Test turning switches on and off."""
    device = await async_setup_network_quido(http_client)
    device._send_command = AsyncMock()

    await device.turn_on_switch("1")
    device._send_command.assert_called_with("s", "1")

    await device.turn_off_switch("4")
    device._send_command.assert_called_with("r", "4")


@pytest.mark.asyncio
async def test_get_fresh_data_success(http_client):
    """Test proper parsing of fresh XML data using real Quido data."""

    device = await async_setup_network_quido(http_client)
    data = await device.get_fresh_data()

    assert data["temperature"]["temperature_1"] == 31.6
    assert data["input"]["1"] == 0
    assert data["input"]["4"] == 1
    assert data["counter"]["pulses_4"] == 5
    assert data["switch"]["1"] == 1
    assert data["switch"]["2"] == 0


@pytest.mark.asyncio
async def test_get_fresh_data_disconnected_temp(http_client):
    """Test behavior when the thermometer is disconnected (sts=4, val='')."""

    device = await async_setup_network_quido(http_client)
    http_client.fetch_data.return_value = DISCONNECTED_TEMP_DATA

    data = await device.get_fresh_data()

    assert data["temperature"]["temperature_1"] is None


@pytest.mark.asyncio
async def test_get_fresh_data_invalid_xml(http_client):
    """Test DeviceParseError on invalid fresh XML."""

    device = await async_setup_network_quido(http_client)
    http_client.fetch_data.return_value = "NOT_XML"

    with pytest.raises(DeviceParseError):
        await device.get_fresh_data()


@pytest.mark.asyncio
async def test_get_fresh_data_missing_id_and_value_errors(http_client):
    """Test elements without ID are skipped, and ValueError returns None."""

    device = await async_setup_network_quido(http_client)
    http_client.fetch_data.return_value = """
    <root>
        <status level="0" /> <!-- No ID, should skip -->
        <temp id="1" val="invalid_float" />
        <din id="1" val="invalid_int" cnt="invalid_int" />
        <dout id="1" val="" />
    </root>
    """

    data = await device.get_fresh_data()

    assert data["temperature"]["temperature_1"] is None
    assert data["input"]["1"] is None
    assert data["counter"]["pulses_1"] is None
    assert data["switch"]["1"] is None


@pytest.mark.asyncio
async def test_get_fresh_data_missing_attributes(http_client):
    """Test require_attr triggers DeviceParseError if strict attributes are missing."""
    device = await async_setup_network_quido(http_client)

    http_client.fetch_data.return_value = '<root><temp id="1" /></root>'
    with pytest.raises(DeviceParseError):
        await device.get_fresh_data()

    http_client.fetch_data.return_value = '<root><din id="1" val="1" /></root>'
    with pytest.raises(DeviceParseError):
        await device.get_fresh_data()


@pytest.mark.asyncio
async def test_set_number_value(http_client):
    """Test setting numbers (counters and duration)."""

    device = await async_setup_network_quido(http_client)
    device._send_command = AsyncMock()

    await device.set_number_value("decrease_counter", "1", 50)
    device._send_command.assert_called_with("c", "1", "50")

    await device.set_number_value("output_on_duration", "1", 10.0)
    device._send_command.assert_called_with("s", item_id="1", time="20")

    await device.set_number_value("output_off_duration", "1", 200.0)
    device._send_command.assert_called_with("r", item_id="1", time="255")

    await device.set_number_value("output_on_duration", "1", 0.1)
    device._send_command.assert_called_with("s", item_id="1", time="1")

    with pytest.raises(DeviceLogicError):
        await device.set_number_value("invalid", "1", 10.0)


@pytest.mark.asyncio
async def test_select_options_logic(http_client):
    """Test getting and setting select options."""
    device = await async_setup_network_quido(http_client)

    assert device.get_select_option("counter_mode", "1") == "off"
    with pytest.raises(DeviceLogicError):
        device.get_select_option("invalid", "1")

    http_client.write_command.return_value = '<root><result status="1" /></root>'
    await device.set_select_option("counter_mode", "1", "counts_descending_edges")

    payload = http_client.write_command.call_args[0][0]
    assert 'num1="1"' in payload
    assert 'num4="1"' in payload
    assert device.conf.counter_states["1"] == "counts_descending_edges"

    with pytest.raises(DeviceParseError):
        await device.set_select_option("counter_mode", "99", "off")

    with pytest.raises(DeviceLogicError):
        await device.set_select_option("counter_mode", "1", "invalid_mode")

    with pytest.raises(DeviceLogicError):
        await device.set_select_option("invalid", "1", "off")


@pytest.mark.asyncio
@patch("aiopapouch.devices.quido.asyncio.sleep", new_callable=AsyncMock)
async def test_switch_to_web_mode(mock_sleep, http_client):
    """Test switching device to web mode."""

    device = await async_setup_network_quido(http_client)

    http_client.write_command.return_value = '<root><result status="1" /></root>'

    await device.switch_to_web_mode()

    payload = http_client.write_command.call_args[0][0]

    assert 'ip1="192.168.003.040"' in payload
    assert 'num3="3"' in payload
    assert 'num1="00080"' in payload

    device.settings_root = ET.fromstring("<root></root>")
    with pytest.raises(DeviceParseError):
        await device.switch_to_web_mode()
