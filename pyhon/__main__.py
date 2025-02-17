#!/usr/bin/env python
import argparse
import asyncio
import json
import logging
import sys
from getpass import getpass
from pathlib import Path
from typing import Any

import httpx
import yaml

from .const import API_KEY, API_URL, APP_VERSION, OS
from .diagnostic import Anonymiser, Diagnoser
from .hon import Hon

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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

    subparser = parser.add_subparsers(dest="command", required=True)

    subparser.add_parser("dump", help="dumps hOn APIs data")

    app_config = subparser.add_parser(
        "app-config", help="print urls for app configuration"
    )
    app_config.add_argument("language", help="language (de, en, fr...)")

    subparser.add_parser("mqtt", help="test mqtt client")
    subparser.add_parser(
        "credentials", help="perform authentication flow and return tokens"
    )

    arguments = vars(parser.parse_args())

    if arguments["command"] not in {"translate"}:
        if arguments["user"] is None:
            arguments["user"] = input("User for hOn account: ")
        if arguments["password"] is None:
            arguments["password"] = getpass("Password for hOn account: ")

    return arguments


async def main() -> None:
    args = get_arguments()

    # TODO: if --import is set, monkeypatch API to use local data

    match args:
        case {"command": "credentials", "json": as_json}:
            async with Hon(
                email=args["user"],
                password=args["password"],
                enable_mqtt=False,
                autoload=False,
            ) as hon:
                data = await Diagnoser(hon).tokens()
                writer = json if as_json else yaml
                writer.dump(data, sys.stdout)

        case {"command": "mqtt"}:
            async with Hon(
                email=args["user"],
                password=args["password"],
                enable_mqtt=True,
                autoload=True,
            ) as hon:
                await hon.mqtt_client.loop_task

        case {"command": "dump", "json": as_json, "anonymous": anon}:
            async with Hon(
                email=args["user"],
                password=args["password"],
                enable_mqtt=False,
                autoload=False,
            ) as hon:
                writer = json if as_json else yaml
                dump = await Diagnoser(hon).full_dump()
                dump = dump.model_dump(
                    mode="json",
                    context={"anonymiser": Anonymiser().anonymise} if anon else None,
                )
                writer.dump(dump, sys.stdout, indent=2)

        case {"command": "app-config", "language": lang, "json": as_json}:
            async with httpx.AsyncClient(
                base_url=API_URL,
                headers={"x-api-key": API_KEY},
            ) as client:
                response = await client.post(
                    "app-config",
                    json={
                        "languageCode": lang,
                        "beta": True,
                        "appVersion": APP_VERSION,
                        "os": OS,
                    },
                )
                writer = json if as_json else yaml
                writer.dump(response.json(), sys.stdout)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Aborted by user")
