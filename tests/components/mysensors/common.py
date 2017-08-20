"""Test helpers for MySensors integration."""
from asynctest import MagicMock

from mysensors import const_22 as const, message, sensor
from mysensors.gateway_mqtt import AsyncMQTTGateway
from mysensors.gateway_serial import AsyncSerialGateway
from mysensors.gateway_tcp import AsyncTCPGateway

from homeassistant.components import mysensors as mysensors_comp
from homeassistant.setup import async_setup_component

DEVICE = "/dev/ttyACM0"

DEFAULT_CONFIG = {
    "mysensors": {
        "gateways": [{"device": DEVICE}],
        "version": "2.0",
        "persistence": False,
    }
}


def get_gateway(hass):
    """Get a gateway from set up gateways."""
    gateways = hass.data[mysensors_comp.MYSENSORS_GATEWAYS]
    gateway = next(iter(gateways.values()))
    return gateway


async def setup_mysensors(hass, config=None):
    """Set up mysensors component."""
    if config is None:
        config = DEFAULT_CONFIG

    assert await async_setup_component(hass, "mysensors", config)


def set_gateway_attrs(mock):
    """Set gateway attributes."""
    mock.sensors = {}
    mock.metric = True
    mock.const = const
    mock.ota = MagicMock()
    return mock


def mock_mqtt_gateway(pub_callback, sub_callback, **kwargs):
    """Return a mock MQTT gateway."""
    gateway = MagicMock(
        spec=AsyncMQTTGateway,
        pub_callback=pub_callback,
        sub_callback=sub_callback,
        **kwargs,
    )
    gateway = set_gateway_attrs(gateway)
    return gateway


def mock_serial_gateway(port, **kwargs):
    """Return a mock MQTT gateway."""
    gateway = MagicMock(spec=AsyncSerialGateway, port=port, **kwargs)
    gateway = set_gateway_attrs(gateway)
    return gateway


def mock_tcp_gateway(host, port=5003, **kwargs):
    """Return a mock MQTT gateway."""
    gateway = MagicMock(spec=AsyncTCPGateway, server_address=(host, port), **kwargs)
    gateway = set_gateway_attrs(gateway)
    return gateway


def get_mock_node(
    node_id,
    node_type=const.Presentation.S_ARDUINO_NODE,
    sketch_name="mock sketch",
    sketch_version="1.0",
):
    """Return a mock node."""
    node = MagicMock(
        spec=sensor.Sensor,
        sensor_id=node_id,
        type=node_type,
        sketch_name=sketch_name,
        sketch_version=sketch_version,
        children={},
    )
    return node


def get_mock_child(child_id, child_type, description=""):
    """Return a mock child."""
    child = MagicMock(
        spec=sensor.ChildSensor,
        id=child_id,
        type=child_type,
        description=description,
        values={},
    )
    return child


def get_mock_message(
    node_id=0, child_id=0, msg_type=0, ack=0, sub_type=0, payload="", gateway=None
):
    """Return a mock message."""
    msg = MagicMock(
        spec=message.Message,
        node_id=node_id,
        child_id=child_id,
        type=msg_type,
        ack=ack,
        sub_type=sub_type,
        payload=payload,
        gateway=gateway,
    )
    return msg
