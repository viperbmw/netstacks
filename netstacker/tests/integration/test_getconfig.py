import random

import pytest

from .helper import NetstackerTestHelper

helper = NetstackerTestHelper()
r = "cornicorneo" + str(random.randint(1, 101))

pytestmark = pytest.mark.fulllab


@pytest.mark.getconfig
def test_getconfig_prepare_environment():
    pl = {
        "library": "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
        },
        "config": ["hostname " + r],
    }
    res = helper.post_and_check("/setconfig", pl)
    matchstr = r + "#"
    assert matchstr in str(res)




@pytest.mark.getconfig
@pytest.mark.cisgoalternate
def test_getconfig_netmiko_post_check():
    pl = {
        "library":
        "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
            "timeout": 5,
        },
        "command":
        "show run | i hostname",
        "queue_strategy":
        "pinned",
        "post_checks": [{
            "match_type": "include",
            "get_config_args": {
                "command": "show run | i hostname"
            },
            "match_str": ["hostname " + r],
        }],
    }
    res = helper.post_and_check_errors("/getconfig", pl)
    assert len(res) == 0








@pytest.mark.getconfig
@pytest.mark.cisgoalternate
def test_getconfig_netmiko():
    pl = {
        "library": "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
        },
        "command": "show run | i hostname",
    }
    res = helper.post_and_check("/getconfig", pl)
    matchstr = "hostname " + r
    assert matchstr in str(res)


@pytest.mark.getconfig
@pytest.mark.cisgoalternate
def test_getconfig_netmiko_with_textfsm():
    pl = {
        "library": "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
        },
        "command": "show ip int brief",
        "args": {
            "use_textfsm": True
        },
    }
    res = helper.post_and_check("/getconfig", pl)
    assert res["show ip int brief"][0]["status"] == "up"


@pytest.mark.getconfig
@pytest.mark.cisgoalternate
def test_getconfig_netmiko_multiple():
    pl = {
        "library": "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
        },
        "command": ["show run | i hostname", "show ip int brief"],
    }
    res = helper.post_and_check("/getconfig", pl)
    assert len(res["show ip int brief"]) > 1
    assert len(res["show run | i hostname"]) >= 1




