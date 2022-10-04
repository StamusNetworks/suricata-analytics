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
import urllib.parse

import networkx as nx
import pandas as pd

from datetime import datetime, timedelta

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
        self.endpoint = "127.0.0.1"
        self.token = None
        self.tls = True
        self.tls_verify = True

        if KEY_ENDPOINT in kwargs:
            self.endpoint = kwargs[KEY_ENDPOINT]
        elif KEY_ENDPOINT in os.environ:
            self.endpoint = os.environ[KEY_ENDPOINT]
        elif os.path.exists(env_file()):
            self.endpoint = load_param_from_env_file(KEY_ENDPOINT)

        if KEY_TOKEN in kwargs and KEY_TOKEN is not None:
            self.token = kwargs[KEY_TOKEN]
        elif KEY_TOKEN in os.environ:
            # This is a conveniece feature for testing and lab setups, use mapped env file instead
            self.token = os.environ[KEY_TOKEN]
        elif os.path.exists(env_file()):
            self.token = load_param_from_env_file(KEY_TOKEN)
        else:
            raise ValueError("{} not configured".format(KEY_TOKEN))

        if KEY_TLS_VERIFY in kwargs:
            self.tls_verify = check_str_bool(kwargs[KEY_TLS_VERIFY])
        elif KEY_TLS_VERIFY in os.environ:
            self.tls_verify = check_str_bool(os.environ[KEY_TLS_VERIFY])
        elif os.path.exists(env_file()):
            self.tls_verify = load_param_from_env_file(KEY_TLS_VERIFY)
            if self.tls_verify is not None:
                self.tls_verify = check_str_bool(self.tls_verify)
            else:
                self.tls_verify = True

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
        } if event_type not in (None, "all") else None, ignore_time=True)
        return data.get("fields", [])

    def get_data(self, api: str, qParams=None, ignore_time=False):
        resp = self.__get(api, qParams, ignore_time)
        if resp.status_code not in (200, 302):
            raise requests.RequestException(resp)
        return json.loads(resp.text)

    def set_query_timeframe(self, from_date: str, to_date: str) -> object:
        self.from_date = int(datetime.fromisoformat(from_date).strftime('%s')) * 1000
        self.to_date = int(datetime.fromisoformat(to_date).strftime('%s')) * 1000
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


def load_param_from_env_file(key: str):
    """
    .env file should have bash style variable declarations KEY=VALUE
    """
    with open(env_file(), "r") as handle:
        for line in handle:
            bits = line.split("=", 1)
            if len(bits) != 2:
                raise ValueError("invalid line in env file: {}".format(line))
            if bits[0] == key:
                return bits[1].rstrip()


def env_file() -> str:
    return os.path.join(os.path.expanduser("~"), ".env")
