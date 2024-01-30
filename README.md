<div align="center">
  <img height="250px" src="tomodo-nopg.png" alt="tomodo logo"></img>

![Latest Release](https://img.shields.io/github/v/release/yuviherziger/tomodo?display_name=release&style=flat&color=%2332c955)
![Unit Tests](https://github.com/yuviherziger/tomodo/actions/workflows/unit-tests.yml/badge.svg)
</div>

# tomodo

**tomodo** is a Toolbox for MongoDB on Docker.

-------

Use it to create and manage Docker-based MongoDB community deployments - standalone instances, replica sets,
and sharded clusters.

* [Installation](#installation)
    + [Install with Homebrew](#install-with-homebrew)
    + [Install with Python](#install-with-python)
        - [Install with Poetry Package Manager for Python](#install-with-poetry-package-manager-for-python)
    + [Install with pip](#install-with-pip)
* [CLI Usage](#cli-usage)
    + [Create a Deployment](#create-a-deployment)
    + [Describe Deployments](#describe-deployments)
    + [List Deployments](#list-deployments)
    + [Stop Deployments](#stop-deployments)
    + [Start Deployments](#start-deployments)
    + [Remove Deployments](#remove-deployments)

--- 

## Installation

### Install with Homebrew

[Homebrew](https://brew.sh/) is a popular package manager for macOS. You can install tomodo by
running the following commands:

```shell
brew tap yuviherziger/homebrew-tomodo
brew install tomodo
```

After installing the tool with `brew`, you can run it the following way:

```bash
tomodo --help
```

### Install with Python

If you wish to set up a development environment, or if you simply can't use Homebrew or aren't a macOS user,
you can install tomodo using Python. The recommended way to perform the Python installation is by using the
[Poetry](https://python-poetry.org/) Python package manager. However, it's also possible to install tomodo and
its dependencies with `pip` (see [here](#install-with-pip)).

**Requirements:**

* Python 3.8 or higher

#### Install with Poetry Package Manager for Python

If you have the [Poetry](https://python-poetry.org/) Python package manager installed locally, you can install
the CLI the following way:

```bash
poetry shell
poetry install
```

After installing the tool with Poetry, you can run it the following way:

```bash
tomodo --help
```

### Install with pip

You can install the dependencies with pip using the following command:

```bash
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
tomodo provision --standalone
```

To create a replica set with zero configuration, run the `provision` command in the following way:

```shell
tomodo provision --replica-set
```

To create a sharded cluster with zero configuration, run the `provision` command in the following way:

```shell
tomodo provision --sharded
```

Take a look at the `provision` command's help page to read the full set of options
with `tomodo provision --help`:

```
 Usage: tomodo provision [OPTIONS]

 Provision a MongoDB deployment

╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --standalone        --no-standalone                                  Provision a MongoDB standalone instance [default: no-standalone]                    │
│ --replica-set       --no-replica-set                                 Provision a MongoDB replica set [default: no-replica-set]                           │
│ --sharded           --no-sharded                                     Provision a MongoDB sharded cluster [default: no-sharded]                           │
│ --replicas                              INTEGER                      The number of replica set nodes to provision [default: 3]                           │
│ --shards                                INTEGER                      The number of shards to provision in a sharded cluster [default: 2]                 │
│ --arbiter           --no-arbiter                                     Arbiter node (currently ignored) [default: no-arbiter]                              │
│ --name                                  TEXT                         The deployment's name; auto-generated if not provided [default: None]               │
│ --priority          --no-priority                                    Priority (currently ignored) [default: no-priority]                                 │
│ --port                                  INTEGER RANGE [0<=x<=65535]  The deployment's start port [default: 27017]                                        │
│ --config-servers                        INTEGER                      The number of config server replica set nodes [default: 1]                          │
│ --mongos                                INTEGER                      The number of mongos routers (currently ignored) [default: 1]                       │
│ --auth              --no-auth                                        Whether to enable authentication (currently ignored) [default: no-auth]             │
│ --username                              TEXT                         Optional authentication username [default: None]                                    │
│ --password                              TEXT                         Optional authentication password [default: None]                                    │
│ --auth-db                               TEXT                         Authorization DB (currently ignored) [default: None]                                │
│ --auth-roles                            TEXT                         Default authentication roles (currently ignored)                                    │
│                                                                      [default: dbAdminAnyDatabase readWriteAnyDatabase userAdminAnyDatabase              │
│                                                                      clusterAdmin]                                                                       │
│ --image-repo                            TEXT                         [default: mongo]                                                                    │
│ --image-tag                             TEXT                         The MongoDB image tag, which determines the MongoDB version to install              │
│                                                                      [default: latest]                                                                   │
│ --network-name                          TEXT                         The Docker network to provision the deployment in; will create a new one or use an  │
│                                                                      existing one with the same name if such network exists                              │
│                                                                      [default: mongo_network]                                                            │
│ --help                                                               Show this message and exit.                                                         │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
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

# Describe only running deployments
tomodo list --exclude-stopped
```

### Stop Deployments

Use the `stop` command to stop your deployments:

```shell
# Stop all deployments
tomodo stop

# Stop a deployment by name
tomodo stop --name troubled-narwhal

# Stop a deployment without prompting for confirmation
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

# Remove a deployment without prompting for confirmation
tomodo remove --auto-approve
```
