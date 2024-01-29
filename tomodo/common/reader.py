import io
import logging
from typing import List, Dict

import docker
from docker.models.containers import Container
from rich.console import Console

from tomodo.common.errors import EmptyDeployment, InvalidDeploymentType
from tomodo.common.models import Deployment, Mongod, ReplicaSet, ShardedCluster, Mongos, Shard

io = io.StringIO()

console = Console(file=io)
logger = logging.getLogger("rich")

SOURCE_KEY = "source"
SOURCE_VALUE = "tomodo"
RUNNING = "Running"
STOPPED = "Stopped"
STANDALONE = "Standalone"
REPLICA_SET = "Replica Set"
SHARDED_CLUSTER = "Sharded Cluster"


def port_sorter(c: Dict):
    return int(c.get("tomodo-port"))


def shard_and_port_sorter(c: Dict):
    return int(c.get("tomodo-shard-id", 0)) * int(c.get("tomodo-port", 0))


def transform_deployment_type(depl: str) -> str:
    res = depl.replace(" ", "-").replace("_", "-").lower()
    if res == "standalone":
        return STANDALONE
    if res == "replica-set":
        return REPLICA_SET
    if res == "sharded-cluster":
        return SHARDED_CLUSTER
    raise InvalidDeploymentType


def _key_by(list_of_dicts: List[Dict], attr: str) -> Dict[str, List[Dict]]:
    result: Dict[str, List[Dict]] = {}
    for d in list_of_dicts:
        if attr in d:
            clean = {k: v for k, v in d.items() if k.startswith("tomodo-")}
            if d[attr] in result:
                result[d[attr]].append(clean)
            else:
                result[d[attr]] = [clean]
    return result


def marshal_deployment(components: List[Dict]) -> Deployment:
    if len(components) == 0:
        raise EmptyDeployment()
    deployment_type = transform_deployment_type(components[0].get("tomodo-type"))

    if deployment_type == "Replica Set":
        return marshal_replica_set(components)
    elif deployment_type == "Sharded Cluster":
        return marshal_sharded_cluster(components)
    elif deployment_type == "Standalone":
        return marshal_standalone_instance(component=components[0])
    else:
        raise InvalidDeploymentType(deployment_type)


def marshal_replica_set(components: List[Dict]) -> ReplicaSet:
    name = components[0].get("tomodo-group")
    mongo_version = components[0].get("tomodo-mongo-version")
    sorted_components = sorted(components, key=port_sorter)
    stopped_containers = 0
    running_containers = 0
    members = []
    for component in sorted_components:
        container: Container = component.get("tomodo-container")
        members.append(
            Mongod(
                port=int(component.get("tomodo-port", 0)),
                hostname=component.get("tomodo-name"),
                name=component.get("tomodo-name"),
                container_id=component.get("tomodo-container-id"),
                host_data_dir=component.get("tomodo-data-dir"),
                container=container,
                mongo_version=_read_mongo_version_from_container(container)
            )
        )

        if container.status == "running":
            running_containers += 1
        else:
            stopped_containers += 1
    replica_set = ReplicaSet(
        members=members,
        name=name,
        start_port=members[0].port,
        size=len(members)
    )
    if running_containers > 0:
        replica_set.last_known_state = RUNNING
    else:
        replica_set.last_known_state = STOPPED
    replica_set.mongo_version = mongo_version
    return replica_set


def split_into_chunks(lst, y):
    chunk_size = len(lst) // y
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def marshal_standalone_instance(component: Dict) -> Mongod:
    container: Container = component.get("tomodo-container")
    mongo_version = component.get("tomodo-mongo-version")
    mongod = Mongod(
        port=int(component.get("tomodo-port", 0)),
        hostname=component.get("tomodo-name"),
        name=component.get("tomodo-name"),
        container_id=component.get("tomodo-container-id"),
        host_data_dir=component.get("tomodo-data-dir"),
        container=container
    )
    mongod.mongo_version = mongo_version
    mongod.last_known_state = RUNNING if container.status == "running" else STOPPED
    return mongod


def marshal_sharded_cluster(components: List[Dict]) -> ShardedCluster:
    name = components[0].get("tomodo-group")
    mongo_version = components[0].get("tomodo-mongo-version")
    config_svr_components = sorted([c for c in components if c.get("tomodo-role") == "cfg-svr"], key=port_sorter)
    mongos_components = sorted([c for c in components if c.get("tomodo-role") == "mongos"], key=port_sorter)
    shard_mongod_components = sorted([c for c in components if c.get("tomodo-role") == "rs-member"],
                                     key=shard_and_port_sorter)
    stopped_containers = 0
    running_containers = 0

    cfg_server_members = []
    for component in config_svr_components:
        container: Container = component.get("tomodo-container")
        cfg_server_members.append(
            Mongod(
                port=int(component.get("tomodo-port", 0)),
                hostname=component.get("tomodo-name"),
                name=component.get("tomodo-name"),
                container_id=component.get("tomodo-container-id"),
                host_data_dir=component.get("tomodo-data-dir"),
                container=container
            )
        )
        if container.status == "running":
            running_containers += 1
        else:
            stopped_containers += 1
    config_svr_replicaset = ReplicaSet(
        members=cfg_server_members,
        name=name,
        start_port=cfg_server_members[0].port,
        size=len(cfg_server_members)
    )
    routers = []
    for component in mongos_components:
        container: Container = component.get("tomodo-container")
        routers.append(
            Mongos(
                port=int(component.get("tomodo-port", 0)),
                hostname=component.get("tomodo-name"),
                name=component.get("tomodo-name"),
                container_id=component.get("tomodo-container-id"),
                _type="mongos",
                container=container
            )
        )
        if container.status == "running":
            running_containers += 1
        else:
            stopped_containers += 1

    num_shards = int(shard_mongod_components[0].get("tomodo-shard-count", 0)) if len(shard_mongod_components) else 0
    shards = []
    if num_shards > 0:
        chunked_shard_components = split_into_chunks(shard_mongod_components, num_shards)
    else:
        chunked_shard_components = []
    for shard_components in chunked_shard_components:
        members = []
        for component in shard_components:
            container: Container = component.get("tomodo-container")
            members.append(
                Mongod(
                    port=int(component.get("tomodo-port", 0)),
                    hostname=component.get("tomodo-name"),
                    name=component.get("tomodo-name"),
                    container_id=component.get("tomodo-container-id"),
                    host_data_dir=component.get("tomodo-data-dir"),
                    container=container
                )
            )
            if container.status == "running":
                running_containers += 1
            else:
                stopped_containers += 1
        shards.append(
            Shard(
                shard_id=int(shard_components[0].get("tomodo-shard-id", 0)),
                members=members,
                name=name,
                size=len(shard_components),
                start_port=int(shard_components[0].get("tomodo-port", 0))
            )
        )

    sharded_cluster = ShardedCluster(
        config_svr_replicaset=config_svr_replicaset,
        routers=routers,
        shards=shards,
        name=name
    )
    if running_containers > 0:
        sharded_cluster.last_known_state = RUNNING
    else:
        sharded_cluster.last_known_state = STOPPED
    sharded_cluster.mongo_version = mongo_version
    return sharded_cluster


def _read_mongo_version_from_container(container: Container) -> str:
    return next(
        (
            var.split("=")[1] for var in container.attrs.get("Config", {}).get("Env", []) if
            var.startswith("MONGO_VERSION=")
        ),
        None
    )


class Reader:
    def __init__(self):
        self.docker_client = docker.from_env()

    def list_deployments_in_markdown_table(self, deployments: Dict[str, Deployment], include_stopped: bool = True):
        headers = ["Name", "Type", "Status", "Containers", "Version", "Port(s)"]
        rows = [
            "| " + "|".join(headers) + " |",
            "| " + "|".join(["------" for _ in range(len(headers))]) + " |",
        ]
        for name in deployments.keys():
            depl = deployments.get(name)
            rows.append(depl.as_markdown_table_row(name))
        return "\n".join(rows)

    def describe_all(self, include_stopped: bool = False) -> List[str]:
        deployments: Dict[str, Deployment] = self.get_all_deployments(include_stopped=include_stopped)
        descriptions = []
        for deployment_name in deployments.keys():
            descriptions.append(deployments[deployment_name].as_markdown_table())
        return descriptions

    def describe_by_name(self, name: str, include_stopped: bool = False) -> str:
        deployment: Deployment = self.get_deployment_by_name(name, include_stopped=include_stopped)
        return deployment.as_markdown_table()

    def _extract_details_from_containers(self, containers) -> List[Dict]:
        container_details = []
        for container in containers:
            mongo_version = _read_mongo_version_from_container(container)
            container_details.append({
                **container.labels,
                "tomodo-container-id": container.short_id,
                "tomodo-container-status": container.status,
                "tomodo-mongo-version": mongo_version,
                "tomodo-type": container.labels.get("tomodo-type", "Standalone"),
                "tomodo-container": container,
            })
        return container_details

    def _get_containers(self, name: str = None, include_stopped: bool = False) -> List[Dict]:
        container_filters = {"label": f"{SOURCE_KEY}={SOURCE_VALUE}"}
        if name:
            container_filters = {"label": f"tomodo-group={name}"}
        containers = self.docker_client.containers.list(filters=container_filters, all=include_stopped)
        return self._extract_details_from_containers(containers=containers)

    def get_all_deployments(self, include_stopped: bool = False) -> Dict[str, Deployment]:
        container_details = self._get_containers(include_stopped=include_stopped)
        unmarshalled = _key_by(container_details, "tomodo-group")
        return {
            deployment_name: marshal_deployment(unmarshalled[deployment_name])
            for deployment_name in unmarshalled.keys()
        }

    def get_deployment_by_name(self, name: str, include_stopped: bool = False) -> Deployment:
        container_details = self._get_containers(name=name, include_stopped=include_stopped)
        return marshal_deployment(container_details)
