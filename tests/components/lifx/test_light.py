"""Test the lifx light platform."""
from aiolifx.aiolifx import Light
from asynctest import MagicMock, patch
import pytest

from homeassistant.components.lifx import CONF_BROADCAST, CONF_SERVER, DOMAIN
from homeassistant.const import CONF_PORT, STATE_OFF, STATE_ON
from homeassistant.setup import async_setup_component

from tests.common import async_mock_service

CONFIG = {
    DOMAIN: {
        "light": [
            {
                CONF_SERVER: "localhost",
                CONF_PORT: 8888,
                CONF_BROADCAST: "broadcast_address",
            }
        ]
    }
}


@pytest.fixture(name="persistent_notification", autouse=True)
def persistent_notification_fixture(hass):
    """Mock the persistent notification service."""
    async_mock_service(hass, "persistent_notification", "create")
    async_mock_service(hass, "persistent_notification", "dismiss")


@pytest.fixture(name="aiolifx_scan", autouse=True)
def aiolifx_scan_fixture():
    """Patch aiolifx scan."""
    with patch("aiolifx.LifxScan"):
        yield


@pytest.fixture(name="aiolifx_light")
def aiolifx_light_fixture():
    """Mock aiolifx.Light."""
    mock_light = MagicMock(
        Light,
        color=(65535, 65535, 0, 0),
        mac_addr="12:34:56:78:91:23",
        ip_addr="1.2.3.4",
        label="test",
        power_level=0,
        product=3,
        version="1",
    )

    def get_color(callb=None):
        """Mock light get color method."""
        if callb is not None:
            callb(mock_light, (65535, 65535, 0, 0))

    def set_color(value, callb=None, duration=0, rapid=False):
        """Mock light set color method."""
        mock_light.color = value
        if callb is not None:
            callb(mock_light, value)

    def set_power(value, callb=None, duration=0, rapid=False):
        """Mock light set power method."""
        if value:
            mock_light.power_level = 65535
        else:
            mock_light.power_level = 0
        if callb is not None:
            callb(mock_light, value)

    def get_version(callb=None):
        """Mock light get version method."""
        if callb is not None:
            callb(mock_light, "1")

    mock_light.get_color.side_effect = get_color
    mock_light.set_color.side_effect = set_color
    mock_light.get_version.side_effect = get_version
    mock_light.set_power.side_effect = set_power

    return mock_light


@pytest.fixture(name="aiolifx_discovery")
def aiolifx_discovery_fixture():
    """Patch aiolifx.LifxDiscovery."""
    with patch("aiolifx.LifxDiscovery", autospec=True) as discovery:
        yield discovery


@pytest.fixture(name="ping_pong_wait", autouse=True)
def ping_pong_wait_fixture():
    """Patch ping pong sleep wait time to avoid long tests."""
    with patch("homeassistant.components.lifx.light.PING_PONG_WAIT", 0):
        yield


async def test_bulb_discovery(hass, aiolifx_discovery, aiolifx_light):
    """Test discovering a bulb."""
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()

    manager = aiolifx_discovery.call_args[0][1]
    manager.register(aiolifx_light)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state is not None
    assert state.state == STATE_OFF


async def test_service_on(hass, aiolifx_discovery, aiolifx_light):
    """Test turning a light on."""
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()

    manager = aiolifx_discovery.call_args[0][1]
    manager.register(aiolifx_light)
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state is not None
    assert state.state == STATE_OFF

    # test from off to on
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.test"}, blocking=True
    )
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state is not None
    assert state.state == STATE_ON

    # test from on to on
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.test"}, blocking=True
    )
    await hass.async_block_till_done()

    state = hass.states.get("light.test")
    assert state is not None
    assert state.state == STATE_ON
