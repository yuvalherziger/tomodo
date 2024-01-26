import logging
from enum import Enum
from sys import exit

import docker
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from unique_names_generator import get_random_name
from unique_names_generator.data import ADJECTIVES, ANIMALS

from tomodo.common import TOMODO_VERSION
from tomodo.common.cleaner import Cleaner
from tomodo.common.config import ProvisionerConfig
from tomodo.common.errors import EmptyDeployment
from tomodo.common.provisioner import Provisioner
from tomodo.common.reader import Reader
from tomodo.common.starter import Starter
from tomodo.common.util import AnonymizingFilter, is_docker_running

console = Console()

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
    name = name or get_random_name(combo=[ADJECTIVES, ANIMALS], separator="-", style="lowercase")
    if sum([standalone, replica_set, sharded]) != 1:
        logger.error("Exactly one of the following has to be specified: --standalone, --replica-set, or --sharded")
        exit(1)
    config = ProvisionerConfig(
        standalone=standalone, replica_set=replica_set, replicas=replicas, shards=shards,
        arbiter=arbiter, name=name, priority=priority,
        sharded=sharded, port=port, config_servers=config_servers, mongos=mongos,
        auth=auth, username=username, password=password, auth_db=auth_db,
        auth_roles=auth_roles.split(" "), image_repo=image_repo, image_tag=image_tag,
        network_name=network_name
    )
    provisioner = Provisioner(config=config)
    provisioner.provision()


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
            help="Exclude stopped deployments (if '--name' not provided)"
        ),
):
    check_docker()
    reader = Reader()

    if name:
        try:
            markdown = Markdown(reader.describe_by_name(name, include_stopped=True))
            console.print(markdown)
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
    else:
        for description in reader.describe_all(include_stopped=exclude_stopped):
            markdown = Markdown(description)
            console.print(markdown)


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
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
    else:
        if auto_confirm is True:
            cleaner.stop_all_deployments()
        else:
            if typer.confirm(f"Stop all deployments?"):
                cleaner.stop_all_deployments()
            else:
                raise typer.Abort()


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
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
    else:
        if auto_confirm is True:
            cleaner.delete_all_deployments()
        else:
            if typer.confirm(f"Delete all deployments?"):
                cleaner.delete_all_deployments()
            else:
                raise typer.Abort()


@cli.command(
    help="List deployments",
    no_args_is_help=False,
    name="list")
def list_(
        exclude_stopped: bool = typer.Option(
            default=False,
            help="Exclude stopped deployments"
        ),
):
    check_docker()
    reader = Reader()
    markdown = Markdown(reader.list_all())
    console.print(markdown)


def run():
    cli()


if __name__ == "__main__":
    run()
