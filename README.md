![Unit Tests](https://github.com/yuviherziger/tomodo/actions/workflows/unit-tests.yml/badge.svg)
# tomodo
<div align="center">
  <img height="250px" src="tomodo-nopg.png" alt="tomodo logo"></img>
</div>

**tomodo** is a **To**olbox for **Mo**ngoDB on **Do**cker.

Use it to create and manage MongoDB community deployments - standalone instances, replica sets,
and sharded clusters.

## Installation

### Install with Homebrew

[Homebrew](https://brew.sh/) is a popular package manager for MacOS.  You can install tomodo by
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

If you wish to set up a development environment, or if you simply can't use Homebrew or aren't a MacOS user,
you can install tomodo using Python. The recommended way to perform the Python installation is by using the
[Poetry](https://python-poetry.org/) Python package manager.  However, it's also possible to install tomodo and
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

## How to use tomodo

### Create a Deployment

