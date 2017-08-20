"""Test MySensors base component."""
from unittest.mock import MagicMock, call, patch

import pytest
import voluptuous as vol

from homeassistant.components import mysensors as mysensors_comp
from homeassistant.setup import async_setup_component

from .common import DEVICE

from tests.common import mock_coro_func

WIN_CONFIG = {
    "mysensors": {
        "gateways": [{"device": "COM4"}],
        "version": "2.0",
        "persistence": False,
    }
}


@pytest.fixture(name="mock_win")
def win_fixture():
    """Mock a windows environment."""
    with patch(
        "homeassistant.components.mysensors.gateway.sys.platform", return_value="win32"
    ):
        yield


async def test_no_mqtt_config(hass, mock_mysensors):
    """Test setup of mysensors with mqtt device but without mqtt config."""
    config = {
        "mysensors": {
            "gateways": [{"device": "mqtt"}],
            "version": "2.0",
            "persistence": False,
        }
    }

    with patch(
        "homeassistant.components.mysensors.gateway.async_setup_component",
        side_effect=mock_coro_func(),
    ) as mock_stp_comp:
        mock_stp_comp.return_value = False
        res = await async_setup_component(hass, "mysensors", config)
    assert not res


async def test_bad_device(hass, mock_mysensors):
    """Test setup of mysensors with bad device referens."""
    config = {
        "mysensors": {
            "gateways": [{"device": ""}],
            "version": "2.0",
            "persistence": False,
        }
    }

    with patch(
        "homeassistant.components.mysensors.gateway.cv.isdevice",
        side_effect=vol.Invalid("Bad device"),
    ):
        with patch("socket.getaddrinfo", side_effect=OSError("Not a socket address")):
            res = await async_setup_component(hass, "mysensors", config)
    assert not res


@pytest.mark.parametrize("config", [WIN_CONFIG])
async def test_win_device(hass, mock_win, config, gateway):
    """Test setup of mysensors with windows serial device."""
    assert gateway.device == "COM4"
    assert not gateway.sensors


async def test_bad_win_device(hass, mock_mysensors):
    """Test setup of mysensors with bad windows serial device."""
    config = {
        "mysensors": {
            "gateways": [{"device": "bad"}],
            "version": "2.0",
            "persistence": False,
        }
    }

    with patch(
        "homeassistant.components.mysensors.gateway.sys.platform", return_value="win32"
    ):
        with patch("socket.getaddrinfo", side_effect=OSError("Not a socket address")):
            res = await async_setup_component(hass, "mysensors", config)
    assert not res


async def test_persistence_file_not_all(hass, mock_mysensors):
    """Test persistence file not set for all gateways."""
    config = {
        "mysensors": {
            "gateways": [
                {"device": "/dev/ttyACM0", "persistence_file": "test0.json"},
                {"device": "/dev/ttyACM1"},
            ],
            "version": "2.0",
            "persistence": True,
        }
    }
    assert not await async_setup_component(hass, "mysensors", config)


async def test_persistence_file_unique(hass, mock_mysensors):
    """Test persistence file not unique for each gateway."""
    config = {
        "mysensors": {
            "gateways": [
                {"device": "/dev/ttyACM0", "persistence_file": "test0.json"},
                {"device": "/dev/ttyACM1", "persistence_file": "test0.json"},
            ],
            "version": "2.0",
            "persistence": True,
        }
    }
    assert not await async_setup_component(hass, "mysensors", config)


async def test_bad_persistence_file(hass, mock_mysensors):
    """Test persistence bad file."""
    config = {
        "mysensors": {
            "gateways": [{"device": "/dev/ttyACM0", "persistence_file": "test.bad"}],
            "version": "2.0",
            "persistence": True,
        }
    }
    assert not await async_setup_component(hass, "mysensors", config)


async def test_old_debug_option(
    hass, caplog, mock_isdevice, mock_mysensors, mock_gw_ready
):
    """Test persistence bad file."""
    config = {
        "mysensors": {
            "gateways": [{"device": DEVICE}],
            "version": "2.0",
            "persistence": False,
            "debug": True,
        }
    }
    assert await async_setup_component(hass, "mysensors", config)
    await hass.async_block_till_done()
    assert (
        "debug option for mysensors is deprecated. "
        "Please remove debug from your configuration file" in caplog.text
    )


async def test_setup_platform(hass, gateway, node):
    """Test setup_mysensors_platform."""
    device_instance = MagicMock()
    mock_device_class = MagicMock(return_value=device_instance)
    child_id = 1
    value_type = 0
    new_dev_ids = [(id(gateway), node.sensor_id, child_id, value_type)]
    discovery_info = {"devices": new_dev_ids, "name": mysensors_comp.DOMAIN}
    new_devices = mysensors_comp.setup_mysensors_platform(
        hass, "sensor", discovery_info, mock_device_class
    )
    assert mock_device_class.call_count == 1
    assert mock_device_class.call_args == call(
        gateway, node.sensor_id, child_id, "mock sketch 1 1", value_type
    )
    assert new_devices == [device_instance]


async def test_setup_platform_device_map(hass, gateway, node, child):
    """Test setup_mysensors_platform with device class map."""
    device_instance = MagicMock()
    mock_device_class = MagicMock(return_value=device_instance)
    device_class_dict = {"S_TEMP": mock_device_class}
    value_type = list(child.values)[0]
    new_dev_ids = [(id(gateway), node.sensor_id, child.id, value_type)]
    discovery_info = {"devices": new_dev_ids, "name": mysensors_comp.DOMAIN}
    new_devices = mysensors_comp.setup_mysensors_platform(
        hass, "sensor", discovery_info, device_class_dict
    )
    assert mock_device_class.call_count == 1
    assert mock_device_class.call_args == call(
        gateway, node.sensor_id, child.id, "mock sketch 1 1", value_type
    )
    assert new_devices == [device_instance]


async def test_setup_platform_no_info(hass):
    """Test setup_mysensors_platform with no discovery_info."""
    device_instance = MagicMock()
    mock_device_class = MagicMock(return_value=device_instance)
    new_devices = mysensors_comp.setup_mysensors_platform(
        hass, "sensor", None, mock_device_class
    )
    assert mock_device_class.call_count == 0
    assert not new_devices


async def test_setup_platform_old(hass, gateway, node):
    """Test setup_mysensors_platform with only old devices."""
    device_instance = MagicMock()
    mock_device_class = MagicMock(return_value=device_instance)
    child_id = 1
    value_type = 0
    new_dev_ids = [(id(gateway), node.sensor_id, child_id, value_type)]
    discovery_info = {"devices": new_dev_ids, "name": mysensors_comp.DOMAIN}
    new_devices = mysensors_comp.setup_mysensors_platform(
        hass, "sensor", discovery_info, mock_device_class
    )
    assert mock_device_class.call_count == 1
    assert mock_device_class.call_args == call(
        gateway, node.sensor_id, child_id, "mock sketch 1 1", value_type
    )
    assert new_devices == [device_instance]

    new_devices = mysensors_comp.setup_mysensors_platform(
        hass, "sensor", discovery_info, mock_device_class
    )
    assert mock_device_class.call_count == 1
    assert not new_devices


async def test_setup_platform_bad_gateway(hass, mock_isdevice):
    """Test setup_mysensors_platform with bad gateway."""
    device_instance = MagicMock()
    mock_device_class = MagicMock(return_value=device_instance)
    node_id = 1
    child_id = 1
    value_type = 0
    new_dev_ids = [(id(object()), node_id, child_id, value_type)]
    discovery_info = {"devices": new_dev_ids, "name": mysensors_comp.DOMAIN}
    new_devices = mysensors_comp.setup_mysensors_platform(
        hass, "sensor", discovery_info, mock_device_class
    )
    assert mock_device_class.call_count == 0
    assert not new_devices
