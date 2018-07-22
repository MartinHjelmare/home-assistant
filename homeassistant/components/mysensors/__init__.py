"""
Connect to a MySensors gateway via pymysensors API.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/mysensors/
"""
import logging

import voluptuous as vol

from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

# Loading the config flow file will register the flow
from .config_flow import MySensorsFlowHandler  # noqa
from .const import (
    ATTR_DEVICES, CONF_DEVICE, CONF_GATEWAYS, CONF_NODE_NAME, DOMAIN,
    ENTRY_GATEWAY, GATEWAY_SCHEMA, MQTT_COMPONENT, MYSENSORS_GATEWAYS)
from .device import get_mysensors_devices
from .gateway import (
    async_setup_gateways, create_gateway, finish_gateway_setup,
    get_mysensors_gateway)

REQUIREMENTS = ['pymysensors==0.16.0']

_LOGGER = logging.getLogger(__name__)

CONF_DEBUG = 'debug'
CONF_PERSISTENCE = 'persistence'


def deprecated(key):
    """Mark key as deprecated in configuration."""
    def validator(config):
        """Check if key is in config, log warning and remove key."""
        if key not in config:
            return config
        _LOGGER.warning(
            "%s option for %s is deprecated. Please remove %s from your "
            "configuration file", key, DOMAIN, key)
        config.pop(key)
        return config
    return validator


CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema(vol.All(
        deprecated(CONF_DEBUG), {
            vol.Required(CONF_GATEWAYS): vol.All(
                cv.ensure_list, [
                    vol.All(deprecated(CONF_PERSISTENCE), GATEWAY_SCHEMA)]),
        }
    ))
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    """Set up the MySensors component."""
    conf = config.get(DOMAIN, {})
    hass.data[MYSENSORS_GATEWAYS] = {}

    # User has configured gateways
    if CONF_GATEWAYS in conf:
        gateways = conf[CONF_GATEWAYS]
    else:
        # Component not specified in config, we're loaded via config entries
        gateways = []

    if not gateways:
        return True

    await async_setup_gateways(hass, conf)

    return True


async def async_setup_entry(hass, entry):
    """Set up a MySensors gateway from a config entry."""
    gateways = hass.data[MYSENSORS_GATEWAYS]
    gateway_conf = entry.data[ENTRY_GATEWAY]

    if gateway_conf[CONF_DEVICE] == MQTT_COMPONENT:
        result = await hass.config_entries.async_forward_entry_setup(
            entry, MQTT_COMPONENT)
        if not result:
            _LOGGER.error("Failed to set up %s component", MQTT_COMPONENT)
            return False

    ready_gateway = await hass.async_add_job(
        create_gateway, hass, gateway_conf)
    if ready_gateway is not None:
        gateways[id(ready_gateway)] = ready_gateway

        hass.async_add_job(finish_gateway_setup(hass, ready_gateway))

        return True
    _LOGGER.error(
        "Failed to create gateway for device %s", gateway_conf[CONF_DEVICE])
    return False


def _get_mysensors_name(gateway, node_id, child_id):
    """Return a name for a node child."""
    node_name = '{} {}'.format(
        gateway.sensors[node_id].sketch_name, node_id)
    node_name = next(
        (node[CONF_NODE_NAME] for conf_id, node in gateway.nodes_config.items()
         if node.get(CONF_NODE_NAME) is not None and conf_id == node_id),
        node_name)
    return '{} {}'.format(node_name, child_id)


@callback
def setup_mysensors_platform(
        hass, domain, discovery_info, device_class, device_args=None,
        async_add_devices=None):
    """Set up a MySensors platform."""
    # Only act if called via MySensors by discovery event.
    # Otherwise gateway is not setup.
    if not discovery_info:
        return
    if device_args is None:
        device_args = ()
    new_devices = []
    new_dev_ids = discovery_info[ATTR_DEVICES]
    for dev_id in new_dev_ids:
        devices = get_mysensors_devices(hass, domain)
        if dev_id in devices:
            continue
        gateway_id, node_id, child_id, value_type = dev_id
        gateway = get_mysensors_gateway(hass, gateway_id)
        if not gateway:
            continue
        device_class_copy = device_class
        if isinstance(device_class, dict):
            child = gateway.sensors[node_id].children[child_id]
            s_type = gateway.const.Presentation(child.type).name
            device_class_copy = device_class[s_type]
        name = _get_mysensors_name(gateway, node_id, child_id)

        args_copy = (*device_args, gateway, node_id, child_id, name,
                     value_type)
        devices[dev_id] = device_class_copy(*args_copy)
        new_devices.append(devices[dev_id])
    if new_devices:
        _LOGGER.info("Adding new devices: %s", new_devices)
        if async_add_devices is not None:
            async_add_devices(new_devices, True)
    return new_devices
