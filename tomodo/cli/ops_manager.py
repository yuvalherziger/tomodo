import logging

import typer
from typing_extensions import Annotated

from tomodo import ProvisionerConfig
from tomodo.common.ops_manager import OpsManagerProvisioner

cli = typer.Typer(no_args_is_help=True, help="Manager MongoDB Ops Manager deployments")
logger = logging.getLogger("rich")


@cli.command(
    help="Provision an Ops Manager instance"
)
def create(
        name: str = typer.Option(
            default=None,
            help="The deployment's name; auto-generated if not provided"
        ),
        replicate_app_db: bool = typer.Option(
            default=False,
            help="Whether or not to use a replica set for Ops Manager's App DB"
        )
):
    provisioner = OpsManagerProvisioner(config=ProvisionerConfig())
    logger.info("Creating a new Ops Manager instance")


@cli.command(
    help="Add a server to Ops Manager. This server can then be used in Ops Manager to deploy MongoDB instances."
)
def add_server(
        ops_manager_name: str = typer.Argument(
            help="The Ops Manager deployment name. tomodo will add it to the same Docker network."
        ),
        name: str = typer.Option(
            help="The node's name (auto-generated if not provided)",
            default=None
        ),
        port: bool = typer.Option(
            default=27017,
            help="The port that the server should expose. If another container is already listening and exposing "
                 "this port, the action will fail."
        )
):
    pass


@cli.command(
    help="Remove the Ops Manager instance and any servers associated with it."
)
def remove(
        name: str = typer.Argument(
            help="Ops Manager name"
        ),
        auto_confirm: bool = typer.Option(
            default=False,
            help="Don't prompt for confirmation"
        )
):
    pass
