import base64
import inspect
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
from docker.models.containers import Container
from docker.models.networks import Network
from docker.types import Mount, NetworkingConfig, EndpointConfig
from unique_names_generator import get_random_name
from unique_names_generator.data import ADJECTIVES, ANIMALS

from tomodo.common.errors import InvalidDeploymentType, PortsTakenException, InvalidShellException
from tomodo.common.util import get_os, is_port_range_available, with_retry, clean_up_mongo_output

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


def generate_name():
    return get_random_name(combo=[ADJECTIVES, ANIMALS], separator="-", style="lowercase")


def _network_name_from_container(container: Container) -> str:
    networks: Dict = container.attrs.get("NetworkSettings", {}).get("Networks")
    network_names = list(networks.keys())
    if len(network_names) == 0:
        raise ValueError("The container has no networks")
    return network_names[0]


def create_mongod_container(mongod: "Mongod", image: str, port: int, name: str, network: Network, group_name: str,
                            sharded: bool = False, shard_id: int = 0, arbiter: bool = False,
                            ephemeral: bool = False, username: str = None, password: str = None,
                            shards: int = 0) -> Container:
    logger.info("Creating container from '%s'. Port %d will be exposed to your host", image, port)
    is_config_svr = isinstance(mongod, ConfigServer)
    is_shard_member = isinstance(mongod, ShardMember)
    is_replica = isinstance(mongod, Replica)
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
    if is_config_svr:
        command.extend(["--configsvr", "--replSet", mongod.parent_name])
        deployment_type = "Sharded Cluster"
    elif is_shard_member:
        command.extend(["--shardsvr", "--replSet", mongod.parent_name])
        deployment_type = "Sharded Cluster"
    elif is_replica:
        command.extend(["--replSet", mongod.parent_name])
        deployment_type = "Replica Set"

    labels = {
        "source": "tomodo",
        "tomodo-name": name,
        "tomodo-group": mongod.group_name,
        "tomodo-port": str(port),
        "tomodo-role": "cfg-svr" if is_config_svr else "rs-member" if mongod.parent_name else "standalone",
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


def create_mongos_container(image: str, port: int, name: str, group_name: str,
                            csrs: "ConfigServerReplicaSet", network: Network, shard_count: int):
    logger.info("Creating container from '%s'. Port %d will be exposed to your host", image, port)
    command = [
        "mongos",
        "--bind_ip_all",
        "--port", str(port),
        "--configdb", csrs.config_db
    ]
    labels = {
        "source": "tomodo",
        "tomodo-name": name,
        "tomodo-group": group_name,
        "tomodo-port": str(port),
        "tomodo-role": "mongos",
        "tomodo-type": "Sharded Cluster",
        "tomodo-shard-count": str(shard_count or 0),
    }
    return _create_docker_container(
        name=name, image=image, labels=labels, mounts=[],
        environment={}, port=port, command=command,
        network=network
    )


def wait_for_readiness(mongod: "Mongod"):
    logger.debug("Checking the readiness of %s", mongod.name)
    mongo_cmd = "db.runCommand({ping: 1}).ok"

    try:
        exit_code, output, _ = run_shell_command(mongo_cmd=mongo_cmd, mongod=mongod)
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


def run_shell_command(mongo_cmd: str, mongod: "Mongod", shell: str = "mongosh",
                      serialize_json: bool = False) -> (int, str, str):
    docker_client = docker.from_env()
    container: Container = docker_client.containers.get(mongod.container.short_id)
    if not container:
        raise Exception(f"Could not find the container '{mongod.container.short_id}'")
    hostname = mongod.name

    shell_check_exit_code, _ = container.exec_run(cmd=["which", shell])
    if shell_check_exit_code != 0:
        if shell != "mongo":
            logger.debug(
                "The '%s' shell could not be found in the container. Checking for the legacy 'mongo' shell",
                shell)
            shell = "mongo"
            shell_check_exit_code, _ = container.exec_run(cmd=["which", shell])
        if shell_check_exit_code != 0:
            logger.error("The '%s' shell could not be found in the container.", shell)
            # No valid shell --> error out:
            raise InvalidShellException
    # If the output needs to be JSON-serialized by the tool, it's required to stringify it with mongosh:
    if shell == "mongosh" and serialize_json:
        mongo_cmd = f"JSON.stringify({mongo_cmd})"
    cmd = [shell, "--host", hostname, "--quiet", "--norc", "--port", str(mongod.port), "--eval", mongo_cmd]

    if mongod.is_auth_enabled and not isinstance(mongod, ConfigServer) and not isinstance(mongod, Mongos):
        cmd.extend(["--username", mongod.username])
        cmd.extend(["--password", mongod.password])
    command_exit_code: int
    command_output: bytes
    command_exit_code, command_output = container.exec_run(cmd=cmd)
    caller = inspect.stack()[1][3]
    logger.debug("Docker-exec [%s]: command output: %s", caller, command_output.decode("utf-8").strip())
    logger.debug("Docker-exec [%s]: command exit code: %d", caller, command_exit_code)
    return command_exit_code, clean_up_mongo_output(command_output.decode("utf-8").strip()), mongod.container.short_id


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

    def __init__(self, name: str = None, version: str = None, network_name: str = "mongo_network",
                 status: Status = Status.STAGED, port: int = 27017, group_name: str = None, image: str = None):
        self.docker_client = docker.from_env()
        self.status = status
        self.version = version
        self.network_name = network_name
        self.name = name or generate_name()
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
    parent_name: str
    container_data_dir: str
    is_arbiter: bool = False
    is_ephemeral: bool = False
    username: str = None
    password: str = None

    def __init__(self, version: str = None, network_name: str = "mongo_network",
                 port: int = 27017, name: str = None, group_name: str = None, container: Container = None,
                 host_data_dir: str = None, container_data_dir: str = None,
                 is_arbiter: bool = False, is_ephemeral: bool = False, status: Status = Status.STAGED,
                 image: str = "mongo:latest", username: str = None, password: str = None,
                 parent_name: str = None):
        super().__init__(version=version, name=name, port=port, network_name=network_name, group_name=group_name,
                         status=status, image=image)
        self.container = container
        self.host_data_dir = host_data_dir
        self.container_data_dir = container_data_dir
        self.is_arbiter = is_arbiter
        self.is_ephemeral = is_ephemeral
        self.username = username
        self.password = password
        self.parent_name = parent_name

    @property
    def is_auth_enabled(self) -> bool:
        return self.username is not None and self.password is not None

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
            mongod=self,
            image=self.image,
            port=self.port,
            name=self.name,
            network=get_network(self.network_name),
            group_name=self.group_name,
            ephemeral=self.is_ephemeral,
            username=self.username,
            password=self.password,
            arbiter=self.is_arbiter
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
        wait_for_readiness(mongod=self)

    def __str__(self) -> str:
        """
        :return: A Markdown table row representing the instance
        """
        data = [self.name, "Standalone", self.status.value, "1", self.version, str(self.port)]
        return f"|{'|'.join(data)}|"

    def __dict__(self) -> Dict:
        return {}


class Standalone(Mongod):
    pass


class Mongos(Mongod):
    shard_count: int
    csrs: "ConfigServerReplicaSet"

    def __init__(self, name: str, port: int, shard_count: int, version: str, csrs: "ConfigServerReplicaSet",
                 status: Status = Status.STAGED, network_name: str = "mongo_network", group_name: str = None,
                 image: str = "mongo:latest"):
        super().__init__(name=name, port=port, version=version, status=status,
                         network_name=network_name, image=image, group_name=group_name)
        self.shard_count = shard_count
        self.csrs = csrs

    def create(self) -> "Mongos":
        self.container = create_mongos_container(
            image=self.image,
            port=self.port,
            name=self.name,
            csrs=self.csrs,
            network=get_network(self.network_name),
            shard_count=self.shard_count
        )
        return self


class Replica(Mongod):
    pass


class ReplicaSet(Deployment):
    members: List[Replica]
    size: int
    has_arbiter: bool = False
    username: str = None
    password: str = None
    is_csrs: bool = False
    is_shard: bool = False
    member_class = Replica

    def __init__(self, version: str = None,
                 port: int = 27017, name: str = None, group_name: str = None,
                 members: List[Mongod] = None, status: Status = Status.STAGED,
                 has_arbiter: bool = False, size: int = None, image: str = "mongo:latest",
                 network_name: str = "mongo_network", username: str = None, password: str = None):
        super().__init__(name=name, version=version, status=status,
                         network_name=network_name, image=image)
        # TODO: NAME IS NONE!!!!
        self.port = port
        self.group_name = group_name or name
        self.members = members or []
        self.size = size or len(self.members)
        self.has_arbiter = has_arbiter
        self.username = username
        self.password = password

    @staticmethod
    def from_container_group(containers: List[Container]) -> "ReplicaSet":
        members: List[Mongod] = []
        for container in containers:
            members.append(Mongod.from_container(container))
        return ReplicaSet(
            members=members,
            port=members[0].port,
            version=members[0].version,
            status=Status.from_group([m.status for m in members])
        )

    @property
    def type_str(self) -> str:
        return "replica-set"

    def create(self):
        start_port = self.port
        ports = range(start_port, start_port + self.size)
        if not is_port_range_available(tuple(ports)):
            raise PortsTakenException
        if self.has_arbiter:
            logger.info("An arbiter node will also be provisioned")
        members: List[Mongod] = []
        for port in ports:
            idx = port - start_port
            members.append(
                self.member_class(
                    name=f"{self.name}-{idx}",
                    port=port,
                    group_name=self.group_name,
                    is_arbiter=self.has_arbiter and idx == len(list(ports)),
                    network_name=self.network_name,
                    image=self.image,
                    parent_name=self.name
                )
            )
        for member in members:
            self.members.append(member.create())
        self.initialize()
        return self

    def initialize(self) -> None:
        init_scripts: List[str] = ["rs.initiate()"]
        if self.has_arbiter:
            rc = self.size // 2
            init_scripts.append(
                "db.adminCommand({ setDefaultRWConcern: 1, defaultWriteConcern: { 'w': %s } })" % str(rc)
            )
        for m in self.members[1:self.size]:
            logger.info("Checking the readiness of %s", m.name)
            m.wait_for_mongod_readiness()
            if m.is_arbiter:
                init_scripts.append(f"rs.addArb('{m.name}:{m.port}')")
            else:
                init_scripts.append(f"rs.add('{m.name}:{m.port}')")

        first_mongod = self.members[0]
        for script in init_scripts:
            # TODO: this should become a single initialization command
            run_shell_command(mongo_cmd=script, mongod=first_mongod)

    def __str__(self) -> str:
        return ""


class ConfigServer(Replica):
    pass


class ShardMember(Replica):
    pass


class Shard(ReplicaSet):
    is_shard: bool = False
    shard_id: str
    member_class: type = ShardMember

    def __init__(self, version: str, port: int, name: str, shard_id: str,
                 group_name: str = None, status: Status = Status.STAGED, image: str = "mongo:latest",
                 network_name: str = "mongo_network", shard_count: int = 2, size: int = 3):
        super().__init__(name=name, version=version, status=status,
                         network_name=network_name, image=image)
        self.port = port
        self.group_name = group_name or name
        self.shard_count = shard_count
        self.size = size
        self.shard_id = shard_id

    @property
    def shard_host(self) -> str:
        hosts = ",".join([f"{m.name}:{m.port}" for m in self.members])
        return f"{self.name}/{hosts}"


class ConfigServerReplicaSet(ReplicaSet):
    is_csrs: bool = True
    members: List[ConfigServer]
    member_class: type = ConfigServer

    @property
    def config_db(self) -> str:
        hosts = ",".join([f"{m.name}:{m.port}" for m in self.members])
        return f"{self.name}/{hosts}"


class ShardedCluster(Deployment):
    shard_count: int = 2
    members: List[ShardMember]
    shards: List[Shard]
    shard_size: int = 3
    config_servers: int = 1
    mongos_count: int = 1
    mongos: List[Mongos]
    csrs: ConfigServerReplicaSet = None
    port: int = 27017

    def __init__(self, version: str = None, port: int = 27017, name: str = None,
                 group_name: str = None, csrs: ConfigServerReplicaSet = None,
                 status: Status = Status.STAGED, image: str = "mongo:latest",
                 network_name: str = "mongo_network", mongos_count: int = 1,
                 config_servers: int = 1, shard_count: int = 2, shard_size: int = 3):
        super().__init__(name=name, version=version, status=status,
                         network_name=network_name, image=image)
        self.port = port
        self.group_name = group_name or name
        self.csrs = csrs
        self.mongos_count = mongos_count
        self.config_servers = config_servers
        self.shard_count = shard_count
        self.shard_size = shard_size

    @staticmethod
    def from_container(container: Container) -> "Deployment":
        pass

    @property
    def type_str(self) -> str:
        return "sharded-cluster"

    def create(self) -> "ShardedCluster":
        logger.info("This action will provision a MongoDB sharded cluster with %d shards (%d replicas each)",
                    self.shard_count, self.shard_size)
        # (# replicas x # shards) + # config servers + # mongos
        num_ports: int = (self.shard_count * self.shard_size) + self.config_servers + self.mongos_count
        ports = range(self.port, self.port + num_ports)
        if not is_port_range_available(tuple(ports)):
            raise PortsTakenException
        self.csrs = ConfigServerReplicaSet(
            name=f"{self.name}-cfg-svr",
            group_name=self.name,
            port=self.port,
            size=self.config_servers
        )
        self.csrs.create()
        mongos_start_port = self.port + self.config_servers
        mongos_ports = range(mongos_start_port, mongos_start_port + self.mongos_count)
        mongos_end_port = mongos_start_port
        for port in mongos_ports:
            idx = mongos_start_port - port + 1
            mongos = Mongos(
                version=self.version,
                port=port,
                name=f"{self.name}-mongos-{idx}",
                group_name=self.name,
                csrs=self.csrs,
                shard_count=self.shard_count
            ).create()
            self.mongos.append(mongos)
            mongos_end_port = port
        self.shards = [
            Shard(
                version=self.version,
                name=f"{self.name}-sh-{i}",
                port=mongos_end_port + (i * self.shard_size) + 1,
                size=self.shard_size,
                shard_id=str(i)
            ).create() for i in range(self.shard_count)
        ]
        shard_init_commands = []
        for shard in self.shards:
            shard_init_commands.append(
                f"sh.addShard('{shard.shard_host}')"
            )
        for cmd in shard_init_commands:
            run_shell_command(mongo_cmd=cmd, mongod=self.mongos[0])

        return self

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


if __name__ == "__main__":
    # mongod = Standalone(name="my-mongo", port=27017, network_name="my-network")
    # mongod.create()
    rs = ReplicaSet(size=3, username="admin", password="passw0rd")
    rs.create()
