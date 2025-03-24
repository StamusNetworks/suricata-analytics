"""
Helper objects to deal with elasticsearch results
"""

import requests

import pandas as pd


class Aggregation:
    raw: dict

    def __init__(self, raw: dict | requests.Response, timeline: bool = False) -> None:
        if isinstance(raw, dict):
            self.raw = raw
        elif isinstance(raw, requests.Response):
            self.raw = raw.json()

        self.timeline = timeline

    def aggs(self) -> dict:
        return self.raw.get("aggregations", {})

    def flatten_timeline(self, pivot: bool = True) -> pd.DataFrame:
        """
        Flatten and pivot date histogram aggregation.
        Naive implementation which assumes simple 2 level aggregation where first level is time bucket and second is term aggregation.
        """
        if not self.timeline:
            raise ValueError("not a timeline aggregation")

        tx = {"timestamp": []}
        cols = set()
        for data in self.aggs().values():
            for bucket in data.get("buckets"):
                aggs = [k for k, v in bucket.items() if isinstance(v, dict) and "buckets" in v]
                for agg in aggs:
                    cols.add(agg)
                    if agg not in tx:
                        tx[agg] = []
                        tx["count"] = []
                    for bucket2 in bucket[agg].get("buckets", []):
                        tx[agg].append(bucket2["key"])
                        tx["count"].append(bucket2["doc_count"])
                        tx["timestamp"].append(bucket["key_as_string"])

        df = pd.DataFrame(tx)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if pivot:
            df = df.pivot(index="timestamp", columns=list(cols)).fillna(0)
            df.columns = [c[1] for c in df.columns.values]
        return df
