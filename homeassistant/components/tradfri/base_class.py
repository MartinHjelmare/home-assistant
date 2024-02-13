"""Base class for IKEA TRADFRI."""
from __future__ import annotations

from abc import abstractmethod
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any, Concatenate, ParamSpec, TypeVar, cast

from pytradfri.command import Command
from pytradfri.device import Device
from pytradfri.error import RequestError

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import TradfriDeviceDataUpdateCoordinator

_T = TypeVar("_T", bound="CoordinatorEntity")
_P = ParamSpec("_P")


def handle_error(
    func: Callable[Concatenate[_T, _P], Awaitable[Any]],
) -> Callable[Concatenate[_T, _P], Coroutine[Any, Any, None]]:
    """Handle tradfri api call error."""

    @wraps(func)
    async def wrapper(self: _T, *args: _P.args, **kwargs: _P.kwargs) -> None:
        """Decorate api call."""
        try:
            await func(self, *args, **kwargs)
        except RequestError as err:
            LOGGER.error("Unable to execute command %s: %s", args, err)
            self.coordinator.last_update_success = False
            await self.coordinator.async_request_refresh()

    return wrapper


class TradfriBaseEntity(CoordinatorEntity[TradfriDeviceDataUpdateCoordinator]):
    """Base Tradfri device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        device_coordinator: TradfriDeviceDataUpdateCoordinator,
        gateway_id: str,
        api: Callable[[Command | list[Command]], Any],
    ) -> None:
        """Initialize a device."""
        super().__init__(device_coordinator)

        self._gateway_id = gateway_id

        self._device: Device = device_coordinator.data

        self._device_id = self._device.id
        self._api = api

        info = self._device.device_info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer=info.manufacturer,
            model=info.model_number,
            name=self._device.name,
            sw_version=info.firmware_version,
            via_device=(DOMAIN, gateway_id),
        )
        self._attr_unique_id = f"{gateway_id}-{self._device_id}"

    @abstractmethod
    @callback
    def _refresh(self) -> None:
        """Refresh device data."""

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Tests fails without this method.
        """
        self._refresh()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return cast(bool, self._device.reachable) and super().available
