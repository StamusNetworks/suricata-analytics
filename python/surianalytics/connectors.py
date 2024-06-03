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
from copy import deepcopy

import networkx as nx
import pandas as pd
import subprocess
from IPython.display import display, Markdown

from dotenv import dotenv_values
from datetime import datetime, timedelta, timezone
from dateutil import parser

# Search for scirius env file in user home rather than local folder
KEY_ENV_IN_HOME = "SCIRIUS_ENVFILE_IN_HOME"

KEY_ENDPOINT = "SCIRIUS_HOST"
KEY_TOKEN = "SCIRIUS_TOKEN"
KEY_TLS_VERIFY = "SCIRIUS_TLS_VERIFY"

LOCAL_TZ = datetime.now(timezone(timedelta(0))).astimezone().tzinfo

QUERY_RETROSEARCH_SNI = "event_type: tls AND tls.sni.keyword: ({domains})"
QUERY_RETROSEARCH_HTTP_HOST = "event_type: http AND http.hostname.keyword: ({domains})"


class RESTSciriusConnector():

    """
    APIConnector is for ingesting data from Scirius REST API
    """
    last_request = None
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

        self.set_query_timeframe(None, None)

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

    def retrosearch(self, domains: list[str], batchsize: int = 50) -> pd.DataFrame:
        """
        This method does retroactive search for IoC values listed in arguments. It batches up values and does multiple queries
        in order to not overload elastic. It then builds pandas dataframe of EVE events that match the retroscan.

        In: list of domain IoC values
        Out: pandas dataframe with IoC sightings
        """
        if batchsize > 100:
            raise ValueError("batch size is too high, more than 100 values is likely to cause failed elastic query")
        df = pd.DataFrame()
        batches = int(len(domains) / batchsize) + 1
        for i in range(batches):
            if len(domains) > batchsize:
                batch = domains[:batchsize]
                domains = domains[batchsize:]
            else:
                batch = domains

            for q in ((QUERY_RETROSEARCH_SNI.format(domains=" OR ".join(batch)), "exact", "tls.sni"),
                      (QUERY_RETROSEARCH_SNI.format(domains=" OR ".join(["*.{d}".format(d=d) for d in batch])), "sub", "tls.sni"),
                      (QUERY_RETROSEARCH_HTTP_HOST.format(domains=" OR ".join(batch)), "exact", "http.hostname"),
                      (QUERY_RETROSEARCH_HTTP_HOST.format(domains=" OR ".join(["*.{d}".format(d=d) for d in batch])), "sub", "http.hostname")):
                result = self.get_events_df(qfilter=q[0])
                if len(result) > 0:
                    result["ioc.type"] = "domain"
                    result["ioc.match"] = q[1]
                    result["ioc.source"] = q[2]
                    result["ioc.value.match"] = result[q[2]]

                    result["ioc.batch.count"] = i
                    if len(result) == self.page_size:
                        result["ioc.batch.partial"] = True
                    else:
                        result["ioc.batch.partial"] = False
                    df = pd.concat([df, result], axis=0)

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def get_data(self, api: str, qParams=None, ignore_time=False):
        resp = self.__get(api, qParams, ignore_time)
        if resp.status_code not in (200, 302):
            raise requests.RequestException(resp)
        return json.loads(resp.text)

    def set_from_date(self, from_date):
        if isinstance(from_date, str):
            from_date = parser.parse(from_date)
        elif isinstance(from_date, int):
            from_date = datetime.fromtimestamp(from_date / 1000, tz=timezone.utc)
        elif from_date is None:
            from_date = datetime.now(LOCAL_TZ) - timedelta(days=30)
        elif isinstance(from_date, datetime):
            from_date = from_date
        else:
            raise TypeError("from_date invalid type")

        self.from_date = from_date

    def set_to_date(self, to_date):
        if isinstance(to_date, str):
            to_date = parser.parse(to_date)
        elif isinstance(to_date, int):
            to_date = datetime.fromtimestamp(to_date / 1000, tz=timezone.utc)
        elif to_date is None:
            to_date = datetime.now(LOCAL_TZ)
        elif isinstance(to_date, datetime):
            to_date = to_date
        else:
            raise TypeError("to_date invalid type")

        self.to_date = to_date

    def set_query_timeframe(self, from_date, to_date) -> object:
        self.set_from_date(from_date)
        self.set_to_date(to_date)

        if self.from_date.date() > self.to_date.date():
            raise ValueError("Timespan beginning must be before the end")

        return self

    def set_query_delta(self, days=0, hours=0, minutes=0) -> object:
        if hours == 0 and minutes == 0 and days == 0:
            hours = 1
        self.to_date = datetime.now(LOCAL_TZ)
        self.from_date = self.to_date - timedelta(days=days, hours=hours, minutes=minutes)
        return self

    def set_page_size(self, size: int) -> object:
        if not isinstance(size, int) or size < 0:
            raise ValueError("page size must be 0 or positive integer")
        self.page_size = size
        return self

    def _from_date_param(self) -> int:
        return int(self.from_date.strftime('%s')) * 1000

    def _to_date_param(self) -> int:
        return int(self.to_date.strftime('%s')) * 1000

    def _time_params(self) -> dict:
        return {
            "from_date": self._from_date_param(),
            "to_date": self._to_date_param(),
        }

    def _post(self, api, index, qFilters=None, aggs=None, qParams=None, time_filter='@timestamp') -> requests.Response:
        url = urllib.parse.urljoin(self._host(), api)
        if qParams is not None:
            url = f'{url}?{urllib.parse.urlencode(qParams)}'

        if qFilters is None:
            qFilters = '*'

        resp = requests.post(
            url,
            json={
                'index': index,
                'qfilter': qFilters,
                'aggs': aggs,
                'size': self.page_size,
                'time_filter': time_filter
            },
            verify=self.tls_verify,
            headers={"Authorization": "Token {}".format(self.token)}
        )
        return resp

    def __get(self, api: str, qParams=None, ignore_time=False) -> requests.Response:
        url = urllib.parse.urljoin(self._host(), api)
        if qParams is None:
            qParams = {}

        if not ignore_time and self.to_date is not None and self.to_date is not None:
            qParams = {**self._time_params(), **qParams}

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

    def _host(self) -> str:
        return "https://{}".format(self.endpoint)


class ESQueryBuilder(RESTSciriusConnector):
    API = '/rest/rules/es/search/'
    TEMPLATE = {
        'query': {
            'bool': {
                'must': [{
                    'query_string': {
                        'analyze_wildcard': True,
                        'query': '*'
                    }
                }, {
                    'range': {}
                }]
            }
        },
        'size': 10
    }
    AGG = {
        'aggs': {
            '<name>': {
                'terms': {
                    'field': None
                }
            }
        }
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.reset()

    def __str__(self):
        self.__build_query()
        return json.dumps(self.body)

    def __dict__(self):
        self.__build_query()
        return self.body

    def set_tenant(self, tenant):
        self.tenant = tenant

    def set_index(self, index):
        self.index = index

    def reset(self):
        self.body = deepcopy(self.TEMPLATE)
        self.qfilter = None
        self.aggs = None
        self.time_filter = '@timestamp'
        self.set_page_size(10)
        self.nb_aggs = 0
        self.tenant = None
        self.index = 'logstash-alert-*'
        self.aggs_cols = []

    def set_time_filter(self, time_filter):
        self.time_filter = time_filter

    def add_aggs(self, field, col_name, order=None, sort='desc', size=10):
        self.aggs_cols.append(col_name)
        self.nb_aggs += 1
        agg = deepcopy(self.AGG)
        sub_section = agg['aggs'].pop('<name>')
        agg['aggs'][str(self.nb_aggs)] = sub_section
        agg['aggs'][str(self.nb_aggs)]['terms']['field'] = field

        if order:
            agg['aggs'][str(self.nb_aggs)]['terms']['order'] = {'_count': 'desc' if not sort else sort}

        agg['aggs'][str(self.nb_aggs)]['terms']['size'] = size

        if self.aggs:
            sub = self.aggs['aggs']['1']
            for cpt in range(2, self.nb_aggs + 1):
                if 'aggs' in sub:
                    sub = sub['aggs'][str(cpt)]
                    continue
                break

            sub.update(agg)
        else:
            self.aggs = agg

    def __build_query(self):
        if self.qfilter:
            self.body['query']['bool']['must'][0]['query_string']['query'] = self.qfilter

        self.body['query']['bool']['must'][1]['range'] = {
            self.time_filter: {
                'from': self._from_date_param(),
                'to': self._to_date_param()
            }
        }

        if self.aggs:
            self.body["aggs"] = self.aggs

        self.body['size'] = self.page_size

    @classmethod
    def _match_filter(cls, item, keys, val):

        for idx, key in enumerate(keys, 1):
            item = item[key]

            if isinstance(item, dict):
                continue
            elif isinstance(item, list):
                for sub_item in item:
                    return cls._match_filter(sub_item, keys[idx:], val)
            else:
                return item == val

        return False

    @classmethod
    def clean_host_id(cls, arr: list, **filters):
        for item in deepcopy(arr):
            for key, val in filters.items():
                if not cls._match_filter(deepcopy(item), key.split('.'), val):
                    arr.remove(item)
                    break
        return arr

    def post(self) -> requests.Response:
        qParams = {}

        if self.tenant is not None:
            qParams.update({'tenant': self.tenant})

        qParams.update({'from_date': self._from_date_param()})
        qParams.update({'to_date': self._to_date_param()})

        return self._post(
            self.API, self.index, self.qfilter, self.aggs,
            qParams=qParams, time_filter=self.time_filter)

    @staticmethod
    def filter_join(filters, operator='AND'):
        return f"({f' {operator} '.join(filters)})"

    def set_qfilter(self, qfilter):
        self.qfilter = qfilter
        if self.tenant and self.qfilter and 'tenant' not in self.qfilter:
            qfilter = self.filter_join([self.qfilter, f'tenant: {self.tenant}'])
            self.set_qfilter(qfilter)

    def __parse_aggs(self, val, res, idx=0, row_res=None):
        if row_res is None:
            row_res = {}

        for item in val.get('buckets', []):
            row_res[idx] = item['key']
            if str(idx + 2) in item:
                self.__parse_aggs(item[str(idx + 2)], res, idx + 1, row_res)
            else:
                for j in range(0, idx + 1):
                    res[self.aggs_cols[j]].append(row_res[j])
                res[self.aggs_cols[idx + 1]].append(item['doc_count'])

    def flatten_aggregation(self, content):
        if 'Count' not in self.aggs_cols:
            self.aggs_cols.append('Count')
        res = dict((key, []) for key in self.aggs_cols)

        for _, val in content.get('aggregations', {}).items():
            self.__parse_aggs(val, res)

        return pd.DataFrame(dict((key, res[key]) for key in self.aggs_cols))


def escape(string):
    '''
    Escape other elasticsearch reserved characters
    '''
    return string. \
        replace('=', r'\='). \
        replace('+', r'\+'). \
        replace('-', r'\-'). \
        replace('&', r'\&'). \
        replace('|', r'\|'). \
        replace('!', r'\!'). \
        replace('(', r'\('). \
        replace(')', r'\)'). \
        replace('{', r'\{'). \
        replace('}', r'\}'). \
        replace('[', r'\['). \
        replace(']', r'\]'). \
        replace('^', r'\^'). \
        replace('"', r'\"'). \
        replace('~', r'\~'). \
        replace(':', r'\:'). \
        replace('/', r'\/'). \
        replace('\\', r'\\')


def check_str_bool(val: str) -> bool:
    if val in ("y", "yes", "t", "true", "on", "1", "enabled", "enable"):
        return True
    elif val in ("n", "no", "f", "false", "off", "0", "disabled", "disable"):
        return False
    else:
        raise ValueError("invalid truth value {}".format(val))


class Report:
    COUNTER = 0

    def __init__(self, debug=False) -> None:
        self.debug = debug

    def output(self, df: pd.DataFrame, column_format=None, size=None):
        if size is not None:
            df = df[:size]

        if self.debug:
            return display(df)

        output = f'{Report.COUNTER}.tex'
        Report.COUNTER += 1

        if df is not None and len(df):
            df.to_latex(output, column_format=column_format, index=False, escape=True)
        else:
            if os.path.exists(output):
                os.remove(output)
            open(output, 'a').close()

        display(Markdown(f'STAMUSINPUT: {output}'))


def getGitRoot():
    return subprocess.Popen(['git', 'rev-parse', '--show-toplevel'],
                            stdout=subprocess.PIPE).communicate()[0].rstrip().decode('utf-8')
