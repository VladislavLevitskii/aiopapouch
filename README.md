# aiopapouch

This repository contains an asynchronous Python I/O library for Papouch s.r.o. devices.

The library provides two major components: **Devices** and **API Client** for communication with the hardware.

## Requirements

* **Python 3.14+**: The library requires Python 3.14 or higher (PEP 758).
* **aiohttp**: Required for handling asynchronous HTTP communication with the devices.
* **pap_spinel**: Required for serial communication.

## Installation

```bash
pip install aiopapouch
```

## Supported Devices

Currently, the library supports the following Ethernet devices communicating via WEB mode:

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

* THT2

## Devices

The library is designed using an object-oriented approach. Every device (or device family) is a subclass of `PapouchDevice`, which provides contract methods such as `parse_fresh_data`, `get_supported_sensors`, and properties like `name` and `identifier`. The `base.py` file also includes mixins (primarily for HTTP communication), as various network devices share the same functions. Creating an additional layer between `PapouchDevice` and the final subclasses is unnecessary since only a specific subset of functions needs to be included.

Due to polymorphism, the `create_device` function returns an abstract `PapouchDevice`. It works in tandem with the `is_device_supported` function, which validates whether the hardware is supported by this library.

> ***Note:*** The constructors are asynchronous (implementing the factory pattern). Creating any device instance utilizes the network/serial communication to download the initial configuration.

> ***Note:*** The library was designed specifically for Home Assistant. Methods like `get_supported_sensors` return configurations required for entity creation. This remains the primary purpose of the library.

> ***Note:*** Initial fresh fetch of data happens before the creation of the entities, making it a valid approach to generate configurations during/after the parsing of fresh data.

> ***Note:*** While using the create_device factory function is the recommended approach for automatic hardware detection and initialization, specific device subclasses (e.g. QuidoETH, TH2E, THT2) can also be imported and instantiated directly if the exact device type is already known.

## API Client

The library provides 2 major types of the communication: Network and Serial (via RS485).

### Network

For communication via network you can use `PapouchHTTPClient` that handles communication over HTTP. If the hardware is protected by credentials or uses a non-standard port, you can provide the password and port arguments directly when initializing the client alongside the IP address:

```python
# Initialize the client with authentication and a custom port
client = PapouchHTTPClient("192.168.1.100", session, password="my_secure_password", port=8080)
```

If you want to communicate with the device that has extra functionality (e.g. TH2E has memory) you can send GET and POST methods using `read_command` and `write_command`.

#### Usage

Although `aiopapouch` is primarily designed to serve as the underlying library for the official Home Assistant Papouch integration, it can also be used independently in standalone Python scripts.

The following example illustrates how to create a client, instantiate a device, fetch raw telemetry data, and pass it to `parse_fresh_data`:

```python
import asyncio
import aiohttp
from aiopapouch import PapouchHTTPClient, create_network_device
from aiopapouch.exception import DeviceAuthError, DeviceConnectionError, DeviceParseError
# Option B
# from aiopapouch.devices.papago import PapagoETH_1TH_2DI_1DO

async def main():
    # Initialize the aiohttp client session
    async with aiohttp.ClientSession() as session:
        # Initialize the API transport client
        client = PapouchHTTPClient("192.168.1.100", session)
        
        # Option A: Automatic detection via factory pattern (Recommended)
        try:
            device = await create_network_device(client)
        except DeviceConnectionError:
            print("Failed to connect to the device.")
            return
        except DeviceAuthError:
            print("Invalid credentials.")
            return
        except DeviceParseError:
            print("Failed to parse device configuration.")
            return

        if device is None:
            print("Device not supported or connection failed.")
            return

        print(f"Connected to: {device.name} at {device.location}")

        # Option B: Direct instantiation if the device model is known beforehand
        # settings_xml = await client.fetch_settings()
        # device = PapagoETH_1TH_2DI_1DO(client, settings_xml, device_name="Papago ETH 1HT 2DI DO", location="Rack 1")

        # Fetch raw fresh XML data from the device
        raw_fresh_xml = await client.fetch_data()

        # Parse fresh data to update device state and return processed readings
        parsed_data = await device.parse_fresh_data(raw_fresh_xml)
        print("Parsed telemetry data:", parsed_data)

if __name__ == "__main__":
    asyncio.run(main())

```

### Serial RS485

For serial communication you can use `PapouchSerialClient` that handles communication over RS485.

> **Note**: Don't forget to give permissions to open/close port.

The client can also resolve some data from the device without needing to know its exact type:

`get_info`, `get_man_data` and `get_location`

All you need is an address, but if you bought the device right now and you don't know the address, you can set it up using `set_address` method. All you need is a serial number.

> **Warning**: Make sure that during setting the address there is only 1 device connected.

Of course the library doesn't provide all of the possible tools that the particular device can have, so you can communicate with it using `write_command` method that returns `SpinelPacket` (97 format). Then you can access its payload (bytes) via `data` property.

#### Usage

```python
import asyncio

from aiopapouch import create_serial_device
from aiopapouch.client import PapouchSerialClient
from pap_spinel import SerialTransport, SpinelClient


async def main():

    transport = SerialTransport(port = "/dev/ttyUSB0", baudrate = 9600)
    client = PapouchSerialClient(SpinelClient(transport))

    await client.open()

    try:
        device = await create_serial_device(api_client = client, address = 0)
        data = await device.parse_fresh_data()
        print(data)
        # {'sensor': {'temperature_1': 27.1, 'humidity_2': 45.8, 'dew_point_3': 14.4}}

        print(f"Name: {device.name}, location: {device.location}, serial number: {device.identifier}")
        # Name: THT2, location: Workspace, serial number: 0523/19559

    finally:
        await client.close()


asyncio.run(main())
```

### Exceptions

The library defines custom exceptions raised during execution. The usage is [below](#code-example).

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

#### Code Example

```python
import asyncio
import aiohttp
from aiopapouch import PapouchHTTPClient, create_device

async def main():
    # Initialize the aiohttp client session
    async with aiohttp.ClientSession() as session:
        # Initialize the API transport client
        client = PapouchHTTPClient("192.168.1.100", session)
        device = await create_device(client)
        
        if device is None:
            return

        # 1. Discover available controls and parameters by printing them
        print("Switches:", device.get_supported_switches())
        # Output example: [{'item_id': '1', 'name': 'Output 1', ...}, ...]

        print("Selects:", device.get_supported_selects())
        # Output example: [{'item_id': '1', 'category': 'sensor_type', 'options': ['unused', 'temperature_ds', ...], ...}, ...]

        print("Buttons:", device.get_supported_buttons())
        # Output example: [{'cmd': 'set_sensor_1', ...}, ...]

        print("Numbers:", device.get_supported_numbers())
        # Output example: [{'item_id': '1', 'category': 'decrease_counter', 'min_value': 0, 'max_value': 4294967295, ...}, ...]

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
