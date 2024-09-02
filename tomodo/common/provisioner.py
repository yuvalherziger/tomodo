import logging
import platform
from typing import List, Union

from docker import DockerClient
from docker.errors import APIError
from docker.models.containers import Container
from docker.models.networks import Network
from docker.types import EndpointConfig, Mount, NetworkingConfig
from pymongo import MongoClient
from rich.console import Console
from rich.markdown import Markdown

from tomodo.common.base_provisioner import ProvisionerMixin
from tomodo.common.config import ProvisionerConfig
from tomodo.common.errors import (
    InvalidConfiguration,
    PortsTakenException,
    DeploymentNotFound,
    DeploymentNameCollision
)
from tomodo.common.models import Mongod, ReplicaSet, ShardedCluster, Mongos, Shard, ConfigServer, Deployment, \
    AtlasDeployment
from tomodo.common.util import (
    is_port_range_available, with_retry, run_mongo_shell_command, get_os
)

DOCKER_ENDPOINT_CONFIG_VER = "1.43"

console = Console()
logger = logging.getLogger("rich")


class Provisioner(ProvisionerMixin):
    network: Network = None
    config: ProvisionerConfig = None
    docker_client: DockerClient = None

    def __init__(self, config: ProvisionerConfig):
        super().__init__()
        self.config = config

    def provision(self, deployment_getter: callable, print_summary: bool = True) -> Union[
        Mongod, ReplicaSet, ShardedCluster, AtlasDeployment]:
        if sum([self.config.standalone, self.config.replica_set, self.config.sharded, self.config.atlas]) != 1:
            logger.error("Exactly one of the following has to be specified: standalone, replica-set, sharded, or atlas")
            raise InvalidConfiguration
        if self.config.standalone and self.config.arbiter:
            logger.error("Arbiter nodes are supported only in replica sets and sharded clusters")
            raise InvalidConfiguration

        try:
            _ = deployment_getter(self.config.name)
            raise DeploymentNameCollision(f"The deployment {self.config.name} already exists")
        except DeploymentNotFound:
            pass
        self.check_and_pull_image(f"{self.config.image_repo}:{self.config.image_tag}")
        self.network = self.get_network(config=self.config)
        deployment: Deployment = Deployment()
        if self.config.standalone:
            deployment: Mongod = Mongod(
                name=self.config.name,
                port=self.config.port,
                hostname=f"mongodb://{self.config.name}:{self.config.port}"
            )
            deployment = self.provision_standalone_instance(mongod=deployment)
        elif self.config.replica_set:
            deployment: ReplicaSet = ReplicaSet(name=self.config.name, start_port=self.config.port,
                                                size=self.config.replicas)
            deployment = self.provision_replica_set(replicaset=deployment, arbiter=self.config.arbiter)
        elif self.config.sharded:
            deployment: ShardedCluster = self.provision_sharded_cluster()
        elif self.config.atlas:
            deployment: AtlasDeployment = self.provision_atlas_deployment()
        if print_summary:
            self.print_deployment_summary(deployment=deployment)
            self.print_connection_details(deployment=deployment)
        return deployment

    def print_deployment_summary(self, deployment: Deployment = None):
        summary_md = deployment.as_markdown_table()
        markdown = Markdown(summary_md)
        console.print(markdown)

    def print_connection_details(self, deployment: Deployment = None):
        auth = ""
        if self.config.is_auth_enabled:
            auth = f"{self.config.username}:{self.config.password}@"
        members: List[Mongod] = []
        localhost_conn_string: List[str] = [f"mongodb://{auth}localhost:{self.config.port}"]
        mapped_conn: List[str] = []

        if isinstance(deployment, AtlasDeployment):
            mapped_conn: List[str] = [f"mongodb://{auth}{self.config.name}:{self.config.port}"]
            members = [deployment]

        elif isinstance(deployment, Mongod):
            mapped_conn: List[str] = [f"mongodb://{auth}{self.config.name}-1:{self.config.port}/?directConnection=True"]
            members = [deployment]
        elif isinstance(deployment, ReplicaSet):
            rs_hosts = ",".join([f"{m.name}:{m.port}" for m in deployment.members])
            members = deployment.members
            mapped_conn: List[str] = [
                f"mongodb://{auth}{rs_hosts}/?replicaSet={self.config.name}"]
        elif isinstance(deployment, ShardedCluster):
            members = deployment.routers
            localhost_conn_string: List[str] = [
                f"mongodb://{auth}localhost:{r.port}"
                for r in deployment.routers
            ]
            mapped_conn: List[str] = [
                f"mongodb://{auth}{r.name}:{r.port}"
                for r in deployment.routers
            ]
            host_list = []
            for m in deployment.config_svr_replicaset.members:
                host_list.append(m.name)
            for r in deployment.routers:
                host_list.append(r.name)
            for s in deployment.shards:
                for m in s.members:
                    host_list.append(m.name)
        command = ""
        for m in members:
            command += f"echo '127.0.0.1 {m.name}' | sudo tee -a /etc/hosts\n"
        localhost_conn_strings = "\n".join(f"mongosh '{s}'" for s in localhost_conn_string)
        mapped_conns = "\n".join(f"mongosh '{s}'" for s in mapped_conn)
        markdown = Markdown(f"""
```bash
# Connect to the deployment with mongosh using localhost:
{localhost_conn_strings}

# Optionally, map the deployment hosts:
{command}

# Once you've mapped the hosts,
# you'll be able to connect with mongosh this way:
{mapped_conns}

# Print the deployment details:
tomodo describe --name {self.config.name}
```""")

        console.print(markdown)

    def provision_sharded_cluster(self) -> ShardedCluster:
        logger.info("This action will provision a MongoDB sharded cluster with %d shards (%d replicas each)",
                    self.config.shards, self.config.replicas)
        # (replicas x shards) + config server + mongos
        num_ports = (self.config.shards * self.config.replicas) + self.config.config_servers + self.config.mongos
        ports = range(self.config.port, self.config.port + num_ports)
        if not is_port_range_available(tuple(ports)):
            raise PortsTakenException
        sharded_cluster = ShardedCluster()
        config_servers = []
        for i in range(self.config.config_servers):
            curr_name = f"{self.config.name}-cfg-svr-{i + 1}"
            curr_port = self.config.port + i
            config_svr = ConfigServer(
                port=curr_port,
                hostname=f"mongodb://{curr_name}:{curr_port}",
                name=curr_name,
                _type="mongod (config server)"
            )
            config_servers.append(config_svr)
        config_svr_replicaset = ReplicaSet(
            name=f"{self.config.name}-cfg-svr",
            start_port=self.config.port,
            members=config_servers,
            size=self.config.config_servers
        )
        self.provision_replica_set(replicaset=config_svr_replicaset, config_svr=True, sh_cluster=True)

        sharded_cluster.config_svr_replicaset = config_svr_replicaset
        last_mongos_port: int = 0
        for i in range(self.config.mongos):
            mongos_port = self.config.port + self.config.config_servers + i
            mongos_name = f"{self.config.name}-mongos-{i + 1}"
            mongos_container = self.create_mongos_container(
                port=mongos_port,
                name=mongos_name,
                config_svr_replicaset=config_svr_replicaset
            )

            mongos = Mongos(
                port=mongos_port,
                hostname=f"mongodb://{mongos_name}:{mongos_port}",
                name=mongos_name,
                _type="mongos",
                container=mongos_container
            )
            mongos.container_id = mongos_container.short_id
            logger.info("Checking the readiness of %s", mongos.name)
            self.wait_for_mongod_readiness(mongod=mongos)
            sharded_cluster.routers.append(mongos)
            last_mongos_port = mongos_port

        sharded_cluster.shards = []
        for s in range(self.config.shards):
            shard_id = s + 1
            sharded_cluster.shards.append(
                Shard(
                    shard_id=shard_id,
                    name=f"{self.config.name}-sh-{shard_id}",
                    start_port=last_mongos_port + (s * self.config.replicas) + 1,
                    size=self.config.replicas
                )
            )
        shard_init_commands = []
        for s in sharded_cluster.shards:
            self.provision_replica_set(replicaset=s, sh_cluster=True, shard_id=s.shard_id)
            shard_host = f"{s.name}/"
            shard_host += ",".join(f"{m.name}:{m.port}" for m in s.members)
            shard_init_commands.append(
                f"sh.addShard('{shard_host}')"
            )
        for cmd in shard_init_commands:
            run_mongo_shell_command(mongo_cmd=cmd, mongod=sharded_cluster.routers[0])
        return sharded_cluster

    def provision_atlas_deployment(self) -> AtlasDeployment:
        atlas_depl = AtlasDeployment(
            port=self.config.port,
            name=self.config.name,
            hostname=self.config.name
        )
        logger.info("This action will provision a local MongoDB Atlas instance")
        logger.info("Please note: An Atlas deployment might take a little longer to provision, as "
                    "the MongoDB binaries are downloaded lazily in the container's runtime")
        if not is_port_range_available((atlas_depl.port,)):
            raise PortsTakenException
        container, host_path, container_path = self.create_atlas_container(
            port=atlas_depl.port,
            name=atlas_depl.name
        )
        atlas_depl.container = container
        atlas_depl.host_data_dir = host_path
        atlas_depl.container_data_dir = container_path
        atlas_depl.container_id = container.short_id
        logger.info("MongoDB container created [id: %s]", atlas_depl.container_id)
        logger.info("Checking the readiness of %s", atlas_depl.name)
        self.wait_for_atlas_deployment_readiness(depl=atlas_depl)
        return atlas_depl

    def provision_replica_set(self, replicaset: ReplicaSet, config_svr: bool = False, sh_cluster: bool = False,
                              shard_id: int = 0, arbiter: bool = False) -> ReplicaSet:
        if arbiter:
            logger.info("An arbiter node will also be provisioned")
        start_port = replicaset.start_port
        ports = range(start_port, start_port + replicaset.size)
        members: List[Mongod] = []
        for port in ports:
            idx = port - start_port + 1
            members.append(
                (ConfigServer if config_svr else Mongod)(
                    port=port,
                    hostname=f"mongodb://{replicaset.name}-{idx}:{port}",
                    name=f"{replicaset.name}-{idx}",
                    deployment_type="Sharded Cluster" if shard_id or config_svr else "Replica Set",
                    is_arbiter=arbiter and idx == len(list(ports))
                )
            )

        replicaset.members = members
        if not is_port_range_available(tuple(ports)):
            raise PortsTakenException
        # Provision nodes:
        for member in replicaset.members:
            container, host_data_dir, container_data_dir = self.create_mongod_container(
                image=f"{self.config.image_repo}:{self.config.image_tag}",
                port=member.port,
                replica_set=True,
                name=member.name,
                ephemeral=self.config.ephemeral,
                username=self.config.username,
                password=self.config.password,
                network=self.network,
                replset_name=replicaset.name,
                config_svr=config_svr,
                shard_id=shard_id,
                arbiter=member.is_arbiter
            )
            member.container_id = container.short_id
            member.host_data_dir = host_data_dir
            member.container_data_dir = container_data_dir
            logger.info("MongoDB container created [id: %s]", member.container_id)

        logger.info("Checking the readiness of %s", replicaset.members[0].name)
        self.wait_for_mongod_readiness(mongod=replicaset.members[0])
        self.init_replica_set(replicaset, arbiter=self.config.arbiter)
        return replicaset

    def provision_standalone_instance(self, mongod: Mongod) -> Mongod:
        logger.info("This action will provision a standalone MongoDB instance")
        if not is_port_range_available((mongod.port,)):
            raise PortsTakenException
        container, host_data_dir, container_data_dir = self.create_mongod_container(
            image=f"{self.config.image_repo}:{self.config.image_tag}",
            port=mongod.port,
            name=mongod.name,
            network=self.network,
            username=self.config.username,
            password=self.config.password,
            ephemeral=self.config.ephemeral
        )
        mongod.container = container
        mongod.container_id = container.short_id
        mongod.host_data_dir = host_data_dir
        mongod.container_data_dir = container_data_dir
        logger.info("MongoDB container created [id: %s]", mongod.container_id)
        logger.info("Checking the readiness of %s", mongod.name)
        self.wait_for_mongod_readiness(mongod=mongod)
        return mongod

    def init_replica_set(self, replicaset: ReplicaSet, arbiter: bool = False) -> None:
        init_scripts: List[str] = ["rs.initiate()"]
        if arbiter:
            rc = self.config.replicas // 2
            init_scripts.append(
                "db.adminCommand({ setDefaultRWConcern: 1, defaultWriteConcern: { 'w': %s } })" % str(rc)
            )
        for m in replicaset.members[1:len(replicaset.members)]:
            logger.info("Checking the readiness of %s", m.name)
            self.wait_for_mongod_readiness(mongod=m)
            if m.is_arbiter:
                init_scripts.append(f"rs.addArb('{m.name}:{m.port}')")
            else:
                init_scripts.append(f"rs.add('{m.name}:{m.port}')")

        first_mongod = replicaset.members[0]
        for script in init_scripts:
            run_mongo_shell_command(mongo_cmd=script, mongod=first_mongod, config=self.config)

    @with_retry(max_attempts=60, delay=2, retryable_exc=(APIError, Exception))
    def wait_for_mongod_readiness(self, mongod: Mongod):
        self.wait_for_readiness(mongod, config=self.config)

    @with_retry(max_attempts=10, delay=10, retryable_exc=(APIError, Exception))
    def wait_for_atlas_deployment_readiness(self, depl: AtlasDeployment):
        logger.debug("Checking the readiness of %s", depl.name)
        client_args = {"directConnection": True}
        if self.config.is_auth_enabled:
            client_args.update(username=self.config.username, password=self.config.password)
        client = MongoClient(host="localhost", port=depl.port, **client_args)
        res = client.admin.command("ping")
        if not int(res["ok"]) == 1:
            logger.debug("Server %s is not ready to accept connections", depl.name)
            raise Exception("Server isn't ready")
        logger.info("Server %s is ready to accept connections", depl.name)

    def create_atlas_container(self, port: int, name: str) -> Container:
        # TODO: port
        repo = self.config.image_repo
        tag = self.config.image_tag
        image = f"{repo}:{tag}"
        environment = [
            f"PORT={port}",
            f"NAME={name}",
        ]
        if self.config.is_auth_enabled:
            environment.extend([f"MONGODB_INITDB_ROOT_USERNAME={self.config.username}",
                                f"MONGODB_INITDB_ROOT_PASSWORD={self.config.password}"])
        mounts = []
        host_path = ""
        container_path = ""

        logger.info("Creating container from '%s'. Port %d will be exposed to your host", image, port)
        networking_config = NetworkingConfig(
            endpoints_config={
                self.network.name: EndpointConfig(version=DOCKER_ENDPOINT_CONFIG_VER, aliases=[name])
            }
        )
        return self.docker_client.containers.run(
            f"{repo}:{tag}",
            detach=True,
            privileged=True,
            ports={f"27017/tcp": port},
            platform=f"linux/{platform.machine()}",
            mounts=mounts,
            network=self.network.id,
            hostname=name,
            name=name,
            environment=environment,
            networking_config=networking_config,
            labels={
                "source": "tomodo",
                "tomodo-name": name,
                "tomodo-group": name,
                "tomodo-port": str(port),
                "tomodo-data-dir": host_path,
                "tomodo-container-data-dir": container_path,
                "tomodo-role": "atlas",
                "tomodo-type": "Atlas Deployment",
                "tomodo-shard-count": str(self.config.shards or 0),
                "tomodo-ephemeral": str(int(self.config.ephemeral))
            }
        ), host_path, container_path

    def create_mongos_container(self, port: int, name: str, config_svr_replicaset: ReplicaSet):
        repo = self.config.image_repo
        tag = self.config.image_tag
        image = f"{repo}:{tag}"
        logger.info("Creating container from '%s'. Port %d will be exposed to your host", image, port)
        command = [
            "mongos",
            "--bind_ip_all",
            "--port", str(port),
            "--configdb", config_svr_replicaset.config_db
        ]
        networking_config = NetworkingConfig(
            endpoints_config={
                self.network.name: EndpointConfig(version=DOCKER_ENDPOINT_CONFIG_VER, aliases=[name])
            }
        )
        return self.docker_client.containers.run(
            f"{repo}:{tag}",
            detach=True,
            ports={f"{port}/tcp": port},
            platform=f"linux/{platform.machine()}",
            network=self.network.id,
            hostname=name,
            name=name,
            command=command,
            networking_config=networking_config,
            labels={
                "source": "tomodo",
                "tomodo-name": name,
                "tomodo-group": self.config.name,
                "tomodo-port": str(port),
                "tomodo-role": "mongos",
                "tomodo-type": "Sharded Cluster",
                "tomodo-shard-count": str(self.config.shards or 0),
            }
        )
