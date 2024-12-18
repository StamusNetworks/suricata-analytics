# Suricata Analytics

## Summary

This repository contains various resources that are useful when interacting with Suricata data.

## Jupyter

[Project Jupyter](https://jupyter.org/) provides a interactive data analytics environment. We provide threat hunting and data exploration notebooks which are located under `jupyter/Notebooks`. Those notebooks are designed to interact with [Scirius](https://github.com/StamusNetworks/scirius) REST API endpoints using the `python/surianalytics` data connectors.

## Getting started

### Connection prep

Firstly, set up authentication parameters for connecting to SCS or ClearNDR.

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

More detailed info about generating the token can be found in [embedded blog post](jupyter/Notebooks/blogs/playbook-scirius/JupyterPlaybooksForScirius.ipynb)

### Setting up the python helper

We provide a python library that implements data connector, widgets and various helpers. A clean python virtual environment is recommended.

```
python -m .venv venv
source .venv/bin/activate
pip install .
```

This will set up helper along with most dependencies that we use in notebooks. It does not install jupyter notebooks or jupyterlab itself. Installing it's basically just a tool for interacting with our data connector and not a hard requirement. In other words, embedded lib can be used regardless of editor. But we provide a simple requirements file for env setup.

```
pip install -r requirements.txt
```
