# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for TME and TMERadioMulti network devices."""

from inspect import iscoroutinefunction
from unittest.mock import AsyncMock

import pytest
from aiopapouch.devices.tme import TME, TMERadioMulti, async_setup_network_tme
from aiopapouch.exceptions import (
    DeviceLogicError,
    DeviceParseError,
    DeviceResponseError,
)

VALID_TME_SETTINGS = """
<root>
<set box="1" ip="192.168.3.42" mask="255.255.255.0" gate="0.0.0.0" wport="80" lport="10001" dip="0.0.0.0" rip="0.0.0.0" rport="0" mport="502" keep="0" com="8"/>
<set box="8" name="Thermometer" skin="0"/>
<set box="12" mac="00:80:A3:85:BF:8F"/>
</root>
"""

VALID_TME_MULTI_SETTINGS = """
<root>
<set box="1" ip="192.168.3.47" mask="255.255.0.0" gate="0.0.0.0" dip="0.0.0.0" wport="80" lport="10001" mport="502" rip="0.0.0.0" rport="0" mode="3" com="0"/>
<set box="8" name="NONAME" per="60"/>
<set box="12" mac="00:80:A3:85:A4:6E" sn="" info=""/>
</root>
"""

TME_DATA = """
<root>
<sns id="1" type="4" location="Thermometer" status="0" hi="0" lo="0" unit="0" val="255" min="-550" max="1250"/>
<status location="Thermometer" mac="0080A385BF8F"/>
</root>
"""

TME_MULTI_DATA = """
<root>
<sns id="10" vc="1395" sn="149" name="" w1="0" mx1="0" mi1="0" w2="0" mx2="0" mi2="0" w3="0" mx3="0" mi3="0" s1="0" v1="312" s2="0" v2="269" s3="0" v3="767" batt="5" rssi="-60"/>
<status unit="C" location="NONAME"/>
</root>
"""


@pytest.fixture
def http_client():
    """Mock HTTP client for TME devices."""
    client = AsyncMock()
    client.ip_address = "192.168.3.42"
    client.get_device_mac.return_value = "MAC"
    client.fetch_settings.return_value = VALID_TME_SETTINGS
    return client


@pytest.mark.asyncio
async def test_setup_network_tme(http_client):
    """Test factory creates correct instances based on device name."""

    http_client.get_device_info.return_value = ("TME", "Loc")
    device = await async_setup_network_tme(http_client)
    assert isinstance(device, TME)

    http_client.get_device_info.return_value = ("TME MULTI", "Loc")
    http_client.fetch_settings.return_value = VALID_TME_MULTI_SETTINGS
    device = await async_setup_network_tme(http_client)
    assert isinstance(device, TMERadioMulti)

    http_client.get_device_info.return_value = ("UnknownDevice", "Loc")
    device = await async_setup_network_tme(http_client)
    assert device is None

    http_client.get_device_info.return_value = (None, None)
    with pytest.raises(DeviceParseError):
        await async_setup_network_tme(http_client)


@pytest.mark.asyncio
async def test_tme_parsing(http_client):
    """Test TME classic data parsing."""

    http_client.fetch_data.return_value = TME_DATA
    device = TME(http_client, VALID_TME_SETTINGS, "TME", "Loc", "MAC")

    data = await device.get_fresh_data()
    assert data["sensor"]["temperature_1"] == 25.5

    sensors = device.get_supported_sensors()
    assert len(sensors) == 1
    assert sensors[0]["name"] == "TME"


@pytest.mark.asyncio
async def test_tme_parsing_errors(http_client):
    """Test TME parsing errors."""
    device = TME(http_client, VALID_TME_SETTINGS, "TME", "Loc", "MAC")

    http_client.fetch_data.return_value = "NOT_XML"
    with pytest.raises(DeviceParseError):
        await device.get_fresh_data()

    http_client.fetch_data.return_value = (
        '<root><sns id="1" status="0" unit="0" val="err"/></root>'
    )
    data = await device.get_fresh_data()
    assert data["sensor"]["temperature_1"] is None

    http_client.fetch_data.return_value = (
        '<root><sns id="1" status="1" unit="0" val="225"/></root>'
    )
    data = await device.get_fresh_data()
    assert data["sensor"]["temperature_1"] is None


@pytest.mark.asyncio
async def test_tme_multi_parsing(http_client):
    """Test TMERadioMulti parsing including CO2, batt, and rssi."""
    http_client.fetch_data.return_value = TME_MULTI_DATA
    device = TMERadioMulti(
        http_client, VALID_TME_MULTI_SETTINGS, "TME MULTI", "Loc", "MAC"
    )

    data = await device.get_fresh_data()

    print(data)

    assert data["sensor"]["temperature_10"] == 31.2
    assert data["sensor"]["humidity_10_2"] == 26.9
    assert data["sensor"]["co2_10_3"] == 767
    assert data["sensor"]["battery_10_batt"] == 57.1
    assert data["sensor"]["signal_strength_10_rssi"] == -60

    sensors = device.get_supported_sensors()
    assert len(sensors) == 5


@pytest.mark.asyncio
async def test_tme_multi_errors_and_limits(http_client):
    """Test TMERadioMulti error handling and parsing limits."""
    device = TMERadioMulti(
        http_client, VALID_TME_MULTI_SETTINGS, "TME MULTI", "Loc", "MAC"
    )

    http_client.fetch_data.return_value = '<root><sns id="10" s1="1" v1="312" s2="0" v2="err" batt="err" rssi="err"/></root>'
    data = await device.get_fresh_data()

    assert data["sensor"]["temperature_10"] is None
    assert data["sensor"]["humidity_10_2"] is None
    assert data["sensor"]["battery_10_batt"] is None
    assert data["sensor"]["signal_strength_10_rssi"] is None


@pytest.mark.asyncio
async def test_tme_multi_web_mode(http_client):
    """Test switching TMERadioMulti to web mode."""
    device = TMERadioMulti(
        http_client, VALID_TME_MULTI_SETTINGS, "TME MULTI", "Loc", "MAC"
    )

    http_client.write_command.return_value = '<root><result status="2" /></root>'

    await device.switch_to_web_mode()

    payload = http_client.write_command.call_args[0][0]
    assert 'num4="3"' in payload
    assert 'ip1="192.168.003.047"' in payload

    http_client.write_command.return_value = '<root><result status="1" /></root>'
    with pytest.raises(DeviceResponseError):
        await device.switch_to_web_mode()

    http_client.write_command.return_value = "NOT_XML"
    with pytest.raises(DeviceParseError):
        await device.switch_to_web_mode()


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
    ],
)
@pytest.mark.asyncio
async def test_tme_unimplemented_methods(http_client, method_name, args):
    """Test unused methods across both TME classes."""
    devices = [
        TME(http_client, VALID_TME_SETTINGS, "N", "L", "MAC"),
        TMERadioMulti(http_client, VALID_TME_MULTI_SETTINGS, "N", "L", "MAC"),
    ]

    for device in devices:
        func = getattr(device, method_name)
        if method_name.startswith("get_supported_"):
            assert func(*args) == []
        else:
            with pytest.raises(DeviceLogicError):
                if iscoroutinefunction(func):
                    await func(*args)
                else:
                    func(*args)


@pytest.mark.asyncio
async def test_tme_switch_web_mode_unused(http_client):
    """Test that base TME explicitly raises error on web mode switch."""
    device = TME(http_client, VALID_TME_SETTINGS, "N", "L", "MAC")
    with pytest.raises(DeviceLogicError):
        await device.switch_to_web_mode()


def test_tme_init_invalid_settings(http_client):
    """Test initialization failure on invalid XML settings."""
    with pytest.raises(DeviceParseError):
        TME(http_client, "NOT_XML", "TME", "Loc", "MAC")


@pytest.mark.asyncio
async def test_tme_classic_unknown_sensor_type(http_client):
    """Test TME classic warning on unknown sensor type."""
    http_client.fetch_data.return_value = (
        '<root><sns id="1" status="0" unit="0" val="225"/></root>'
    )
    device = TME(http_client, VALID_TME_SETTINGS, "TME", "Loc", "MAC")

    device.TYPE_MAPPING = {}
    data = await device.get_fresh_data()

    assert not data["sensor"]


@pytest.mark.asyncio
async def test_tme_multi_invalid_vc_and_unknown_type(http_client):
    """Test TMERadioMulti handling of invalid vc attribute and unknown sensor index."""

    http_client.fetch_data.return_value = (
        '<root><sns id="1" vc="invalid" s1="0" v1="225" s2="0" v2="10"/></root>'
    )
    device = TMERadioMulti(
        http_client, VALID_TME_MULTI_SETTINGS, "TME MULTI", "Loc", "MAC"
    )

    device.TYPE_MAPPING = {}
    data = await device.get_fresh_data()

    assert not data["sensor"]


@pytest.mark.asyncio
async def test_tme_multi_web_mode_missing_box(http_client):
    """Test TMERadioMulti web mode switch with missing settings box."""

    device = TMERadioMulti(http_client, "<root></root>", "TME MULTI", "Loc", "MAC")

    with pytest.raises(DeviceParseError):
        await device.switch_to_web_mode()


def test_tme_multi_check_response_errors(http_client):
    """Test TMERadioMulti response validation with missing result tag or invalid XML."""
    device = TMERadioMulti(
        http_client, VALID_TME_MULTI_SETTINGS, "TME MULTI", "Loc", "MAC"
    )

    with pytest.raises(DeviceParseError):
        device._check_sensor_response("<root><other/></root>", "2", "testing")

    with pytest.raises(DeviceParseError):
        device._check_sensor_response("NOT_XML", "2", "testing")
