# Copyright © 2022 Stamus Networks oss@stamus-networks.com

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Connectors for easily ingesting data from remote sources. Ideally, the user should be able to
simply create a new instace that would pull all needed params from .env file in user home dir,
os environment, or be provided as argument. This order should also work as override sequence,
whereby OS env overrides local file, and API arguments override both.
"""

import json
import os
import requests
import shutil
import urllib.parse

import networkx as nx
import pandas as pd
import subprocess

from dotenv import dotenv_values
from datetime import datetime, timedelta

# Search for scirius env file in user home rather than local folder
KEY_ENV_IN_HOME = "SCIRIUS_ENVFILE_IN_HOME"

KEY_ENDPOINT = "SCIRIUS_HOST"
KEY_TOKEN = "SCIRIUS_TOKEN"
KEY_TLS_VERIFY = "SCIRIUS_TLS_VERIFY"


class RESTSciriusConnector():

    """
    APIConnector is for ingesting data from Scirius REST API
    """
    last_request = None

    from_date = None
    to_date = None

    page_size = 1000

    def __init__(self, **kwargs) -> None:
        env_in_home = os.environ.get(KEY_ENV_IN_HOME, "no")
        self.__env_file = ".env"
        if check_str_bool(env_in_home):
            self.__env_file = os.path.join(os.path.expanduser("~"),
                                           self.__env_file)
        elif shutil.which("git") is not None:
            self.__env_file = os.path.join(getGitRoot(),
                                           self.__env_file)

        if not os.path.exists(self.__env_file):
            raise LookupError("unable to find env config in {}".format(self.__env_file))

        config = {
            **os.environ,
            **dotenv_values(self.__env_file),
        }

        self.endpoint = kwargs.get(KEY_ENDPOINT.lower(),
                                   config.get(KEY_ENDPOINT,
                                              "127.0.0.1"))
        self.token = kwargs.get(KEY_TOKEN.lower(),
                                config.get(KEY_TOKEN,
                                           None))
        self.tls_verify = kwargs.get(KEY_TLS_VERIFY.lower(),
                                     config.get(KEY_TLS_VERIFY,
                                                "yes"))
        self.tls_verify = check_str_bool(self.tls_verify)
        self.tls_verify = "/etc/ssl/certs/ca-certificates.crt" if self.tls_verify else False

        if self.token is None:
            raise ValueError("{} not configured".format(KEY_TOKEN))

    def get_event_types(self) -> list:
        """
        Out: list of event types from Scirius REST API
        """
        return list(self.get_eve_unique_values(counts="no", field="event_type"))

    def get_eve_fields_graph_nx(self, **kwargs) -> nx.Graph:
        data = self.get_eve_fields_graph(**kwargs)
        data = data["graph"]
        graph = nx.Graph()
        for node in data["nodes"]:
            graph.add_node(node["index"], field=node["field"], kind=node["kind"])
        for edge in data["edges"]:
            graph.add_edge(edge["edge"][0], edge["edge"][1], doc_count=edge["doc_count"])
        return graph

    def get_eve_unique_values(self, **kwargs) -> dict:
        return self.get_data(api="rest/rules/es/unique_values/", qParams=kwargs)

    def get_events_tail(self, **kwargs) -> list:
        return [d for d in
                self.get_data(api="rest/rules/es/events_tail/",
                              qParams=kwargs).get("results", [])]

    def get_events_df(self, **kwargs) -> pd.DataFrame:
        return pd.json_normalize(self.get_events_tail(**kwargs))

    def get_alerts_tail(self, **kwargs) -> list:
        return [d.get("_source", {}) for d in
                self.get_data(api="rest/rules/es/alerts_tail/",
                              qParams=kwargs).get("results", [])]

    def get_alerts_df(self, **kwargs) -> pd.DataFrame:
        return pd.json_normalize(self.get_alerts_tail(**kwargs))

    def get_eve_fields_graph(self, **kwargs) -> dict:
        """
        Out: dict of graph data that wraps around nested elastic terms aggregation

        Kwargs dict is passed directly to GET handler and treated as query params.
        """
        return self.get_data(api="rest/rules/es/graph_agg/", qParams=kwargs)

    def get_unique_fields(self, event_type=None) -> list:
        """
        Out: list of unique fields for index pattern

        event_type should match one of the event types indexed in elastic
        event_type "any" is treated as None and will collect fields over all index patterns
        """
        data = self.get_data(api="rest/rules/es/unique_fields/", qParams={
            "event_type": event_type
        } if event_type not in (None, "all") else None, ignore_time=False)
        return data.get("fields", [])

    def get_data(self, api: str, qParams=None, ignore_time=False):
        resp = self.__get(api, qParams, ignore_time)
        if resp.status_code not in (200, 302):
            raise requests.RequestException(resp)
        return json.loads(resp.text)

    def set_query_timeframe(self, from_date, to_date) -> object:
        if isinstance(from_date, str):
            from_date = datetime.fromisoformat(from_date)
        elif from_date is None:
            from_date = datetime.utcnow() - timedelta(days=30)

        if isinstance(to_date, str):
            to_date = datetime.fromisoformat(to_date)
        elif to_date is None:
            to_date = datetime.utcnow()

        if from_date.date() > to_date.date():
            raise ValueError("Timespan beginning must be before the end")

        self.from_date = int(from_date.strftime('%s')) * 1000
        self.to_date = int(to_date.strftime('%s')) * 1000

        return self

    def set_query_delta(self, hours=0, minutes=0) -> object:
        if hours == 0 and minutes == 0:
            hours = 1
        time_to = datetime.utcnow()
        time_from = time_to - timedelta(hours=hours, minutes=minutes)
        self.to_date = int(time_to.strftime('%s')) * 1000
        self.from_date = int(time_from.strftime('%s')) * 1000
        return self

    def set_page_size(self, size: int) -> object:
        if not isinstance(size, int) or size < 1:
            raise ValueError("page size must be positive integer")
        self.page_size = size
        return self

    def __get(self, api: str, qParams=None, ignore_time=False) -> requests.Response:
        url = urllib.parse.urljoin(self.__host(), api)
        if qParams is None:
            qParams = {}

        if not ignore_time and self.to_date is not None and self.to_date is not None:
            time_params = {"from_date": self.from_date, "to_date": self.to_date}
            qParams = {**time_params, **qParams}

        if self.page_size > 0:
            qParams["page_size"] = self.page_size

        if "qfilter" in qParams and qParams["qfilter"] == "":
            qParams["qfilter"] = "*"
        url += "?{}".format(urllib.parse.urlencode(qParams))

        self.last_request = url
        return requests.get(url,
                            headers={
                                "Authorization": "Token {}".format(self.token)
                            },
                            verify=self.tls_verify)

    def __host(self) -> str:
        return "https://{}".format(self.endpoint)


def check_str_bool(val: str) -> bool:
    if val in ("y", "yes", "t", "true", "on", "1", "enabled", "enable"):
        return True
    elif val in ("n", "no", "f", "false", "off", "0", "disabled", "disable"):
        return False
    else:
        raise ValueError("invalid truth value {}".format(val))


def getGitRoot():
    return subprocess.Popen(['git', 'rev-parse', '--show-toplevel'],
                            stdout=subprocess.PIPE).communicate()[0].rstrip().decode('utf-8')
