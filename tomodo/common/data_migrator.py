import os
import platform
import secrets
from typing import Union

import docker
from docker.models.containers import Container
from docker.types import Mount

from tomodo.common.errors import OperationNotSupportForDeploymentType
from tomodo.common.models import AtlasDeployment, Mongod, ShardedCluster, ReplicaSet
from tomodo.common.reader import AnyDeployment, Reader

TEMPLATES_FOLDER = "/var/tmp/tomodo/templates"


class DataMigrator:

    def __init__(self, reader: Reader = None):
        self.reader = reader or Reader()
        self.docker_client = docker.from_env()

    def create_instance_snapshot(self, deployment_name):
        deployment: AnyDeployment = self.reader.get_deployment_by_name(name=deployment_name)
        container: Container
        if isinstance(deployment, AtlasDeployment):
            raise OperationNotSupportForDeploymentType(deployment_type="Atlas")
        if isinstance(deployment, Mongod):
            container = deployment.container
        elif isinstance(deployment, ReplicaSet):
            container = deployment.members[0].container
        elif isinstance(deployment, ShardedCluster):
            container = deployment.routers[0].container

    def _run_migration(self, deployment: AnyDeployment, container: Container):
        migrator_name = f"migrator-{secrets.token_hex(8)}"
        template_dir_name = f"dump/{deployment.name}"
        data_dir_path = os.path.join(TEMPLATES_FOLDER, template_dir_name)
        os.makedirs(data_dir_path, exist_ok=True)
        host_path = os.path.abspath(data_dir_path)
        container_path = f"/{template_dir_name}"
        mounts = [Mount(
            target=container_path, source=host_path, type="bind"
        )]
        container_info = container.attrs
        networks = container_info["NetworkSettings"]["Networks"]
        network_id: Union[str, None] = None
        for network_name, network_details in networks.items():
            network_id = network_details["NetworkID"]
            break
        if not network_id:
            raise Exception("No network found")
        return self.docker_client.containers.run(
            "mongo:7.0",
            detach=True,
            platform=f"linux/{platform.machine()}",
            network=network_id,
            hostname=migrator_name,
            name=migrator_name,
            command=command,
            mounts=mounts,
            networking_config=networking_config,
            environment=environment,
            labels={
                "source": "tomodo",
                "tomodo-name": name,
                "tomodo-group": self.config.name,
                "tomodo-port": str(port),
                "tomodo-role": "cfg-svr" if config_svr else "rs-member" if replset_name else "standalone",
                "tomodo-type": deployment_type,
                "tomodo-data-dir": host_path,
                "tomodo-container-data-dir": container_path,
                "tomodo-shard-id": str(shard_id),
                "tomodo-shard-count": str(self.config.shards or 0),
                "tomodo-arbiter": str(int(arbiter))
            }
        ), host_path, container_path