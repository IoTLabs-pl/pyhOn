#!/usr/bin/env python
import argparse
import asyncio
import json
import logging
import sys
from getpass import getpass
from pathlib import Path
from typing import Any

import yaml

from pyhon.diagnostic import tool

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from pyhon import Hon

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


def get_arguments() -> dict[str, Any]:
    """Get parsed arguments."""
    parser = argparse.ArgumentParser(description="pyhOn: Command Line Utility")
    parser.add_argument("-u", "--user", help="user for haier hOn account")
    parser.add_argument("-p", "--password", help="password for haier hOn account")
    parser.add_argument(
        "-i",
        "--import",
        help="import mock data from specified directory",
        metavar="DIR",
        type=Path,
    )
    parser.add_argument("-x", "--anonymous", help="anonymize data", action="store_true")
    parser.add_argument(
        "--json", help="print output as json instead of yaml", action="store_true"
    )

    subparser = parser.add_subparsers(dest="command")

    dump = subparser.add_parser("dump", help="print devices data")
    dump.add_argument("--keys", help="print as key format", action="store_true")

    export = subparser.add_parser("export", help="export hOn APIs data")
    export.add_argument("--zip", help="create zip archive", action="store_true")
    export.add_argument(
        "--directory",
        help="output directory, cwd if not specified",
        default=Path().cwd(),
        type=Path,
    )

    translation = subparser.add_parser(
        "translate", help="print available translation keys"
    )
    translation.add_argument("language", help="language (de, en, fr...)")

    subparser.add_parser("mqtt", help="test mqtt client")

    arguments = vars(parser.parse_args())

    if arguments["command"] is None:
        arguments["command"] = "dump"
        arguments["keys"] = False

    if arguments["command"] not in {"translate"}:
        if arguments["user"] is None:
            arguments["user"] = input("User for hOn account: ")
        if arguments["password"] is None:
            arguments["password"] = getpass("Password for hOn account: ")

    return arguments


async def main() -> None:
    args = get_arguments()

    # TODO: if --import is set, monkeypatch API to use local data
    async with Hon(
        args["user"], args["password"], start_mqtt=False, load_data=False
    ) as hon:
        match args:
            case {
                "command": "export",
                "anonymous": anon,
                "directory": path,
                "zip": as_zip,
            }:
                await tool.Diagnoser.from_raw_api_data(hon._api, path, anon, as_zip)  # noqa: SLF001

            case {"command": "mqtt"}:
                await hon.load_data()
                async with hon.mqtt_client as m:
                    if m.loop_task:
                        await m.loop_task

            case {"command": "dump", "keys": flat, "json": as_json, "anonymous": anon}:
                await hon.load_data()
                writer = json if as_json else yaml
                for d in hon.appliances:
                    data = tool.Diagnoser(d).as_dict(flat, anon)
                    _LOGGER.info("%s - %s >>", d.appliance_type, d.nick_name)
                    writer.dump(data, sys.stdout, sort_keys=False)

            case {"command": "translate", "language": lang, "json": as_json}:
                writer = json if as_json else yaml
                data = await hon.get_translations(lang)
                writer.dump(data, sys.stdout)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Aborted by user")
