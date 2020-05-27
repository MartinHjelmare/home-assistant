"""The Supervisor API Test integration."""
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Supervisor API Test component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Supervisor API Test from a config entry."""
    hassio = hass.components.hassio
    services = SupervisorServices(hass, hassio)
    services.async_register()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    return True


class SupervisorServices:
    """Handle Supervisor services."""

    def __init__(self, hass, hassio):
        """Set up instance."""
        self._hass = hass
        self._hassio = hassio

    @callback
    def async_register(self):
        """Register all services."""
        self._hass.services.async_register(
            DOMAIN,
            "is_addon_installed",
            self.async_is_addon_installed,
            schema=vol.Schema(
                {vol.Required("slug"): cv.string, vol.Required("repository"): cv.string}
            ),
        )

    async def async_is_addon_installed(self, call):
        """Log if addon is installed."""
        slug = call.data["slug"]
        repository = call.data["repository"]
        is_addon_installed = await self._hassio.async_addon_is_installed(
            self._hass, slug, repository
        )
        _LOGGER.warning(
            "Add-on %s_%s installed: %s", repository, slug, is_addon_installed
        )
