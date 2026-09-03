"""File contains helper functions that are used in various places."""


def parse_device_name(raw_name: bytes) -> str:
    """Parse device name from raw Spinel bytes."""

    result = raw_name.decode("ascii", errors="ignore")
    result = result.split(";")[0]
    return result.replace("\x00", "").strip()


def parse_device_location(raw_location: bytes) -> str:
    """Parse device location from raw Spinel bytes."""

    result = raw_location.decode("ascii", errors="ignore")
    return result.replace("\x00", "").strip()


def parse_device_serial_number(raw_serial_number: bytes) -> str:
    """Parse device serial number from raw Spinel bytes."""

    product_number = int.from_bytes(raw_serial_number[0:2], "big")
    serial_number_num = int.from_bytes(raw_serial_number[2:4], "big")
    return f"{product_number:04d}/{serial_number_num}"
