# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for TH2E device."""

import asyncio
from inspect import iscoroutinefunction
from unittest.mock import AsyncMock

import pytest
from aiopapouch.devices.th2e import TH2E, async_setup_network_th2e
from aiopapouch.exceptions import (
    DeviceLogicError,
    DeviceParseError,
    DeviceResponseError,
)

VALID_TH2E_SETTINGS = """
<root>
<set box="1" ip="192.168.2.233" mask="255.255.240.0" gate="192.168.1.201" dip="1.1.1.1" wport="80" lport="10001" mport="502" rip="0.0.0.0" rport="0" mode="3" com="6"/>
<set box="2" telnet="0" upd="0" mobile="0" usrset="0" admset="0"/>
<set box="3" enbmail="0" domain="" ip="0.0.0.0" sport="25" from="" to="" enbwatch="0" enbauth="0"/>
<set box="4" enb="0" ip="0.0.0.0" enbtrap="0" enbwatch="0" per="0" readcom="public" writecom="private"/>
<set box="5" enbhttp="1" domain="" ip="0.0.0.0" port="80" per="0" pathget="" pathpost=""/>
<set box="8" name="U Lukase" enbntp="1" domain="tik.cesnet.cz" ipntp="0.0.0.0" zone="186" daylight="1" units="0" ext="1"/>
<set box="9" typesens="1">
<sns id="1" enbwatch="0" max="123.8" min="-40.0" hyst="0.0" sns2mem="1" memhyst="25"/>
<sns id="2" enbwatch="0" max="100.0" min="0.0" hyst="0.0" sns2mem="1" memhyst="50"/>
<sns id="3" enbwatch="0" max="123.8" min="-40.0" hyst="0.0" sns2mem="0" memhyst="1"/>
</set>
<set box="12" mac="00:80:A3:5B:8B:41" sn="00436/17917" info="TH2E; v0436.04.08; f66 97; t1; h1; rtc" typesens="1"/>
<set box="13" mode="3" action="0" lapstart="0" stday="0" stdow="0" period="15"/>
</root>
"""

TH2E_DATA = """
<root>
<sns id="1" type="1" status="0" unit="0" val="17.9" w-min="" w-max="" e-min-val=" 0.5" e-max-val=" 38.2" e-min-dte="04/30/2026 05:52:51" e-max-dte="06/28/2026 15:47:32"/>
<sns id="2" type="2" status="0" unit="3" val="62.1" w-min="" w-max="" e-min-val=" 19.2" e-max-val=" 98.9" e-min-dte="05/29/2026 17:24:37" e-max-dte="06/13/2026 07:18:04"/>
<sns id="3" type="3" status="0" unit="0" val="10.5" w-min="" w-max="" e-min-val=" -8.0" e-max-val=" 21.5" e-min-dte="04/09/2026 13:46:03" e-max-dte="07/01/2026 08:58:01"/>
<status frm="1" location="U Lukase" time="10/06/2026 13:23:00" typesens="1"/>
</root>
"""


@pytest.fixture
def http_client():
    """Mock HTTP client for TH2E."""
    client = AsyncMock()
    client.ip_address = "192.168.2.233"
    client.get_device_mac.return_value = "00:80:A3:5B:8B:41"
    client.get_device_info.return_value = ("TH2E", "U Lukase")
    client.fetch_settings.return_value = VALID_TH2E_SETTINGS
    client.fetch_data.return_value = TH2E_DATA
    return client


@pytest.mark.asyncio
async def test_setup_network_th2e(http_client):
    """Test successful setup of TH2E network device."""

    device = await async_setup_network_th2e(http_client)
    assert isinstance(device, TH2E)
    assert device.conf.name == "TH2E"


@pytest.mark.asyncio
async def test_th2e_parsing(http_client):
    """Test parsing of fresh TH2E data."""

    device = await async_setup_network_th2e(http_client)
    data = await device.get_fresh_data()

    assert device.conf.sensor_type == 1
    assert data["sensor"]["temperature_1"] == 17.9
    assert data["sensor"]["humidity_2"] == 62.1
    assert data["sensor"]["dew_point_3"] == 10.5

    sensors = device.get_supported_sensors()
    assert len(sensors) == 3

    selects = device.get_supported_selects()
    assert len(selects) == 1
    assert selects[0]["category"] == "sensor_type"

    buttons = device.get_supported_buttons()
    assert len(buttons) == 1
    assert buttons[0]["cmd"] == "set_sensor"


@pytest.mark.asyncio
async def test_th2e_parsing_errors(http_client):
    """Test TH2E behavior with invalid XML data."""

    device = TH2E(http_client, VALID_TH2E_SETTINGS, "N", "L", "MAC")

    http_client.fetch_data.return_value = "NOT_XML"
    with pytest.raises(DeviceParseError):
        await device.get_fresh_data()

    http_client.fetch_data.return_value = (
        '<root><sns id="1" type="1" unit="0" status="0" val="err"/></root>'
    )
    with pytest.raises(DeviceParseError):
        await device.get_fresh_data()

    http_client.fetch_data.return_value = '<root><status typesens="1"/><sns id="1" type="1" unit="0" status="1" val="err"/></root>'
    data = await device.get_fresh_data()
    assert data["sensor"]["temperature_1"] is None


@pytest.mark.asyncio
async def test_th2e_set_sensor_type_and_buttons(http_client):
    """Test setting TH2E sensor type and corresponding button logic."""
    device = await async_setup_network_th2e(http_client)

    http_client.write_command.side_effect = [
        '<root><result status="4" typesens="2" /></root>',
        '<root><result status="2" /></root>',
    ]

    await device.execute_button_command("set_sensor")

    set_payload = http_client.write_command.call_args_list[1][0][0]

    assert 'str1="       -40"' in set_payload
    assert 'str2="     123.8"' in set_payload
    assert 'str3="         0"' in set_payload
    assert 'num3="00025"' in set_payload
    assert 'num2="48"' in set_payload

    http_client.write_command.side_effect = [
        '<root><result status="2" typesens="1" /></root>'
    ]

    await device.set_select_option("sensor_type", "1", "temperature_ds")
    assert device.conf.sensor_type == 2

    assert device.get_select_option("sensor_type", "1") == "temperature_ds"


@pytest.mark.asyncio
async def test_th2e_web_mode(http_client):
    """Test switching TH2E to web mode."""

    device = await async_setup_network_th2e(http_client)
    http_client.write_command.return_value = (
        '<root><result status="2" typesens="0" /></root>'
    )

    await device.switch_to_web_mode()

    payload = http_client.write_command.call_args[0][0]
    assert 'num4="3"' in payload
    assert 'ip1="192.168.002.233"' in payload
    assert 'num5="6"' in payload


@pytest.mark.parametrize(
    "method_name, args",
    [
        ("get_supported_binary_sensors", ()),
        ("get_supported_numbers", ()),
        ("get_supported_switches", ()),
        ("execute_button_command", ("invalid_cmd",)),
        ("turn_on_switch", ("1",)),
        ("turn_off_switch", ("1",)),
        ("set_number_value", ("cat", "1", 1.0)),
        ("get_select_option", ("invalid_cat", "1")),
    ],
)
@pytest.mark.asyncio
async def test_th2e_unimplemented_methods(http_client, method_name, args):
    """Test methods that are unsupported by the TH2E device."""
    device = TH2E(http_client, VALID_TH2E_SETTINGS, "N", "L", "MAC")

    func = getattr(device, method_name)
    if method_name.startswith("get_supported_"):
        assert func(*args) == []
    else:
        with pytest.raises(DeviceLogicError):
            if iscoroutinefunction(func):
                await func(*args)
            else:
                func(*args)


def test_th2e_init_invalid_xml(http_client):
    """Test TH2E initialization with broken XML."""

    with pytest.raises(DeviceParseError):
        TH2E(http_client, "NOT_XML", "N", "L", "MAC")


@pytest.mark.asyncio
async def test_th2e_get_fresh_data_edge_cases(http_client):
    """Test edge cases and invalid values in get_fresh_data."""
    device = TH2E(http_client, VALID_TH2E_SETTINGS, "N", "L", "MAC")

    http_client.fetch_data.return_value = '<root><status typesens="abc"/></root>'
    with pytest.raises(DeviceParseError):
        await device.get_fresh_data()

    http_client.fetch_data.return_value = """
    <root>
        <status typesens="1"/>
        <sns id="1" type="999" unit="0" status="0" val="20.0"/>
        <sns id="2" type="1" unit="0" status="0" val="invalid_float"/>
    </root>
    """
    data = await device.get_fresh_data()

    assert "unknown_1" not in data["sensor"]
    assert data["sensor"]["temperature_2"] is None


@pytest.mark.asyncio
async def test_th2e_set_sensor_type_edge_cases(http_client):
    """Test error handling during setting sensor type."""

    device = TH2E(http_client, VALID_TH2E_SETTINGS, "N", "L", "MAC")

    http_client.fetch_settings.return_value = "NOT_XML"
    with pytest.raises(DeviceParseError):
        await device.set_sensor_type(1)

    http_client.fetch_settings.return_value = '<root><set box="1"/></root>'
    http_client.write_command.return_value = (
        '<root><result status="2" typesens="1"/></root>'
    )
    await device.set_sensor_type(1)

    assert http_client.write_command.called


def test_th2e_check_sensor_response_errors(http_client):
    """Test error handling in _check_sensor_response."""
    device = TH2E(http_client, "<root></root>", "N", "L", "MAC")

    with pytest.raises(DeviceParseError):
        device._check_sensor_response("NOT_XML", "2", "act")

    with pytest.raises(DeviceParseError):
        device._check_sensor_response("<root><other/></root>", "2", "act")

    with pytest.raises(DeviceResponseError):
        device._check_sensor_response(
            '<root><result status="5" typesens="1"/></root>', "2", "act"
        )

    with pytest.raises(DeviceParseError):
        device._check_sensor_response(
            '<root><result status="2" typesens="abc"/></root>', "2", "act"
        )


@pytest.mark.asyncio
async def test_th2e_select_option_edge_cases(http_client):
    """Test edge cases for select options."""

    device = TH2E(http_client, VALID_TH2E_SETTINGS, "N", "L", "MAC")

    device.conf.sensor_type = 999
    with pytest.raises(DeviceLogicError):
        device.get_select_option("sensor_type", "1")

    with pytest.raises(DeviceLogicError):
        await device.set_select_option("sensor_type", "1", "nonexistent_option")

    with pytest.raises(DeviceLogicError):
        device.get_select_option("sensor_type", "99")

    with pytest.raises(DeviceLogicError):
        await device.set_select_option("sensor_type", "99", "temperature_ds")

    with pytest.raises(DeviceLogicError):
        await device.set_select_option("unknown_type", "1", "temperature_ds")


@pytest.mark.asyncio
async def test_th2e_web_mode_missing_box(http_client):
    """Test web mode switch when network box is missing."""

    device = TH2E(http_client, "<root></root>", "N", "L", "MAC")
    with pytest.raises(DeviceParseError):
        await device.switch_to_web_mode()


def test_th2e_check_sensor_response_success_no_typesens(http_client):
    """Test that missing typesens returns None instead of raising an error."""
    device = TH2E(http_client, "<root></root>", "N", "L", "MAC")

    result = device._check_sensor_response(
        '<root><result status="2" /></root>', "2", "act"
    )

    assert result is None


@pytest.mark.asyncio
async def test_th2e_get_sensor_type_missing_attr(http_client):
    """Test that get_sensor_typeexplicitly raises error if typesens is missing."""

    device = TH2E(http_client, "<root></root>", "N", "L", "MAC")

    http_client.write_command.return_value = '<root><result status="4" /></root>'

    with pytest.raises(DeviceParseError):
        await device.get_sensor_type()
