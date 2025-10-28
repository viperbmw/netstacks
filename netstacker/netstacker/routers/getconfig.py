import logging

from fastapi import APIRouter

# load models
from netstacker.backend.core.models.models import GetConfig
from netstacker.backend.core.models.netmiko import NetmikoGetConfig
from netstacker.backend.core.models.puresnmp import PureSNMPGetConfig
from netstacker.backend.core.models.task import Response

from netstacker.backend.core.manager import ntplm

from netstacker.routers.route_utils import error_handle_w_cache, whitelist

log = logging.getLogger(__name__)
router = APIRouter()


# read config
@router.post("/getconfig", response_model=Response, status_code=201)
@router.post("/get", response_model=Response, status_code=201)
@error_handle_w_cache
@whitelist
def get_config(getcfg: GetConfig):
    return ntplm._get_config(getcfg)


# read config
@router.post("/getconfig/netmiko", response_model=Response, status_code=201)
@router.post("/get/netmiko", response_model=Response, status_code=201)
@error_handle_w_cache
@whitelist
def get_config_netmiko(getcfg: NetmikoGetConfig):
    return ntplm.get_config_netmiko(getcfg)




# read config
@router.post("/getconfig/puresnmp", response_model=Response, status_code=201)
@router.post("/get/puresnmp", response_model=Response, status_code=201)
@error_handle_w_cache
@whitelist
def get_config_puresnmp(getcfg: PureSNMPGetConfig):
    return ntplm.get_config_puresnmp(getcfg)




