# Copyright © 2024 Stamus Networks oss@stamus-networks.com

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

import networkx as nx
import hvplot.networkx as hvnx


def draw_nx_graph(g: nx.Graph, width: int = 1024, height: int = 1024):
    # generate layout
    pos = nx.layout.spring_layout(g)

    # locate source nodes
    n_src = [i for i, (_, a) in enumerate(g.nodes(data=True)) if a["kind"] == "source"]
    # locate destination nodes
    n_dst = [i for i, (_, a) in enumerate(g.nodes(data=True)) if a["kind"] == "destination"]

    # generate nodes per kind
    nodes_src = hvnx.draw_networkx_nodes(g, pos, nodelist=n_src, node_color='#A0CBE2').opts(width=width, height=height)
    nodes_dst = hvnx.draw_networkx_nodes(g, pos, nodelist=n_dst, node_color="Orange").opts(width=width, height=height)

    # generate edges
    edges = (
        hvnx
        .draw_networkx_edges(g, pos)
        .opts(width=width, height=height)
    )

    # overlay nodes and edges
    res = edges * nodes_src * nodes_dst

    labels = hvnx.draw_networkx_labels(g, pos, nodelist=n_src)
    res = res * labels

    labels = hvnx.draw_networkx_labels(g, pos, nodelist=n_dst)
    res = res * labels

    return res
