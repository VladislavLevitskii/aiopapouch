# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for Papago devices."""

from unittest.mock import AsyncMock

import pytest
from aiopapouch.devices.papago import (
    PapagoETH_1TH_2DI_1DO,
    async_setup_network_papago,
)
from aiopapouch.exceptions import (
    DeviceLogicError,
    DeviceParseError,
    DeviceResponseError,
)

VALID_INFO_XML = """
<root>
    <heartbeat location="NONAME" ver="3.1" lang="e" device="Papago 2TH ETH"
    admset="0" usrset="0"/>
</root>
"""

SETTINGS_2TH_XML = """
<root>
<set box="1" dhcp="0" ip="192.168.3.43" mask="255.255.240.0" gate="192.168.1.201" dip="192.168.1.201" wport="80" lport="10001" mport="502" tcpto="0"/>
<set box="2" telnet="1" upd="1" usrset="0" admset="0"/>
<set box="3" domain="" ip="0.0.0.0" sport="25" from="" to="" host="" name="" enbwatch="0" auth="0" pswset="0"/>
<set box="4" enb="1" ip="0.0.0.0" per="0" readcom="public" writecom="private" enbtrap="0" enbwatch="0"/>
<set box="5" mode="0" path="" ip="0.0.0.0" domain="" per="0" keyset="0" pswset="0" user="" port="0" change="0" qos="0"/>
<set box="8" name="NONAME" lang="e" enbntp="0" ipntp="0.0.0.0" zone="41" daylight="1" units="0"/>
<set box="30" name="Senzor A" type="0" watch="0" max="100.0" min="0.0" hyst="0.0" watch2="0" max2="100.0" min2="0.0" hyst2="0.0" watch3="0" max3="125.0" min3="-40.0" hyst3="0.0"/>
<set box="31" name="Senzor B" type="4" watch="0" max="125.0" min="-40.0" hyst="0.0" watch2="0" max2="100.0" min2="0.0" hyst2="0.0" watch3="0" max3="125.0" min3="-40.0" hyst3="0.0"/>
<set box="12" type="Papago 2TH ETH" mac="00:80:A3:46:16:86" fw="3.1" sn="00530/08848" core="Papago 2TH ETH; v0530.01.18; N T"/>
</root>
"""

SETTINGS_1TH_2DI_1DO_XML = """
<root>
<set box="1" dhcp="0" ip="192.168.3.44" mask="255.255.240.0" gate="192.168.1.201" dip="192.168.1.201" wport="80" lport="10001" mport="502" tcpto="0"/>
<set box="2" telnet="1" upd="1" usrset="0" admset="0"/>
<set box="3" domain="" ip="0.0.0.0" sport="25" from="" to="" host="" name="" period="0" startat="0" auth="0" pswset="0" enbwatch="0"/>
<set box="4" enb="1" ip="0.0.0.0" per="0" readcom="public" writecom="private" enbtrap="0" enbwatch="0"/>
<set box="5" mode="0" path="" sub="" ip="0.0.0.0" domain="" per="00000000" keyset="0" pswset="0" user="" port="0" change="0" qos="0"/>
<set box="8" name="NONAME" lang="e" enbntp="0" ipntp="0.0.0.0" zone="41" daylight="1"/>
<set box="12" type="Papago 1TH 2DI 1DO ETH" mac="00:80:A3:46:DF:57" fw="2.3" sn="01075/08144" core="Papago 1TH 2DI 1DO ETH; v1075.01.20; H3"/>
<set box="30" sampl="0" nosns="0" out1name="-40" out1start="1" out1mode="0" out1pulsenb="0" out1puls="0.1" out1max="125.0" out1min="-55.0" out1hyst="0.0" out1qty="0"/>
<set box="31" enb="3" src="1" dst="1" dec="0" unit="" name="Input 139"/>
<set box="32" enb="2" src="10" dst="1" dec="2" unit="Some2" name="Input 26"/>
<set box="40" type="3" tunit="0" watch="0" max="125.0" min="-40.0" hyst="0.0" watch2="0" max2="100.0" min2="0.0" hyst2="0.0" watch3="0" max3="125.0" min3="-40.0" hyst3="0.0"/>
</root>
"""

SETTINGS_5HDI_1DO_XML = """
<root>
<set box="1" dhcp="0" ip="192.168.3.45" mask="255.255.255.0" gate="0.0.0.0" dip="0.0.0.0" wport="80" lport="10001" mport="502" tcpto="0"/>
<set box="2" telnet="1" upd="1" usrset="0" admset="0"/>
<set box="3" domain="" ip="0.0.0.0" sport="25" from="" to="" host="" name="" period="0" startat="0" auth="0" pswset="0"/>
<set box="4" enb="1" ip="0.0.0.0" per="0" readcom="public" writecom="private" enbtrap="0" enbwatch="0"/>
<set box="5" mode="0" path="" sub="" ip="0.0.0.0" domain="" per="00000000" keyset="0" pswset="0" user="" port="0" change="0" qos="0"/>
<set box="8" name="NONAME" lang="e" enbntp="0" ipntp="0.0.0.0" zone="186" daylight="1"/>
<set box="12" type="Papago 5HDI 1DO ETH" mac="00:80:A3:44:DC:75" fw="2.1" sn="01218/00867" core="Papago 5HDI 1DO ETH; v1218.01.13"/>
<set box="30" out1start="0" out1name="Output" sampl="20"/>
<set box="31" enb="3" src="1" dst="1" dec="0" unit="" name="Input 1"/>
<set box="32" enb="3" src="1" dst="1" dec="0" unit="" name="Input 2"/>
<set box="33" enb="0" src="1" dst="1" dec="0" unit="" name="Input 3"/>
<set box="34" enb="0" src="1" dst="1" dec="0" unit="" name="Input 4"/>
<set box="35" enb="0" src="1" dst="1" dec="0" unit="" name="Input 5"/>
</root>
"""

DATA_XML = """
<root>
<din id="1" name="Input 139" bin="0" val="28 " raw="28"/>
<din id="2" name="Input 26" bin="0" val="60777.10 Some2" raw="607771"/>
<dout id="1" name="-40" bin="1" mode="0" qty="0"/>
<sns id="1" type="1" status="0" unit="0" val="25.2" w-min="" w-max="" type2="2" status2="0" unit2="0" val2="39.9" w-min2="" w-max2="" type3="3" status3="0" unit3="0" val3="10.6" w-min3="" w-max3=""/>
<status level="2" location="NONAME" time="01/01/2024 12:00:26"/>
</root>
"""


@pytest.fixture
def http_client():
    """Mock HTTP client returning valid base XMLs. (Defaults to 1TH 2DI 1DO to test all features)."""
    client = AsyncMock()

    # 1TH 2DI DO because it containes everything
    client.fetch_settings.return_value = SETTINGS_1TH_2DI_1DO_XML
    client.fetch_info.return_value = VALID_INFO_XML
    client.fetch_data.return_value = DATA_XML
    client.ip_address = "192.168.1.10"
    return client


async def test_setup_network_papago_success(http_client):
    """Test successful creation of Papago 1TH 2DI 1DO ETH."""
    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )

    device = await async_setup_network_papago(http_client)

    assert isinstance(device, PapagoETH_1TH_2DI_1DO)
    assert device.conf.name == "Papago 1TH 2DI 1DO ETH"
    assert device.conf.location == "NONAME"
    assert device.conf.identifier == "00:80:A3:46:DF:57"


async def test_setup_network_papago_unsupported(http_client):
    """Test factory returns None for unsupported Papago variant."""
    http_client.get_device_info = AsyncMock(
        return_value=("Papago Unknown ETH", "NONAME")
    )
    device = await async_setup_network_papago(http_client)
    assert device is None


async def test_setup_network_papago_missing_heartbeat(http_client):
    """Test factory returns None when heartbeat (info) is completely missing."""
    http_client.get_device_info = AsyncMock(return_value=(None, None))
    device = await async_setup_network_papago(http_client)
    assert device is None


async def test_setup_network_papago_missing_mac(http_client):
    """Test factory raises DeviceParseError when MAC is missing from settings."""
    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    http_client.fetch_settings.return_value = '<root><set box="1" /></root>'

    with pytest.raises(DeviceParseError):
        await async_setup_network_papago(http_client)


@pytest.mark.asyncio
async def test_papago_get_fresh_data_valid(http_client):
    """Test parsing of sensors, inputs, counters, and outputs using the valid global constants."""
    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )

    device = await async_setup_network_papago(http_client)
    data = await device.get_fresh_data()

    assert data == {
        "sensor": {
            "temperature_1": 25.2,
            "humidity_1_2": 39.9,
            "dew_point_1_3": 10.6,
        },
        "input": {"1": False, "2": False},
        "counter": {"pulses_1": 28.0, "pulses_2": 60777.1},
        "switch": {"1": 1},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data_xml, expected",
    [
        (
            """<root>
                <sns id="1" type="1" status="4" unit="0" val="-9999.0"
                     type2="6" status2="0" unit2="0" val2="NW" />
            </root>""",
            {
                "sensor": {"temperature_1": None, "wind_direction_1_2": "NW"},
                "input": {},
                "counter": {},
                "switch": {},
            },
        ),
        (
            """<root>
                <sns type="1" status="0" val="25.2" />
                <unknown_tag id="1" />
            </root>""",
            {"sensor": {}, "input": {}, "counter": {}, "switch": {}},
        ),
        (
            """<root>
                <dout bin="1" mode="0" qty="0" />
                <sns id="99" name="Novy Senzor" type="1" status="0" unit="0" val="12.3" />
                <din id="1" bin="0" val="invalid_float" />
                <din id="2" bin="0" val="" />
            </root>""",
            {
                "sensor": {"temperature_99": 12.3},
                "input": {"1": False, "2": False},
                "counter": {"pulses_1": None, "pulses_2": None},
                "switch": {},
            },
        ),
    ],
)
async def test_papago_get_fresh_data_edge_cases(http_client, data_xml, expected):
    """Test silent fails and error statuses override fresh data without breaking."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    http_client.fetch_data.return_value = data_xml

    device = await async_setup_network_papago(http_client)
    data = await device.get_fresh_data()

    assert data == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data_xml",
    [
        '<root><sns id="1" type="1" status="0" val="28.5" /></root>',
        '<root><sns id="1" type="1" unit="0" val="28.5" /></root>',
        '<root><sns id="1" type="1" status="0" unit="0" /></root>',
        '<root><din id="1" val="10" /></root>',
        '<root><dout id="1" mode="0" /></root>',
    ],
)
async def test_papago_get_fresh_data_missing_required_attrs(http_client, data_xml):
    """Test that missing strictly required attributes raise DeviceParseError."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    http_client.fetch_data.return_value = data_xml

    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceParseError):
        await device.get_fresh_data()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_xml",
    ["500 Bad Gateway", """{user: "Marek"}"""],
)
async def test_papago_get_fresh_data_invalid_xml(http_client, invalid_xml):
    """Test behavior when API returns something else than XML."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    http_client.fetch_data.return_value = invalid_xml

    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceParseError):
        await device.get_fresh_data()


@pytest.mark.asyncio
async def test_papago_get_fresh_data_unknown_sensor_type(http_client):
    """Test behavior when device sends an unknown sensor type (missing in TYPE_MAPPING)."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    http_client.fetch_data.return_value = (
        '<root><sns id="1" type="99" status="0" unit="0" val="28.5" /></root>'
    )

    device = await async_setup_network_papago(http_client)

    data = await device.get_fresh_data()

    assert "sensor" in data
    assert not data["sensor"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", ["2", "3"])
async def test_papago_get_fresh_data_limit_statuses(http_client, status_code):
    """Test that limits exceeded/dropped statuses (2 and 3) successfully parse the value."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    http_client.fetch_data.return_value = f'<root><sns id="1" type="1" status="{status_code}" unit="0" val="25.5" /></root>'

    device = await async_setup_network_papago(http_client)
    data = await device.get_fresh_data()

    assert data["sensor"]["temperature_1"] == 25.5


async def test_papago_set_number_value_formatting(http_client):
    """Test that float values are formatted correctly (removesuffix .0)."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    device = await async_setup_network_papago(http_client)
    device._send_command = AsyncMock()

    await device.set_number_value("decrease_counter", "1", 25.0)
    device._send_command.assert_called_once_with("m", item_id="1", value="25")


async def test_papago_set_number_value_invalid_category(http_client):
    """Test that unknown number category raises DeviceLogicError."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceLogicError):
        await device.set_number_value("unknown_category", "1", 25.0)


async def test_papago_execute_button_command_invalid(http_client):
    """Test that unsupported button command raises DeviceLogicError."""
    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceLogicError):
        await device.execute_button_command("unsupported_cmd")


async def test_papago_switch_to_web_mode_not_implemented(http_client):
    """Test that switch_to_web_mode raises DeviceLogicError (unused in Papago)."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceLogicError):
        await device.switch_to_web_mode()


SETTINGS_2TH_XML = """
<root>
    <set box="12" type="Papago 2TH ETH" mac="00:11:22:33:44:55" />
    <set box="30" name="Teplomer" type="1" />
    <set box="31" name="Neznamy" type="99" />
</root>
"""

SETTINGS_5HDI_XML = """
<root>
    <set box="12" type="Papago 5HDI 1DO ETH" mac="AA:BB:CC:DD:EE:FF" />
    <set box="30" name="Hlavni Rele" />
    <set box="31" name="Vstup A" unit="V" dec="1" src="1" dst="1" enb="0" />
    <set box="32" name="Vstup B" unit="A" dec="0" src="1" dst="1" enb="1" />
</root>
"""

SETTINGS_METEO_XML = """
<root>
    <set box="12" type="Papago METEO ETH" mac="11:22:33:44:55:66" />
    <set box="30" name="Vitrek" type="7" />
    <set box="32" name="Davis Stanice" type="6" />
</root>
"""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_name, settings_xml, expected_binary, expected_switches, expected_numbers",
    [
        (
            "Papago 2TH ETH",
            SETTINGS_2TH_XML,
            [],
            [],
            [],
        ),
        (
            "Papago 5HDI 1DO ETH",
            SETTINGS_5HDI_XML,
            [
                {"item_id": "1", "type": "input", "name": "Vstup A"},
                {"item_id": "2", "type": "input", "name": "Vstup B"},
            ],
            [{"item_id": "1", "name": ""}],
            [
                {
                    "item_id": "1",
                    "category": "decrease_counter",
                    "type": "counter",
                    "name": "Vstup A",
                    "min_value": 0,
                    "max_value": 4294967295,
                    "step": 0.1,
                },
                {
                    "item_id": "1",
                    "category": "set_counter",
                    "type": "counter",
                    "name": "Vstup A",
                    "min_value": 0,
                    "max_value": 4294967295,
                    "step": 0.1,
                },
                {
                    "item_id": "2",
                    "category": "decrease_counter",
                    "type": "counter",
                    "name": "Vstup B",
                    "min_value": 0,
                    "max_value": 4294967295,
                    "step": 1.0,
                },
                {
                    "item_id": "2",
                    "category": "set_counter",
                    "type": "counter",
                    "name": "Vstup B",
                    "min_value": 0,
                    "max_value": 4294967295,
                    "step": 1.0,
                },
            ],
        ),
    ],
)
async def test_get_supported_static_io(
    http_client,
    device_name,
    settings_xml,
    expected_binary,
    expected_switches,
    expected_numbers,
):
    """Test binary sensors, switches and number entities that are statically determined from settings."""

    http_client.get_device_info = AsyncMock(return_value=(device_name, "NONAME"))
    http_client.fetch_settings.return_value = settings_xml

    device = await async_setup_network_papago(http_client)

    assert device.get_supported_binary_sensors() == expected_binary
    assert device.get_supported_switches() == expected_switches
    assert device.get_supported_numbers() == expected_numbers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_name, settings_xml, expected_buttons, expected_select_categories",
    [
        (
            "Papago 2TH ETH",
            SETTINGS_2TH_XML,
            [
                {"cmd": "set_sensor_1", "name": "Teplomer"},
                {"cmd": "set_sensor_2", "name": "Neznamy"},
            ],
            [
                {"item_id": "1", "category": "sensor_type", "name": "Teplomer"},
                {"item_id": "2", "category": "sensor_type", "name": "Neznamy"},
            ],
        ),
        (
            "Papago 5HDI 1DO ETH",
            SETTINGS_5HDI_XML,
            [],
            [
                {"item_id": "1001", "category": "counter_mode", "name": "Vstup A"},
                {"item_id": "1002", "category": "counter_mode", "name": "Vstup B"},
            ],
        ),
        (
            "Papago METEO ETH",
            SETTINGS_METEO_XML,
            [
                {"cmd": "set_sensor_1", "name": "Vitrek"},
            ],
            [
                {"item_id": "1", "category": "sensor_type_meteo_ab", "name": "Vitrek"},
                {
                    "item_id": "3",
                    "category": "sensor_type_meteo_c",
                    "name": "Davis Stanice",
                },
            ],
        ),
    ],
)
async def test_get_supported_ui_elements(
    http_client, device_name, settings_xml, expected_buttons, expected_select_categories
):
    """Test configuration of actionable UI elements (buttons and selects) heavily affected by device type."""

    http_client.get_device_info = AsyncMock(return_value=(device_name, "NONAME"))
    http_client.fetch_settings.return_value = settings_xml

    device = await async_setup_network_papago(http_client)

    assert device.get_supported_buttons() == expected_buttons

    selects = device.get_supported_selects()

    for i, expected_cat in enumerate(expected_select_categories):
        assert selects[i]["item_id"] == expected_cat["item_id"]
        assert selects[i]["category"] == expected_cat["category"]
        assert selects[i]["name"] == expected_cat["name"]


@pytest.mark.asyncio
async def test_get_supported_sensors_dynamic(http_client):
    """
    Test supported sensors for METEO.
    Sensors require get_fresh_data to run first because they depend on 'sub_sensors' discovery.
    This also tests that unknown sensor types are silently ignored, and rain/wind logic formats correctly.
    """

    http_client.get_device_info = AsyncMock(return_value=("Papago METEO ETH", "NONAME"))
    http_client.fetch_settings.return_value = """
    <root>
        <set box="12" type="Papago METEO ETH" mac="AA:BB:CC:DD" />
        <set box="30" name="Srazky" type="10" />
        <set box="31" name="Vitrek" type="7" />
        <set box="32" name="Neznamy" type="99" />
    </root>"""

    http_client.fetch_data.return_value = """
    <root>
        <sns id="1" type="8" status="0" unit="0" val="1.5" />
        <sns id="2" type="6" status="0" unit="1" val="NNE" />
    </root>"""

    device = await async_setup_network_papago(http_client)

    await device.get_fresh_data()
    sensors = device.get_supported_sensors()

    assert sensors == [
        {
            "item_id": "1",
            "value_key": "rain_1",
            "type": "sensor",
            "data_type": "rain",
            "name": "Srazky 15 Min",
            "unit": "mm/15 min",
        },
        {
            "item_id": "2",
            "value_key": "wind_direction_2",
            "type": "sensor",
            "data_type": "wind_direction_text",
            "name": "Vitrek",
            "unit": None,
        },
    ]


@pytest.mark.asyncio
async def test_get_supported_sensors_inputs(http_client):
    """Test that physical inputs are correctly exported as counter sensors."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 5HDI 1DO ETH", "NONAME")
    )
    http_client.fetch_settings.return_value = SETTINGS_5HDI_1DO_XML

    device = await async_setup_network_papago(http_client)
    sensors = device.get_supported_sensors()

    assert len(sensors) == 5
    assert sensors[0]["value_key"] == "pulses_1"
    assert sensors[0]["type"] == "counter"
    assert sensors[0]["name"] == "Input 1"
    assert sensors[4]["value_key"] == "pulses_5"


@pytest.mark.asyncio
async def test_execute_button_command_auto_detect(http_client):
    """Test auto-detecting sensors via execute_button_command."""

    http_client.get_device_info = AsyncMock(return_value=("Papago 2TH ETH", "NONAME"))
    http_client.fetch_settings.return_value = SETTINGS_2TH_XML

    http_client.write_command = AsyncMock(
        return_value='<root><result status="1" /><set box="30" type="1" /></root>'
    )

    device = await async_setup_network_papago(http_client)
    await device.execute_button_command("set_sensor_1")

    http_client.write_command.assert_called_once()
    payload = http_client.write_command.call_args[0][0]
    assert 'box="98"' in payload
    assert 'num01="4"' in payload


@pytest.mark.asyncio
async def test_set_select_option_sensor_type(http_client):
    """Test setting a sensor type via select option."""

    http_client.get_device_info = AsyncMock(return_value=("Papago 2TH ETH", "NONAME"))
    http_client.fetch_settings.return_value = SETTINGS_2TH_XML

    http_client.write_command = AsyncMock(
        side_effect=[
            '<root><result status="1" /></root>',
            '<root><result status="1" /></root>',
            '<root><result status="2" /></root>',
        ]
    )

    device = await async_setup_network_papago(http_client)

    await device.set_select_option("sensor_type", "1", "temperature_ds")

    assert http_client.write_command.call_count == 3

    set_payload = http_client.write_command.call_args_list[1][0][0]
    assert 'box="30"' in set_payload
    assert 'num01="2"' in set_payload


@pytest.mark.asyncio
async def test_set_select_option_invalid(http_client):
    """Test setting options that are unknown or invalid."""

    http_client.get_device_info = AsyncMock(return_value=("Papago 2TH ETH", "NONAME"))
    http_client.fetch_settings.return_value = SETTINGS_2TH_XML
    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceLogicError):
        await device.set_select_option("unknown_category", "1", "temperature_ds")

    http_client.write_command = AsyncMock()
    await device.set_select_option("sensor_type", "1", "invalid_option")
    http_client.write_command.assert_not_called()


@pytest.mark.asyncio
async def test_papago_missing_id_and_non_digit_box(http_client):
    """Test parsing handles non-digit boxes and elements missing IDs."""

    http_client.fetch_settings.return_value = SETTINGS_5HDI_1DO_XML
    http_client.get_device_info = AsyncMock(
        return_value=("Papago 5HDI 1DO ETH", "NONAME")
    )
    device = await async_setup_network_papago(http_client)

    http_client.fetch_data.return_value = '<root><din bin="0" val="28" /></root>'
    data = await device.get_fresh_data()
    assert "1" not in data["input"]


@pytest.mark.asyncio
async def test_meteo_rain_units_and_unknown_sensor(http_client):
    """Test METEO rain specific unit conversion and unknown sensor skip."""

    http_client.get_device_info = AsyncMock(return_value=("Papago METEO ETH", "NONAME"))
    http_client.fetch_settings.return_value = (
        "<root>"
        '<set box="12" type="Papago METEO ETH" mac="00:11:22" />'
        '<set box="30" name="Rain" type="10" />'
        '<set box="31" name="Rain" type="10" />'
        "</root>"
    )
    http_client.fetch_data.return_value = (
        "<root>"
        '<sns id="1" type="8" status="0" unit="1" val="1.0" />'
        '<sns id="2" type="8" status="0" unit="2" val="2.0" />'
        "</root>"
    )
    device = await async_setup_network_papago(http_client)
    await device.get_fresh_data()

    sensors = device.get_supported_sensors()
    names = [s["name"] for s in sensors]

    assert "Rain Hourly" in names
    assert "Rain Daily" in names
    assert len(sensors) == 2


@pytest.mark.asyncio
async def test_switch_and_counter_commands(http_client):
    """Test command generation for switches and counter setter."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 5HDI 1DO ETH", "NONAME")
    )
    http_client.fetch_settings.return_value = SETTINGS_5HDI_1DO_XML
    device = await async_setup_network_papago(http_client)
    device._send_command = AsyncMock()

    await device.turn_on_switch("1")
    device._send_command.assert_called_with("s", "1")

    await device.turn_off_switch("1")
    device._send_command.assert_called_with("r", "1")

    await device.set_number_value("set_counter", "1", 50.0)
    device._send_command.assert_called_with("n", item_id="1", value="50")


@pytest.mark.asyncio
async def test_internal_xml_parse_errors(http_client):
    """Test defused_ET parsing errors and missing result tags."""

    client_mock = AsyncMock()
    client_mock.fetch_settings = AsyncMock(return_value="""{user: "Marek}""")
    with pytest.raises(DeviceParseError):
        device = await async_setup_network_papago(client_mock)

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceParseError):
        await device._check_auto_detect_sensor_response("NOT_XML_DATA")

    http_client.fetch_settings.return_value = "INVALID_XML"
    with pytest.raises(DeviceParseError):
        await device._update_settings()

    with pytest.raises(DeviceParseError):
        device._check_sensor_response("<root><other/></root>", "1", "msg")

    with pytest.raises(DeviceResponseError):
        device._check_sensor_response('<root><result status="9" /></root>', "1", "msg")

    with pytest.raises(DeviceParseError):
        device._check_sensor_response("INVALID_XML", "1", "msg")


@pytest.mark.asyncio
async def test_auto_detect_edge_cases(http_client):
    """Test auto-detect silent return and bad status raise."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 1TH 2DI 1DO ETH", "NONAME")
    )
    device = await async_setup_network_papago(http_client)

    http_client.write_command = AsyncMock(return_value="")
    await device.auto_detect_sensor("1")

    http_client.write_command = AsyncMock(
        return_value='<root><result status="2" /></root>'
    )
    with pytest.raises(DeviceResponseError):
        await device.auto_detect_sensor("1")


@pytest.mark.asyncio
async def test_set_sensor_type_edge_cases(http_client):
    """Test BOX_SENSOR_BASE check and missing box check."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 5HDI 1DO ETH", "NONAME")
    )
    http_client.fetch_settings.return_value = SETTINGS_5HDI_1DO_XML
    device_5hdi = await async_setup_network_papago(http_client)
    await device_5hdi.set_sensor_type("1", "1")

    http_client.get_device_info = AsyncMock(return_value=("Papago 2TH ETH", "NONAME"))
    http_client.fetch_settings.return_value = (
        '<root><set box="12" type="Papago 2TH ETH" mac="00:11" /></root>'
    )
    device_2th = await async_setup_network_papago(http_client)
    device_2th._update_settings = AsyncMock()

    with pytest.raises(DeviceParseError):
        await device_2th.set_sensor_type("1", "1")


@pytest.mark.asyncio
async def test_input_counter_mode_logic(http_client):
    """Test counter mode select setters and XML payload formatting."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 5HDI 1DO ETH", "NONAME")
    )
    http_client.fetch_settings.return_value = SETTINGS_5HDI_1DO_XML
    device = await async_setup_network_papago(http_client)
    device._update_settings = AsyncMock()
    device._save_setting = AsyncMock()

    await device.set_select_option("counter_mode", "1001", "invalid_mode")
    device._save_setting.assert_not_called()

    await device.set_select_option("counter_mode", "1001", "off")
    payload = device._save_setting.call_args[0][0]
    assert 'num01="0"' in payload
    assert "num02=" not in payload

    await device.set_select_option("counter_mode", "1002", "counts_ascending_edges")
    payload2 = device._save_setting.call_args[0][0]
    assert 'num01="2"' in payload2
    assert "num02=" in payload2

    with pytest.raises(DeviceLogicError):
        await device.set_input_type("invalid_id", "1")
    with pytest.raises(DeviceLogicError):
        await device.set_input_type("9999", "1")


@pytest.mark.asyncio
async def test_get_select_option_base_logic(http_client):
    """Test logic for retrieving select options."""

    http_client.get_device_info = AsyncMock(
        return_value=("Papago 5HDI 1DO ETH", "NONAME")
    )
    http_client.fetch_settings.return_value = (
        "<root>"
        '<set box="12" type="Papago 5HDI 1DO ETH" mac="00:11" />'
        '<set box="31" unit="" dec="0" src="1" dst="1" enb="3" />'
        "</root>"
    )
    device = await async_setup_network_papago(http_client)

    assert (
        device.get_select_option("counter_mode", "1001")
        == "counts_ascending_and_descending_edges"
    )
    assert device.get_select_option("counter_mode", "9999") is None

    with pytest.raises(DeviceLogicError):
        device.get_select_option("invalid_cat", "1")

    http_client.get_device_info = AsyncMock(return_value=("Papago 2TH ETH", "NONAME"))
    http_client.fetch_settings.return_value = (
        "<root>"
        '<set box="12" type="Papago 2TH ETH" mac="00:11" />'
        '<set box="31" type="4" />'
        "</root>"
    )

    device_2th = await async_setup_network_papago(http_client)
    assert device_2th.get_select_option("sensor_type", "2") == "temperature_tmp"


@pytest.mark.asyncio
async def test_get_select_option_none_returns(http_client):
    """Coverage for returning None in get_select_option when data is missing or invalid."""

    http_client.get_device_info = AsyncMock(return_value=("Papago 2TH ETH", "NONAME"))
    http_client.fetch_settings.return_value = SETTINGS_2TH_XML
    device = await async_setup_network_papago(http_client)

    assert device.get_select_option("sensor_type", "999") is None

    device.conf.sensors_types["abc"] = "invalid_string"
    assert device.get_select_option("sensor_type", "abc") is None

    device.conf.sensors_types["999"] = "99"
    assert device.get_select_option("sensor_type", "999") is None


@pytest.mark.asyncio
async def test_parse_initial_settings_continues(http_client):
    """Coverage for the 'continue' statements in _parse_initial_settings."""

    http_client.get_device_info = AsyncMock(return_value=("Papago 2TH ETH", "NONAME"))

    http_client.fetch_settings.return_value = (
        "<root>"
        '<set box="12" type="Papago 2TH ETH" mac="00:11" />'
        "<ignore_me />"
        '<set type="1" />'
        '<set box="abc" />'
        "</root>"
    )

    device = await async_setup_network_papago(http_client)
    assert device is not None


@pytest.mark.asyncio
async def test_meteo_select_options_coverage(http_client):
    """Coverage for GET and SET select options in METEO."""
    http_client.get_device_info = AsyncMock(return_value=("Papago METEO ETH", "NONAME"))

    http_client.fetch_settings.return_value = (
        "<root>"
        '<set box="12" type="Papago METEO ETH" mac="00:11" />'
        '<set box="30" type="7" />'
        '<set box="32" type="6" />'
        "</root>"
    )
    device = await async_setup_network_papago(http_client)

    assert (
        device.get_select_option("sensor_type_meteo_ab", "1") == "atmospheric_pressure"
    )
    assert device.get_select_option("sensor_type_meteo_c", "3") == "davis"

    assert device.get_select_option("sensor_type_meteo_ab", "999") is None
    assert device.get_select_option("invalid_cat", "1") is None

    device.set_sensor_type = AsyncMock()

    await device.set_select_option("sensor_type_meteo_ab", "1", "atmospheric_pressure")
    device.set_sensor_type.assert_called_with("1", "7")

    await device.set_select_option("sensor_type_meteo_c", "3", "davis")
    device.set_sensor_type.assert_called_with("3", "6")

    device.set_sensor_type.reset_mock()
    await device.set_select_option("sensor_type_meteo_ab", "1", "nesmysl_option")
    device.set_sensor_type.assert_not_called()
