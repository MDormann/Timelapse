#!/usr/bin/env python3
"""Reolink Kamera Screenshot -> QNAP NAS (NFS)"""

import configparser
import logging
import random
import string
import sys
from datetime import datetime
from pathlib import Path

import requests

CONFIG_FILE = Path(__file__).parent / "config.ini"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if not CONFIG_FILE.exists():
        log.error("Konfigurationsdatei nicht gefunden: %s", CONFIG_FILE)
        log.error("Bitte config.ini aus config.example.ini erstellen und anpassen.")
        sys.exit(1)
    cfg.read(CONFIG_FILE)
    return cfg


def random_rs(length: int = 16) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def fetch_snapshot(host: str, user: str, password: str, channel: int, timeout: int) -> bytes:
    url = (
        f"http://{host}/cgi-bin/api.cgi"
        f"?cmd=Snap&channel={channel}&rs={random_rs()}"
        f"&user={user}&password={password}"
    )
    log.info("Lade Snapshot von %s (Kanal %d) ...", host, channel)
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "image" not in content_type:
        raise ValueError(f"Unerwarteter Content-Type: {content_type!r}. Zugangsdaten prüfen.")

    return resp.content


def save_snapshot(data: bytes, nas_path: Path, filename_prefix: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    daily_dir = nas_path / datetime.now().strftime("%Y-%m-%d")
    daily_dir.mkdir(parents=True, exist_ok=True)

    dest = daily_dir / f"{filename_prefix}_{timestamp}.jpg"
    dest.write_bytes(data)
    log.info("Gespeichert: %s (%d Bytes)", dest, len(data))
    return dest


def main() -> None:
    cfg = load_config()

    host = cfg.get("camera", "host")
    user = cfg.get("camera", "user")
    password = cfg.get("camera", "password")
    channel = cfg.getint("camera", "channel", fallback=0)
    timeout = cfg.getint("camera", "timeout", fallback=15)

    nas_path = Path(cfg.get("nas", "path"))
    prefix = cfg.get("nas", "filename_prefix", fallback="snapshot")

    if not nas_path.exists():
        log.error("NAS-Pfad nicht erreichbar: %s", nas_path)
        sys.exit(1)

    data = fetch_snapshot(host, user, password, channel, timeout)
    save_snapshot(data, nas_path, prefix)


if __name__ == "__main__":
    main()
