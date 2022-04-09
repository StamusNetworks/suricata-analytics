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
ARG WHEEL_DIST="/tmp/wheels"

FROM python:3.9-slim-bullseye as builder
ARG WHEEL_DIST

RUN apt-get update && \
    apt-get install -y gcc g++ unixodbc-dev

RUN mkdir /src
COPY . /src
WORKDIR /src
RUN python3 -m pip wheel -w "${WHEEL_DIST}" .

FROM jupyter/scipy-notebook

LABEL maintainer="Stamus Networks oss@stamus-networks.com"

ARG WHEEL_DIST

RUN mamba install --quiet --yes \
  'elasticsearch' \
  'hvplot' \
  'bokeh' \
  'scikit-image' \
  'xarray'  \
  'datashader' \
  'holoviews' && \
  mamba clean --all -f -y && \
  fix-permissions "${CONDA_DIR}" && \
  fix-permissions "/home/${NB_USER}"

# Not provided in conda forge, fall back to pip
RUN python3 -m pip install --user msticpy && \
  fix-permissions "/home/${NB_USER}"

ARG WHEEL_DIST
COPY --from=builder "${WHEEL_DIST}" "${WHEEL_DIST}"
WORKDIR "${WHEEL_DIST}"
RUN python3 -m pip --no-cache-dir install *.whl --force-reinstall

WORKDIR ${HOME}

USER root

COPY jupyter/scripts/clear_notebooks /usr/local/bin

COPY jupyter/Notebooks /home/${NB_USER}/Notebooks
RUN chown -R ${NB_USER}:${NB_GROUP} /home/${NB_USER}/Notebooks

USER ${NB_USER}

VOLUME /home/${NB_USER}/Notebooks
