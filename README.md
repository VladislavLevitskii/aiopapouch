# aiopapouch

This repository contains an asynchronous Python I/O library for Papouch s.r.o. devices.

The library provides major components: **Devices**, **API Clients**, and **Hubs** for managing multiple devices efficiently.

## Requirements

* **Python 3.14+**: The library requires Python 3.14 or higher (PEP 758).
* **aiohttp**: Required for handling asynchronous HTTP communication with the network devices.
* **pap_spinel**: Required for serial communication.

## Installation

```bash
pip install aiopapouch
```

## Supported Devices

Currently, the library supports the following Ethernet devices communicating via WEB and TCP server mode:

* Quido ETH
* Papago
    * Meteo
    * 2TH
    * 5HDI DO
    * TH 2DI DO
* TH2E
* TME
* TME Multi / Radio

and these are devices that use serial communiction (RS485):

* Quido RS485
* THT2
* THCO2
* TQS 4

## Devices

The library is designed using an object-oriented approach. Every device (or device family) is a subclass of either `PapouchNetworkDevice` or `PapouchSerialDevice` (which both inherit from the abstract `PapouchDevice` core). This clear separation of the transport layer provides shared contract methods such as `get_fresh_data`, `get_supported_sensors`, and properties like `name` and `identifier`.

Due to polymorphism, the factory functions `create_network_device` and `create_serial_device` return a generic `PapouchNetworkDevice` and `PapouchSerialDevice` respectively. This works in tandem with the `is_device_supported` function, which validates whether the hardware is supported by this library.

> ***Note:*** The constructors are asynchronous (implementing the factory pattern). Creating any device instance utilizes the network/serial communication to download the initial configuration.

> ***Note:*** The library was designed specifically for Home Assistant. Methods like `get_supported_sensors` return configurations required for entity creation. This remains the primary purpose of the library.

> ***Note:*** Initial fresh fetch of data happens before the creation of the entities, making it a valid approach to generate configurations during/after the parsing of fresh data.

## Hubs (Recommended)

When dealing with multiple devices, it is highly recommended to use **Hubs**. Hubs act as managers that group devices together, providing unified methods to concurrently fetch data (`get_fresh_data`) or verify device states (`check_health`).

The library provides **3 types of Hubs** based on the transport layer:

1. **`NetworkHub`**: Used for IP-based devices (HTTP). It utilizes a single shared `aiohttp.ClientSession` to dynamically spawn and manage individual HTTP clients for each added IP address.
2. **`SerialHub`**: Used for RS485-based devices. It takes a single shared `PapouchSerialClient` (since all devices share the same serial bus or TCP gateway) and manages devices by their hardware address or serial number.
3. **`NetworkSpinelHub`**: Used for standalone network devices that communicate via the Spinel protocol directly over a TCP socket. Unlike `SerialHub`, this hub manages individual TCP connections for each registered IP address automatically.

### Pythonic Features (Magic Methods & Context Managers)

All hubs are designed to behave like standard Python collections. You can easily get the device count using `len(hub)`, check for existence with `device in hub`, or iterate directly over the hub using `for device in hub:`.

Furthermore, hubs handling persistent socket or serial connections (`SerialHub` and `NetworkSpinelHub`) support asynchronous context managers (`async with`), ensuring that all ports and connections are cleanly closed when the block is exited.

---

## API Client & Usage

The library provides 2 major types of communication: Network and Serial (via RS485 or Spinel TCP). Although `aiopapouch` is primarily designed to serve as the underlying library for the official Home Assistant Papouch integration, it can also be used independently in standalone Python scripts.

### 1. Network Usage Example (HTTP)

```python
import asyncio
import aiohttp
from aiopapouch import NetworkHub
from aiopapouch.exceptions import DeviceLogicError

async def main():
    # Initialize the shared aiohttp client session
    async with aiohttp.ClientSession() as session:
        hub = NetworkHub(session)

        try:
            # Automatically create API clients and initialize devices by IP
            await hub.create_and_add_device("192.168.1.100", password="admin")
            await hub.create_and_add_device("192.168.1.101")
        except DeviceLogicError as err:
            print(f"Failed to add device: {err}")
            return

        # Check health of all devices concurrently
        health_status = await hub.check_health()
        print("Device health:", health_status)

        # Parse fresh data concurrently from all devices
        parsed_data = await hub.get_fresh_data()
        print("Parsed telemetry data:", parsed_data)

        # Utilize pythonic magic methods for iteration and length
        print(f"Currently managing {len(hub)} devices.")
        for device in hub:
            print(f"Device: {device.conf.name} - IP: {device.api_client.ip_address}")

if __name__ == "__main__":
    asyncio.run(main())

```

### 2. Network Spinel Usage Example (TCP)

For devices that use the Spinel protocol over an Ethernet connection, the `NetworkSpinelHub` manages individual TCP transports for you.

```python
import asyncio
from aiopapouch.hub import NetworkSpinelHub

async def main():
    # Context manager ensures all TCP ports are automatically closed on exit
    async with NetworkSpinelHub() as hub:

        # Add Spinel device by its IP and Port
        await hub.create_and_add_device("192.168.3.40", 10001)

        print("Health Status:", await hub.check_health())
        print("Telemetry Data:", await hub.get_fresh_data())

        # Showcasing pythonic iteration over the hub
        for device in hub:
            print(f"Serial Device Context: {device.conf.context}")

if __name__ == "__main__":
    asyncio.run(main())

```

### 3. Serial RS485 Usage Example

For serial communication, you can use `PapouchSerialClient` that wraps the `pap_spinel` transport layer. The client can also resolve some data from the device without needing to know its exact type.

> **Note**: Don't forget to give permissions to open/close the port if using direct USB/Serial connection (`/dev/ttyUSB0`).

The `SerialHub` also features a **Plug & Play discovery** method (`discover_and_add_single_device()`). If you have exactly one new device physically connected to the bus, this method uses the broadcast address to automatically identify and add it. *(Note: If multiple unknown devices are on the bus, this will raise an error due to data collision).*

```python
import asyncio
from aiopapouch import SerialHub
from aiopapouch.client import PapouchSerialClient
from pap_spinel import TcpTransport, SerialTransport

async def main():
    # You can use either a TCP Gateway or Direct Serial connection:
    transport = TcpTransport("192.168.3.33", 10001)
    # transport = SerialTransport(port="/dev/ttyUSB0", baudrate=9600)

    client = PapouchSerialClient(transport)
    await client.open()

    # The async context manager automatically calls client.close() when done
    async with SerialHub(client) as hub:

        # Option A: Plug & Play - Auto-detect a single connected device
        # await hub.discover_and_add_single_device()

        # Option B: Automatically assign free addresses by known serial numbers
        await hub.create_device_by_serial_number("1395/0149")
        await hub.create_device_by_serial_number("1255/5627")

        # Option C: Add a device by a known address
        # await hub.create_and_add_device(address=1)

        # Check health and fetch data concurrently
        print("Health Status:", await hub.check_health())
        print("Telemetry Data:", await hub.get_fresh_data())

        for device in hub:
            print(f"Device: {device.conf.name} - Address: {device.conf.address}")

if __name__ == "__main__":
    asyncio.run(main())

```

### Exceptions

The library defines custom exceptions raised during execution, such as `DeviceConnectionError`, `DeviceAuthError`, `DeviceParseError`, and `DeviceLogicError`.

### Device Control and Configuration

In addition to fetching telemetry data, the library allows controlling devices and modifying their settings. Because supported entities (switches, selects, numbers, buttons) vary by hardware model and configuration, `PapouchDevice` provides introspection methods (`get_supported_switches`, `get_supported_selects`, `get_supported_buttons`, `get_supported_numbers`) to discover available controls and their valid parameters before executing control methods.

For a complete list of available methods and properties, please refer to the docstrings in the source code of the `PapouchDevice` base class.

#### Discovery Methods

* `get_supported_switches()`: Returns a list of available switch entities and their `item_id`.
* `get_supported_selects()`: Returns available select entities, including `category`, `item_id`, and allowed `options`.
* `get_supported_buttons()`: Returns button commands (`cmd`) and placeholders.
* `get_supported_numbers()`: Returns configuration for counter operations. Rather than generic numbers, these entities represent specific actions like decreasing a counter or setting a counter to a specific value. It includes allowed min/max values, step size, `category` (e.g., `decrease_counter`, `set_counter`), and `item_id`.

#### Control Methods

* `turn_on_switch(item_id)` / `turn_off_switch(item_id)`: Controls digital outputs by `item_id`.
* `set_select_option(category, item_id, option)`: Changes a selection setting by `category`, `item_id`, and `option` string.
* `set_number_value(category, item_id, value)`: Executes a counter operation (such as decreasing or directly setting the counter) based on the `category`, `item_id`, and specified `value`.
* `execute_button_command(cmd_type)`: Triggers a button action using the `cmd` identifier.

#### Code Example (Control)

```python
import asyncio
import aiohttp
from aiopapouch import PapouchHTTPClient, create_network_device

async def main():
    async with aiohttp.ClientSession() as session:
        client = PapouchHTTPClient("192.168.1.100", session)
        device = await create_network_device(client)

        if device is None:
            return

        # 1. Discover available controls and parameters
        print("Switches:", device.get_supported_switches())
        print("Selects:", device.get_supported_selects())
        print("Buttons:", device.get_supported_buttons())
        print("Numbers:", device.get_supported_numbers())

        # 2. Execute actions using the explicitly discovered IDs and exact option strings

        # Turn on the relay identified by item_id "1"
        await device.turn_on_switch("1")

        # Set the sensor type for item_id "1" in the "sensor_type" category
        await device.set_select_option("sensor_type", "1", "temperature_ds")

        # Execute the autodetect button command
        await device.execute_button_command("set_sensor_1")

        # Decrease the counter on input "1" by a specific value
        await device.set_number_value("decrease_counter", "1", 10)

if __name__ == "__main__":
    asyncio.run(main())

```
