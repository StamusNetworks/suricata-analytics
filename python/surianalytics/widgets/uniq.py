"""
Hunting and flow extraction by exploring unique value
"""

import pickle
import os

from ipywidgets.widgets.interaction import display
from copy import deepcopy

import ipywidgets as widgets
import pandas as pd
import networkx as nx

from ..connectors import RESTSciriusConnector
from ..viz import draw_nx_graph
from ..helpers import escape_special_chars
from ..datamining import nx_filter_scaled_src_dest

OUTPUT_DEBUG = widgets.Output()

DEFAULT_COLUMNS = ["timestamp", "flow_id", "event_type", "src_ip", "dest_ip", "app_proto"]

DUMP_COLS = "./columns.pkl"
DUMP_Q_BASE = "./basequery.pkl"
DUMP_Q_VALS = "./valquery.pkl"


class UniqPivot(object):
    connector: RESTSciriusConnector

    event_types: list = []
    fields: list = []
    data: pd.DataFrame = pd.DataFrame()
    graph: nx.Graph = nx.Graph()

    w_limit: widgets.IntSlider = widgets.IntSlider(min=10, max=1000, description="Limit")
    w_fields: widgets.Combobox = widgets.Combobox(description="Fields")
    w_values: widgets.SelectMultiple = widgets.SelectMultiple(description="Values", rows=30)
    w_flow_id: widgets.SelectMultiple = widgets.SelectMultiple(description="Flow ID", rows=30)
    w_columns: widgets.SelectMultiple = widgets.SelectMultiple(description="Columns", rows=30)
    w_groupby: widgets.Dropdown = widgets.Dropdown(description="Group by")
    w_groupby_time: widgets.Dropdown = widgets.Dropdown(description="Time bucket",
                                                        options=["NA", "weekly", "daily", "12 hours", "6 hours", "4 hours", "hourly"],
                                                        value="NA")
    w_colset: widgets.Dropdown = widgets.Dropdown(description="Columns set")

    w_graph_src: widgets.Combobox = widgets.Combobox(description="Graph Source")
    w_graph_dest: widgets.Combobox = widgets.Combobox(description="Graph Destination")
    w_graph_degree_src: widgets.FloatRangeSlider = widgets.FloatRangeSlider(description="Source Degree",
                                                                            min=0, max=1, value=[0, 1], step=0.01)
    w_graph_degree_dest: widgets.FloatRangeSlider = widgets.FloatRangeSlider(description="Destination Degree",
                                                                             min=0, max=1, value=[0, 1], step=0.01)
    w_graph_resolution_w: widgets.Text = widgets.Text(description="Width", value="1024")
    w_graph_resolution_h: widgets.Text = widgets.Text(description="Height", value="1024")

    w_button_values: widgets.Button = widgets.Button(description="Update values")
    w_button_flow_id: widgets.Button = widgets.Button(description="Update Flow ID")
    w_button_df: widgets.Button = widgets.Button(description="Download EVE")
    w_button_reset_cols: widgets.Button = widgets.Button(description="Reset columns")
    w_button_show_data: widgets.Button = widgets.Button(description="Show data")
    w_button_save_colset: widgets.Button = widgets.Button(description="Save column set")
    w_button_graph: widgets.Button = widgets.Button(description="Graph")

    w_slider_limit: widgets.IntSlider = widgets.IntSlider(description="Limit", continuous_update=False, min=10, max=1000)

    w_q_base: widgets.Textarea = widgets.Textarea(description="Base query", layout=widgets.Layout(width="auto"))
    w_q_base_dropdown: widgets.Dropdown = widgets.Dropdown(description="Base query list")
    w_button_save_baseq: widgets.Button = widgets.Button(description="Save base query")

    w_q_values: widgets.Textarea = widgets.Textarea(description="Query: values", layout=widgets.Layout(width="auto"))
    w_q_values_dropdown: widgets.Dropdown = widgets.Dropdown(description="Value query list")
    w_button_save_values: widgets.Button = widgets.Button(description="Save value query")

    q_flow_id: str = ""
    columns: list = deepcopy(DEFAULT_COLUMNS)

    intr_build_q_val: widgets.interactive
    intr_build_q_flow_id: widgets.interactive
    intr_values: widgets.interactive
    intr_update_cols: widgets.interactive
    intr_select_groupby: widgets.interactive
    intr_pick_colset: widgets.interactive
    intr_pick_q_base: widgets.interactive
    intr_pick_q_vals: widgets.interactive

    output_df: widgets.Output = widgets.Output()
    output_agg: widgets.Output = widgets.Output()
    output_nx: widgets.Output = widgets.Output()

    box_query: widgets.Box = widgets.VBox()
    box_interact: widgets.Box = widgets.HBox()
    tab_output: widgets.Tab = widgets.Tab()

    box: widgets.Box = widgets.VBox()

    def __init__(self, c=RESTSciriusConnector()) -> None:
        self.connector = c

        self.event_types = sorted(c.get_event_types())
        self.fields = []
        self.update_fields(None)

        load_options(self.w_colset, DUMP_COLS)
        load_options(self.w_q_base_dropdown, DUMP_Q_BASE)
        load_options(self.w_q_values_dropdown, DUMP_Q_VALS)

        self.w_button_values.on_click(self._pick_value)
        self.w_button_flow_id.on_click(self._pull_flow_id)
        self.w_button_df.on_click(self._pull_data)
        self.w_button_reset_cols.on_click(self._reset_columns)
        self.w_button_show_data.on_click(self._show_data)
        self.w_button_save_colset.on_click(self._save_column_set)
        self.w_button_graph.on_click(self._build_graph)
        self.w_button_save_baseq.on_click(self._save_query_base)
        self.w_button_save_values.on_click(self._save_query_val)

        self.intr_build_q_val = widgets.interactive(self._intr_set_base_q, query=self.w_q_base)
        self.intr_build_q_flow_id = widgets.interactive(self._intr_build_flow_id_q, values=self.w_flow_id)
        self.intr_values = widgets.interactive(self._intr_gen_query, values=self.w_values)
        self.intr_update_cols = widgets.interactive(self._intr_update_cols, cols=self.w_columns)
        self.intr_limit = widgets.interactive(self._intr_limit_show, limit=self.w_slider_limit)

        self.intr_select_groupby = widgets.interactive(self._intr_aggregate, group_by=self.w_groupby, time=self.w_groupby_time)
        self.intr_select_colset = widgets.interactive(self._intr_colset, col_set=self.w_colset)

        self.intr_pick_q_base = widgets.interactive(self._intr_update_q_base, value=self.w_q_base_dropdown)
        self.intr_pick_q_vals = widgets.interactive(self._intr_update_q_vals, value=self.w_q_values_dropdown)

        self.box_query.children = [
            widgets.HBox([self.w_q_base, self.w_q_base_dropdown, self.w_button_save_baseq]),
            widgets.HBox([self.w_q_values, self.w_q_values_dropdown, self.w_button_save_values])
        ]

        self.box_interact.children = [
            widgets.VBox([self.w_fields, self.intr_values]),
            widgets.VBox([self.intr_build_q_flow_id]),
            widgets.VBox([self.intr_update_cols]),
            widgets.VBox([
                self.w_button_values,
                self.w_button_flow_id,
                self.w_button_df,
                self.w_button_reset_cols,
                self.w_button_show_data,
                self.w_slider_limit,
                self.intr_select_groupby,
                self.w_button_save_colset,
                self.intr_select_colset,
            ]),
        ]

        self.tab_output.children = [
            self.output_df,
            self.output_agg,
            widgets.VBox([
                widgets.VBox([
                    widgets.HBox([self.w_graph_src, self.w_graph_degree_src, self.w_graph_resolution_w]),
                    widgets.HBox([self.w_graph_dest, self.w_graph_degree_dest, self.w_graph_resolution_h]),
                    self.w_button_graph,
                ]),
                self.output_nx,
            ])
        ]
        self.tab_output.set_title(0, "Dataframe")
        self.tab_output.set_title(1, "Aggregate")
        self.tab_output.set_title(2, "Graph")

        self.box.children = [self.box_query, self.box_interact, self.tab_output]

    def _intr_aggregate(self, group_by: str, time: str) -> None:
        if group_by in (None, ""):
            return

        aggs = {"timestamp": ["min", "max", "count"]}
        for c in self.columns:
            if c in ["flow_id", "timestamp", "metadata.flowbits"]:
                continue
            aggs[c] = ["unique", "nunique"]

        self.output_agg.clear_output()
        with self.output_agg:
            match time:
                case "weekly":
                    grp = [pd.Grouper(freq="1W"), group_by]
                case "daily":
                    grp = [pd.Grouper(freq="1d"), group_by]
                case "12 hours":
                    grp = [pd.Grouper(freq="12h"), group_by]
                case "6 hours":
                    grp = [pd.Grouper(freq="12h"), group_by]
                case "4 hours":
                    grp = [pd.Grouper(freq="12h"), group_by]
                case "hourly":
                    grp = [pd.Grouper(freq="1h"), group_by]
                case _:
                    grp = group_by

            df_agg = (
                self.data
                .groupby(grp)
                .agg({k: v for k, v in aggs.items() if k != group_by})
            )
            display(df_agg)

    def _intr_set_base_q(self, query: str) -> None:
        if query in ("", None):
            return
        self.connector.basefilter = query

    def _pick_value(self, args: None) -> None:
        if self.w_fields.value in ("", None):
            return

        resp = self.connector.get_eve_unique_values(field=self.w_fields.value, counts="no")
        self.w_values.options = resp
        with OUTPUT_DEBUG:
            print("got %d values" % len(resp))

    def _intr_update_q_base(self, value: str) -> None:
        if value in (None, ""):
            return
        self.w_q_base.value = value

    def _intr_update_q_vals(self, value: str) -> None:
        if value in (None, ""):
            return
        self.w_q_values.value = value

    def _intr_update_cols(self, cols: list) -> None:
        if cols in (None, [], ()):
            return

        self.columns = cols
        self.w_groupby.options = cols

    def _intr_gen_query(self, values: list) -> None:
        if values in (None, []):
            return

        key = self.w_fields.value
        val = [escape_special_chars(v, "{}:()/") for v in values]
        val = [f"\"{v}\"" if " " in v else v for v in val]
        val = " OR ".join(val)

        if len(values) > 1:
            val = f"({val})"

        if key in ("", None) and val in ("", None):
            self.w_q_values.value = "*"
        else:
            self.w_q_values.value = f"{key}: {val}"

    def _intr_build_flow_id_q(self, values: list[int]) -> None:
        if values in (None, []):
            return

        values_fmt = " OR ".join([str(i) for i in values])
        self.q_flow_id = f"flow_id: ({values_fmt})"

    def _intr_colset(self, col_set: list) -> None:
        if col_set in ((), [], None):
            return
        self.columns = [c for c in col_set if c in list(self.data.columns.values)]
        self._update_w_columns()

    def _intr_limit_show(self, limit: int) -> None:
        pd.set_option('display.max_rows', limit)
        pd.set_option('display.min_rows', limit)

    def _pull_flow_id(self, args: None) -> None:
        if self.w_values.value in ([], None):
            return

        if self.w_q_values.value in ("", None):
            with OUTPUT_DEBUG:
                print("value query is empty")
            return

        self.w_flow_id.options = self.connector.get_eve_unique_values(
            qfilter=self.w_q_values.value,
            field="flow_id"
        )
        with OUTPUT_DEBUG:
            print("got %d flow_id" % len(self.w_flow_id.options))

    def _pull_data(self, args: None) -> None:
        self.connector.ignore_basefilter = True
        self.data = self.connector.get_events_df(qfilter=self.q_flow_id)
        self.data.index = pd.to_datetime(self.data["timestamp"])
        self.data.index.rename("index", inplace=True)

        self.connector.ignore_basefilter = False

        self._update_w_columns()
        self._show_data(None)

        self.w_groupby.options = deepcopy(self.columns)

        with OUTPUT_DEBUG:
            print("got %d events" % len(self.data))

    def _show_data(self, args: None) -> None:
        pd.set_option('display.max_colwidth', None)
        pd.set_option('display.max_columns', None)

        self.output_df.clear_output()
        with self.output_df:
            display(
                self
                .data
                .sort_values(by=["flow_id", "timestamp"], ascending=True)
                [list(self.columns)]
                .dropna(how="all", axis=1)
            )

    def _build_graph(self, args: None) -> None:
        self.output_nx.clear_output()
        with self.output_nx:
            self.graph = self.connector.get_eve_fields_graph_nx(qfilter=self.w_q_values.value,
                                                                col_src=self.w_graph_src.value,
                                                                col_dest=self.w_graph_dest.value)
            nx_filter_scaled_src_dest(g=self.graph,
                                      thresh_src=self.w_graph_degree_src.value,
                                      thresh_dest=self.w_graph_degree_dest.value)
            display(draw_nx_graph(g=self.graph,
                                  width=int(self.w_graph_resolution_w.value),
                                  height=int(self.w_graph_resolution_h.value)))

    def _update_w_columns(self) -> None:
        if self.columns in (None, [], ()):
            self._reset_columns(None)
        self.w_columns.options = list(self.data.columns.values)
        self.w_columns.value = [v for v in self.columns if v in list(self.data.columns.values)]

    def _save_column_set(self, args: None) -> None:
        dump_options(self.w_colset, self.columns, DUMP_COLS)

    def _save_query_base(self, args: None) -> None:
        dump_options(self.w_q_base_dropdown, self.w_q_base.value, DUMP_Q_BASE)

    def _save_query_val(self, args: None) -> None:
        dump_options(self.w_q_values_dropdown, self.w_q_values.value, DUMP_Q_VALS)

    def _reset_columns(self, args: None) -> None:
        self.columns = deepcopy(DEFAULT_COLUMNS)
        self._update_w_columns()

    def update_fields(self, args: None) -> None:
        self.fields = self.connector.get_unique_fields()

        self.w_fields.options = self.fields
        self.w_graph_src.options = self.fields
        self.w_graph_dest.options = self.fields

    def display(self):
        display(self.box)


def dump_options(dropdown: widgets.Dropdown,
                 value: object,
                 filename: str) -> None:
    if dropdown.options is None:
        opts = []
    else:
        opts = list(dropdown.options)

    opts.append(value)
    dropdown.options = opts
    with open(filename, "wb") as handle:
        pickle.dump(opts, handle)


def load_options(dropdown: widgets.Dropdown,
                 filename: str) -> None:
    if os.path.exists(filename):
        with open(filename, "rb") as handle:
            opts = pickle.load(handle)
            dropdown.options = opts
