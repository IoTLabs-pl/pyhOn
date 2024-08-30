import random
from string import hexdigits

from pyhon import const

MQTT_CLIENT_ID = f"{const.MOBILE_ID}_{''.join(random.choices(hexdigits, k=16))}"


def descriptor(mobile: bool = False) -> dict[str, str | int]:
    os_key = "mobileOs" if mobile else "os"

    return {
        "appVersion": const.APP_VERSION,
        "mobileId": const.MOBILE_ID,
        os_key: const.OS,
        "osVersion": const.OS_VERSION,
        "deviceModel": const.DEVICE_MODEL,
    }
