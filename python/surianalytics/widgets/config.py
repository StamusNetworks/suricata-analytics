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

import os
import json

from datetime import datetime, timedelta, timezone

import ipywidgets as widgets
from ipywidgets.widgets.interaction import display

from ..connectors import RESTSciriusConnector

LOCAL_TZ = datetime.now(timezone(timedelta(0))).astimezone().tzinfo


class Timepicker(object):

    def __init__(self, dump_path: str = "config.json") -> None:
        self._output_debug = widgets.Output()

        self.dump_path = os.path.abspath(dump_path)

        self._register_time_components()
        self._register_time_slider()
        self._register_time_picker()
        self._register_time_dump()

        self.box = widgets.VBox([self._box_time_slider,
                                 self._box_time_picker,
                                 self._button_dump_time,
                                 self._output_debug])

    def _register_time_components(self):
        self._slider_time_minutes = widgets.IntSlider(description="Minutes", min=0, max=60, value=0, continuous_update=False)
        self._slider_time_hours = widgets.IntSlider(description="Hours", min=0, max=24, value=1, continuous_update=False)
        self._slider_time_days = widgets.IntSlider(description="Days", min=0, max=365*2, value=0, continuous_update=False)

        self._picker_date_from = widgets.DatetimePicker(description="From", value=datetime.now(LOCAL_TZ) - timedelta(minutes=self._slider_time_minutes.value,
                                                                                                                     hours=self._slider_time_hours.value,
                                                                                                                     days=self._slider_time_days.value))
        self._picker_date_to = widgets.DatetimePicker(description="To", value=datetime.now(LOCAL_TZ))

    def _register_time_picker(self):
        self._box_time_picker = widgets.VBox([self._picker_date_from,
                                              self._picker_date_to])

    def _register_time_slider(self):
        self._tickbox_time_use_relative = widgets.Checkbox(description="Use relative time", value=True)
        self._interactive_time_slide = widgets.interactive(self._set_query_timepick,
                                                           minutes=self._slider_time_minutes,
                                                           hours=self._slider_time_hours,
                                                           days=self._slider_time_days)

        self._box_time_slider = widgets.VBox([self._interactive_time_slide,
                                              self._tickbox_time_use_relative])

    def _set_query_timepick(self, minutes: int, hours: int, days: int):
        if self._tickbox_time_use_relative.value is True:
            self._picker_date_to.value = datetime.now(LOCAL_TZ)
            self._picker_date_from.value = datetime.now(LOCAL_TZ) - timedelta(minutes=minutes, hours=hours, days=days)

    def _register_time_dump(self):
        self._button_dump_time = widgets.Button(description="Dump time to JSON")
        self._button_dump_time.on_click(self._dump_time)

    def _dump_time(self, args: None):
        data = {"from_date": str(self._picker_date_from.value),
                "to_date": str(self._picker_date_to.value),
                "time_minutes": self._slider_time_minutes.value,
                "time_hours": self._slider_time_hours.value,
                "time_days": self._slider_time_days.value,
                "use_relative_time": self._tickbox_time_use_relative.value}

        self._output_debug.clear_output()
        with self._output_debug:
            with open(self.dump_path, "w") as handle:
                handle.write(json.dumps(data))

    def display(self) -> None:
        display(self.box)


def update_connector_timeframe(c: RESTSciriusConnector, dump_path: str):
    with open(dump_path, "rb") as handle:
        data = json.loads(handle.read())

    if data["use_relative_time"] is True:
        c.days = data["time_days"]
        c.hours = data["time_hours"]
        c.minutes = data["time_minutes"]
        c.set_time_delta()
    else:
        c.set_query_timeframe(from_date=data["from_date"],
                              to_date=data["to_date"])
