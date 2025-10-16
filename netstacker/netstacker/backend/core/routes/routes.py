# load plugins
from netstacker.backend.core.calls.dryrun.dryrun import dryrun
from netstacker.backend.core.calls.getconfig.exec_command import exec_command
from netstacker.backend.core.calls.scriptrunner.script import script_kiddy
from netstacker.backend.core.calls.setconfig.exec_config import exec_config
from netstacker.backend.core.utilities.jinja2.j2 import j2gettemplate
from netstacker.backend.core.utilities.jinja2.j2 import render_j2template
from netstacker.backend.core.utilities.ls.ls import list_files
from netstacker.backend.core.utilities.textfsm.template import (
    listtemplates,
    pushtemplate,
    addtemplate,
    removetemplate,
    gettemplate,
)

routes = {
    "getconfig": exec_command,
    "setconfig": exec_config,
    "listtemplates": listtemplates,
    "gettemplate": gettemplate,  # replace with universal template mgr get_template in future
    "addtemplate": addtemplate,
    "pushtemplate": pushtemplate,
    "removetemplate": removetemplate,
    "ls": list_files,
    "script": script_kiddy,
    "j2gettemplate": j2gettemplate,
    "render_j2template": render_j2template,
    "dryrun": dryrun,
}
