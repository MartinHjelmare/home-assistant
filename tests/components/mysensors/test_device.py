"""Test MySensors device."""
from unittest.mock import patch

import pytest

from .common import get_mock_message


@pytest.fixture(name="mock_update_delay")
def update_delay_fixture():
    """Mock update delay time."""
    with patch("homeassistant.components.mysensors.device.UPDATE_DELAY", 0):
        yield


async def wait_for_update(hass):
    """Wait for update to complete.

    The update logic involves many subsequent jobs.
    """
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def test_sensor_unit_prefix(hass, gateway, child, node, message):
    """Test discovery of a sensor platform with sensor with unit prefix."""
    child.type = gateway.const.Presentation.S_SOUND
    value_type = gateway.const.SetReq.V_LEVEL
    child.values.clear()
    payload = "20.0"
    child.values[value_type] = payload
    child.values[gateway.const.SetReq.V_UNIT_PREFIX] = "MdB"
    gateway.event_callback(message())
    await hass.async_block_till_done()
    entity_id = "sensor.mock_sketch_{}_{}".format(node.sensor_id, child.id)
    state = hass.states.get(entity_id)
    assert state.state == payload
    assert state.attributes["unit_of_measurement"] == "MdB"


async def test_update_switch(hass, gateway, node, child, message, mock_update_delay):
    """Test update value of switch device."""
    child.type = gateway.const.Presentation.S_BINARY
    value_type = gateway.const.SetReq.V_STATUS
    child.values.clear()
    payload = "0"
    child.values[value_type] = payload
    gateway.event_callback(message())
    await wait_for_update(hass)
    entity_id = "switch.mock_sketch_{}_{}".format(node.sensor_id, child.id)
    state = hass.states.get(entity_id)
    assert state.state == "off"
    payload = "1"
    child.values[value_type] = payload
    gateway.event_callback(message())
    await wait_for_update(hass)
    state = hass.states.get(entity_id)
    assert state.state == "on"


async def test_update_light(hass, gateway, node, child, mock_update_delay):
    """Test update value of light device."""
    child.type = gateway.const.Presentation.S_DIMMER
    value_type = gateway.const.SetReq.V_PERCENTAGE
    child.values.clear()
    payload = "100"
    child.values[value_type] = payload
    v_status_type = gateway.const.SetReq.V_STATUS
    child.values[v_status_type] = "0"
    msg = get_mock_message(
        node.sensor_id,
        child.id,
        1,
        sub_type=value_type,
        payload=payload,
        gateway=gateway,
    )
    gateway.event_callback(msg)
    await wait_for_update(hass)
    entity_id = "light.mock_sketch_{}_{}".format(node.sensor_id, child.id)
    state = hass.states.get(entity_id)
    assert state.state == "off"
    child.values[v_status_type] = "1"
    msg = get_mock_message(
        node.sensor_id,
        child.id,
        1,
        sub_type=v_status_type,
        payload="1",
        gateway=gateway,
    )
    gateway.event_callback(msg)
    await wait_for_update(hass)
    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state.attributes["brightness"] == 255
