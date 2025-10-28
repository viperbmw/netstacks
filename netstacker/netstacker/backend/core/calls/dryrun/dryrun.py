from netstacker.backend.core.utilities.rediz_meta import (
    render_netstacker_payload,
    write_mandatory_meta,
)
from netstacker.backend.core.utilities.rediz_meta import write_meta_error
from netstacker.backend.core.utilities.jinja2.j2 import render_j2template
from netstacker.backend.core.utilities.webhook.webhook import exec_webhook_func

from netstacker.backend.core.driver import driver_map


def dryrun(**kwargs):
    lib = kwargs.get("library", False)
    config = kwargs.get("config", False)
    j2conf = kwargs.get("j2config", False)
    webhook = kwargs.get("webhook", False)
    enable_mode = kwargs.get("enable_mode", False)
    result = False

    try:
        write_mandatory_meta()

        if j2conf:
            j2confargs = j2conf.get("args")
            res = render_j2template(
                j2conf["template"], template_type="config", kwargs=j2confargs
            )
            config = res["data"]["task_result"]["template_render_result"]

        result = {}

        if not driver_map.get(lib):
            raise NotImplementedError(f"unknown 'driver' {lib}")

        driver_obj = driver_map[lib](**kwargs)
        sesh = driver_obj.connect()

        if config and not enable_mode:
            result = driver_obj.dryrun(session=sesh, command=config, dry_run=True)
        if config and enable_mode:
            result = driver_obj.dryrun(
                session=sesh, command=config, dry_run=True, enable_mode=enable_mode
            )

        driver_obj.logout(sesh)

        if webhook:
            current_jobdata = render_netstacker_payload(job_result=result)
            exec_webhook_func(jobdata=current_jobdata, webhook_payload=webhook)

    except Exception as e:
        write_meta_error(e)

    return result
