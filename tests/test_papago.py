# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for Papago devices."""

from unittest.mock import AsyncMock

import pytest
from aiopapouch.devices.papago import (
    PapagoETH_1TH_2DI_1DO,
    PapagoETH_2TH,
    async_setup_network_papago,
)
from aiopapouch.exceptions import DeviceLogicError, DeviceParseError

VALID_INFO_XML = """
<root>
    <heartbeat location="NONAME" ver="3.1" lang="e" device="Papago 2TH ETH"
    admset="0" usrset="0"/>
</root>
"""

VALID_SETTINGS_XML = """
<root>
<set box="1" dhcp="0" ip="192.168.3.43" mask="255.255.240.0" gate="192.168.1.201"
    dip="192.168.1.201" wport="80" lport="10001" mport="502" tcpto="0"/>

<set box="2" telnet="1" upd="1" usrset="0" admset="0"/>

<set box="3" domain="" ip="0.0.0.0" sport="25" from="" to="" host="" name=""
    enbwatch="0" auth="0" pswset="0"/>

<set box="4" enb="1" ip="0.0.0.0" per="0" readcom="public" writecom="private"
    enbtrap="0" enbwatch="0"/>

<set box="5" mode="0" path="" ip="0.0.0.0" domain="" per="0" keyset="0"
    pswset="0" user="" port="0" change="0" qos="0"/>

<set box="8" name="NONAME" lang="e" enbntp="0" ipntp="0.0.0.0" zone="41"
    daylight="1" units="0"/>

<set box="30" name="Senzor A" type="0" watch="0" max="100.0" min="0.0"
    hyst="0.0" watch2="0" max2="100.0" min2="0.0" hyst2="0.0" watch3="0" max3="125.0" min3="-40.0" hyst3="0.0"/>

<set box="31" name="Senzor B" type="4" watch="0" max="125.0" min="-40.0"
    hyst="0.0" watch2="0" max2="100.0" min2="0.0" hyst2="0.0" watch3="0" max3="125.0" min3="-40.0" hyst3="0.0"/>

<set box="12" type="Papago 2TH ETH" mac="00:80:A3:46:16:86" fw="3.1"
    sn="00530/08848" core="Papago 2TH ETH; v0530.01.18; N T"/>
</root>"""

DATA_XML = """
<root>
<din id="1" name="Input 139" bin="0" val="28 " raw="28"/>
<din id="2" name="Input 26" bin="0" val="60777.10 Some2" raw="607771"/>
<dout id="1" name="-40" bin="1" mode="0" qty="0"/>
<sns id="1" type="1" status="4" unit="0" val="-9999.0" w-min="" w-max="" type2="2" status2="4" unit2="0" val2="-9999.0" w-min2="" w-max2="" type3="3" status3="4" unit3="0" val3="-9999.0" w-min3="" w-max3=""/>
<status level="2" location="NONAME" time="02/08/2024 14:21:36"/>
</root>
"""


@pytest.fixture
def http_client():
    """Mock HTTP client returning valid base XMLs."""

    client = AsyncMock()
    client.fetch_settings.return_value = VALID_SETTINGS_XML
    client.fetch_info.return_value = VALID_INFO_XML
    client.fetch_data.return_value = DATA_XML
    client.ip_address = "192.168.1.10"
    return client


async def test_setup_network_papago_success(http_client):
    """Test successful creation of Papago 2TH ETH."""

    device = await async_setup_network_papago(http_client)

    assert isinstance(device, PapagoETH_2TH)
    assert device.conf.name == "Papago 2TH ETH"
    assert device.conf.location == "NONAME"
    assert device.conf.identifier == "00:80:A3:46:16:86"


async def test_setup_network_papago_unsupported(http_client):
    """Test factory returns None for unsupported Papago variant."""

    http_client.fetch_info.return_value = (
        '<root><heartbeat device="Papago Unknown ETH" /></root>'
    )

    device = await async_setup_network_papago(http_client)
    assert device is None


async def test_setup_network_papago_missing_heartbeat(http_client):
    """Test factory raises DeviceParseError when heartbeat is missing."""

    http_client.fetch_info.return_value = "<root><other /></root>"

    with pytest.raises(DeviceParseError):
        await async_setup_network_papago(http_client)


# --- TESTS FOR PARSING INITIAL SETTINGS (MAC Address) ---


async def test_papago_missing_mac_address(http_client):
    """Test DeviceParseError is raised if settings XML lacks box 12 (MAC)."""
    http_client.fetch_settings.return_value = '<root><set box="1" /></root>'

    with pytest.raises(DeviceParseError):
        await async_setup_network_papago(http_client)


# --- TESTS FOR DATA FETCHING (get_fresh_data) ---


async def test_papago_get_fresh_data(http_client):
    """Test parsing of sensors, inputs, counters, and outputs from fresh data."""
    # Vytvoříme zařízení
    device = await async_setup_network_papago(http_client)

    # Zavoláme metodu pro parsování DATA_XML (které jsme namockovali v klientovi)
    data = await device.get_fresh_data()

    # 1. Kontrola senzoru
    # Senzor id=1 by měl mít 25.5
    # (Předpokládáme semantic_key generátor v base class vrací něco jako "temperature_1")
    # Pro test jen zkontrolujeme, zda se ta hodnota 25.5 objevila ve values.
    assert 25.5 in data["sensor"].values()

    # Senzor id=2 má status="1" (odpojen), takže hodnota by měla být None
    assert None in data["sensor"].values()

    # 2. Kontrola digitálního vstupu
    assert data["input"]["1"] is True  # bin="1" -> True

    # 3. Kontrola čítače
    # val="1234.0 imp" by se mělo rozdělit (split) a parsovat jako 1234.0
    assert 1234.0 in data["counter"].values()

    # 4. Kontrola digitálního výstupu
    assert data["switch"]["1"] == 0  # bin="0"


# --- TESTS FOR COMMANDS & ERRORS ---


async def test_papago_set_number_value_formatting(http_client):
    """Test that float values are formatted correctly (removesuffix .0)."""
    device = await async_setup_network_papago(http_client)
    device._send_command = AsyncMock()

    # Pokud pošleme 25.0, do API by mělo jít "25"
    await device.set_number_value("decrease_counter", "1", 25.0)
    device._send_command.assert_called_once_with("m", item_id="1", value="25")


async def test_papago_set_number_value_invalid_category(http_client):
    """Test that unknown number category raises DeviceLogicError."""
    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceLogicError):
        await device.set_number_value("unknown_category", "1", 25.0)


async def test_papago_execute_button_command_invalid(http_client):
    """Test that unsupported button command raises DeviceLogicError."""
    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceLogicError):
        await device.execute_button_command("unsupported_cmd")


async def test_papago_switch_to_web_mode_not_implemented(http_client):
    """Test that switch_to_web_mode raises DeviceLogicError (unused in Papago)."""
    device = await async_setup_network_papago(http_client)

    with pytest.raises(DeviceLogicError):
        await device.switch_to_web_mode()
