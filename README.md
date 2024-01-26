![Unit Tests](https://github.com/yuviherziger/tomodo/actions/workflows/unit-tests.yml/badge.svg)
# tomodo
<div align="center">
  <img height="250px" src="tomodo-nopg.png" alt="tomodo logo"></img>
</div>

**tomodo** is a **To**olbox for **Mo**ngoDB on **Do**cker.

Use it to create and manage MongoDB community deployments - standalone instances, replica sets,
and sharded clusters.

## Installation

**Requirements:**

* Python 3.8 or higher

### Install with Poetry (Recommended)

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

## How to use tomodo

### Create a Deployment

