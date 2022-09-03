"""Support for MySensors updates."""

from __future__ import annotations

from typing import Any, cast

from mysensors import BaseAsyncGateway, Message, Sensor, ota

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_DEVICE_FIRMWARE,
    DOMAIN as MYSENSORS_DOMAIN,
    MYSENSORS_DISCOVERY,
    MYSENSORS_GATEWAYS,
    NODE_FIRMWARE_CALLBACK,
    DiscoveryInfo,
)
from .firmware_store import FirmwareData


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up MySensors update platform based on a config entry."""

    @callback
    def async_discover(discovery_info: DiscoveryInfo) -> None:
        """Discover and add a MySensors update entity."""
        dev_ids = discovery_info["devices"]
        entities: list[UpdateEntity] = []
        for dev_id in dev_ids:
            gateway_id, node_id, _, _ = dev_id
            gateway: BaseAsyncGateway = hass.data[MYSENSORS_DOMAIN][MYSENSORS_GATEWAYS][
                gateway_id
            ]
            entities.append(MySensorsUpdateEntity(gateway_id, gateway, node_id))

        async_add_entities(entities)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            MYSENSORS_DISCOVERY.format(config_entry.entry_id, Platform.UPDATE),
            async_discover,
        ),
    )


class MySensorsUpdateEntity(UpdateEntity):
    """Represent a MySensors update entity."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )
    _attr_title = "MySensors"
    _attr_name = "Firmware"
    _firmware_total_blocks: int | None = None
    _firmware_block = 0

    def __init__(
        self, gateway_id: str, gateway: BaseAsyncGateway, node_id: int
    ) -> None:
        """Set up instance attributes."""
        self.gateway_id = gateway_id
        self.gateway = gateway
        self.node_id = node_id
        node: Sensor = self.gateway.sensors[self.node_id]
        sketch_name = cast(str, node.sketch_version)
        self._attr_unique_id = f"{gateway_id}-{node_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(MYSENSORS_DOMAIN, f"{gateway_id}-{node_id}")},
            manufacturer=MYSENSORS_DOMAIN,
            name=f"{sketch_name} {node_id}",
            sw_version=self.sketch_version,
        )

    @property
    def available(self) -> bool:
        """Return true if entity is available."""
        firmware_data = self._get_firware_data()

        return firmware_data is not None

    @property
    def sketch_version(self) -> str:
        """Return the sketch version."""
        node: Sensor = self.gateway.sensors[self.node_id]
        return cast(str, node.sketch_version)

    @property
    def installed_version(self) -> str:
        """Version currently installed and in use."""
        return self.sketch_version

    @property
    def latest_version(self) -> str | None:
        """Latest version available for install."""
        firmware_data = self._get_firware_data()

        if firmware_data is None:
            return None

        return firmware_data.sketch_version

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install an update."""
        firmware_data = self._get_firware_data()
        if firmware_data is None:
            raise ValueError(f"No firmware data available for {self.name}")

        await self.gateway.update_fw(
            self.node_id, firmware_data.type, firmware_data.version, firmware_data.file
        )

    async def async_added_to_hass(self) -> None:
        """Register update callback."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                NODE_FIRMWARE_CALLBACK.format(self.gateway_id, self.node_id),
                self._update_state,
            )
        )

    @callback
    def _update_state(self, msg: Message) -> None:
        """Update the entity state from a MySensors message."""
        stream_type = msg.gateway.const.Stream(msg.sub_type)
        if stream_type == msg.gateway.const.Stream.ST_FIRMWARE_CONFIG_REQUEST:
            requested_blocks = ota.fw_hex_to_int(msg.payload, 5)[2]
            self._firmware_total_blocks = requested_blocks
        elif stream_type == msg.gateway.const.Stream.ST_FIRMWARE_REQUEST:
            current_block = ota.fw_hex_to_int(msg.payload, 3)[2]
            self._firmware_block = current_block

        if self._firmware_total_blocks is not None:
            self._attr_update_percentage = round(
                self._firmware_block / self._firmware_total_blocks * 100
            )
            self.async_write_ha_state()

    def _get_firware_data(self) -> FirmwareData | None:
        """Return firmware data for this update."""
        if not self.platform or not self.platform.config_entry:
            return None

        device_firmware: dict[str, dict[str, Any]] | None = (
            self.platform.config_entry.options.get(CONF_DEVICE_FIRMWARE)
        )
        if device_firmware is None:
            return None

        device_registry = dr.async_get(self.hass)
        device_entry = device_registry.async_get_device(
            identifiers={(MYSENSORS_DOMAIN, f"{self.gateway_id}-{self.node_id}")}
        )
        if device_entry is None:
            return None

        firmware_data = device_firmware.get(device_entry.id)

        if firmware_data is None:
            return None

        return FirmwareData.from_dict(firmware_data)
