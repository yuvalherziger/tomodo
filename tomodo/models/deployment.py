import logging
from abc import ABC, abstractmethod
from enum import Enum, member
from typing import List, Dict

import docker
from docker import DockerClient
from docker.models.networks import Network
from docker.models.containers import Container

from tomodo.common.errors import InvalidDeploymentType

logger = logging.getLogger("rich")


class Status(Enum):
    STAGED = 0
    CREATED = 10
    RESTARTING = 20
    RUNNING = 30
    REMOVING = 40
    PAUSED = 50
    EXITED = 60
    DEAD = 70

    @staticmethod
    def from_container(container: Container) -> "Status":
        if not container:
            return Status.STAGED
        return Status[str(container.status).upper()]


def _network_name_from_container(container: Container) -> str:
    networks: Dict = container.attrs.get("NetworkSettings", {}).get("Networks")
    network_names = list(networks.keys())
    if len(network_names) == 0:
        raise ValueError("The container has no networks")
    return network_names[0]


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
            image=container.image.tags[0]  # Should never be empty
        )

    @property
    def type_str(self) -> str:
        return "standalone"

    def create(self):
        pass

    def __str__(self) -> str:
        return ""


class Standalone(Mongod):
    pass


class ReplicaSet(Deployment):
    members: List[Mongod]
    size: int

    def __init__(self, version: str = None,
                 port: int = 27017, name: str = None, group_name: str = None,
                 members: List[Mongod] = None):
        super().__init__(version)
        self.port = port
        self.name = name
        self.group_name = group_name
        self.members = members
        self.size = len(self.members)

    @staticmethod
    def from_container_group(containers: List[Container]) -> "ReplicaSet":
        first_container = containers[0]
        members = []
        for container in containers:
            members.append(Mongod.from_container(container))
        return ReplicaSet(
            members=members,
            port=members[0].port
        )

    @property
    def type_str(self) -> str:
        return "replica-set"

    def create(self):
        pass

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
