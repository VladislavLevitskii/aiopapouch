# pylint: disable=protected-access, unused-argument, redefined-outer-name

"""Tests for utility functions."""

import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiopapouch.exceptions import (
    DeviceConnectionError,
    DeviceLogicError,
    DeviceParseError,
)
from aiopapouch.utils import (
    assign_next_available_address,
    find_tag,
    get_device_details,
    parse_device_location,
    parse_device_name,
    parse_device_serial_number,
    require_attr,
)


def test_find_tag_success_no_namespace():
    """Test finding a tag without any XML namespace."""
    root = ET.fromstring('<root><heartbeat attr="val" /><other /></root>')
    tag = find_tag(root, "heartbeat")

    assert tag is not None
    assert tag.attrib.get("attr") == "val"


def test_find_tag_success_with_namespace():
    """Test finding a tag when it is wrapped in an XML namespace."""

    xml_content = """
    <root xmlns:ns0="http://example.com">
    <ns0:heartbeat attr="val" /><other />
    </root>
    """
    root = ET.fromstring(xml_content)

    tag = find_tag(root, "heartbeat")

    assert tag is not None
    assert tag.attrib.get("attr") == "val"


def test_find_tag_not_found():
    """Test finding a tag that doesn't exist."""
    root = ET.fromstring("<root><other /></root>")
    assert find_tag(root, "heartbeat") is None


def test_find_tag_none_root():
    """Test safe handling of None as root element."""
    assert find_tag(None, "heartbeat") is None


@pytest.mark.parametrize("invalid_input", [None, 123, "Quido", ["bytes"]])
def test_parse_device_name_invalid_type(invalid_input):
    """Test that DeviceLogicError is raised for non-bytes input."""

    with pytest.raises(DeviceLogicError):
        parse_device_name(invalid_input)


def test_parse_device_name_empty_bytes():
    """Test that DeviceParseError is raised when payload is empty."""
    with pytest.raises(DeviceParseError):
        parse_device_name(b"")


@pytest.mark.parametrize(
    "raw_bytes, expected",
    [
        (
            b"Quido 10/1;v1.2\x00",
            "Quido 10/1",
        ),
        (b"TH2E\x00\x00\x00", "TH2E"),
        (b"  Papago  \x00", "Papago"),
    ],
)
def test_parse_device_name(raw_bytes, expected):
    """Test extraction and cleaning of device name from bytes."""
    assert parse_device_name(raw_bytes) == expected


@pytest.mark.parametrize(
    "raw_bytes, expected",
    [
        (b"Sklep\x00", "Sklep"),
        (b"  Kotelna  \x00", "Kotelna"),
        (b"", ""),
    ],
)
def test_parse_device_location(raw_bytes, expected):
    """Test extraction and cleaning of location from bytes."""
    assert parse_device_location(raw_bytes) == expected


@pytest.mark.parametrize("invalid_input", [None, 123, "Living Room", ["bytes"]])
def test_parse_device_location_invalid_type(invalid_input):
    """Test that DeviceLogicError is raised for non-bytes input."""

    with pytest.raises(DeviceLogicError):
        parse_device_location(invalid_input)


@pytest.mark.parametrize(
    "raw_bytes, expected",
    [
        (b"\x00\x7b\xb2\x6e\x00\x14\x78\x91", "0123/45678"),
        (b"\x00\x01\x00\x01\x00\x14\x78\x91", "0001/1"),
    ],
)
def test_parse_device_serial_number_success(raw_bytes, expected):
    """Test correct parsing of the 4-byte serial number structure."""
    assert parse_device_serial_number(raw_bytes) == expected


@pytest.mark.parametrize("invalid_input", [None, 123, "0123/45678", ["bytes"]])
def test_parse_device_serial_number_invalid_type(invalid_input):
    """Test that DeviceLogicError is raised for non-bytes input."""

    with pytest.raises(DeviceLogicError):
        parse_device_serial_number(invalid_input)


@pytest.mark.parametrize(
    "invalid_bytes",
    [
        b"",
        b"\x01\x02\x03",
        b"\x01\x02\x03\x04\x05",
    ],
)
def test_parse_device_serial_number_invalid_length(invalid_bytes):
    """Test that DeviceParseError is raised when payload length is not exactly 4 bytes."""
    with pytest.raises(DeviceParseError):
        parse_device_serial_number(invalid_bytes)


async def test_get_device_details():
    """Test orchestration of fetching device details."""
    api_client = AsyncMock()

    man_packet = MagicMock()
    man_packet.adr = 5
    man_packet.data = b"\x00\x7b\xb2\x6e\x00\x14\x78\x91"
    api_client.get_man_data.return_value = man_packet

    info_packet = MagicMock()
    info_packet.data = b"Quido 10/1;\x00"
    api_client.get_info.return_value = info_packet

    name, sn, adr = await get_device_details(api_client, address=5)

    assert name == "Quido 10/1"
    assert sn == "0123/45678"
    assert adr == 5


@patch("aiopapouch.utils.asyncio.sleep")
@patch("aiopapouch.utils.get_device_details")
async def test_assign_next_available_address_first_try(mock_details, mock_sleep):
    """Test when the very first scanned address (250) is available."""
    api_client = AsyncMock()

    api_client.write_command.side_effect = DeviceConnectionError()

    mock_details.return_value = ("Quido", "0123/45678", 250)

    addr, name = await assign_next_available_address(api_client, [], "0123/45678")

    assert addr == 250
    assert name == "Quido"
    api_client.set_address.assert_called_once_with(
        250, "0123/45678", "device with 250 for SN 0123/45678"
    )


@patch("aiopapouch.utils.asyncio.sleep")
@patch("aiopapouch.utils.get_device_details")
async def test_assign_next_available_address_skip_used(mock_details, mock_sleep):
    """Test skipping addresses that are in used_addresses or respond to ping."""
    api_client = AsyncMock()

    api_client.write_command.side_effect = [None, DeviceConnectionError()]

    mock_details.return_value = ("Quido", "0123/45678", 248)

    addr, name = await assign_next_available_address(api_client, [250], "0123/45678")

    assert addr == 248
    assert name == "Quido"

    api_client.set_address.assert_called_once_with(
        248, "0123/45678", "device with 248 for SN 0123/45678"
    )


@patch("aiopapouch.utils.asyncio.sleep")
async def test_assign_next_available_address_max_retries(mock_sleep):
    """Test exceeding MAX_ATTEMPTS_ASSIGNING returns (addr, None)."""
    api_client = AsyncMock()

    api_client.write_command.side_effect = DeviceConnectionError()
    api_client.set_address.side_effect = DeviceConnectionError()

    addr, name = await assign_next_available_address(api_client, [], "0123/45678")

    assert addr == 248
    assert name is None
    assert api_client.set_address.call_count == 3


async def test_assign_next_available_address_all_occupied():
    """Test behavior when all addresses from 250 down to 0 are already occupied."""

    api_client = AsyncMock()

    api_client.write_command.return_value = MagicMock()

    addr, name = await assign_next_available_address(api_client, [], "0123/45678")

    assert addr is None
    assert name is None

    assert api_client.write_command.call_count == 251

    api_client.set_address.assert_not_called()


@patch("aiopapouch.utils.asyncio.sleep")
@patch("aiopapouch.utils.get_device_details")
async def test_assign_next_available_address_details_timeout(mock_details, mock_sleep):
    """Test when set_address succeeds, but fetching details immediately fails."""

    api_client = AsyncMock()

    api_client.write_command.side_effect = DeviceConnectionError()

    mock_details.side_effect = [
        DeviceConnectionError("Timeout fetching details"),
        ("Quido", "0123/45678", 249),
    ]

    addr, name = await assign_next_available_address(api_client, [], "0123/45678")

    assert addr == 249
    assert name == "Quido"
    assert api_client.set_address.call_count == 2


@patch("aiopapouch.utils.asyncio.sleep")
@patch("aiopapouch.utils.get_device_details")
async def test_assign_next_available_address_parse_error_bubbles_up(
    mock_details, mock_sleep
):
    """Test that if device sends corrupted data during verification, it crashes the loop."""

    api_client = AsyncMock()

    api_client.write_command.side_effect = DeviceConnectionError()

    mock_details.side_effect = DeviceParseError()

    with pytest.raises(DeviceParseError):
        await assign_next_available_address(api_client, [], "0123/45678")


def test_require_attr():
    """Negative test of the require attribute function."""

    element = ET.Element("test", {"valid": "1"})

    assert require_attr(element, "valid", "ctx", "dev") == "1"

    with pytest.raises(DeviceParseError):
        require_attr(element, "missing", "ctx", "dev")
