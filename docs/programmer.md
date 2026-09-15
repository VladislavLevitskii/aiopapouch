# Programmer Documentation

Before reading this documentation, we strongly suggest you read the [README](../README.md) as it provides the big picture of the library. This section focuses on the concrete implementation details.

## PapouchDevice

This section describes the nuances every programmer should know about the base class of the devices.

### Mixins

Every network device inherits from `HTTPMixin`, which allows us to reduce repeating code and keep network-specific logic out of serial devices. Specifically, it contains `_send_command` that creates a REST query and uses an HTTP client to send it, and `_check_response` that controls the return status of the request.

`HttpMixinHost` is nothing more than a Mypy helper.

### Configuration

`PapouchDevice` provides various properties (e.g., name, location, context, etc.), but all of these properties are structured within the base dataclass `PapouchConfiguration`. Specific devices extend this dataclass to include their unique properties (e.g., sensors). It is strongly advised to return properties directly from the configuration, as Home Assistant (HA) can manipulate the configuration directly. For example, HA can change the identifier from a serial number to a MAC address when changing the device mode to a TCP server.

### Constants / Unit Map

Since almost every device uses various types of sensors, it was decided to create a universal map of units, type mappings, and sensor/counter types.

The library also provides methods to work with these maps. `_get_unit` is the most important one, it looks into the map and returns the unit in its text representation. Usage:

```python
self._conf.unit = self._get_unit(self.TEMPERATURE_SNS_TYPE, "0")

```

The code above returns the first unit in the temperature block ("°C").

The second method is `_generate_semantic_key`, used for creating a key for the parsed data to improve readability. The method simply uses the `...SNS_TYPE` constants to retrieve their text representation.

> **Note**: Some devices may send different indices for the sensor map (e.g., for some devices, "3" means "co2" and not "dew_point"). That means you must map it back to the universal constants. Also, the units from the devices are not standardized at all (e.g., you might receive "C" instead of "0" for Celsius).

### Fetching the Data

Please note that `parse_fresh_data` in serial devices will actively fetch the data, whereas network devices expect the already fetched data via the `xml_data` argument.

## Clients

This section describes minor details about both clients. Both are designed for easier usage at the expense of the single-responsibility principle. This is done to keep context-related code together.

### HTTP

`PapouchHTTPClient` is not just a simple HTTP client, it handles more functionality than a standard client should. The client holds context about the devices, meaning it provides methods for fetching specific data (fresh data, info, settings, device mode) and retrieving particular pieces of it.

> **Note**: Don't forget about `get_device_mode`, this method is used in retrieving device mode of the device and some of them does **NOT** have the proper tag (it is not standardized), so you will need to include these devices in the exception list.

### Serial

The same applies to `PapouchSerialClient`. It is a wrapper around `SpinelClient` from the `pap_spinel` library and has standard transport methods (`open`/`close`), as well as device-related methods (fetching manufacturing data, location, setting the address, etc.).

### Context

Since every device provides a `context` property, it is heavily used in the communication methods of the clients. This is utilized to include the context of the problem within exceptions. For example, exceptions will automatically provide the identifier and name of the device that threw them.

## Converters

This section is straightforward, don't use converters at all unless you need somehow to distinguish between converters and network devices using only IP address. Converters are created in Home Assistant primarily for UX purposes and delegate the responsibility of resolving the converter mode to this library.

## Creating the Devices

The library provides two functions to create a serial or network device. Both are async and fetch the initial data required to create the proper configuration.

The backbone of these functions are **device handlers**—dictionaries where keys represent the type of communication (network/serial) and values are async factory lambdas for the concrete devices.

These handlers are also used to deduce whether a particular device is supported. The function tries to match a handler key within the device name.

## Adding a New Device

The first thing you should do is create a new async factory for your device. The device class itself must inherit from `PapouchDevice`. Then, include that factory function in the handler or create a new handler with the proper key (type).

We strongly advise you to look at the existing implementation of some devices as an example (e.g., [tqs4.py](../src/aiopapouch/devices/tqs4.py)).
