import asyncio

from pap_spinel import SerialTransport, SpinelClient

from aiopapouch.client import PapouchSerialClient
from aiopapouch.devices.tht2 import async_setup_tht2


async def main():

    transport = SerialTransport("/dev/ttyUSB0", 9600)
    client = PapouchSerialClient(SpinelClient(transport))

    await client.open()

    try:
        device = await async_setup_tht2(client, 0x31, "052319559")
        data = await device.parse_fresh_data()
        print(data)

        print(f"Name: {device.name}, location: {device.location}")


    finally:
        await client.close()


asyncio.run(main())