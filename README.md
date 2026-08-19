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

## API Client

The API Client follows a similar architecture. There is an abstract base class `PapouchTransport` that defines the contract methods for subclasses, such as `fetch_info`, `read_command`, and `write_command`.

Currently, there is one subclass, `PapouchHTTPClient`, which fulfills this contract and handles network communication over HTTP.

## Exceptions

The library defines custom exceptions raised during execution. These exceptions are designed to be caught and handled within the Home Assistant integration.

## Usage

Although `aiopapouch` is primarily designed to serve as the underlying library for the official Home Assistant Papouch integration, it can also be used independently in standalone Python scripts.

The following example illustrates how to create a client, instantiate a device, fetch raw telemetry data, and pass it to `parse_fresh_data`:

```python
import asyncio
import aiohttp
from aiopapouch import PapouchHTTPClient, create_device

async def main():
    # Initialize the aiohttp client session
    async with aiohttp.ClientSession() as session:
        # Initialize the API transport client
        client = PapouchHTTPClient("192.168.1.100", session)
        
        # Create the device
        device = await create_device(client)
        
        if device is None:
            print("Device not supported or connection failed.")
            return

        print(f"Connected to: {device.name} at {device.location}")

        # Fetch raw fresh XML data from the device
        raw_fresh_xml = await client.fetch_data()

        # Parse fresh data to update device state and return processed readings
        parsed_data = await device.parse_fresh_data(raw_fresh_xml)
        print("Parsed telemetry data:", parsed_data)

if __name__ == "__main__":
    asyncio.run(main())

```

## Future Extensions

Papouch manufactures not only network-based devices but also serial ones (e.g., using RS485). Future extensions will include a new serial transport subclass implementing `PapouchTransport`, alongside new `PapouchDevice` subclasses designed specifically for serial communication protocols.
