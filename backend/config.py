"""PostgreSQL connection settings from config.ini."""

from __future__ import annotations

import configparser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.ini"

DEFAULTS = {
    "host": "localhost",
    "port": "5432",
    "database": "postgres",
    "user": "postgres",
    "password": "",
}
HTTP_DEFAULTS = {
    "port": "17778",
    "jwt_secret": "dev-secret",
}


def load_config() -> dict[str, str]:
    values = dict(DEFAULTS)
    parser = configparser.ConfigParser(interpolation=None)
    if not CONFIG_PATH.exists():
        return values
    parser.read(CONFIG_PATH, encoding="utf-8")
    if parser.has_section("postgresql"):
        for key in values:
            if parser.has_option("postgresql", key):
                values[key] = parser.get("postgresql", key)
    return values


def load_http_config() -> dict[str, str]:
    """API port and JWT secret. Missing keys keep the local defaults."""
    values = dict(HTTP_DEFAULTS)
    parser = configparser.ConfigParser(interpolation=None)
    if not CONFIG_PATH.exists():
        return values
    parser.read(CONFIG_PATH, encoding="utf-8")
    if parser.has_section("http"):
        for key in values:
            if parser.has_option("http", key):
                values[key] = parser.get("http", key)
    return values
