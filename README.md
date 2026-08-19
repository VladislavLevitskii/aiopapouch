# aiopapouch
The repository contains I/O Python library for Papouch s.r.o. devices.

The library provides 2 major components: **Devices** and **API Client** for communication with these devices.

## Devices

The library is designed in object oriented way, that means that every device (or family) is a child of **PapouchDevice** that provides contract methods for example, `parse_fresh_data`, `get_supported_sensors` or properties `name`, `location` etc. This file `base.py` also includes mixins, they are especially for HTTP communication, because various devices that communicates via network use same functions. Creating 1 more layer between **PapouchDevice** and end subclasses is unnecessary since we need to include only a couple of functions.

Due to polymorphism function `create_device` returns abstract **PapouchDevice** it works in tandem with function `is_device_supported` that is used for checking if the device is supported.

> **_Note:_** The constructors are async (factory pattern) and creating any device uses network and downloads the proper configuration.

> **_Note:_** The library was designed especially for Home Assistant, so methods like `get_support_...` return configurations for entities in HA. And it is actually the only main purpose of that library.

## API Client

API Client provides 