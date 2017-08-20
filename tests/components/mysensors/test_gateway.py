"""Test MySensors gateway."""
import asyncio
from unittest.mock import call, patch

import pytest
import voluptuous as vol

from homeassistant.components import mysensors as mysensors_comp
from homeassistant.setup import async_setup_component

from .common import (
    DEVICE,
    get_gateway,
    get_mock_child,
    get_mock_message,
    get_mock_node,
    setup_mysensors,
)

from tests.common import (
    async_fire_mqtt_message,
    async_mock_mqtt_component,
    mock_coro_func,
)

MQTT_CONFIG = {
    "mysensors": {
        "gateways": [{"device": "mqtt"}],
        "version": "2.0",
        "persistence": False,
    }
}


@pytest.fixture(name="mock_mqtt")
async def mqtt_fixture(hass):
    """Set up the mqtt component and return a mock mqtt client."""
    mqtt_mock = await async_mock_mqtt_component(hass)
    return mqtt_mock


@pytest.fixture(name="mock_discover_platform")
def discover_platform_fixture():
    """Mock discovery.load_platform."""
    with patch(
        "homeassistant.components.mysensors.helpers.discovery.async_load_platform",
        side_effect=mock_coro_func(),
    ) as mock_discovery:
        yield mock_discovery


async def test_setup(gateway):
    """Test setup of mysensors."""
    assert gateway.event_callback is not None


async def test_domain_name_device(hass, mock_mysensors, mock_gw_ready):
    """Test setup of mysensors with domain name device."""
    config = {
        "mysensors": {
            "gateways": [{"device": "domain.com"}],
            "version": "2.0",
            "persistence": False,
        }
    }

    with patch(
        "homeassistant.components.mysensors.cv.isdevice",
        side_effect=vol.Invalid("Bad device"),
    ):
        with patch("socket.getaddrinfo"):
            res = await async_setup_component(hass, "mysensors", config)
    assert res
    await hass.async_block_till_done()
    gateway = get_gateway(hass)
    assert gateway.device == "domain.com"
    assert not gateway.sensors


@pytest.mark.parametrize("config", [MQTT_CONFIG])
async def test_mqtt_device(hass, mock_mqtt, config, gateway, caplog):
    """Test setup of mysensors with mqtt device."""
    assert gateway.device == "mqtt"
    assert not gateway.sensors

    topic = "test"
    payload = "test_payload"
    qos = 0
    retain = False

    gateway.pub_callback(topic, payload, qos, retain)
    await hass.async_block_till_done()

    assert mock_mqtt.async_publish.call_count == 1
    assert mock_mqtt.async_publish.call_args == call(topic, payload, qos, retain)

    calls = []

    def sub_callback(*args):
        """Mock the subscription callback."""
        calls.append(args)

    gateway.sub_callback(topic, sub_callback, qos)
    await hass.async_block_till_done()
    async_fire_mqtt_message(hass, topic, payload, qos, retain)
    await hass.async_block_till_done()
    await hass.async_block_till_done()  # not sure why we need two?

    assert len(calls) == 1
    assert calls[0] == (topic, payload, qos)


async def test_persistence(
    hass, mock_isdevice, mock_discover_platform, mock_mysensors, mock_gw_ready
):
    """Test MySensors gateway persistence."""
    config = {
        "mysensors": {
            "gateways": [{"device": DEVICE, "persistence_file": "test.json"}],
            "version": "2.0",
            "persistence": True,
        }
    }
    assert await async_setup_component(hass, "mysensors", config)
    gateway = get_gateway(hass)
    node_id = 1
    child_id = 1
    gateway.sensors[node_id] = get_mock_node(node_id)
    child_type = gateway.const.Presentation.S_TEMP
    value_type = gateway.const.SetReq.V_TEMP
    gateway.sensors[node_id].children[child_id] = child = get_mock_child(
        child_id, child_type
    )
    payload = "20.0"
    child.values[value_type] = payload
    new_dev_ids = [(id(gateway), node_id, child.id, value_type)]
    await hass.async_block_till_done()
    assert mock_discover_platform.call_count == 1
    assert mock_discover_platform.call_args[0][:4] == (
        hass,
        "sensor",
        mysensors_comp.DOMAIN,
        {"devices": new_dev_ids, "name": mysensors_comp.DOMAIN},
    )


async def test_gateway_not_ready(hass, caplog, mock_isdevice, mock_mysensors):
    """Test gateway not ready."""
    called = False

    async def fut():
        """Fake future that raises asyncio.TimeoutError."""
        nonlocal called
        called = True
        raise asyncio.TimeoutError

    with patch(
        "homeassistant.components.mysensors.gateway.asyncio.Future", return_value=fut()
    ):
        assert not called
        await setup_mysensors(hass)
        await hass.async_block_till_done()

    assert called
    assert (
        "Gateway {} not ready after {} secs".format(
            DEVICE, mysensors_comp.gateway.GATEWAY_READY_TIMEOUT
        )
        in caplog.text
    )


async def test_set_gateway_ready(hass, mock_isdevice, mock_mysensors):
    """Test set gateway ready."""
    fut = asyncio.Future(loop=hass.loop)

    with patch(
        "homeassistant.components.mysensors.gateway.asyncio.Future", return_value=fut
    ):
        await setup_mysensors(hass)
        gateway = get_gateway(hass)

        async def gateway_start():
            """Start gateway."""
            value_type = gateway.const.Internal.I_GATEWAY_READY
            msg = get_mock_message(0, 255, 3, sub_type=value_type, gateway=gateway)
            gateway.event_callback(msg)

        gateway.start = gateway_start
        await hass.async_block_till_done()

    assert fut.done()


async def test_validate_child(gateway, node, child):
    """Test validate_child."""
    value_type = list(child.values)[0]
    validated = mysensors_comp.gateway.validate_child(gateway, node.sensor_id, child)
    assert "sensor" in validated
    assert len(validated["sensor"]) == 1
    dev_id = validated["sensor"][0]
    assert dev_id == (id(gateway), node.sensor_id, child.id, value_type)


async def test_validate_child_no_values(gateway, node, child):
    """Test validate_child without child values."""
    child.values.clear()
    validated = mysensors_comp.gateway.validate_child(gateway, node.sensor_id, child)
    assert not validated


async def test_validate_node_no_sketch_name(gateway, node):
    """Test validate node with no sketch name."""
    node.sketch_name = None
    validated = mysensors_comp.gateway.validate_node(gateway, node.sensor_id)
    assert not validated


async def test_validate_bad_child(gateway, node, child):
    """Test validate_child with bad child type."""
    child.type = -1
    validated = mysensors_comp.gateway.validate_child(gateway, node.sensor_id, child)
    assert not validated


async def test_validate_child_bad_value(gateway, node, child):
    """Test validate_child with bad value type."""
    value_type = -1
    child.values.clear()
    child.values[value_type] = "20.0"
    validated = mysensors_comp.gateway.validate_child(gateway, node.sensor_id, child)
    assert not validated


async def test_callback(hass, gateway, node, child, message, mock_discover_platform):
    """Test MySensors gateway callback."""
    value_type = list(child.values)[0]
    new_dev_ids = [(id(gateway), node.sensor_id, child.id, value_type)]
    gateway.event_callback(message())
    await hass.async_block_till_done()
    assert mock_discover_platform.call_count == 1
    assert mock_discover_platform.call_args[0][:4] == (
        hass,
        "sensor",
        mysensors_comp.DOMAIN,
        {"devices": new_dev_ids, "name": mysensors_comp.DOMAIN},
    )


async def test_callback_no_child(gateway, node, mock_discover_platform):
    """Test MySensors gateway callback for non child."""
    msg = get_mock_message(node.sensor_id, 255, 0, sub_type=17, gateway=gateway)
    gateway.event_callback(msg)
    assert mock_discover_platform.call_count == 0


async def test_discover_platform(hass, gateway, node, child, message):
    """Test discovery of a sensor platform."""
    payload = list(child.values.values())[0]
    gateway.event_callback(message())
    await hass.async_block_till_done()
    entity_id = "sensor.mock_sketch_{}_{}".format(node.sensor_id, child.id)
    state = hass.states.get(entity_id)
    assert state.state == payload
