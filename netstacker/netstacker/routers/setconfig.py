import logging

from fastapi import APIRouter

# load models
from netstacker.backend.core.models.models import SetConfig
from netstacker.backend.core.models.netmiko import NetmikoSetConfig
from netstacker.backend.core.models.task import Response

from netstacker.backend.core.manager import ntplm

from netstacker.routers.route_utils import HttpErrorHandler, poison_host_cache, whitelist

log = logging.getLogger(__name__)
router = APIRouter()


# deploy a configuration
@router.post("/setconfig", response_model=Response, status_code=201)
@HttpErrorHandler()
@poison_host_cache
@whitelist
def set_config(setcfg: SetConfig):
    return ntplm._set_config(setcfg)


# dry run a configuration
@router.post("/setconfig/dry-run", response_model=Response, status_code=201)
@HttpErrorHandler()
@whitelist
def set_config_dry_run(setcfg: SetConfig):
    return ntplm.set_config_dry_run(setcfg)


# deploy a configuration
@router.post("/setconfig/netmiko", response_model=Response, status_code=201)
@HttpErrorHandler()
@poison_host_cache
@whitelist
def set_config_netmiko(setcfg: NetmikoSetConfig):
    return ntplm.set_config_netmiko(setcfg)






