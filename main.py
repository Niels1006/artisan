import datetime
import json
import os
from time import sleep
from typing import TypedDict

import dotenv
import pytz
import requests
from niels_coloredlogger.logger import logger
from typing_extensions import ReadOnly

import config

dotenv.load_dotenv(".env")
webhook: str | None = os.getenv("WEBHOOK")
if webhook is None:
    raise Exception("Please define WEBHOOK in .env")

client: requests.Session = requests.Session()


class PadInfo(TypedDict):
    id: ReadOnly[str]
    short: ReadOnly[str]
    long: ReadOnly[str]
    price: ReadOnly[float]
    size: ReadOnly[int]
    hardness: ReadOnly[str]
    inStock: ReadOnly[bool]
    sir: ReadOnly[int]
    color: ReadOnly[int]


def yen_to_eur(client: requests.Session, yen: int) -> float:
    response: dict = client.get(
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/jpy.json"
    ).json()
    rate: float = response["jpy"]["eur"]
    return round(yen * rate, 2)


def fetch(client: requests.Session, sir: int, size: int, color: int) -> PadInfo:
    """
    Fetches data from artisan-jp

    Parameters
    ----------
    client   : requests.Session
    sir      : int
    size     : int
               1: S
               2: M
               3: L
               4: XL
               5: XXL
    color    : int

    Returns
    -------
    PadInfo
        Dict with info about pad
    """
    req = client.post(
        "https://www.artisan-jp.com/get_syouhin.php", data={"kuni": "on", "sir": sir, "size": size, "color": color}
    )

    if req.status_code != 200:
        raise ConnectionError

    attrs: list[str] = req.text.split("/")
    info: PadInfo = {
        "id": attrs[0],
        "short": attrs[1],
        "long": attrs[2],
        "price": yen_to_eur(client, int(float(attrs[3]))),
        "size": int(attrs[4]),
        "hardness": attrs[5],
        "inStock": is_available(attrs[0]),
        "color": color,
        "sir": sir,
    }
    logger.info(f"Fetched {info["short"]}")
    return info


def is_available(id: str) -> bool:
    return id != "NON"


def get_key(info: PadInfo) -> str:
    return f"{info["sir"]}|{info["size"]}|{info["color"]}"


def conv_key(key: str) -> tuple[int, int, int]:
    sir, size, color = key.split("|")
    return int(sir), int(size), int(color)


def size_to_str(size: int) -> str:
    return ["Small", "Medium", "Large", "XLarge", "XXLarge"][size - 1]


def send_webhook(info: PadInfo):
    body: dict = {
        "content": None,
        "embeds": [
            {
                "title": info["long"].split(" ")[0],
                "color": 1041978 if info["inStock"] else 15615248,
                "fields": [
                    {"name": "Price", "value": f"{info["price"]}€", "inline": True},
                    {"name": "Size", "value": f"{size_to_str(info["size"])}", "inline": True},
                    {"name": "Hardness", "value": f"{info["hardness"]}", "inline": True},
                ],
                "timestamp": str(datetime.datetime.now(pytz.timezone("Europe/Berlin"))),
            }
        ],
        "attachments": [],
    }

    requests.post(webhook, json=body)


def get_avail():
    with open("data.json", "r") as f:
        return json.load(f)


def add_to_avail(availablity: dict[str, PadInfo], info: PadInfo):
    availablity[get_key(info)] = info


def save_avail(availability: dict[str, PadInfo]):
    with open("data.json", "w") as f:
        json.dump(availability, f)


def run():
    availability: dict[str, PadInfo] = get_avail()
    for c in config.pads:
        try:

            info: PadInfo = fetch(client, *c)
        except ConnectionError:
            logger.error(f"{c} failed to fetch")
            continue
        if availability.get(get_key(info)) == None:
            add_to_avail(availability, info)
            send_webhook(info)
        else:
            if availability[get_key(info)]["inStock"] != info["inStock"]:
                add_to_avail(availability, info)
                send_webhook(info)
    save_avail(availability)


def __main__():
    while True:
        run()
        sleep(3600)


if __name__ == "__main__":
    __main__()
