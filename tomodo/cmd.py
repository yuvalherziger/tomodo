import io
import logging
from enum import Enum
from sys import exit
from typing import Dict

import docker
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.syntax import Syntax
from ruamel.yaml import YAML

from tomodo.common import TOMODO_VERSION
from tomodo.common.cleaner import Cleaner
from tomodo.common.config import ProvisionerConfig
from tomodo.common.errors import EmptyDeployment
from tomodo.common.models import Deployment
from tomodo.common.provisioner import Provisioner
from tomodo.common.reader import Reader
from tomodo.common.starter import Starter
from tomodo.common.util import AnonymizingFilter, is_docker_running

console = Console()
yaml = YAML()

cli = typer.Typer(no_args_is_help=True)

log_handler = RichHandler(show_path=False)
log_handler.addFilter(AnonymizingFilter())

logging.basicConfig(
    level=logging.INFO, format="%(message)s", datefmt="%Y-%m-%dT%H:%M:%S.%f %z", handlers=[log_handler]
)

logger = logging.getLogger("rich")


class LogLevel(str, Enum):
    INFO = "INFO"
    DEBUG = "DEBUG"


class OutputFormat(str, Enum):
    JSON = "json"
    TABLE = "table"
    YAML = "yaml"


def check_docker():
    if not is_docker_running():
        logger.error("The Docker daemon isn't running")
        exit(1)


@cli.command(help="Print tomodo's version")
def version():
    docker_ver = docker.from_env().version()
    console.print_json(data={
        "tomodo_version": TOMODO_VERSION,
        "docker_version": {
            "engine": docker_ver.get("Version"),
            "platform": docker_ver.get("Platform", {}).get("Name")
        }
    })


@cli.command(
    help="Provision a MongoDB deployment",
    no_args_is_help=True)
def provision(
        standalone: bool = typer.Option(
            default=False,
            help="Provision a MongoDB standalone instance"
        ),
        replica_set: bool = typer.Option(
            default=False,
            help="Provision a MongoDB replica set"
        ),
        sharded: bool = typer.Option(
            default=False,
            help="Provision a MongoDB sharded cluster"
        ),
        replicas: int = typer.Option(
            default=3,
            help="The number of replica set nodes to provision"
        ),
        shards: int = typer.Option(
            default=2,
            help="The number of shards to provision in a sharded cluster"
        ),
        arbiter: bool = typer.Option(
            default=False,
            help="Arbiter node (currently ignored)"
        ),
        name: str = typer.Option(
            default=None,
            help="The deployment's name; auto-generated if not provided"
        ),
        priority: bool = typer.Option(
            default=False,
            help="Priority (currently ignored)"
        ),
        port: int = typer.Option(
            default=27017,
            min=0,
            max=65535,
            help="The deployment's start port"
        ),
        config_servers: int = typer.Option(
            default=1,
            help="The number of config server replica set nodes"
        ),
        mongos: int = typer.Option(
            default=1,
            help="The number of mongos routers (currently ignored)"
        ),
        auth: bool = typer.Option(
            default=False,
            help="Whether to enable authentication (currently ignored)"
        ),
        username: str = typer.Option(
            default=None,
            help="Optional authentication username"
        ),
        password: str = typer.Option(
            default=None,
            help="Optional authentication password"
        ),
        auth_db: str = typer.Option(
            default=None,
            help="Authorization DB (currently ignored)"
        ),
        auth_roles: str = typer.Option(
            default="dbAdminAnyDatabase readWriteAnyDatabase userAdminAnyDatabase clusterAdmin",
            help="Default authentication roles (currently ignored)"
        ),
        image_repo: str = typer.Option(
            default="mongo",
            help=""
        ),
        image_tag: str = typer.Option(
            default="latest",
            help="The MongoDB image tag, which determines the MongoDB version to install"
        ),
        network_name: str = typer.Option(
            default="mongo_network",
            help="The Docker network to provision the deployment in; will create a new one or use an existing one "
                 "with the same name if such network exists"
        )
):
    check_docker()
    config = ProvisionerConfig(
        standalone=standalone, replica_set=replica_set, replicas=replicas, shards=shards,
        arbiter=arbiter, name=name, priority=priority,
        sharded=sharded, port=port, config_servers=config_servers, mongos=mongos,
        auth=auth, username=username, password=password, auth_db=auth_db,
        auth_roles=auth_roles.split(" "), image_repo=image_repo, image_tag=image_tag,
        network_name=network_name
    )
    provisioner = Provisioner(config=config)
    try:
        provisioner.provision()
    except Exception as e:
        logger.exception("Could not provision your deployment - an error has occurred")
        exit(1)


@cli.command(
    help="Describe running deployments",
    no_args_is_help=False)
def describe(
        name: str = typer.Option(
            default=None,
            help="Deployment name (optional). Prints all tomodo deployments if not specified"
        ),
        exclude_stopped: bool = typer.Option(
            default=False,
            help="Exclude stopped deployments (if '--name' is not provided)"
        ),
        output: OutputFormat = typer.Option(
            default=OutputFormat.TABLE,
            help="Output format"
        )
):
    check_docker()
    reader = Reader()

    if name:
        try:
            if output == OutputFormat.JSON:
                deployment = reader.get_deployment_by_name(name, include_stopped=True)
                console.print_json(data=deployment.as_dict(detailed=True))
            elif output == OutputFormat.YAML:
                yaml_str = io.StringIO()
                deployment = reader.get_deployment_by_name(name, include_stopped=True)
                yaml.dump(data=deployment.as_dict(detailed=True),
                          stream=yaml_str)
                yaml_syntax = Syntax(yaml_str.getvalue(), "yaml")
                console.print(yaml_syntax)
            else:
                markdown = Markdown(reader.describe_by_name(name, include_stopped=True))
                console.print(markdown)
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
        except Exception as e:
            logger.exception("Could not describe your deployment - an error has occurred")
            exit(1)
    else:
        try:
            if output == OutputFormat.JSON:
                deployments = reader.get_all_deployments(include_stopped=True)
                console.print_json(data={name: deployments[name].as_dict(detailed=True) for name in deployments.keys()})
            elif output == OutputFormat.YAML:
                deployments = reader.get_all_deployments(include_stopped=True)
                yaml_str = io.StringIO()
                yaml.dump(data={name: deployments[name].as_dict(detailed=True) for name in deployments.keys()},
                          stream=yaml_str)
                yaml_syntax = Syntax(yaml_str.getvalue(), "yaml")
                console.print(yaml_syntax)
            else:
                for description in reader.describe_all(include_stopped=exclude_stopped):
                    markdown = Markdown(description)
                    console.print(markdown)
        except Exception as e:
            logger.exception("Could not describe your deployments - an error has occurred")
            exit(1)


@cli.command(
    help="Stop running deployments",
    no_args_is_help=False)
def stop(
        name: str = typer.Option(
            default=None,
            help="Deployment name (optional). Stops all deployments if not specified."
        ),
        auto_confirm: bool = typer.Option(
            default=False,
            help="Don't prompt for confirmation"
        )
):
    check_docker()
    cleaner = Cleaner()
    if name:
        try:
            if auto_confirm is True:
                cleaner.stop_deployment(name)
            else:
                if typer.confirm(f"Stop deployment '{name}'?"):
                    cleaner.stop_deployment(name)
                else:
                    raise typer.Abort()
        except typer.Abort:
            pass
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
        except Exception as e:
            logger.exception("Could not stop your deployment - an error has occurred")
            exit(1)
    else:
        try:
            if auto_confirm is True:
                cleaner.stop_all_deployments()
            else:
                if typer.confirm(f"Stop all deployments?"):
                    cleaner.stop_all_deployments()
                else:
                    raise typer.Abort()
        except typer.Abort:
            pass
        except Exception as e:
            logger.exception("Could not stop your deployments - an error has occurred")
            exit(1)


@cli.command(
    help="Start a non-running deployment",
    no_args_is_help=False)
def start(
        name: str = typer.Option(
            help="Deployment name."
        ),
):
    check_docker()
    starter = Starter()
    if name:
        try:
            starter.start_deployment(name)
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
    else:
        raise NotImplementedError


@cli.command(
    help="Remove running deployments permanently",
    no_args_is_help=False)
def remove(
        name: str = typer.Option(
            default=None,
            help="Deployment name (optional). Removes all deployments if not specified."
        ),
        auto_confirm: bool = typer.Option(
            default=False,
            help="Don't prompt for confirmation"
        )
):
    check_docker()
    cleaner = Cleaner()
    if name:
        try:
            if auto_confirm is True:
                cleaner.delete_deployment(name)
            else:
                if typer.confirm(f"Delete deployment '{name}'?"):
                    cleaner.delete_deployment(name)
                else:
                    raise typer.Abort()
        except typer.Abort:
            pass
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
        except Exception as e:
            logger.exception("Could not remove your deployment - an error has occurred")
            exit(1)
    else:
        try:
            if auto_confirm is True:
                cleaner.delete_all_deployments()
            else:
                if typer.confirm(f"Delete all deployments?"):
                    cleaner.delete_all_deployments()
                else:
                    raise typer.Abort()
        except typer.Abort:
            pass
        except Exception as e:
            logger.exception("Could not remove your deployments - an error has occurred")
            exit(1)


@cli.command(
    help="List deployments",
    no_args_is_help=False,
    name="list")
def list_(
        exclude_stopped: bool = typer.Option(
            default=False,
            help="Exclude stopped deployments",
        ),
        output: OutputFormat = typer.Option(
            default=OutputFormat.TABLE,
            help="Output format"
        )
):
    check_docker()
    reader = Reader()
    try:
        deployments: Dict[str, Deployment] = reader.get_all_deployments(include_stopped=not exclude_stopped)
        if output == OutputFormat.JSON:
            console.print_json(data={name: deployments[name].as_dict() for name in deployments.keys()})
        elif output == OutputFormat.YAML:
            yaml_str = io.StringIO()
            yaml.dump(data={name: deployments[name].as_dict() for name in deployments.keys()},
                      stream=yaml_str)
            yaml_syntax = Syntax(yaml_str.getvalue(), "yaml")
            console.print(yaml_syntax)
        else:
            markdown = Markdown(
                reader.list_deployments_in_markdown_table(deployments, include_stopped=not exclude_stopped),
            )
            console.print(markdown)
    except Exception as e:
        logger.exception("Could not list your deployments - an error has occurred")
        exit(1)


def run():
    cli()


if __name__ == "__main__":
    run()
