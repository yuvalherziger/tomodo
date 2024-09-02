import base64
import logging
import os
import platform
import secrets
from typing import List, Dict

import docker

from docker.errors import ImageNotFound, NotFound
from docker.models.containers import Container
from docker.models.networks import Network
from docker.types import Mount, NetworkingConfig, EndpointConfig

from tomodo import ProvisionerConfig
from tomodo.common.errors import MongoDBImageNotFound
from tomodo.common.models import Mongod
from tomodo.common.util import run_mongo_shell_command, get_os

logger = logging.getLogger("rich")

DOCKER_ENDPOINT_CONFIG_VER = "1.43"


class ProvisionerMixin:

    def __init__(self):
        self.docker_client = docker.from_env()

    # TODO: move to utils:
    def check_and_pull_image(self, image_name: str):
        try:
            self.docker_client.images.get(image_name)
            logger.info("Image '%s' was found locally", image_name)
        except ImageNotFound:
            # If not found, pull the image
            try:
                logger.info("Pulling image '%s' from registry", image_name)
                self.docker_client.images.pull(image_name)
                logger.info("Pulled image '%s' successfully", image_name)
            except NotFound:
                raise MongoDBImageNotFound(image=image_name)
        except Exception:
            raise

    def wait_for_readiness(self, mongod: Mongod, config: ProvisionerConfig):
        logger.debug("Checking the readiness of %s", mongod.name)
        mongo_cmd = "db.runCommand({ping: 1}).ok"

        try:
            exit_code, output, _ = run_mongo_shell_command(mongo_cmd=mongo_cmd, mongod=mongod, config=config)
            is_ready = int(output) == 1
        except Exception as e:
            logger.debug(str(e))
            is_ready = False
        if not is_ready:
            logger.info("Server %s is not ready to accept connections", mongod.name)
            raise Exception("Server isn't ready")
        logger.info("Server %s is ready to accept connections", mongod.name)

    def get_network(self, config: ProvisionerConfig, name: str = None) -> Network:
        name = name or config.network_name
        networks = self.docker_client.networks.list(filters={"name": name})
        if len(networks) > 0:
            network = networks[0]
            logger.info("At least one Docker network exists with the name '%s'. Picking the first one [id: %s]",
                        network.name, network.short_id)
        else:
            network = self.docker_client.networks.create(name=name)
            logger.info("Docker network '%s' was created [id: %s]", name, network.short_id)
        return network

    def _create_docker_container(self, name: str, image: str, labels: Dict, mounts: List[Mount], environment: List[str],
                                 port: int, command: List[str], network: Network) -> Container:
        networking_config = NetworkingConfig(
            endpoints_config={
                network.name: EndpointConfig(version=DOCKER_ENDPOINT_CONFIG_VER, aliases=[name])
            }
        )
        return self.docker_client.containers.run(
            image,
            detach=True,
            ports={f"{port}/tcp": port},
            platform=f"linux/{platform.machine()}",
            network=network.id,
            hostname=name,
            name=name,
            command=command,
            mounts=mounts,
            networking_config=networking_config,
            environment=environment,
            labels=labels
        )

    def create_mongod_container(self, image: str, port: int, name: str, network: Network, replset_name: str = None,
                                config_svr: bool = False, replica_set: bool = False, sharded: bool = False,
                                shard_id: int = 0, arbiter: bool = False, ephemeral: bool = False, username: str = None,
                                password: str = None) -> Container:
        logger.info("Creating container from '%s'. Port %d will be exposed to your host", image, port)
        host_path = ""
        container_path = ""
        mounts = []
        command = [
            "mongod",
            "--bind_ip_all",
            "--port", str(port),
        ]
        home_dir = os.path.expanduser("~")
        if not ephemeral:
            data_dir_name = f".tomodo/data/{name}-db"
            data_dir_path = os.path.join(home_dir, data_dir_name)
            os.makedirs(data_dir_path, exist_ok=True)
            host_path = os.path.abspath(data_dir_path)
            container_path = "/data/db"
            mounts = [Mount(
                target=container_path, source=host_path, type="bind", read_only=False
            )]
            command.extend(["--dbpath", container_path, "--logpath", f"{container_path}/mongod.log"])

        environment = []
        target_keyfile_path = "/etc/mongo/mongo_keyfile" if get_os() == "macOS" else "/data/db/mongo_keyfile"
        if username and password and not sharded:
            environment = [f"MONGO_INITDB_ROOT_USERNAME={username}",
                           f"MONGO_INITDB_ROOT_PASSWORD={password}"]

            keyfile_path = os.path.abspath(os.path.join(home_dir, ".tomodo/mongo_keyfile"))

            if not os.path.isfile(keyfile_path):
                random_bytes = secrets.token_bytes(756)
                base64_bytes = base64.b64encode(random_bytes)
                with open(keyfile_path, "wb") as file:
                    file.write(base64_bytes)
                os.chmod(keyfile_path, 0o400)
            mounts.append(
                Mount(target=target_keyfile_path, source=keyfile_path, type="bind")
            )
            command.extend(["--keyFile", target_keyfile_path])
        deployment_type = "Standalone"
        if config_svr:
            command.extend(["--configsvr", "--replSet", replset_name])
            deployment_type = "Sharded Cluster"
        elif replica_set:
            command.extend(["--replSet", replset_name])
            deployment_type = "Replica Set"
        elif sharded:
            command.extend(["--shardsvr", "--replSet", replset_name])
            deployment_type = "Sharded Cluster"

        labels = {
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
            "tomodo-arbiter": str(int(arbiter)),
            "tomodo-ephemeral": str(int(self.config.ephemeral))
        }

        container = self._create_docker_container(
            name=name, image=image, labels=labels, mounts=mounts,
            environment=environment, port=port, command=command,
            network=network
        )

        return container, host_path, container_path
