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
Helpers for datamining tasks
"""
import pandas as pd
import networkx as nx
import numpy as np


def min_max_scaling(c: pd.Series) -> pd.Series | pd.DataFrame:
    min = c.min()
    max = c.max()
    return c.apply(lambda x: (x - min) / (max - min))


def nx_add_scaled_doc_count(g: nx.Graph):
    doc_counts = [attr["doc_count"] for (_, _, attr) in g.edges(data=True)]

    doc_counts = np.log2(doc_counts)
    doc_counts = min_max_scaling(pd.Series(doc_counts))

    # add scaled doc counts to edges to serve as weights
    for i, (_, _, attr) in enumerate(g.edges(data=True)):
        if attr is not None:
            attr["scaled_doc_count"] = doc_counts[i]


def nx_degree_scale(g: nx.Graph) -> pd.Series | pd.DataFrame:
    degree = [g.degree(n) for n in g.nodes()]
    return min_max_scaling(pd.Series(degree))


def nx_scale_param(g: nx.Graph, value: str, name="kind"):
    vals = []
    for k, v in g.nodes(data=True):
        if v[name] == value:
            vals.append((k, g.degree(k)))
    vect = min_max_scaling(pd.Series([v[1] for v in vals]))
    for i, v in enumerate(vect):
        g.nodes[vals[i][0]][f"degree_scaled_{name}_{value}"] = v


def nx_filter_scaled_src_dest(g: nx.Graph, thresh_src=(0, 1), thresh_dest=(0, 1)):
    nx_scale_param(g, "source")
    nx_scale_param(g, "destination")
    to_remove = set()
    for k, v in g.nodes(data=True):
        if v["kind"] == "source" and not _val_in_range(v, "degree_scaled_kind_source", thresh_src[0], thresh_src[1]):
            to_remove.add(k)
        elif v["kind"] == "destination" and not _val_in_range(v, "degree_scaled_kind_destination", thresh_dest[0], thresh_dest[1]):
            to_remove.add(k)
    for n in to_remove:
        g.remove_node(n)

    no_connections = [n for n in g.nodes() if g.degree(n) == 0]
    for n in no_connections:
        g.remove_node(n)


def _val_in_range(d: dict, k: str, floor: float, ceil: float) -> bool:
    return d[k] >= floor and d[k] <= ceil
