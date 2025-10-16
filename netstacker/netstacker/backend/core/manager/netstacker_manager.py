import time

import logging

from typing import Any

from netstacker.backend.core.redis.rediz import Rediz
from fastapi.encoders import jsonable_encoder

from netstacker.backend.core.models.models import GetConfig
from netstacker.backend.core.models.netmiko import NetmikoGetConfig
from netstacker.backend.core.models.puresnmp import PureSNMPGetConfig

from netstacker.backend.core.models.models import SetConfig
from netstacker.backend.core.models.netmiko import NetmikoSetConfig
from netstacker.backend.core.models.task import Response

from netstacker.backend.core.models.models import Script

from netstacker.backend.core.utilities.webhook.webhook import exec_webhook_func
from netstacker.backend.core.calls.scriptrunner.script import script_model_finder

log = logging.getLogger(__name__)


class NetpalmManager(Rediz):
    def _get_config(self, getcfg: GetConfig, library: str = None) -> Response:
        """ executes the base netpalm getconfig method async and returns the task id response obj """
        if isinstance(getcfg, dict):
            req_data = getcfg
        else:
            req_data = getcfg.dict(exclude_none=True)
        if library is not None:
            req_data["library"] = library
        r = self.execute_task(method="getconfig", kwargs=req_data)
        resp = jsonable_encoder(r)
        return resp

    def get_config_netmiko(self, getcfg: NetmikoGetConfig):
        """ executes the netpalm netmiko getconfig method async and returns the response obj """
        return self._get_config(getcfg, library="netmiko")

    def get_config_puresnmp(self, getcfg: PureSNMPGetConfig):
        """ executes the netpalm puresnmp getconfig method async and returns the response obj """
        return self._get_config(getcfg, library="puresnmp")

    def _set_config(self, setcfg: SetConfig, library: str = None) -> Response:
        """ executes the base netpalm setconfig method async and returns the task id response obj """
        if isinstance(setcfg, dict):
            req_data = setcfg
        else:
            req_data = setcfg.dict(exclude_none=True)
        if library is not None:
            req_data["library"] = library
        r = self.execute_task(method="setconfig", kwargs=req_data)
        resp = jsonable_encoder(r)
        return resp

    def set_config_dry_run(self, setcfg: SetConfig):
        """ executes the netpalm setconfig dry run method async and returns the response obj """
        if isinstance(setcfg, dict):
            req_data = setcfg
        else:
            req_data = setcfg.dict(exclude_none=True)
        r = self.execute_task(method="dryrun", kwargs=req_data)
        resp = jsonable_encoder(r)
        return resp

    def set_config_netmiko(self, setcfg: NetmikoSetConfig):
        """ executes the netmiko setconfig method async and returns the response obj """
        return self._set_config(setcfg, library="netmiko")

    def execute_script(self, **kwargs):
        """ executes the netpalm script method async and returns the response obj """
        log.debug(f"execute_script: called with {kwargs}")
        req_data = kwargs
        # check if pinned required
        if req_data.get("queue_strategy") == "pinned":
            if isinstance(req_data.get("connection_args"), dict):
                req_data["connection_args"]["host"] = req_data["script"]
            else:
                req_data["connection_args"] = {}
                req_data["connection_args"]["host"] = req_data["script"]

        r = self.execute_task(method="script", kwargs=req_data)
        resp = jsonable_encoder(r)
        return resp

    def retrieve_task_result(self, netpalm_response: Response):
        """ waits for the task to complete the returns the result """
        if isinstance(netpalm_response, dict):
            req_data = netpalm_response
        else:
            req_data = netpalm_response.dict(exclude_none=True)

        if req_data["status"] == "success":
            task_id = req_data["data"]["task_id"]

            while True:
                r = self.fetchtask(task_id=task_id)
                if (r["data"]["task_status"] == "finished") or (
                    r["data"]["task_status"] == "failed"
                ):
                    return r
                time.sleep(0.3)
        else:
            return req_data

    def retrieve_task_result_multiple(self, netpalm_response_list: list):
        """
        retrieves multiple task results in a sync fashion

        Args:
            netpalm_response_list: list of netpalm response objects


        Returns:
            list of netpalm responses objects with result
        """

        result = []
        for netpalm_response in netpalm_response_list:
            one_result = self.retrieve_task_result(netpalm_response)
            result.append(one_result)

        return result

    def trigger_webhook(self, webhook_payload: dict, webhook_meta_data: dict):
        """
        executes a webhook call

        can also run the job_data through a j2 template if the j2template name is specificed in the

        Args:
            webhook_payload: dictionary containing the result of the job to be passed into the webhook e.g a netpalm Response dict
            webhook_meta_data: This is a dictionary describing the metadata of webhook itself e.g webhook name, user specified args to pass into the webhook itself
                    {
                        "name": "default_webhook", # webhook name
                        "args": {
                            "insert": "something useful" # args to pass into webhook
                        },
                        "j2template": "myj2template" # add this key if you want to run the job data through a j2template before passing it into the webhook
                    }

        Returns:
            the result of executing the webhook
        """
        res = exec_webhook_func(
            jobdata=webhook_payload, webhook_payload=webhook_meta_data
        )
        return res
