# Programmer Documentation

Before reading this documentation, we strongly suggest you read the [README](../README.md) as it provides the big picture of the library. This section focuses on the concrete implementation details.

## Architecture & Device Hierarchy

This section describes the core architecture of the library, specifically how device logic and transport mechanisms are cleanly separated.

### Transport Layers

Instead of using generic mixins, the library strictly enforces the transport layer at the base class level. `PapouchDevice` is the absolute abstract root, but concrete devices must inherit from one of its two primary transport branches:

* **`PapouchNetworkDevice`**: Provides HTTP-specific logic (e.g., `_send_command` mapped to `SET.XML`, response checking).
* **`PapouchSerialDevice`**: Provides RS485-specific logic.

### Cooperative Multiple Inheritance (The Diamond Pattern)

Some device families, such as **Quido**, exist in both Ethernet and RS485 variants. To keep the codebase DRY and fully type-safe, the library utilizes Python's cooperative multiple inheritance to solve the **Diamond Problem** efficiently.

Instead of duplicating code or relying on untyped mixins, complex devices are built using composition:

1. **Logic Base:** A class like `QuidoBase` contains solely the device's internal logic (counters, inputs, outputs, parsing rules). It does not know how it communicates.
2. **Transport Base:** `PapouchNetworkDevice` or `PapouchSerialDevice` provides the communication methods.
3. **Final Device:** `QuidoRS485` inherits from **both** `QuidoBase` and `PapouchSerialDevice`.

This forms a classic diamond inheritance structure, terminating at the root `PapouchDevice`. Python handles this seamlessly using its **C3 Linearization (Method Resolution Order - MRO)**, ensuring the root class is initialized only once.

> **Note on Type-Safety:** When composing devices this way, Mypy requires explicit type narrowing. The final subclass (e.g., `QuidoRS485`) must override the `conf` property to return the specific combined dataclass (e.g., `QuidoSerialConfiguration`), ensuring statical analysis knows both device-specific parameters and transport parameters (like `address`) are safely available.

### Configuration

`PapouchDevice` provides fundamental properties (e.g., name, location, context), but all structured data is held within the base dataclass `PapouchConfiguration`.

Just like the device classes, configurations are split into transport branches:

* **`PapouchNetworkConfiguration`**: For HTTP devices.
* **`PapouchSerialConfiguration`**: Adds the required `address` field.

Specific devices extend these dataclasses. For devices using the Diamond Pattern (like Quido), the configuration dataclasses also use multiple inheritance (e.g., `QuidoSerialConfiguration` inherits from both `QuidoConfiguration` and `PapouchSerialConfiguration`). Python's `@dataclass` automatically merges these fields correctly based on the MRO.

It is strongly advised to return properties directly from the configuration, as Home Assistant (HA) can manipulate the configuration directly (e.g., changing the identifier from a serial number to a MAC address when changing the device mode to a TCP server).

### Constants / Unit Map

Since almost every device uses various types of sensors, the library implements a universal map of units, type mappings, and sensor/counter types inside the base class.

The library provides methods to work with these maps. `_get_unit` looks into the map and returns the unit in its text representation. Usage:

```python
self.conf.unit = self._get_unit(self.TEMPERATURE_SNS_TYPE, "0")

```

The code above returns the first unit in the temperature block ("°C").

The second method is `_generate_semantic_key`, used for creating a standardized key for the parsed data to improve readability. The method uses the `...SNS_TYPE` constants to retrieve their text representation.

> **Note**: Some devices may send different indices for the sensor map (e.g., for some devices, "3" means "co2" and not "dew_point"). That means you must map it back to the universal constants manually. Also, the units sent by the hardware are not standardized (e.g., receiving "C" instead of "0" for Celsius).

## Clients

Both clients are designed for easier usage at the expense of the single-responsibility principle. This design choice keeps context-related code centralized.

### HTTP

`PapouchHTTPClient` handles more functionality than a standard HTTP client. It holds device context and provides dedicated methods for fetching specific XML data chunks (fresh data, info, settings, device mode) and retrieving particular pieces of it.

> **Note**: Pay special attention to `get_device_mode`. This method retrieves the device mode, but some hardware does **NOT** use the proper standard tags. You will need to handle these exceptions directly in the client parsing logic.

### Serial

`PapouchSerialClient` wraps the `SpinelClient` from the external `pap_spinel` library. It includes standard transport methods (`open`/`close`) and high-level, device-related operations (fetching manufacturing data, location, setting the address) and most importantly lock preventing race conditions.

Since `aiopapouch` does not provide high-level abstractions for every edge-case tool a device might have, you can use the low-level `write_command` method. It returns a `SpinelPacket` (Format 97), allowing direct access to the raw payload bytes via the `data` property.

### Context

Every device configuration holds a `context` property heavily utilized in the communication methods of the clients. This is used to append descriptive device context to exceptions. For example, exceptions will automatically provide the identifier and name of the hardware that caused the failure, preventing ambiguous crash logs.

## Hubs (Device Management)

To manage multiple devices efficiently and safely, the library provides a Hub architecture. The core `Hub` is implemented as an abstract base class (`ABC`) using generic typing (`Hub[DeviceT]`), bounded by `PapouchDevice`. This ensures strict type safety across different transport layers.

Hubs centralize collective operations, such as concurrent data fetching (`get_fresh_data`) and status polling (`check_health`), leveraging `asyncio.gather` for performance.

### Architectural Differences in Hubs

Because the underlying transport layers behave fundamentally differently, the specific hub implementations reflect this in their instantiation and client management:

* **`SerialHub` (RS485):** Takes a *single* instantiated `PapouchSerialClient`. Since all RS485 devices share the same physical (or virtual) bus, the hub coordinates them using their hardware addresses or serial numbers. It also includes topology-specific methods like `discover_and_add_single_device()`, which utilizes the broadcast address to auto-detect a single connected device (safely catching data collision exceptions internally).
* **`NetworkHub` (HTTP):** Takes a shared `aiohttp.ClientSession`. Because IP devices do not share a logical bus in the same way, the `NetworkHub` acts as a factory, dynamically spawning isolated `PapouchHTTPClient` instances for every added IP address while efficiently recycling the underlying TCP connections via the shared session.

### Custom Hubs

There is a possibility to create subclasses of the `Hub` base class to implement custom topologies, specific event callbacks, or filtering logic tailored to their application needs without breaking the type-safe contracts.

## Converters

Do not use converters directly unless you specifically need to distinguish between dedicated converters (like GNOME/Edgar) and standard network devices using only an IP address. Converters are implemented primarily for Home Assistant UX purposes, delegating the responsibility of resolving the converter mode down to this library.

## Creating the Devices

The library provides two async factory functions: `create_network_device` and `create_serial_device`. Both fetch the initial data required to instantiate the device with a fully populated configuration.

The backbone of these functions are **device handlers**—internal dictionaries mapping string keys to async factory lambdas for concrete devices. These handlers deduce whether a particular device is supported by matching a handler key against the fetched device name.

## Adding a New Device

To implement a new device:

1. Create a new async factory for your device.
2. The device class itself must inherit from either `PapouchNetworkDevice` or `PapouchSerialDevice` (or use the cooperative multiple inheritance pattern if it belongs to a dual-transport family).
3. Include that factory function in the appropriate handler dictionary, or create a new handler entry with the matching string key.

Review the existing implementation of simple devices (e.g., [tqs4.py](../src/aiopapouch/devices/tqs4.py)) and complex devices (e.g., [quido.py](../src/aiopapouch/devices/quido.py)) as templates.
