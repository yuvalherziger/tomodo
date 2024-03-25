import logging
import os
import platform
import secrets
from shutil import rmtree
from typing import Union, Tuple

import docker
from docker.models.containers import Container
from docker.types import Mount, NetworkingConfig, EndpointConfig

from tomodo.common.errors import DeploymentNotFound, BlueprintDeploymentNotFound
from tomodo.common.models import AtlasDeployment, Mongod, ShardedCluster, ReplicaSet
from tomodo.common.reader import AnyDeployment, Reader

TEMPLATES_FOLDER = "/var/tmp/tomodo/templates"

logger = logging.getLogger("rich")


class DataMigrator:

    def __init__(self, reader: Reader = None):
        self.reader = reader or Reader()
        self.docker_client = docker.from_env()

    def create_instance_snapshot(self, deployment_name: str) -> None:
        deployment, container, port = self._parse_deployment(deployment_name=deployment_name)
        host_path = self._dump(deployment=deployment, container=container, port=port)
        logger.info("Database dump for '%s' can be found here: %s", deployment.name, host_path)

    def restore_from_snapshot(self, source_deployment_name: str, target_deployment_name: str) -> None:
        deployment, container, port = self._parse_deployment(deployment_name=target_deployment_name)
        host_path = os.path.join(TEMPLATES_FOLDER, source_deployment_name)
        if os.path.exists(host_path):
            logger.info("Restoring data from an existing snapshot")
        else:
            self.create_instance_snapshot(deployment_name=source_deployment_name)
        self._restore(deployment=deployment, container=container, port=port, host_path=host_path)
        logger.info("Data copied successfully into '%s'", deployment.name)

    def validate_snapshot_source(self, source_deployment_name: str, force: bool = False):
        host_path = os.path.join(TEMPLATES_FOLDER, source_deployment_name)
        if os.path.exists(host_path) and not force:
            return
        else:
            try:
                self.reader.get_deployment_by_name(name=source_deployment_name, include_stopped=False)
            except DeploymentNotFound:
                raise BlueprintDeploymentNotFound(deployment_name=source_deployment_name)

    def _parse_deployment(self, deployment_name: str) -> Tuple[AnyDeployment, Container, int]:
        deployment: AnyDeployment = self.reader.get_deployment_by_name(name=deployment_name)
        container: Container
        port: int
        if isinstance(deployment, AtlasDeployment):
            container = deployment.container
            port = deployment.port
        if isinstance(deployment, Mongod):
            container = deployment.container
            port = deployment.port
        elif isinstance(deployment, ReplicaSet):
            container = deployment.members[0].container
            port = deployment.members[0].port
        elif isinstance(deployment, ShardedCluster):
            container = deployment.routers[0].container
            port = deployment.routers[0].port
        else:
            raise Exception
        return deployment, container, port

    def _restore(self, deployment: AnyDeployment, container: Container, port: int, host_path: str) -> str:
        migrator_name = f"migrator-{secrets.token_hex(8)}"
        template_dir_name = deployment.name
        container_path = f"/{template_dir_name}"
        mounts = [Mount(
            target=container_path, source=host_path, type="bind"
        )]
        container_info = container.attrs
        networks = container_info["NetworkSettings"]["Networks"]
        network_id: Union[str, None] = None
        network_name: Union[str, None] = None
        for network_name, network_details in networks.items():
            network_id = network_details["NetworkID"]
            network_name = network_name
            break
        if not network_id:
            raise Exception("No network found")
        networking_config = NetworkingConfig(
            endpoints_config={
                network_name: EndpointConfig(version="1.43", aliases=[migrator_name])
            }
        )
        command = ["mongorestore",
                   "--uri", f"mongodb://{container.name}:{port}",
                   "--dir", os.path.join(container_path, "dump")]
        logger.info("Now copying data from '%s'", host_path)
        self.docker_client.containers.run(
            "mongo:latest",
            detach=False,
            remove=False,
            platform=f"linux/{platform.machine()}",
            network=network_id,
            hostname=migrator_name,
            name=migrator_name,
            command=command,
            mounts=mounts,
            networking_config=networking_config,
            environment=[],
        )
        return host_path

    def _dump(self, deployment: AnyDeployment, container: Container, port: int) -> str:
        migrator_name = f"migrator-{secrets.token_hex(8)}"
        template_dir_name = deployment.name
        data_dir_path = os.path.join(TEMPLATES_FOLDER, template_dir_name)

        if os.path.exists(data_dir_path):
            logger.info("An existing dump was found - removing it")
            rmtree(data_dir_path)

        os.makedirs(data_dir_path, exist_ok=True)
        host_path = os.path.abspath(data_dir_path)
        container_path = f"/{template_dir_name}"
        mounts = [Mount(
            target=container_path, source=host_path, type="bind"
        )]
        container_info = container.attrs
        networks = container_info["NetworkSettings"]["Networks"]
        network_id: Union[str, None] = None
        network_name: Union[str, None] = None
        for network_name, network_details in networks.items():
            network_id = network_details["NetworkID"]
            network_name = network_name
            break
        if not network_id:
            raise Exception("No network found")
        networking_config = NetworkingConfig(
            endpoints_config={
                network_name: EndpointConfig(version="1.43", aliases=[migrator_name])
            }
        )
        command = ["mongodump",
                   "--uri", f"mongodb://{container.name}:{port}",
                   "--out", os.path.join(container_path, "dump")]
        logger.info("Now dumping '%s'", deployment.name)
        self.docker_client.containers.run(
            "mongo:latest",
            detach=False,
            remove=True,
            platform=f"linux/{platform.machine()}",
            network=network_id,
            hostname=migrator_name,
            name=migrator_name,
            command=command,
            mounts=mounts,
            networking_config=networking_config,
            environment=[],
        )

        return host_path
