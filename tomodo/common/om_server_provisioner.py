import logging
import platform
from typing import Union

from docker.models.containers import Container
from docker.models.networks import Network
from docker.types import NetworkingConfig, EndpointConfig
from rich.console import Console
from rich.markdown import Markdown

from tomodo import Provisioner, Reader
from tomodo.common.config import OpsManagerServerConfig, ProvisionerConfig
from tomodo.common.errors import PortsTakenException
from tomodo.common.models import ReplicaSet, Mongod, OpsManagerInstance
from tomodo.common.util import is_port_range_available

DOCKER_ENDPOINT_CONFIG_VER = "1.43"

console = Console()
logger = logging.getLogger("rich")
# TODO: Switch over when done debugging locally
OM_SERVER_REPO = "ghcr.io/yuvalherziger/tomodo-om-server"
OM_SERVER_TAG = "main"

READINESS_MAX_ATTEMPTS = 60
READINESS_DELAY = 1


# TODO: implement OM reader
class OpsManagerServerProvisioner(Provisioner):
    def __init__(self, config: OpsManagerServerConfig):
        super().__init__(config=ProvisionerConfig())
        self.server_config = config
        self.network = self.get_network()

    def create_server_container(self, port: int, group_name: str, name: str, om: OpsManagerInstance, network: Network) -> Container:
        environment = [
            f"OM_URL={om.network_url}",
            f"PROJECT_ID={self.server_config.agent_config.project_id}",
            f"API_KEY={self.server_config.agent_config.api_key}",
        ]
        networking_config = NetworkingConfig(
            endpoints_config={
                om.network_name: EndpointConfig(version=DOCKER_ENDPOINT_CONFIG_VER, aliases=[self.server_config.name])
            }
        )
        return self.docker_client.containers.run(
            f"{OM_SERVER_REPO}:{OM_SERVER_TAG}",
            detach=True,
            ports={f"{port}/tcp": port},
            platform=f"linux/{platform.machine()}",
            network=network.id,
            hostname=name,
            name=name,
            networking_config=networking_config,
            environment=environment,
            labels={
                "source": "tomodo",
                "tomodo-name": name,
                "tomodo-group": group_name,
                "tomodo-group-size": str(self.server_config.count),
                "tomodo-parent": self.server_config.agent_config.om_name,
                "tomodo-port": str(port),
                "tomodo-start-port": str(self.server_config.port),
                "tomodo-role": "ops-manager-deployment-server",
                "tomodo-type": "ops-manager-deployment-server"
            }
        )

    def create_app_db(self) -> Union[ReplicaSet, Mongod]:
        logger.info("Creating Ops Manager's App DB")
        app_db = self.provision(deployment_getter=Reader().get_deployment_by_name, print_summary=False)
        return app_db

    def create(self) -> None:
        start_port = self.server_config.port
        servers = self.server_config.count
        if not is_port_range_available(tuple(range(start_port, start_port + servers))):
            raise PortsTakenException
        self.check_and_pull_image(image_name=f"{OM_SERVER_REPO}:{OM_SERVER_TAG}")
        om_name = self.server_config.agent_config.om_name
        om: OpsManagerInstance = Reader().get_deployment_by_name(om_name, get_group=False)
        network = self.get_network(om.network_name)
        logger.info("Creating %s for deployments through '%s' Ops Manager instance",
                    "1 server" if servers == 1 else f"{servers} servers", om_name)
        for port in range(start_port, start_port + servers):
            name = f"{self.server_config.name}-{port - start_port}"
            logger.info("Creating server '%s', exposing port %d", name, port)
            self.create_server_container(
                port=port,
                group_name=self.server_config.name,
                name=name,
                om=om,
                network=network
            )
            logger.info("Server '%s:%d' created", name, port)

    def print_ops_manager_summary(self):
        markdown = Markdown(f"""
-------------------------
Your servers are ready!

 Server ''
-------------------------
""", justify="full")

        console.print(markdown)
