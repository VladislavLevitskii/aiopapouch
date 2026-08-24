# aiopapouch

This repository contains an asynchronous Python I/O library for Papouch s.r.o. devices.

The library provides two major components: **Devices** and **API Client** for communication with the hardware.

## Requirements

* **Python 3.14+**: The library requires Python 3.14 or higher (PEP 758).
* **aiohttp**: Required for handling asynchronous HTTP communication with the devices.

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

## Devices

The library is designed using an object-oriented approach. Every device (or device family) is a subclass of `PapouchDevice`, which provides contract methods such as `parse_fresh_data`, `get_supported_sensors`, and properties like `name` and `location`. The `base.py` file also includes mixins (primarily for HTTP communication), as various network devices share the same functions. Creating an additional layer between `PapouchDevice` and the final subclasses is unnecessary since only a specific subset of functions needs to be included.

Due to polymorphism, the `create_device` function returns an abstract `PapouchDevice`. It works in tandem with the `is_device_supported` function, which validates whether the hardware is supported by this library.

> ***Note:*** The constructors are asynchronous (implementing the factory pattern). Creating any device instance utilizes the network to download the initial configuration.

> ***Note:*** The library was designed specifically for Home Assistant. Methods like `get_supported_sensors` return configurations required for entity creation in Home Assistant. This remains the primary purpose of the library.

> ***Note:*** Initial fresh fetch of data happens before the creation of the entities, making it a valid approach to generate configurations during the parsing of fresh data.

> ***Note:*** While using the create_device factory function is the recommended approach for automatic hardware detection and initialization, specific device subclasses (e.g. QuidoETH, TH2E, PapagoETH_2TH) can also be imported and instantiated directly if the exact device type is already known.

## API Client

The API Client follows a similar architecture. There is an abstract base class `PapouchTransport` that defines the contract methods for subclasses, such as `fetch_info`, `read_command`, and `write_command`.

Currently, there is one subclass, `PapouchHTTPClient`, which fulfills this contract and handles network communication over HTTP. If the hardware is protected by credentials or uses a non-standard port, you can provide the password and port arguments directly when initializing the client:

```python
# Initialize the client with authentication and a custom port
client = PapouchHTTPClient("192.168.1.100", session, password="my_secure_password", port=8080)
```

## Exceptions

The library defines custom exceptions raised during execution. The usage is below.

## Usage

Although `aiopapouch` is primarily designed to serve as the underlying library for the official Home Assistant Papouch integration, it can also be used independently in standalone Python scripts.

The following example illustrates how to create a client, instantiate a device, fetch raw telemetry data, and pass it to `parse_fresh_data`:

```python
import asyncio
import aiohttp
from aiopapouch import PapouchHTTPClient, create_device
# Option B
# from aiopapouch.devices.papago import PapagoETH_1TH_2DI_1DO

async def main():
    # Initialize the aiohttp client session
    async with aiohttp.ClientSession() as session:
        # Initialize the API transport client
        client = PapouchHTTPClient("192.168.1.100", session)
        
        # Option A: Automatic detection via factory pattern (Recommended)
        try:
            device = await create_device(client)
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

### Device Control and Configuration

In addition to fetching telemetry data, the library allows controlling devices and modifying their settings. Because supported entities (switches, selects, numbers, buttons) vary by hardware model and configuration, `PapouchDevice` provides introspection methods (`get_supported_switches`, `get_supported_selects`, `get_supported_buttons`, `get_supported_numbers`) to discover available controls and their valid parameters before executing control methods.

For a complete list of available methods and properties, please refer to the docstrings in the source code of the `PapouchDevice` base class.

### Discovery Methods

* `get_supported_switches()`: Returns a list of available switch entities and their `item_id`.
* `get_supported_selects()`: Returns available select entities, including `category`, `item_id`, and allowed `options`.
* `get_supported_buttons()`: Returns button commands (`cmd`) and placeholders.
* `get_supported_numbers()`: Returns configuration for counter operations. Rather than generic numbers, these entities represent specific actions like decreasing a counter or setting a counter to a specific value. It includes allowed min/max values, step size, `category` (e.g., `decrease_counter`, `set_counter`), and `item_id`.

### Control Methods

* `turn_on_switch(item_id)` / `turn_off_switch(item_id)`: Controls digital outputs by `item_id`.
* `set_select_option(category, item_id, option)`: Changes a selection setting by `category`, `item_id`, and `option` string.
* `set_number_value(category, item_id, value)`: Executes a counter operation (such as decreasing or directly setting the counter) based on the `category`, `item_id`, and specified `value`.
* `execute_button_command(cmd_type)`: Triggers a button action using the `cmd` identifier.

### Code Example

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

## Future Extensions

Papouch manufactures not only network-based devices but also serial ones (e.g., using RS485). Future extensions will include a new serial transport subclass implementing `PapouchTransport`, alongside new `PapouchDevice` subclasses designed specifically for serial communication protocols.
