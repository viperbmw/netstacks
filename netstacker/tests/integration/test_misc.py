import pytest
import requests
import json
from tests.integration.helper import NetstackerTestHelper

helper = NetstackerTestHelper()

@pytest.mark.misc_worker_router
def test_worker_route():
    url = f"{helper.base_url}/workers/"
    r = requests.get(url, json={}, headers=helper.headers, timeout=helper.http_timeout)
    res = r.json()
    assert len(res) >= 2 

