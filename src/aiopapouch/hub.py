"""This file is used for defining Hubs."""

from abc import ABC, abstractmethod

from . import PapouchSerialClient, create_serial_device
from .devices import PapouchSerialDevice
from .devices.base import PapouchDevice
from .exceptions import DeviceLogicError
from .utils import assign_next_available_address


class Hub(ABC):
    """Base class for Hub"""

    @abstractmethod
    def add_device(self, device: PapouchDevice) -> None:
        """Adding a device to the hub."""


class SerialHub:
    """Hub for serial devices."""

    _devices: list[PapouchSerialDevice]

    def __init__(self, client: PapouchSerialClient) -> None:
        """Construct serial hub."""

        self.client = client

    async def create_and_add_device(self, address: int) -> None:
        """Create a new device over serial and add it to the hub."""
        if device := await create_serial_device(self.client, address):
            self._devices.append(device)
            return
        raise DeviceLogicError(f"Unable to create device with address: {address}.")

    def add_device(self, device: PapouchSerialDevice) -> None:
        """Add an already existing device instance to the hub."""
        self._devices.append(device)

    def remove_device(self, device: PapouchSerialDevice) -> None:
        """Remove the device from the hub, throw DeviceLogicError when missing."""

        try:
            self._devices.remove(device)
        except ValueError as err:
            raise DeviceLogicError(
                f"{device.conf.identifier} is not in the hub."
            ) from err

    def remove_device_by_address(self, address: int) -> None:
        """Remove the device from the hub using its address, throw DeviceLogicError when missing."""

        for device in self.devices:
            if device.conf.address == address:
                self.devices.remove(device)
                return

        raise DeviceLogicError(f"Device with {address} is not in the hub.")

    async def assign_next_available_address(
        self, serial_number: str
    ) -> tuple[int | None, str | None]:
        """Assign a new address to the device that has serial number from the parameter.

        Return (new address, device name)

        Where (None, None) means there are no available addresses and
        (New Address, None) means that either it is the serial number is invalid
        or there are multiple devices that have adresses from 250 and down
        """

        used_addresses: list[int] = [device.conf.address for device in self.devices]

        return await assign_next_available_address(
            self.client, used_addresses, serial_number
        )

    @property
    def devices(self) -> list[PapouchSerialDevice]:
        """Return devices of the hub."""

        return self._devices
