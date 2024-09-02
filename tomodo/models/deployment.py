import base64
import logging
import os
import platform
import secrets
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Union

import docker
from docker import DockerClient
from docker.errors import APIError
from docker.models.networks import Network
from docker.models.containers import Container
from docker.types import Mount, NetworkingConfig, EndpointConfig

from tomodo.common.config import ProvisionerConfig
from tomodo.common.errors import InvalidDeploymentType, PortsTakenException
from tomodo.common.util import get_os, is_port_range_available, run_mongo_shell_command, with_retry

logger = logging.getLogger("rich")
DOCKER_ENDPOINT_CONFIG_VER = "1.43"

class Status(Enum):
    STAGED = 0
    CREATED = 10
    RESTARTING = 20
    RUNNING = 30
    REMOVING = 40
    PAUSED = 50
    EXITED = 60
    DEAD = 70
    RUNNING_PARTIALLY = 80
    UNKNOWN = 90

    @staticmethod
    def from_container(container: Union[Container, None]) -> "Status":
        if not container:
            return Status.STAGED
        return Status[str(container.status).upper()]

    @staticmethod
    def from_group(statuses: List["Status"]) -> "Status":
        same = all(x == statuses[0] for x in statuses) if statuses else True
        if same:
            return statuses[0] if statuses else None
        if Status.RUNNING in statuses:
            return Status.RUNNING_PARTIALLY
        return Status.UNKNOWN


def _network_name_from_container(container: Container) -> str:
    networks: Dict = container.attrs.get("NetworkSettings", {}).get("Networks")
    network_names = list(networks.keys())
    if len(network_names) == 0:
        raise ValueError("The container has no networks")
    return network_names[0]


def create_mongod_container(image: str, port: int, name: str, network: Network, group_name: str, replset_name: str = None,
                            config_svr: bool = False, replica_set: bool = False, sharded: bool = False,
                            shard_id: int = 0, arbiter: bool = False, ephemeral: bool = False, username: str = None,
                            password: str = None, shards: int = 0) -> Container:
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
        "tomodo-group": group_name,
        "tomodo-port": str(port),
        "tomodo-role": "cfg-svr" if config_svr else "rs-member" if replset_name else "standalone",
        "tomodo-type": deployment_type,
        "tomodo-data-dir": host_path,
        "tomodo-container-data-dir": container_path,
        "tomodo-shard-id": str(shard_id),
        "tomodo-shard-count": str(shards or 0),
        "tomodo-arbiter": str(int(arbiter)),
        "tomodo-ephemeral": str(int(ephemeral))
    }

    container = _create_docker_container(
        name=name, image=image, labels=labels, mounts=mounts,
        environment=environment, port=port, command=command,
        network=network
    )

    return container, host_path, container_path


def wait_for_readiness(mongod: "Mongod", config: ProvisionerConfig):
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


def _create_docker_container(name: str, image: str, labels: Dict, mounts: List[Mount], environment: List[str],
                             port: int, command: List[str], network: Network) -> Container:
    networking_config = NetworkingConfig(
        endpoints_config={
            network.name: EndpointConfig(version=DOCKER_ENDPOINT_CONFIG_VER, aliases=[name])
        }
    )
    return docker.from_env().containers.run(
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


def get_network(name: str = None) -> Network:
    networks = docker.from_env().networks.list(filters={"name": name})
    if len(networks) > 0:
        network = networks[0]
        logger.info("At least one Docker network exists with the name '%s'. Picking the first one [id: %s]",
                    network.name, network.short_id)
    else:
        network = docker.from_env().networks.create(name=name)
        logger.info("Docker network '%s' was created [id: %s]", name, network.short_id)
    return network


class Deployment(ABC):
    version: str
    _network: Network
    name: str
    docker_client: DockerClient
    status: Status
    network_name: str = "mongo_network"
    port: int = 27017
    group_name: str
    image: str = "mongo:latest"

    def __init__(self, name: str, version: str = None, network_name: str = "mongo_network",
                 status: Status = Status.STAGED, port: int = 27017, group_name: str = None, image: str = None):
        self.docker_client = docker.from_env()
        self.status = status
        self.version = version
        self.network_name = network_name
        self.name = name
        self.port = port
        self.group_name = group_name
        self.image = image

    @abstractmethod
    def create(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def type_str(self) -> str:
        raise NotImplementedError

    def start(self):
        pass

    def stop(self):
        pass

    def remove(self):
        pass

    def get(self, name: str) -> "Deployment":
        pass

    def list(self, include_stopped: bool = False) -> List["Deployment"]:
        containers: List[Container] = self.docker_client.containers.list(
            filters={"label": "source=tomodo"}, all=include_stopped
        )
        grouped = {}
        for container in containers:
            group = container.labels.get("tomodo-group")
            if group:
                if group in grouped:
                    grouped[group].append(container)
                else:
                    grouped[group] = [container]
        sorted_groups = {}
        for group in grouped.keys():
            sorted_groups[group] = sorted(grouped[group], key=lambda c: int(c.labels.get("tomodo-port", 0)))
        return [Deployment.from_container_group(containers) for containers in sorted_groups.items()]

    def _create_docker_container(self) -> Container:
        pass

    @staticmethod
    def from_container_group(containers: List[Container]) -> "Deployment":
        container = containers[0]
        deployment_type = container.labels.get("tomodo-type")
        if deployment_type == Standalone.type_str:
            return Standalone.from_container(container)
        if deployment_type == ReplicaSet.type_str:
            return ReplicaSet.from_container_group(containers)
        if deployment_type == ShardedCluster.type_str:
            return ShardedCluster.from_container(container)
        if deployment_type == Atlas.type_str:
            return Atlas.from_container(container)
        if deployment_type == OpsManager.type_str:
            return OpsManager.from_container(container)
        if deployment_type == OpsManagerDeploymentServer.type_str:
            return OpsManagerDeploymentServer.from_container(container)
        raise InvalidDeploymentType

    @property
    def network(self) -> Network:
        if self._network is None:

            networks = self.docker_client.networks.list(filters={"name": self.network_name})
            if len(networks) > 0:
                self._network = networks[0]
                logger.info(
                    "At least one Docker network exists with the name '%s'. Picking the first one [id: %s]",
                    self.network.name, self.network.short_id
                )
            else:
                self._network = self.docker_client.networks.create(name=self.network_name)
                logger.info(
                    "Docker network '%s' was created [id: %s]", self.network_name, self.network.short_id
                )
        return self._network


class Mongod(Deployment):
    container: Container
    host_data_dir: str
    container_data_dir: str
    is_arbiter: bool = False
    is_ephemeral: bool = False
    username: str = None
    password: str = None

    def __init__(self, version: str = None, network_name: str = None,
                 port: int = 27017, name: str = None, group_name: str = None, container: Container = None,
                 host_data_dir: str = None, container_data_dir: str = None,
                 is_arbiter: bool = False, is_ephemeral: bool = False, status: Status = Status.STAGED,
                 image: str = "mongo:latest"):
        super().__init__(version=version, name=name, port=port, network_name=network_name, group_name=group_name,
                         status=status, image=image)
        self.container = container
        self.host_data_dir = host_data_dir
        self.container_data_dir = container_data_dir
        self.is_arbiter = is_arbiter
        self.is_ephemeral = is_ephemeral


    @staticmethod
    def from_container(container: Container) -> "Mongod":
        labels = container.labels
        version = next(
            (
                var.split("=")[1] for var in container.attrs.get("Config", {}).get("Env", []) if
                var.startswith(f"MONGO_VERSION=")
            ),
            None
        )
        return Mongod(
            name=labels.get("tomodo-name"),
            group_name=labels.get("tomodo-group"),
            port=int(labels.get("tomodo-port", 0)),
            container=container,
            host_data_dir=labels.get("tomodo-data-dir"),
            container_data_dir=labels.get("tomodo-container-data-dir"),
            is_arbiter=labels.get("tomodo-arbiter") == "1",
            status=Status.from_container(container),
            version=version,
            image=container.image.tags[0],  # Should never be empty
            network_name=_network_name_from_container(container)
        )

    @property
    def type_str(self) -> str:
        return "standalone"

    def create(self) -> "Mongod":
        if not is_port_range_available((self.port,)):
            raise PortsTakenException
        container, host_data_dir, container_data_dir = create_mongod_container(
            image=self.image,
            port=self.port,
            name=self.name,
            network=get_network(self.network_name),
            group_name=self.name,
            ephemeral=self.is_ephemeral,
            username=self.username,
            password=self.password
        )
        self.container_data_dir = container_data_dir
        self.host_data_dir = host_data_dir
        self.container = container
        logger.info("MongoDB container created [id: %s]", self.container.short_id)
        logger.info("Checking the readiness of %s", self.name)
        self.wait_for_mongod_readiness()
        return self

    @with_retry(max_attempts=60, delay=2, retryable_exc=(APIError, Exception))
    def wait_for_mongod_readiness(self):
        wait_for_readiness(mongod=self, config=self.config)
    
    def __str__(self) -> str:
        """
        :return: A markdown table row representing the instance
        """
        data = [self.name, "Standalone", self.status.value, "1", self.version, str(self.port)]
        return f"|{'|'.join(data)}|"
    
    def __dict__(self) -> Dict:
        return {}


class Standalone(Mongod):
    pass


class ReplicaSet(Deployment):
    members: List[Mongod]
    size: int
    has_arbiter: bool = False
    size: int = None

    def __init__(self, version: str = None,
                 port: int = 27017, name: str = None, group_name: str = None,
                 members: List[Mongod] = None, status: Status = Status.STAGED,
                 has_arbiter: bool = False, size: int = None):
        super().__init__(version=version, status=status)
        self.port = port
        self.name = name
        self.group_name = group_name
        self.members = members
        self.size = size or len(self.members)
        self.has_arbiter = has_arbiter

    @staticmethod
    def from_container_group(containers: List[Container]) -> "ReplicaSet":
        first_container = containers[0]
        members = []
        for container in containers:
            members.append(Mongod.from_container(container))
        return ReplicaSet(
            members=members,
            port=first_container.port,
            version=first_container.version,
            status=Status.from_group([m.status for m in members])
        )

    @property
    def type_str(self) -> str:
        return "replica-set"

    def create(self):
        if not is_port_range_available((self.port,)):
            raise PortsTakenException
        if self.has_arbiter:
            logger.info("An arbiter node will also be provisioned")
        start_port = self.port
        ports = range(start_port, start_port + self.size)
        container, host_data_dir, container_data_dir = create_mongod_container(
            image=self.image,
            port=self.port,
            name=self.name,
            network=get_network(self.network_name),
            group_name=self.name,
            ephemeral=self.is_ephemeral,
            username=self.username,
            password=self.password
        )
        self.container_data_dir = container_data_dir
        self.host_data_dir = host_data_dir
        self.container = container
        logger.info("MongoDB container created [id: %s]", self.container.short_id)
        logger.info("Checking the readiness of %s", self.name)
        self.wait_for_mongod_readiness()
        return self

    def __str__(self) -> str:
        return ""

class ShardedCluster(Deployment):

    @staticmethod
    def from_container(container: Container) -> "Deployment":
        pass

    @property
    def type_str(self) -> str:
        return "sharded-cluster"

    def create(self):
        pass

    def __str__(self) -> str:
        return ""


class Atlas(Deployment):

    @staticmethod
    def from_container(container: Container) -> "Deployment":
        pass

    @property
    def type_str(self) -> str:
        return "atlas-deployment"

    def create(self):
        pass

    def __str__(self) -> str:
        return ""

class OpsManager(Deployment):

    @staticmethod
    def from_container(container: Container) -> "Deployment":
        pass

    @property
    def type_str(self) -> str:
        return "ops-manager"

    def create(self):
        pass

    def __str__(self) -> str:
        return ""


class OpsManagerDeploymentServer(Deployment):

    @staticmethod
    def from_container(container: Container) -> "Deployment":
        pass

    @property
    def type_str(self) -> str:
        return "ops-manager-deployment-server"

    def create(self):
        pass

    def __str__(self) -> str:
        return ""
