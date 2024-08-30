import logging

import typer

from tomodo import OpsManagerConfig, ProvisionerConfig
from tomodo.common.config import OpsManagerServerConfig, AgentConfig
from tomodo.common.errors import TomodoError
from tomodo.common.om_provisioner import OpsManagerProvisioner
from tomodo.common.om_server_provisioner import OpsManagerServerProvisioner
from tomodo.common.util import check_docker

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
        port: int = typer.Option(
            default=8080,
            help="The port that Ops Manager server should expose"
        ),
        app_db_port: int = typer.Option(
            default=20000,
            help="The port that App DB server should expose"
        ),
        replicate_app_db: bool = typer.Option(
            default=False,
            help="Whether or not to use a replica set for Ops Manager's App DB"
        )
):
    check_docker()
    app_db_config = {
        "replica_set": replicate_app_db,
        "standalone": not replicate_app_db,
        "port": app_db_port
    }
    provisioner = OpsManagerProvisioner(
        config=OpsManagerConfig(
            app_db_config=ProvisionerConfig(**app_db_config),
            port=port,
            name=name
        )
    )
    logger.info("Creating a new Ops Manager instance")
    try:
        provisioner.create()
    except TomodoError as e:
        logger.error(str(e))
        exit(1)


@cli.command(
    help="Add one of more servers to Ops Manager. "
         "These servers can then be used in Ops Manager to deploy MongoDB instances."
)
def add_server(
        ops_manager_name: str = typer.Argument(
            help="The Ops Manager deployment name. tomodo will add it to the same Docker network."
        ),
        name: str = typer.Option(
            help="The node's name (auto-generated if not provided)",
            default=None
        ),
        port: int = typer.Option(
            default=27017,
            help="The port that the server should expose. If another container is already listening and exposing "
                 "this port, the action will fail."
        ),
        count: int = typer.Option(
            default=1,
            help="The number of servers to provision."
        ),
        project_id: str = typer.Option(
            min=24,
            max=24,
            help="The Ops Manager project ID"
        ),
        api_key: str = typer.Option(
            min=56,
            max=56,
            help="The Ops Manager Agent API key "
                 "(see https://www.mongodb.com/docs/ops-manager/current/tutorial/manage-agent-api-key)"
        ),
):
    check_docker()
    provisioner = OpsManagerServerProvisioner(config=OpsManagerServerConfig(
        agent_config=AgentConfig(
            project_id=project_id,
            api_key=api_key,
            om_name=ops_manager_name
        ),
        name=name,
        port=port,
        count=count
    ))
    try:
        provisioner.create()
    except TomodoError as e:
        logger.error(str(e))
        exit(1)
