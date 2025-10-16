import random

import pytest

from tests.integration.helper import NetstackerTestHelper

helper = NetstackerTestHelper()
r = "cornicorneo" + str(random.randint(1, 101))

pytestmark = pytest.mark.fulllab




@pytest.mark.setconfig
def test_setconfig_netmiko_pre_post_check():
    pl = {
        "library": "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
        },
        "config": ["hostname herpa_derpa"],
        "queue_strategy": "pinned",
        "pre_checks": [
            {
                "match_type": "include",
                "get_config_args": {"command": "show run | i hostname"},
                "match_str": ["hostname " + str(r)],
            }
        ],
        "post_checks": [
            {
                "match_type": "include",
                "get_config_args": {"command": "show run | i hostname"},
                "match_str": ["hostname herpa_derpa"],
            }
        ],
    }
    res = helper.post_and_check_errors("/setconfig", pl)
    assert len(res) == 0


@pytest.mark.setconfig
def test_setconfig_netmiko_pre_check_fail():
    pl = {
        "library": "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
        },
        "config": ["hostname herpa_derpa"],
        "queue_strategy": "pinned",
        "pre_checks": [
            {
                "match_type": "include",
                "get_config_args": {"command": "show run | i hostname"},
                "match_str": ["hostname " + str(r)],
            }
        ],
        "post_checks": [
            {
                "match_type": "include",
                "get_config_args": {"command": "show run | i hostname"},
                "match_str": ["hostname herpa_derpa"],
            }
        ],
    }
    res = helper.post_and_check_errors("/setconfig", pl)
    assert len(res) > 0


@pytest.mark.setconfig
def test_setconfig_netmiko_post_check_fail():
    pl = {
        "library": "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
        },
        "config": ["hostname herpa_derpa"],
        "queue_strategy": "pinned",
        "pre_checks": [
            {
                "match_type": "include",
                "get_config_args": {"command": "show run | i hostname"},
                "match_str": ["hostname herpa_derpa"],
            }
        ],
        "post_checks": [
            {
                "match_type": "include",
                "get_config_args": {"command": "show run | i hostname"},
                "match_str": ["hostname f"],
            }
        ],
    }
    res = helper.post_and_check_errors("/setconfig", pl)
    assert len(res) > 0














@pytest.mark.setconfig
@pytest.mark.cisgoalternate
def test_setconfig_netmiko():
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
    assert  matchstr in res["changes"]


@pytest.mark.setconfig
@pytest.mark.cisgoalternate
def test_setconfig_netmiko_multiple():
    pl = {
        "library": "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
        },
        "config": ["hostname yeti", "hostname bufoon"],
    }
    res = helper.post_and_check("/setconfig", pl)
    matchstr = r + "#"
    assert len(res["changes"]) > 4


@pytest.mark.setconfig
@pytest.mark.cisgoalternate
def test_setconfig_netmiko_j2():
    pl = {
        "library": "netmiko",
        "connection_args": {
            "device_type": "cisco_ios",
            "host": helper.test_device_ios_cli,
            "username": "admin",
            "password": "admin",
        },
        "j2config": {"template": "test", "args": {"vlans": ["1", "2", "3"]}},
    }
    res = helper.post_and_check("/setconfig", pl)
    assert len(res["changes"]) > 6



