"""File that contains constant values."""

from enum import StrEnum

DOMAIN = "papouch"
AUTH_FAILED_ERROR = 401
DEFAULT_WEB_PORT = 80
UNKNOWN_LOCATION = "NONANE"
UNKNOWN_NAME = "Unknown"

SERIAL_BROADCAST_ADDRESS = 0xFE

INST_READ_TEMPERATURE = 0x51
INST_NEW_ADDR = 0xEB
INST_RESET = 0xE3

TCP_SERVER_MODE_INDEX = 0
TCP_CLIENT_MODE_INDEX = 1
UDP_MODE_INDEX = 2
WEB_MODE_INDEX = 3

CONNECTION_TYPE = "connection_type"


class ConnectionType(StrEnum):
    """Enum that represents all possible connection types of the integration."""

    NETWORK = "network"
    NETWORK_HUB = "network_hub"
    SERIAL = "serial"
    TCP = "tcp"
