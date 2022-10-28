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
ARG BUILD_WORKERS=1

FROM python:3.10-slim-bullseye as builder-python
ARG WHEEL_DIST

RUN apt-get update && \
    apt-get install -y gcc g++ unixodbc-dev

RUN mkdir /src
COPY . /src
WORKDIR /src
RUN python3 -m pip wheel -w "${WHEEL_DIST}" .

FROM ubuntu:22.04 as builder-suricata
LABEL maintainer="Markus Kont <markus@stamus-networks.com>"

ARG BUILD_WORKERS

ENV DEBIAN_FRONTEND=noninteractive
ENV SRC_PATH /src

RUN mkdir -p $SRC_PATH

WORKDIR $SRC_PATH

RUN apt-get update \
&& apt-get install -qq -y \
git \
build-essential \
autogen \
autoconf \
libtool \
pkg-config \
python3 \
curl \
sudo \
cmake \
ragel

RUN apt-get update \
&& apt-get -qq -y install \
libboost-all-dev \
libpcre3 \
libpcre3-dbg \
libpcre3-dev \
libpcre2-dev \
libpcap-dev \
libnet1-dev \
libyaml-0-2 \
libyaml-dev \
zlib1g \
zlib1g-dev \
libcap-ng-dev \
libcap-ng0 \
libmagic-dev \
libjansson-dev \
libhiredis-dev \
libluajit-5.1-dev \
liblz4-dev \
libnss3-dev \
libnspr4-dev \
liblzma-dev \
libhyperscan-dev \
libhyperscan5

RUN curl $CURL_OTPS --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | bash -s - -y
ENV PATH "/root/.cargo/bin:$PATH"
RUN cargo install --force cbindgen

RUN git clone https://github.com/OISF/suricata.git
WORKDIR /${SRC_PATH}/suricata/
RUN if [ ! -d "libhtp" ]; then git clone https://github.com/OISF/libhtp.git -b 0.5.x --depth 1; fi
RUN ./autogen.sh 
RUN ./configure \
  --prefix=/opt/suricata \
  --sysconfdir=/etc \
  --disable-gccmarch-native \
  --disable-shared \
  --localstatedir=/var \
  --enable-hiredis \
  --enable-luajit \
  --enable-python

RUN make -j ${BUILD_WORKERS}
RUN make install
RUN make install-conf

FROM jupyter/scipy-notebook:ubuntu-22.04

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
COPY --from=builder-python "${WHEEL_DIST}" "${WHEEL_DIST}"
WORKDIR "${WHEEL_DIST}"
RUN python3 -m pip --no-cache-dir install *.whl --force-reinstall

WORKDIR ${HOME}

USER root

COPY jupyter/scripts/clear_notebooks /usr/local/bin

RUN mkdir -p /home/${NB_USER}/Notebooks
COPY jupyter/Notebooks/*.ipynb /home/${NB_USER}/Notebooks
RUN chown -R ${NB_USER}:${NB_GROUP} /home/${NB_USER}/Notebooks

RUN apt-get update \
  && apt-get -qq -y install \
  libpcre3 \
  libpcre3-dbg \
  libyaml-0-2 \
  zlib1g \
  libcap-ng0 \
  libhyperscan5 \
  libhiredis0.14 \
  libluajit-5.1-2 \
  libmagic1 \
  libpcap0.8 \
  libnet1 \
  libjansson4 \
  libnss3 \
  libevent-pthreads-2.1-7 \
  libevent-2.1-7 \
  && apt-get -y autoremove && apt-get -y autoclean && apt-get clean

COPY --from=builder-suricata /opt/suricata /opt/suricata
COPY --from=builder-suricata /etc/suricata /etc/suricata

RUN chown -R ${NB_USER} /etc/suricata
RUN mkdir -p /var/lib/suricata
RUN mkdir -p /var/log/suricata && chown -R ${NB_USER} /var/log/suricata
RUN mkdir -p /var/lib/suricata && chown -R ${NB_USER} /var/lib/suricata
ENV PATH "/opt/suricata/bin/:$PATH"

USER ${NB_USER}

VOLUME /home/${NB_USER}/Notebooks
VOLUME /var/log/suricata
VOLUME /var/lib/suricata
