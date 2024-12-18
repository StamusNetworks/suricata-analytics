# Copyright © 2023 Stamus Networks oss@stamus-networks.com

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
Reusable widgets
"""

from ipywidgets.widgets.interaction import display

from ..connectors import RESTSciriusConnector
from ..datamining import nx_add_scaled_doc_count, nx_degree_scale

from copy import deepcopy

import ipywidgets as widgets
import pandas as pd
import networkx as nx
import hvplot.networkx as hvnx
import holoviews as hv

import pickle
import os
import re


CORE_COLUMNS = ["timestamp",
                "flow_id",
                "event_type",
                "proto",
                "app_proto",
                "src_ip",
                "flow.src_ip",
                "src_port",
                "dest_ip",
                "flow.dest_ip",
                "dest_port",
                "direction",
                "payload_printable",
                "metadata.flowbits"]

DEFAULT_COLUMNS = ["timestamp",
                   "flow_id",
                   "event_type",
                   "app_proto",
                   "src_ip",
                   "src_port",
                   "dest_ip",
                   "dest_port"]

TIME_COLS = ["timestamp", "@timestamp", "http.date", "flow.start", "flow.end"]

# ensure that values in these column are not shown as floating points
NORMALIZE_COLS_FLOAT_TO_INT = ["flow_id", "src_port", "dest_port"]

GRAPH_RESOLUTIONS = [
    "480x360",
    "960x540",
    "1280x720",
    "1600x900",
    "1920x1080",
    "2048x1080",
    "2540x1440",
    "3840x2160"
]


class Explorer(object):

    def __init__(self, c=RESTSciriusConnector(), debug=False) -> None:
        # Data connector to backend
        self._connector = c

        # Outputs
        self._output_eve_explorer = widgets.Output()
        self._output_eve_agg = widgets.Output()
        self._output_uniq = widgets.Output()
        self._output_graph = widgets.Output()
        self._output_graph_feedback = widgets.Output()
        self._output_timeline = widgets.Output()

        self._output_debug = widgets.Output()

        # Containers
        self.data = pd.DataFrame()
        self.data_filtered = pd.DataFrame()
        self.data_aggregate = pd.DataFrame()
        self.data_uniq = pd.DataFrame()

        self.data_graph = nx.Graph()

        self._cached_queries = []
        self._selected_columns = deepcopy(DEFAULT_COLUMNS)

        self._pickle_q_time = "./params.pkl"
        if os.path.exists(self._pickle_q_time):
            params = pickle.load(open(self._pickle_q_time, "rb"), encoding="bytes")
            self._connector.set_query_timeframe(params["time"][0], params["time"][1])
            self._cached_queries = params.get("cached_queries", [])
            self._selected_columns = params.get("selected_columns", self._selected_columns)

        self._register_shared_widgets()
        self._register_search_area()
        self._register_eve_explorer()
        self._register_eve_aggregator()
        self._register_uniq()
        self._register_graph()
        self._register_tabs(debug)

    def _register_shared_widgets(self) -> None:
        self._select_agg_col = widgets.Dropdown(description="Group by")

    def _register_search_area(self) -> None:
        self._picker_date_from = widgets.DatetimePicker(description="From", value=self._connector.from_date)
        self._picker_date_to = widgets.DatetimePicker(description="To", value=self._connector.to_date)

        self._interactive_time_pick = widgets.interactive(self._connector.set_query_timeframe,
                                                          from_date=self._picker_date_from,
                                                          to_date=self._picker_date_to)

        self._slider_time_minutes = widgets.IntSlider(description="Minutes", min=0, max=60, value=15, continuous_update=False)
        self._slider_time_hours = widgets.IntSlider(description="Hours", min=0, max=24, value=0, continuous_update=False)
        self._tickbox_time_use_relative = widgets.Checkbox(description="Use relative time", value=True)

        self._slider_page_size = widgets.IntSlider(description="Document count",
                                                   min=1000,
                                                   max=10000)

        self._text_query = widgets.Textarea(description="Query", value=self._select_default_query())

        self._selection_cached_query = widgets.Dropdown(description="Query history",
                                                        options=self._cached_queries)
        self._interactive_select_query = widgets.interactive(self._set_query_selection,
                                                             val=self._selection_cached_query)

        self._box_query_params = widgets.VBox([self._interactive_time_pick,
                                               self._slider_time_hours,
                                               self._slider_time_minutes,
                                               self._tickbox_time_use_relative,
                                               self._text_query,
                                               self._interactive_select_query,
                                               self._slider_page_size])

        self._button_download_eve = widgets.Button(description="Download EVE")
        self._button_download_eve.on_click(self._download_eve)

        self._box_search_area = widgets.VBox([self._box_query_params,
                                              self._button_download_eve])

        self._selection_eve_explore_columns = widgets.SelectMultiple(description="Columns", rows=20)
        self._selection_eve_explore_sort = widgets.SelectMultiple(description="Sort", rows=20)

    def _register_eve_explorer(self) -> None:
        self._slider_show_eve = widgets.IntSlider(min=10, max=1000, continuous_update=False)

        self._find_filtered_columns = widgets.Dropdown(description="Field")
        self._find_filtered_value = widgets.Text(description="Value")

        self._find_filtered_event_type = widgets.Dropdown(description="Event Type")

        self._interactive_explore_eve = widgets.interactive(
            self._display_eve_show,
            limit=self._slider_show_eve,
            columns=self._selection_eve_explore_columns,
            sort=self._selection_eve_explore_sort,
            filter_field=self._find_filtered_columns,
            filter_value=self._find_filtered_value,
            filter_event_type=self._find_filtered_event_type,
        )

        self._box_filter_fields = widgets.VBox([self._find_filtered_columns,
                                                self._find_filtered_value])
        self._box_filter_fields = widgets.HBox([self._box_filter_fields,
                                                widgets.VBox([self._find_filtered_event_type])])

        self._box_eve_explorer = widgets.VBox([self._box_filter_fields,
                                               self._slider_show_eve,
                                               widgets.HBox([self._selection_eve_explore_columns,
                                                             self._selection_eve_explore_sort])])

        self._box_eve_explorer = widgets.HBox([self._box_search_area,
                                               self._box_eve_explorer])

        self._box_eve_explorer = widgets.VBox([self._box_eve_explorer,
                                               self._output_eve_explorer])

    def _register_eve_aggregator(self) -> None:
        self._button_eve_agg = widgets.Button(description="Aggregate EVE")
        self._interactive_aggregate_eve = widgets.interactive(self._display_eve_agg,
                                                              limit=widgets.IntSlider(min=10, max=1000, continuous_update=False),
                                                              groupby=self._select_agg_col)

        self._box_eve_agg = widgets.HBox([self._box_search_area,
                                          self._interactive_aggregate_eve])

        self._box_eve_agg = widgets.VBox([self._box_eve_agg,
                                          self._output_eve_agg,
                                          self._output_debug])

    def _register_uniq(self) -> None:
        options = self._connector.get_unique_fields()
        self._dropdown_select_field = widgets.Combobox(description="Select field",
                                                       options=options)

        self._tickbox_sort_counts = widgets.Checkbox(description="Sort by count", value=False)
        self._tickbox_show_simple = widgets.Checkbox(description="Show only simple values", value=False)

        self._slider_show_uniq = widgets.IntSlider(min=10, max=1000, continuous_update=False, description="Limit display")

        self._interactive_display_uniq = widgets.interactive(self._display_uniq,
                                                             limit=self._slider_show_uniq,
                                                             show_simple=self._tickbox_show_simple,
                                                             sort_by_count=self._tickbox_sort_counts)

        self._button_download_uniq = widgets.Button(description="Pull uniq")
        self._button_download_uniq.on_click(self._download_uniq)

        self._box_uniq = widgets.VBox([self._dropdown_select_field,
                                       self._interactive_display_uniq,
                                       self._button_download_uniq])

        self._box_uniq = widgets.HBox([self._box_search_area,
                                       self._box_uniq])

        self._box_uniq = widgets.VBox([self._box_uniq,
                                       self._output_uniq])

    def _register_graph(self) -> None:
        options = self._connector.get_unique_fields()
        options = col_cleanup(options)

        self._dropdown_graph_node_src = widgets.Combobox(description="Node src", options=options, value="src_ip")
        self._dropdown_graph_node_dst = widgets.Combobox(description="Node dst", options=options, value="dest_ip")

        self._slider_graph_node_agg_src = widgets.IntSlider(description="Max agg", min=10, max=200, value=100, continuous_update=False)
        self._slider_graph_node_agg_dst = widgets.IntSlider(description="Max agg", min=10, max=200, value=100, continuous_update=False)

        self._tickbox_labels_src = widgets.Checkbox(description="Labels", value=False)
        self._tickbox_labels_dst = widgets.Checkbox(description="Labels", value=False)

        self._button_graph_download = widgets.Button(description="Pull graph data")
        self._button_graph_download.on_click(self._download_graph)

        self._dropdown_graph_rez = widgets.Dropdown(
            description="Graph size",
            options=GRAPH_RESOLUTIONS,
            value=GRAPH_RESOLUTIONS[1]
        )

        self._button_graph_draw = widgets.Button(description="Draw graph")
        self._button_graph_draw.on_click(self._display_graph)

        self._box_graph = widgets.HBox([widgets.VBox([self._dropdown_graph_node_src,
                                                      self._slider_graph_node_agg_src,
                                                      self._tickbox_labels_src]),
                                        widgets.VBox([self._dropdown_graph_node_dst,
                                                      self._slider_graph_node_agg_dst,
                                                      self._tickbox_labels_dst])])

        self._box_graph = widgets.VBox([self._box_graph,
                                        self._button_graph_download,
                                        self._button_graph_draw,
                                        self._dropdown_graph_rez])

        self._box_graph = widgets.HBox([self._box_search_area,
                                        self._box_graph])

        self._box_graph = widgets.VBox([self._box_graph,
                                        self._output_graph,
                                        self._output_graph_feedback])

    def _register_tabs(self, debug: bool) -> None:
        boxes = [
            (self._box_eve_explorer, "Expore"),
            (self._box_eve_agg, "Aggregate"),
            (self._box_uniq, "Uniq"),
            (self._box_graph, "Graph"),
        ]
        if debug:
            boxes.append((self._output_debug, "Debug"))

        self._tabs = widgets.Tab(children=[b[0] for b in boxes])

        for i, item in enumerate(boxes):
            self._tabs.set_title(i, item[1])

    def _download_eve(self, args: None) -> None:
        self._connector.set_page_size(self._slider_page_size.value)

        if self._tickbox_time_use_relative.value is True:
            self._connector.set_query_delta(hours=self._slider_time_hours.value,
                                            minutes=self._slider_time_minutes.value)
        else:
            self._connector.set_query_timeframe(from_date=self._picker_date_from.value,
                                                to_date=self._picker_date_to.value)

        self._output_debug.clear_output()
        with self._output_debug:
            try:
                self.data = self._connector.get_events_df(qfilter=self._text_query.value)
            except ConnectionError:
                print("unable to connect to %s" % self._connector.endpoint)

            self.data = reorder_columns(self.data)
            self.data = df_parse_time_colums(self.data)
            self.data = df_recast_float_to_int(self.data)

            self._selection_eve_explore_columns.options = self._data_column_values()
            self._selection_eve_explore_sort.options = self._data_column_values()

            self._cache_params()

        self._display_aggregate_event_types()
        display_df(self.data, self._output_eve_explorer)

        # initial display update and widget population when user has not interacted yet
        # empty dropdowns / boxes and noisy display otherwise

        # FIXME - linting errors from type definitions
        self._display_eve_show(
            limit=self._slider_show_eve.value,
            columns=self._selection_eve_explore_columns.value,
            sort=self._selection_eve_explore_sort.value,
            filter_field=self._find_filtered_columns.value,
            filter_value=self._find_filtered_value.value,
            filter_event_type=self._find_filtered_event_type.value,
        )

    def _download_uniq(self, args: None) -> None:
        self._output_debug.clear_output()
        with self._output_debug:
            try:
                values = self._connector.get_eve_unique_values(counts="yes",
                                                               field=self._dropdown_select_field.value,
                                                               qfilter=self._text_query.value)
                self.data_uniq = pd.DataFrame(values)

            except ConnectionError:
                print("unable to connect to %s" % self._connector.endpoint)

        self.data_uniq = pd.DataFrame(self.data_uniq)
        self._cache_params()
        self._display_uniq(self._slider_show_uniq.value,
                           checkbox_verify(self._tickbox_show_simple),
                           checkbox_verify(self._tickbox_sort_counts))

    def _download_graph(self, args: None) -> None:
        self._output_graph_feedback.clear_output()
        with self._output_graph_feedback:
            print("calling scirius at %s" % self._connector.endpoint)
            kwargs = {
                "col_src": self._dropdown_graph_node_src.value,
                "col_dest": self._dropdown_graph_node_dst.value,
                "size_src": self._slider_graph_node_agg_src.value,
                "size_dest": self._slider_graph_node_agg_dst.value,
                "qfilter": self._text_query.value
            }
            self.data_graph = self._connector.get_eve_fields_graph_nx(**kwargs)

            # drop empty nodes (and connected edges)
            # means missing eve field, no connection can be made
            if "" in list(self.data_graph.nodes()):
                self.data_graph.remove_node("")

            self._cache_params()

            nx_add_scaled_doc_count(self.data_graph)
            nx_degree_scale(self.data_graph)

            display("call done, got %d nodes and %d edges" %
                    (len(self.data_graph.nodes()), len(self.data_graph.edges())))

    def _display_uniq(self, limit: int, show_simple: bool, sort_by_count: bool) -> None:
        if self.data_uniq.empty:
            return

        pd.set_option('display.max_rows', limit)
        pd.set_option('display.min_rows', limit)

        if sort_by_count:
            self.data_uniq = self.data_uniq.sort_values(by="doc_count", ascending=False)
        else:
            self.data_uniq = self.data_uniq.sort_values(by="key")

        if show_simple is True:
            display_list_simple(list(self.data_uniq.key), self._output_uniq)
        else:
            display_df(self.data_uniq, self._output_uniq)

    def _display_graph(self, args) -> None:
        self._output_graph.clear_output()
        with self._output_graph:
            if self.data_graph is None or len(self.data_graph) == 0:
                print("no graph data, please pull first")
                return

            # generate layout
            pos = nx.layout.spring_layout(self.data_graph)

            # parse resolution
            rez = self._dropdown_graph_rez.value
            if not isinstance(rez, str):
                print("something went wrong")
                return

            rez = rez.split("x")
            width = int(rez[0])
            height = int(rez[1])

            # locate source nodes
            n_src = [i for i, (_, a) in enumerate(self.data_graph.nodes(data=True)) if a["kind"] == "source"]
            # locate destination nodes
            n_dst = [i for i, (_, a) in enumerate(self.data_graph.nodes(data=True)) if a["kind"] == "destination"]

            # generate nodes per kind
            nodes_src = hvnx.draw_networkx_nodes(self.data_graph, pos, nodelist=n_src, node_color='#A0CBE2').opts(width=width, height=height)
            nodes_dst = hvnx.draw_networkx_nodes(self.data_graph, pos, nodelist=n_dst, node_color="Orange").opts(width=width, height=height)

            # use kwargs to make parameter handling easier
            edge_params = {
                "alpha": 1,
                "edge_color": 'scaled_doc_count',
                "edge_cmap": 'viridis',
                "edge_width": hv.dim('scaled_doc_count')*5
            }
            # generate edges
            edges = (
                hvnx
                .draw_networkx_edges(self.data_graph, pos, **edge_params)
                .opts(width=width, height=height)
            )

            # overlay nodes and edges
            res = edges * nodes_src * nodes_dst

            if self._tickbox_labels_src.value is True:
                labels = hvnx.draw_networkx_labels(self.data_graph, pos, nodelist=n_src)
                res = res * labels

            if self._tickbox_labels_dst.value is True:
                labels = hvnx.draw_networkx_labels(self.data_graph, pos, nodelist=n_dst)
                res = res * labels

            component_sizes = [len(c) for c in sorted(nx.connected_components(self.data_graph),
                                                      key=len,
                                                      reverse=True)
                               if len(c) > 1]

            print("Number of clusters: {}".format(len(component_sizes)))
            display(res)

    def _display_aggregate_event_types(self):
        self._output_debug.clear_output()
        with self._output_debug:
            if "event_type" not in self._data_column_values():
                print("no event_type column to aggregate")
            else:
                df_agg = (
                    self
                    .data
                    .groupby("event_type")
                    .agg({"event_type": ["count"]})
                )
                if df_agg is not None:
                    df_agg = df_agg.reset_index()
                    df_agg.columns = ["event_type", "event_count"]
                display(df_agg)

    def _display_eve_show(self,
                          limit: int,
                          columns: tuple,
                          sort: tuple,
                          filter_field: str,
                          filter_value: str,
                          filter_event_type: str):
        pd.set_option('display.max_rows', limit)
        pd.set_option('display.min_rows', limit)

        if columns is None or len(list(columns)) == 0:
            cols = [c for c in DEFAULT_COLUMNS if c in self._data_column_values()]
            self._selection_eve_explore_columns.value = cols
        else:
            self._selected_columns = [c for c in columns if c in self._data_column_values()]
            self._selection_eve_explore_columns.value = self._selected_columns

        self._output_eve_explorer.clear_output()
        with self._output_eve_explorer:
            sort_cols = []
            if len(sort) > 0:
                sort_cols = list(sort)
            elif len(sort) == 0 and "timestamp" in self._data_column_values():
                sort_cols = ["timestamp"]
                self._selection_eve_explore_sort.value = sort_cols

        self._output_debug.clear_output()
        with self._output_debug:
            self.data_filtered = (
                self
                .data[self._selected_columns]
                .sort_values(by=sort_cols)
            )
            self.data_filtered = df_filter_value(self.data_filtered, filter_field, filter_value)
            self.data_filtered = df_filter_value(self.data_filtered, "event_type", filter_event_type)

        self._find_filtered_columns.options = self._filtered_column_values()

        update_values(self._find_filtered_event_type, self.data, "event_type")

        self._select_agg_col.options = self._filtered_column_values()

        display_df(self.data_filtered, self._output_eve_explorer)

    def _display_eve_agg(self, limit: int, groupby: str) -> None:
        pd.set_option('display.max_rows', limit)
        pd.set_option('display.min_rows', limit)

        df = self.data if self.data_filtered.empty else self.data_filtered

        if groupby in ("", None):
            return

        self.data_aggregate = (
            df
            .fillna("")
            .dropna(axis=1, how="all")
            .groupby(by=groupby)
            .agg({
                item: ["min", "max"] if item in TIME_COLS
                else ["unique", "nunique"]
                for item in list(df.columns.values) if item != groupby and item not in self._list_cols
            })
        )
        if self.data_aggregate is not None and not self.data_aggregate.empty:
            self.data_aggregate = self.data_aggregate.reset_index()

        if isinstance(self.data_aggregate, pd.DataFrame):
            display_df(self.data_aggregate, self._output_eve_agg)

    def _data_column_values(self) -> list:
        return [] if self.data is None else list(self.data.columns.values)

    def _filtered_column_values(self) -> list:
        self._list_cols = (self.data_filtered.applymap(type) == list).any()
        self._list_cols = list(self._list_cols.loc[self._list_cols].index)

        return [v for v in list(self.data_filtered.columns.values) if v not in self._list_cols]

    def _select_default_query(self) -> str:
        if len(self._cached_queries) > 0:
            return self._cached_queries[-1]
        return ""

    def _append_cached_query(self) -> None:
        if self._text_query.value == "" or \
                (len(self._cached_queries) > 0 and self._text_query.value == self._cached_queries[-1]):
            return

        max = 25
        if len(self._cached_queries) > max:
            self._cached_queries = self._cached_queries[-max:]

        self._cached_queries.append(self._text_query.value)

    def _cache_params(self) -> None:
        self._append_cached_query()

        query = self._text_query.value

        self._selection_cached_query.options = self._cached_queries
        self._selection_cached_query.value = query if query is not None else ""

        dump = {
            "time": (self._connector.from_date, self._connector.to_date),
            "query": self._text_query.value,
            "cached_queries": self._cached_queries,
            "selected_columns": self._selected_columns,
        }
        pickle.dump(dump, open(self._pickle_q_time, "wb"))

    def _set_query_selection(self, val: str | None) -> None:
        if val is not None:
            self._text_query.value = val
        self._selection_cached_query.value = val

    def display(self) -> None:
        display(self._tabs)


def display_df(data: pd.DataFrame | pd.Series, output: widgets.Output):
    output.clear_output()
    with output:
        display(data.dropna(how="all", axis=1))


def display_list_simple(data: list | pd.Series, output: widgets.Output) -> None:
    output.clear_output()
    with output:
        print("\n".join(data))


def reorder_columns(df: pd.DataFrame, core_columns=CORE_COLUMNS) -> pd.DataFrame:
    cols = list(df.columns.values)
    core_cols = [c for c in core_columns if c in cols]

    cols = sorted([c for c in cols if c not in core_cols])
    cols = core_cols + cols
    return df[cols]


def df_existing_columns(df: pd.DataFrame, columns=CORE_COLUMNS) -> list:
    return [c for c in columns if c in list(df.columns.values)]


def df_parse_time_colums(df: pd.DataFrame, columns=TIME_COLS) -> pd.DataFrame:
    for ts in columns:
        if ts in list(df.columns.values):
            df[ts] = pd.to_datetime(df[ts], errors="coerce")
    return df


def df_recast_float_to_int(df: pd.DataFrame, columns=NORMALIZE_COLS_FLOAT_TO_INT) -> pd.DataFrame:
    cols = [c for c in columns if c in list(df.columns.values)]
    df[cols].fillna(0, inplace=True)
    df[cols] = df[cols].astype('Int64')
    return df


def df_filter_value(df: pd.DataFrame, col: str, value: str) -> pd.DataFrame:
    if col in ("", None) or value in ("", None):
        return df
    if col not in list(df.columns.values):
        return df

    df = df.loc[pd.notna(df[col])]

    series = df[col]
    if series.dtype == "object":
        df = df.loc[series.str.contains(value, flags=re.IGNORECASE)]
    elif series.dtype == "int64":
        df = df.loc[series == int(value)]
    elif series.dtype == "float64":
        df = df.loc[series.astype(int) == int(value)]

    return df


def update_values(w: widgets.Dropdown | widgets.Combobox,
                  df: pd.DataFrame,
                  field: str) -> None:
    if field not in list(df.columns.values):
        return
    w.options = [""] + [str(v) for v in list(df[field].dropna().unique())]


def checkbox_verify(c: widgets.Checkbox, default=False) -> bool:
    return c.value if isinstance(c.value, bool) else default


def col_cleanup(c: list[str]) -> list:
    return [i for i in c if i not in TIME_COLS and not i.startswith("@")]
