<div align="center">
  <img height="250px" src="https://github.com/yuvalherziger/tomodo/raw/main/tomodo-nopg.png" alt="tomodo logo"></img>

![Latest Release](https://img.shields.io/github/v/release/yuvalherziger/tomodo?display_name=release&style=flat&color=%2332c955)
![Unit Tests](https://github.com/yuvalherziger/tomodo/actions/workflows/unit-tests.yml/badge.svg)
[![codecov](https://codecov.io/gh/yuvalherziger/tomodo/graph/badge.svg?token=3CE8D8NAAY)](https://codecov.io/gh/yuvalherziger/tomodo)
![Python Version](https://img.shields.io/pypi/pyversions/tomodo)
![License](https://img.shields.io/github/license/yuvalherziger/tomodo)

</div>

# tomodo

**tomodo** is a Toolbox for MongoDB on Docker.

-------

Use it to create and manage Docker-based MongoDB community deployments - standalone instances, replica sets, sharded clusters, and local Atlas deployments.

* [Installation](#installation)
    + [Install with Homebrew](#install-with-homebrew)
    + [Install with pip](#install-with-pip)
    + [Install from Source](#install-from-source)
        - [Install with Poetry Package Manager for Python](#install-with-poetry-package-manager-for-python)
        - [Install from source with pip](#install-from-source-with-pip)
* [CLI Usage](#cli-usage)
    + [Create a Deployment](#create-a-deployment)
    + [Describe Deployments](#describe-deployments)
    + [List Deployments](#list-deployments)
    + [Stop Deployments](#stop-deployments)
    + [Start Deployments](#start-deployments)
    + [Remove Deployments](#remove-deployments)
    + [List Image Tags](#list-tags)
* [Programmatic Usage](#programmatic-usage)
* [Disclaimer](#disclaimer)

--- 

## Installation

### Install with Homebrew

[Homebrew](https://brew.sh/) is a popular package manager for macOS. You can install tomodo by
running the following commands:

```shell
brew tap yuvalherziger/homebrew-tomodo
brew install tomodo
```

After installing the tool with `brew`, you can run it the following way:

```bash
tomodo --help
```

### Install with pip

To install with `pip`, run the following command:

```shell
pip install tomodo
```

### Install from Source

If you wish to set up a development environment, or if you simply can't use Homebrew or aren't a macOS user,
you can install tomodo using Python. The recommended way to perform the Python installation is by using the
[Poetry](https://python-poetry.org/) Python package manager.

**Requirements:**

* Python 3.8 or higher

#### Install with Poetry Package Manager for Python

If you have the [Poetry](https://python-poetry.org/) Python package manager installed locally, you can install
the CLI the following way:

```bash
git clone https://github.com/yuvalherziger/tomodo.git
cd tomodo
poetry shell
poetry install
```

After installing the tool with Poetry, you can run it the following way:

```bash
tomodo --help
```

#### Install from source with pip

You can install the dependencies with pip using the following command:

```bash
git clone https://github.com/yuvalherziger/tomodo.git
cd tomodo
pip install .
```

After installing the dependencies with pip, you can validate the installation by invoking the help page:

```bash
python tomodo/cmd.py --help
```

## CLI Usage

Before you begin, make sure you have a Docker daemon running. The most popular platform
is [Docker Desktop](https://www.docker.com/products/docker-desktop/).

### Create a Deployment

Create a deployment with the `provision` command. For example, here's how you create a standalone
instance with zero configuration:

```shell
tomodo provision standalone
```

To create a replica set with zero configuration, run the following command:

```shell
tomodo provision replica-set
```

To create a sharded cluster with zero configuration, run the following command:

```shell
tomodo provision sharded
```

To create a local Atlas deployment (a single-node replica set) with zero configuration, run the following command:

```shell
tomodo provision atlas
```

Take a look at each `provision` command's help page to read the full set of options
with `tomodo provision --help`.

```
 Usage: tomodo provision [OPTIONS] COMMAND [ARGS]...

 Provision a MongoDB deployment

╭─ Options ──────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                            │
╰────────────────────────────────────────────────────────────────────────╯
╭─ Commands ─────────────────────────────────────────────────────────────╮
│ atlas            Provision a local MongoDB Atlas deployment            │
│ replica-set      Provision a MongoDB replica set deployment            │
│ sharded          Provision a MongoDB sharded cluster                   │
│ standalone       Provision a standalone MongoDB deployment             │
╰────────────────────────────────────────────────────────────────────────╯
```

### Describe Deployments

Use the `describe` command to print the details of one or all deployments:

```shell
# Describe all deployments
tomodo describe

# Describe a deployment by name
tomodo describe --name yawning-mole

# Describe only running deployments
tomodo describe --exclude-stopped
```

### List Deployments

Use the `list` command to list your deployments:

```shell
# List all deployments
tomodo list

# List only running deployments
tomodo list --exclude-stopped
```

### Stop Deployments

Use the `stop` command to stop your deployments:

```shell
# Stop all deployments
tomodo stop

# Stop a deployment by name
tomodo stop --name troubled-narwhal

# Stop all deployments without prompting for confirmation
tomodo stop --auto-approve
```

### Start Deployments

Use the `start` command to start a deployment you previously stopped:

```shell
tomodo start --name printed-lemming
```

### Remove Deployments

Use the `remove` command to permanently remove deployments:

```shell
# Remove all deployments
tomodo remove

# Remove a deployment by name
tomodo remove --name troubled-narwhal

# Remove all deployments without prompting for confirmation
tomodo remove --auto-approve
```

### List Tags

Use the `tags list` command to list the available image tags on Docker Hub.

```shell
tomodo tags list --version 7
```

Sample output:

```
7.0.6
7.0.6-jammy
7.0.6-nanoserver
7.0.6-nanoserver-1809
7.0.6-nanoserver-ltsc2022
7.0.6-windowsservercore
7.0.6-windowsservercore-1809
7.0.6-windowsservercore-ltsc2022
7.0.5
7.0.5-jammy
7.0.5-nanoserver
7.0.5-nanoserver-1809
7.0.5-nanoserver-ltsc2022
7.0.5-windowsservercore
7.0.5-windowsservercore-1809
7.0.5-windowsservercore-ltsc2022
7.0.4
7.0.4-jammy
7.0.4-nanoserver
7.0.4-nanoserver-1809
7.0.4-nanoserver-ltsc2022
7.0.4-windowsservercore
7.0.4-windowsservercore-1809
7.0.4-windowsservercore-ltsc2022
7.0.3
7.0.3-jammy
7.0.3-nanoserver
7.0.3-nanoserver-1809
7.0.3-nanoserver-ltsc2022
7.0.3-windowsservercore
7.0.3-windowsservercore-1809
7.0.3-windowsservercore-ltsc2022
7.0.2
7.0.2-jammy
7.0.2-nanoserver
7.0.2-nanoserver-1809
7.0.2-nanoserver-ltsc2022
7.0.2-windowsservercore
7.0.2-windowsservercore-1809
7.0.2-windowsservercore-ltsc2022
```

## Programmatic Usage

You can install tomodo in your Python (>=3.8) projects using `pip` or any other Python package manager, and use it
programmatically (you'll still need a Docker daemon running).

```python
from typing import Dict

from tomodo import functional as tfunc
from tomodo.common.errors import DeploymentNotFound
from tomodo.common.models import AtlasDeployment, Deployment, Mongod, ReplicaSet, ShardedCluster

# Create a standalone instance:
mongod: Mongod = tfunc.provision_standalone_instance(port=1000)

# Create an Atlas instance:
atlas_depl: AtlasDeployment = tfunc.provision_atlas_instance(port=2000)

# Create a replica set:
replica_set: ReplicaSet = tfunc.provision_replica_set(port=3000, replicas=3)

# Create a sharded cluster:
sh_cluster: ShardedCluster = tfunc.provision_sharded_cluster(port=4000, shards=2, config_servers=3, mongos=2)

# Stop a deployment:
mongod.stop()

# Start a stopped deployment:
mongod.start()

# Remove a deployment permanently:
mongod.remove()

# Find a deployment by name
try:
    deployment = tfunc.get_deployment(name="elegant-leopard", include_stopped=True)
except DeploymentNotFound:
    print("Deployment not found")

# List all deployments:
deployments: Dict = tfunc.list_deployments(include_stopped=True)
for name in deployments.keys():
    deployment: Deployment = deployments[name]
    print(f"Deployment {name} is {deployment.last_known_state}")
```

##  Disclaimer
This software is not supported by MongoDB, Inc. under any of their commercial support subscriptions or otherwise.
Any usage of tomodo is at your own risk. Bug reports, feature requests, and questions can be posted in the
[Issues section](https://github.com/yuvalherziger/tomodo/issues) of this repository.
