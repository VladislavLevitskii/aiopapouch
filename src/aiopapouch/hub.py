"""This file is used for defining Hubs."""

import asyncio
import logging
from abc import ABC
from typing import Any, TypeVar, override

import aiohttp

from pap_spinel import SpinelTransportError, TcpTransport

from .client import PapouchHTTPClient, PapouchSerialClient
from .const import SERIAL_BROADCAST_ADDRESS
from .devices import (
    PapouchNetworkDevice,
    PapouchSerialDevice,
    create_network_device,
    create_serial_device,
)
from .devices.base import PapouchDevice
from .discovery import async_discover_papouch_devices
from .exceptions import DeviceConnectionError, DeviceLogicError
from .utils import _get_device_details, assign_next_available_address

_LOGGER = logging.getLogger(__name__)


class Hub[DeviceT: PapouchDevice[Any]](ABC):
    """Base class for Hub"""

    def __init__(self) -> None:
        """Construct base hub."""
        self._devices: list[DeviceT] = []

    def __len__(self) -> int:
        return len(self._devices)

    def __contains__(self, device: DeviceT) -> bool:
        return device in self._devices

    def __iter__(self):
        return iter(self._devices)

    @property
    def devices(self) -> list[DeviceT]:
        """Return devices of the hub."""
        return self._devices

    async def add_device(self, device: DeviceT) -> None:
        """
        Add an already existing device instance to the hub.

        Raise DeviceLogicError is the device is already in the hub.
        """

        if device not in self.devices:
            self._devices.append(device)
        else:
            raise DeviceLogicError(
                f"Device {device.conf.context} is already in the hub."
            )

    async def remove_device(self, device: DeviceT) -> None:
        """Remove the device from the hub, throw DeviceLogicError when missing."""
        try:
            self._devices.remove(device)
        except ValueError as err:
            raise DeviceLogicError(
                f"{device.conf.identifier} is not in the hub."
            ) from err

    async def get_fresh_data(self) -> dict:
        """
        Get fresh data from all registered devices, where keys are their names.

        Note that there could be devices that are registered and could be pinged
        but they can't return their fresh data.
        """

        if not self.devices:
            return {}

        tasks = [device.get_fresh_data() for device in self.devices]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        fresh_data = {}

        for device, data in zip(self.devices, results):
            if isinstance(data, Exception):
                _LOGGER.warning(
                    "Failed to get fresh data from device %s: %s",
                    device.conf.context,
                    data,
                )
                continue

            key = device.conf.context
            fresh_data[key] = data

        return fresh_data

    def get_device_by_identifier(self, identifier: str) -> DeviceT:
        """
        Find and return a device by its identifier/serial number

        raise DeviceLogicError if not found.
        """
        for device in self.devices:
            if device.conf.identifier == identifier:
                return device

        raise DeviceLogicError(
            f"Device with identifier {identifier} is not in the hub."
        )

    async def check_health(self) -> dict[str, bool]:
        """
        Check if all devices are responding.
        Returns a dictionary mapping device identifiers to True/False.
        """
        if not self.devices:
            return {}

        tasks = [device.ping() for device in self.devices]
        results = await asyncio.gather(*tasks)

        return {
            device.conf.context: result for device, result in zip(self.devices, results)
        }


class SerialHub(Hub[PapouchSerialDevice]):
    """Hub for serial devices."""

    def __init__(self, client: PapouchSerialClient) -> None:
        """Construct serial hub."""

        super().__init__()
        self.client = client

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()

    @property
    def used_addresses(self) -> list[int]:
        """Return used addresses of the bus."""

        return [device.conf.address for device in self.devices]

    async def create_and_add_device(self, address: int) -> None:
        """Create a new device over serial and add it to the hub.

        Raise DeviceLogicError if the device couldn't be created.
        """

        if device := await create_serial_device(self.client, address):
            self._devices.append(device)
            return
        raise DeviceLogicError(f"Unable to create device with address: {address}.")

    async def discover_and_add_single_device(self) -> None:
        """Create a new device over serial and add it to the hub.

        Raise DeviceLogicError if the device couldn't be created.
        """

        try:
            _, serial_number, address = await _get_device_details(
                self.client, SERIAL_BROADCAST_ADDRESS
            )
        except DeviceConnectionError as err:
            raise DeviceConnectionError(
                "Unable to discover device. There are likely multiple devices on the bus."
            ) from err

        if address in self.used_addresses:
            device = self.get_device_by_identifier(serial_number)
            raise DeviceLogicError(
                f"Device: {device.conf.context} is already in the hub."
            )

        await self.create_and_add_device(address)

    def remove_device_by_address(self, address: int) -> None:
        """Remove the device from the hub using its address, raise DeviceLogicError when missing."""

        for device in self.devices:
            if device.conf.address == address:
                self.devices.remove(device)
                return

        raise DeviceLogicError(f"Device with {address} is not in the hub.")

    async def create_device_by_serial_number(self, serial_number: str) -> None:
        """Assign a new address to the device and add it to the hub."""

        new_address, device_name = await assign_next_available_address(
            self.client, self.used_addresses, serial_number
        )

        if new_address and device_name is None:
            raise DeviceLogicError(
                f"Unable to create device with serial number: {serial_number}"
            )

        if new_address is None and device_name is None:
            raise DeviceLogicError(
                f"There is no available free address for: {serial_number}"
            )

        if new_address is None:
            raise DeviceLogicError("Unreachable code.")

        await self.create_and_add_device(new_address)

    def get_device_by_address(self, address: int) -> PapouchSerialDevice:
        """Find and return a device by its bus address, raise DeviceLogicError if not found."""
        for device in self.devices:
            if device.conf.address == address:
                return device

        raise DeviceLogicError(f"Device with address {address} is not in the hub.")


class NetworkHub(Hub[PapouchNetworkDevice]):
    """Hub for network (IP-based) devices."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Construct network hub.

        Unlike SerialHub which shares a single connection, NetworkHub uses
        a shared aiohttp.ClientSession to spawn individual HTTP clients per IP.
        """

        super().__init__()
        self.session = session

    @property
    def used_ips(self) -> list[str]:
        """Return IP addresses currently managed by this hub."""
        return [device.api_client.ip_address for device in self.devices]

    async def create_and_add_device(
        self, ip_address: str, password: str = "", web_port: int = 80
    ) -> None:
        """Create a new device over network and add it to the hub.

        Raise DeviceLogicError if the device couldn't be created.
        """

        client = PapouchHTTPClient(
            ip_address=ip_address,
            session=self.session,
            password=password,
            web_port=web_port,
        )

        if device := await create_network_device(client):
            self._devices.append(device)
            return

        raise DeviceLogicError(f"Unable to create network device at IP: {ip_address}.")

    async def discover_and_add_all_devices(self) -> None:
        """
        Add to the hub all supported devices that are in the network.

        Note that if the device has password or its web port isn't 80,
        this method will ignore this device.
        """

        supported_devices = await async_discover_papouch_devices(self.session)
        available_device_ips = {
            ip for ip in supported_devices if ip not in self.used_ips
        }

        tasks = [self.create_and_add_device(ip) for ip in available_device_ips]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for ip, result in zip(available_device_ips, results):
            if isinstance(result, DeviceConnectionError):
                _LOGGER.warning(
                    "Failed to auto-add discovered device at %s: %s", ip, result
                )

    def remove_device_by_ip(self, ip_address: str) -> None:
        """Remove the device from the hub using its IP, raise DeviceLogicError when missing."""

        for device in self.devices:
            if device.api_client.ip_address == ip_address:
                self.devices.remove(device)
                return

        raise DeviceLogicError(f"Device with IP {ip_address} is not in the hub.")

    def get_device_by_ip(self, ip_address: str) -> PapouchNetworkDevice:
        """Find and return a device by its IP address, raise DeviceLogicError if not found."""

        for device in self.devices:
            if device.api_client.ip_address == ip_address:
                return device

        raise DeviceLogicError(f"Device with IP {ip_address} is not in the hub.")


class NetworkSpinelHub(Hub[PapouchSerialDevice]):
    """Hub for standalone network devices that use the Spinel protocol over TCP."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.remove_all_devices()

    @property
    def used_ips(self) -> list[str]:
        """Return IP addresses currently managed by this hub."""

        result = []

        for device in self.devices:
            if ip := device.conf.host:
                result.append(ip)
            else:
                # should be unreachable
                raise DeviceLogicError(
                    f"Device: {device.conf.context} has invalid host property."
                )

        return result

    @override
    async def add_device(self, device: PapouchSerialDevice) -> None:
        """Add device to the hub and open its TCP connection"""

        try:
            await device.api_client.open()
        except SpinelTransportError as err:
            raise DeviceConnectionError(
                f"Unable to create port for {device.conf.context}"
            ) from err

        if device not in self.devices:
            self._devices.append(device)
        else:
            raise DeviceLogicError(
                f"Device {device.conf.context} is already in the hub."
            )

    async def create_and_add_device(self, ip_address: str, port: int = 10001) -> None:
        """Create a new Spinel TCP device and add it to the hub."""
        transport = TcpTransport(ip_address, port)
        client = PapouchSerialClient(transport)

        try:
            await client.open()
        except SpinelTransportError as err:
            raise DeviceConnectionError(
                f"Unable to open port for {ip_address} on {port}"
            ) from err

        try:
            device = await create_serial_device(
                client, address=SERIAL_BROADCAST_ADDRESS
            )

            if not device:
                raise DeviceLogicError(
                    f"Unable to create network Spinel device at IP: {ip_address}."
                )

            device.conf.host = ip_address
            self._devices.append(device)

        except DeviceLogicError, DeviceConnectionError:
            await client.close()
            raise

    async def remove_device(self, device: PapouchSerialDevice) -> None:
        """Remove the device from the hub and close its TCP connection."""
        try:
            self._devices.remove(device)
            await device.api_client.close()
        except ValueError as err:
            raise DeviceLogicError(
                f"{device.conf.identifier} is not in the hub."
            ) from err
        except DeviceConnectionError as err:
            raise DeviceConnectionError(
                f"Unable to close port for {device.conf.context}"
            ) from err

    async def remove_all_devices(self) -> None:
        """Remove all devices and close their ports."""

        for device in list(self.devices):
            try:
                await device.api_client.close()
            except (DeviceConnectionError, SpinelTransportError) as err:
                _LOGGER.warning(
                    "Unable to close port for %s: %s", device.conf.context, err
                )
            finally:
                self._devices.remove(device)
