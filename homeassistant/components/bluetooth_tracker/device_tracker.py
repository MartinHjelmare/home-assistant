"""Tracking for bluetooth devices."""
import asyncio
import logging
from typing import List, Tuple, Optional

# pylint: disable=import-error
import bluetooth
from bt_proximity import BluetoothRSSI
import voluptuous as vol

from homeassistant.components.device_tracker import PLATFORM_SCHEMA
from homeassistant.components.device_tracker.const import (
    CONF_CONSIDER_HOME,
    CONF_SCAN_INTERVAL,
    CONF_TRACK_NEW,
    DOMAIN,
    SOURCE_TYPE_BLUETOOTH,
)
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import HomeAssistantType
import homeassistant.util.dt as dt_util


_LOGGER = logging.getLogger(__name__)

BT_PREFIX = "BT_"

CONF_REQUEST_RSSI = "request_rssi"

CONF_DEVICE_ID = "device_id"

DEFAULT_DEVICE_ID = -1
TRACKER_UPDATE = "bluetooth_update"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_TRACK_NEW): cv.boolean,
        vol.Optional(CONF_REQUEST_RSSI): cv.boolean,
        vol.Optional(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): vol.All(
            vol.Coerce(int), vol.Range(min=-1)
        ),
    }
)


def is_bluetooth_device(device) -> bool:
    """Check whether a device is a bluetooth device by its mac."""
    return device.mac and device.mac[:3].upper() == BT_PREFIX


def discover_devices(device_id: int) -> List[Tuple[str, str]]:
    """Discover Bluetooth devices."""
    result = bluetooth.discover_devices(
        duration=8,
        lookup_names=True,
        flush_cache=True,
        lookup_class=False,
        device_id=device_id,
    )
    _LOGGER.debug("Bluetooth devices discovered = %d", len(result))
    return result


def lookup_name(mac: str) -> Optional[str]:
    """Lookup a Bluetooth device name."""
    _LOGGER.debug("Scanning %s", mac)
    return bluetooth.lookup_name(mac, timeout=5)


async def async_setup_scanner(
    hass: HomeAssistantType, config: dict, async_see, discovery_info=None
):
    """Set up the Bluetooth Scanner.

    Legacy.
    """
    pass


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up a bluetooth device tracker."""
    device_id: int = config_entry.data[CONF_DEVICE_ID]
    interval = config_entry.options[CONF_SCAN_INTERVAL]
    request_rssi = config_entry.options[CONF_REQUEST_RSSI]
    update_bluetooth_lock = asyncio.Lock()
    devices_to_track = set()
    entities = set()

    # If track new devices is true discover new devices on startup.
    track_new: bool = config_entry.options[CONF_TRACK_NEW]
    _LOGGER.debug("Tracking new devices is set to %s", track_new)

    if request_rssi:
        _LOGGER.debug("Detecting RSSI for devices")

    def see_device(mac: str, device_name: str, rssi=None) -> None:
        """Mark a device as seen."""
        attributes = {}
        if rssi is not None:
            attributes["rssi"] = rssi

        if mac in entities:
            async_dispatcher_send(hass, TRACKER_UPDATE, mac, attributes)
            return

        entities.add(mac)

        async_add_entities(
            [BluetoothEntity(config_entry, mac, device_name, attributes)]
        )

    async def perform_bluetooth_update():
        """Discover Bluetooth devices and update status."""
        _LOGGER.debug("Performing Bluetooth devices discovery and update")

        try:
            if track_new:
                devices = await hass.async_add_executor_job(discover_devices, device_id)
                for mac, device_name in devices:
                    if mac not in devices_to_track:
                        devices_to_track.add(mac)

            for mac in devices_to_track:
                device_name = await hass.async_add_executor_job(lookup_name, mac)
                if device_name is None:
                    # Could not lookup device name
                    continue

                rssi = None
                if request_rssi:
                    client = BluetoothRSSI(mac)
                    rssi = await hass.async_add_executor_job(client.request_rssi)
                    client.close()

                see_device(mac, device_name, rssi)

        except bluetooth.BluetoothError:
            _LOGGER.exception("Error looking up Bluetooth device")

    async def update_bluetooth(now=None):
        """Lookup Bluetooth devices and update status."""
        # If an update is in progress, we don't do anything
        if update_bluetooth_lock.locked():
            _LOGGER.debug(
                "Previous execution of update_bluetooth "
                "is taking longer than the scheduled update of interval %s",
                interval,
            )
            return

        async with update_bluetooth_lock:
            await perform_bluetooth_update()

    async def handle_manual_update_bluetooth(call):
        """Update bluetooth devices on demand."""
        await update_bluetooth()

    hass.async_create_task(update_bluetooth())
    async_track_time_interval(hass, update_bluetooth, interval)

    hass.services.async_register(
        DOMAIN, "bluetooth_tracker_update", handle_manual_update_bluetooth
    )


class BluetoothEntity(ScannerEntity):
    """Represent a tracked device that is on a scanned bluetooth network."""

    def __init__(self, config_entry, mac, device_name, attributes):
        """Set up bluetooth entity."""
        self._attributes = attributes
        self._config_entry = config_entry
        self._last_seen = dt_util.utcnow()
        self._mac = mac
        self._name = device_name
        self._unsub_dispatcher = None

    @property
    def device_state_attributes(self):
        """Return device specific attributes."""
        return self._attributes

    @property
    def is_connected(self):
        """Return true if the device is connected to the network."""
        if (
            dt_util.utcnow() - self._last_seen
            < self._config_entry.options[CONF_CONSIDER_HOME]
        ):
            return True

        return False

    @property
    def name(self):
        """Return the name of the device."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID."""
        return self._mac

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return SOURCE_TYPE_BLUETOOTH

    async def async_added_to_hass(self):
        """Register state update callback."""
        self._unsub_dispatcher = async_dispatcher_connect(
            self.hass, TRACKER_UPDATE, self._async_receive_data
        )

    async def async_will_remove_from_hass(self):
        """Clean up after entity before removal."""
        self._unsub_dispatcher()

    @callback
    def _async_receive_data(self, mac, attributes):
        """Mark the device as seen."""
        if mac != self._mac:
            return

        self._last_seen = dt_util.utcnow()
        self._attributes.update(attributes)
        self.async_write_ha_state()
