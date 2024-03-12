import logging
from enum import Enum
from sys import exit

import typer

from tomodo import ProvisionerConfig, Provisioner, Reader
from tomodo.common.errors import TomodoError
from tomodo.common.util import check_docker

cli = typer.Typer(no_args_is_help=True, help="Provision a MongoDB deployment")
logger = logging.getLogger("rich")


class Replicas(str, Enum):
    ONE = 1
    THREE = 3
    FIVE = 5
    SEVEN = 7


class AtlasVersion(str, Enum):
    SIX_OH = "6.0"
    SEVEN_OH = "7.0"


def _name() -> str:
    return typer.Option(
        default=None,
        help="The deployment's name; auto-generated if not provided"
    )


def _port() -> int:
    return typer.Option(
        default=27017,
        min=0,
        max=65535,
        help="The deployment's start port"
    )


def _network_name() -> str:
    return typer.Option(
        default="mongo_network",
        help="The Docker network to provision the deployment in; will create a new one or use an existing one "
             "with the same name if such network exists"
    )


def _image_repo(default: str = "mongo") -> str:
    return typer.Option(
        default=default,
        help="The MongoDB image name/repo (NOTE: you probably don't want to change it)"
    )


def _image_tag() -> str:
    return typer.Option(
        default="latest",
        help="The MongoDB image tag, which determines the MongoDB version to install"
    )


def _provision(config: ProvisionerConfig) -> None:
    provisioner = Provisioner(config=config)
    try:
        provisioner.provision(deployment_getter=Reader().get_deployment_by_name)
    except TomodoError as e:
        logger.error(str(e))
        exit(1)
    except Exception as e:
        logger.exception("Could not provision your deployment - an error has occurred")
        exit(1)


@cli.command(
    help="Provision a standalone MongoDB deployment"
)
def standalone(
        name: str = _name(),
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
        image_repo: str = _image_repo(),
        image_tag: str = _image_tag(),
        port: int = _port(),
        network_name: str = _network_name()

):
    check_docker()
    config = ProvisionerConfig(
        standalone=True, name=name, port=port,
        auth=auth, username=username, password=password, auth_db=auth_db,
        auth_roles=auth_roles.split(" "), image_repo=image_repo, image_tag=image_tag,
        network_name=network_name
    )
    _provision(config=config)


@cli.command(
    help="Provision a MongoDB replica set deployment"
)
def replica_set(
        replicas: Replicas = typer.Option(
            default=Replicas.THREE.value,
            help="The number of replica set nodes to provision"
        ),
        arbiter: bool = typer.Option(
            default=False,
            help="Add an arbiter node to a replica set"
        ),
        name: str = _name(),
        priority: bool = typer.Option(
            default=False,
            help="Priority (currently ignored)"
        ),
        port: int = _port(),
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
        image_repo: str = _image_repo(),
        image_tag: str = _image_tag(),
        network_name: str = _network_name()
):
    check_docker()
    config = ProvisionerConfig(
        replica_set=True, replicas=int(replicas.value),
        arbiter=arbiter, name=name, priority=priority, port=port,
        auth=auth, username=username, password=password, auth_db=auth_db,
        auth_roles=auth_roles.split(" "), image_repo=image_repo, image_tag=image_tag,
        network_name=network_name
    )
    _provision(config=config)


@cli.command(
    help="Provision a MongoDB sharded cluster"
)
def sharded(
        replicas: Replicas = typer.Option(
            default=Replicas.THREE.value,
            help="The number of replica set nodes to provision"
        ),
        shards: int = typer.Option(
            default=2,
            help="The number of shards to provision in a sharded cluster"
        ),
        arbiter: bool = typer.Option(
            default=False,
            help="Add an arbiter node to a replica set"
        ),
        name: str = _name(),
        priority: bool = typer.Option(
            default=False,
            help="Priority (currently ignored)"
        ),
        port: int = _port(),
        config_servers: int = typer.Option(
            default=1,
            help="The number of config server replica set nodes"
        ),
        mongos: int = typer.Option(
            default=1,
            min=1,
            help="The number of mongos routers"
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
        image_repo: str = _image_repo(),
        image_tag: str = _image_tag(),
        network_name: str = _network_name()
):
    check_docker()
    config = ProvisionerConfig(
        replicas=int(replicas.value), shards=shards,
        arbiter=arbiter, name=name, priority=priority,
        sharded=True, port=port, config_servers=config_servers, mongos=mongos,
        auth=auth, username=username, password=password, auth_db=auth_db,
        auth_roles=auth_roles.split(" "), image_repo=image_repo, image_tag=image_tag,
        network_name=network_name
    )
    _provision(config=config)


@cli.command(
    help="Provision a local MongoDB Atlas deployment"
)
def atlas(
        name: str = _name(),
        port: int = _port(),
        username: str = typer.Option(
            help="Authentication username",
            default="admin"
        ),
        password: str = typer.Option(
            help="Authentication password",
            default="admin"
        ),
        version: AtlasVersion = typer.Option(
            default=AtlasVersion.SEVEN_OH.value,
            help="The MongoDB version to install"
        ),
        image_repo: str = typer.Option(
            default="ghcr.io/yuviherziger/tomodo",
            help="The MongoDB Atlas image name/repo (NOTE: you probably don't want to change it)"
        ),
        image_tag: str = typer.Option(
            default="main",
            help="The MongoDB Atlas image tag (NOTE: you probably don't want to change it)"
        ),
        network_name: str = _network_name()
):
    check_docker()
    config = ProvisionerConfig(
        name=name, atlas=True, port=port,
        username=username, password=password,
        image_repo=image_repo, image_tag=image_tag,
        network_name=network_name, atlas_version=str(version.value)
    )
    _provision(config=config)
