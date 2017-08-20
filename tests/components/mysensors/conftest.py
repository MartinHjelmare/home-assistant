"""Provide pytest fixtures for mysensors tests."""
import asyncio

from asynctest import patch
import pytest

from .common import (
    DEFAULT_CONFIG,
    DEVICE,
    get_gateway,
    get_mock_child,
    get_mock_message,
    get_mock_node,
    mock_mqtt_gateway,
    mock_serial_gateway,
    mock_tcp_gateway,
    setup_mysensors,
)


@pytest.fixture(name="config")
def config_fixture():
    """Return configuration for mysensors."""
    return DEFAULT_CONFIG


@pytest.fixture(name="gateway")
async def gateway_fixture(hass, config, mock_isdevice, mock_mysensors, mock_gw_ready):
    """Set up mysensors component and return a gateway instance."""
    await setup_mysensors(hass, config=config)
    await hass.async_block_till_done()
    gateway = get_gateway(hass)
    return gateway


@pytest.fixture(name="node")
def node_fixture(gateway):
    """Mock a node and insert it in gateway sensors."""
    node_id = 1
    gateway.sensors[node_id] = node = get_mock_node(node_id)
    yield node


@pytest.fixture(name="child")
def child_fixture(gateway, node):
    """Mock a child and insert it in node children."""
    child_id = 1
    child_type = gateway.const.Presentation.S_TEMP
    value_type = gateway.const.SetReq.V_TEMP
    node.children[child_id] = child = get_mock_child(child_id, child_type)
    child.values[value_type] = "20.0"
    yield child


@pytest.fixture(name="message")
def message_fixture(gateway, node, child):
    """Return a function to generate a mock message."""

    def create_message():
        """Return a mock message."""
        value_type = list(child.values)[0]
        payload = list(child.values.values())[0]
        msg = get_mock_message(
            node.sensor_id,
            child.id,
            1,
            sub_type=value_type,
            payload=payload,
            gateway=gateway,
        )
        return msg

    return create_message


@pytest.fixture(name="mock_isdevice")
def isdevice_fixture():
    """Mock isdevice."""
    with patch(
        "homeassistant.helpers.config_validation.isdevice", return_value=DEVICE
    ) as mock_test:
        yield mock_test


@pytest.fixture(name="mock_mysensors")
def mysensors_fixture():
    """Mock mysensors library."""
    with patch(
        "mysensors.mysensors.AsyncMQTTGateway",
        autospec=True,
        side_effect=mock_mqtt_gateway,
    ), patch(
        "mysensors.mysensors.AsyncSerialGateway",
        autospec=True,
        side_effect=mock_serial_gateway,
    ), patch(
        "mysensors.mysensors.AsyncTCPGateway",
        autospec=True,
        side_effect=mock_tcp_gateway,
    ):
        yield


@pytest.fixture(name="mock_gw_ready")
def gw_ready_fixture(loop):
    """Mock gateway ready future."""
    fut = asyncio.Future(loop=loop)
    fut.set_result(True)
    with patch(
        "homeassistant.components.mysensors.gateway.asyncio.Future", return_value=fut
    ) as mock_future:
        yield mock_future
