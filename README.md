# Suricata Analytics

## Summary

This repository contains various resources that are useful when interacting with Suricata data.

## Content

The repository is organized into directories. Each one contains data for the associated software.

## Jupyter

[Project Jupyter](https://jupyter.org/) provides a interactive data analytics environment. We provide threat hunting and data exploration notebooks which are located under `jupyter/Notebooks`. Those notebooks are designed to interact with [Scirius](https://github.com/StamusNetworks/scirius) REST API endpoints using the `python/surianalytics` data connectors.

### Getting started

#### Docker build

We provide a docker image that encapsulates all dependencies needed by the notebooks. Easiest way to get started is using `docker-compose`. Firstly, use `.env.example` as reference for setting up SELKS / SSP connection variables.

```
cp .env.example .env
```

Edit the `.env` file.

```
# This is the scirius API token you can generate under Account Settings -> Edit Token
SCIRIUS_TOKEN=<TOKEN VALUE>
# This points to SELKS / Scirius / SSP manager instance
SCIRIUS_HOST=<IP or Hostname>
# Set to "no" if your SELKS / Scirius / SSP manager uses self-signed HTTPS certificate
SCIRIUS_TLS_VERIFY=yes
```

Build the docker image.

```
docker-compose build
```

Execute the docker image.

```
docker-compose up
```

Copy the jupyter connection string from container log messages and paste into your chosen web browser. Connection string should look like `http://127.0.0.1:8888/lab?token=<GENERATED TOKEN>`.
