"""Provide a store for MySensors firmware."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.core import HomeAssistant

from .const import (
    CONF_FIRMWARE_TYPE,
    CONF_FIRMWARE_VERSION,
    CONF_FIRWMARE_FILE,
    CONF_SKETCH_VERSION,
    DOMAIN,
)

FIRMWARE_STORE = f"{DOMAIN}_firmware"


@dataclass
class FirmwareData:
    """Represent firmware data."""

    file: str
    sketch_version: str
    type: int
    version: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FirmwareData:
        """Create a FirmwareData instance from a dict."""
        return FirmwareData(
            file=data[CONF_FIRWMARE_FILE],
            sketch_version=data[CONF_SKETCH_VERSION],
            type=data[CONF_FIRMWARE_TYPE],
            version=data[CONF_FIRMWARE_VERSION],
        )


def process_firmware_file(hass: HomeAssistant, uploaded_file_id: str) -> str:
    """Read an uploaded firmware file and write it to the firmware store."""
    firmware_dir = hass.config.path(FIRMWARE_STORE)
    if not os.path.exists(firmware_dir):
        os.makedirs(firmware_dir)
    firmware_path = hass.config.path(FIRMWARE_STORE, uploaded_file_id)
    with process_uploaded_file(hass, uploaded_file_id) as file_path, open(
        firmware_path, mode="wb"
    ) as store_file:
        contents = file_path.read_bytes()
        store_file.write(contents)

    return firmware_path
