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
