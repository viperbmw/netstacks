import logging
import os
import shutil
import typing
from collections import defaultdict
from functools import wraps

from requests import get
from requests.exceptions import HTTPError

from netstacker.backend.core.confload.confload import config

log = logging.getLogger(__name__)


class FSMTemplate:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.indexfile = config.txtfsm_index_file

    def get_template(self):
        base_path = config.txtfsm_index_file.replace("index", "")
        template_filename = self.kwargs["template"]
        file_path = base_path + template_filename
        # try:
        with open(file_path) as infil:  # deliberately letting errors propagate right now
            template_text = infil.read()
        # except FileNotFoundError:
        #     log.warning(f"Tried to delete {file_path} but it wasn't there!  Cleaning index anyway")
        #
        result_data = {
            "status": "success",
            "data": {
                "task_result": {
                    "template": template_filename,
                    "template_text": template_text
                }
            }
        }
        return result_data

    def get_template_list(self):
        res = defaultdict(list)  # defaultdict doesn't require initialization

        with open(self.indexfile, "r", encoding="utf-8") as f:
            for line in f:
                if "," in line and "Template, Hostname, Platform, Command" not in line and not line.startswith('#'):
                    fields = line.split(',')
                    template_filename = fields[0]
                    command = fields[3]
                    template_obj = {"command": command, "template": template_filename}
                    driver = fields[2].replace(" ", "")
                    res[driver].append(template_obj)

        result_data = {
            "status": "success",
            "data": {
                "task_result": dict(res)  # we don't want to return a DefaultDict directly
            }
        }
        return result_data

    def fetch_template(self):
        download_filename = self.kwargs["key"].split("_")[0]

        # get template text
        template_url = f"{config.txtfsm_template_server}/static/fsms/{download_filename}.txt"
        result = get(template_url, timeout=10)
        result.raise_for_status()
        template_text = result.text
        return template_text

    def add_template(self, strict=True):
        try:
            self.kwargs["template_text"] = self.fetch_template()
        except HTTPError:
            if strict:
                raise
            self.kwargs[
                "template_text"] = "COULD NOT FETCH"  # useful for automated tests that don't actually need the results

        return self.push_template()

    def push_template(self):
        # prepare args
        command = self.kwargs["command"].replace(" ", "_")
        template_filename = f"{self.kwargs['driver']}_{command}.template"
        base_path = config.txtfsm_index_file.replace("index", "")
        template_path = base_path + template_filename

        template_text = self.kwargs["template_text"]
        with open(template_path, "w") as file:
            file.write(template_text)

        # update index
        with open(self.indexfile, "r") as infile:
            original_index_lines = infile.readlines()

        new_index_lines = self.insert_template_into_index_lines(original_index_lines, template_filename)
        tmp_index_filename = f"{config.txtfsm_index_file}.tmp"
        with open(tmp_index_filename, "w") as outfile:
            outfile.writelines(new_index_lines)

        # overwrites indexfile
        shutil.move(tmp_index_filename, config.txtfsm_index_file)
        result_data = {
            "status": "success",
            "data": {
                "task_result": f"{template_filename} added"
            }
        }
        return result_data

    def remove_template(self):
        base_path = config.txtfsm_index_file.replace("index", "")
        template_filename = self.kwargs["template"]
        file_path = base_path + template_filename
        try:
            os.remove(file_path)
        except FileNotFoundError:
            log.warning(f"Tried to delete {file_path} but it wasn't there!  Cleaning index anyway")

        # update index
        with open(self.indexfile, "r") as infile:
            original_template_lines = infile.readlines()

        new_index_lines = [line for line in original_template_lines
                           if not line.startswith(template_filename)]

        tmp_index_filename = f"{config.txtfsm_index_file}.tmp"
        with open(tmp_index_filename, "w") as outfile:
            outfile.writelines(new_index_lines)

        # overwrite indexfile
        shutil.move(tmp_index_filename, config.txtfsm_index_file)
        result_data = {
            "status": "success",
            "data": {
                "task_result": f"{self.kwargs['template']} removed"
            }
        }
        return result_data

    def insert_template_into_index_lines(self, original_template_lines: typing.List[str],
                                         template_filename: str) -> typing.List[str]:
        """insert line into template index at end of existing section for driver"""
        driver = self.kwargs["driver"]
        command = self.kwargs["command"]
        new_line = f"{template_filename}, .*, {driver}, {command}\n"
        new_index_lines = []
        count = 0
        driver_section_identified = False

        for line in original_template_lines:
            if line.startswith(driver):
                driver_section_identified = True

            if driver_section_identified and count == 0:  # first line after the last in the right driver section
                count += 1
                new_index_lines.append(new_line)
            
            new_index_lines.append(line)

        if not driver_section_identified:  # no existing section, so create a new one
            new_index_lines.append('')
            new_index_lines.append(new_line)

        # remove any duplicates
        result = list(dict.fromkeys(new_index_lines))
        return result


def return_errors(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            result_data = f(*args, **kwargs)
        except Exception as e:
            result_data = {
                "status": "error",
                "data": {"error": str(e)}
            }
        return result_data

    return wrapper


@return_errors
def listtemplates():
    t = FSMTemplate()
    res = t.get_template_list()
    return res


@return_errors
def gettemplate(**kwargs):
    t = FSMTemplate(**kwargs)
    res = t.get_template()
    return res


@return_errors
def addtemplate(**kwargs):
    t = FSMTemplate(**kwargs)
    res = t.add_template()
    return res


@return_errors
def pushtemplate(**kwargs):
    t = FSMTemplate(**kwargs)
    res = t.push_template()
    return res


@return_errors
def removetemplate(**kwargs):
    t = FSMTemplate(**kwargs)
    res = t.remove_template()
    return res
