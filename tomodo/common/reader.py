import io
import logging
from typing import List, Dict, Union

import docker
from docker import DockerClient
from docker.models.containers import Container
from rich.console import Console

from tomodo.common.errors import DeploymentNotFound, InvalidDeploymentType
from tomodo.common.models import Deployment, Mongod, ReplicaSet, ShardedCluster, AtlasDeployment

io = io.StringIO()

console = Console(file=io)
logger = logging.getLogger("rich")

SOURCE_KEY = "source"
SOURCE_VALUE = "tomodo"
STANDALONE = "Standalone"
REPLICA_SET = "Replica Set"
SHARDED_CLUSTER = "Sharded Cluster"
ATLAS_DEPLOYMENT = "Atlas Deployment"

AnyDeployment = Union[Mongod, ReplicaSet, ShardedCluster, AtlasDeployment]


def transform_deployment_type(depl: str) -> str:
    res = depl.replace(" ", "-").replace("_", "-").lower()
    if res == "standalone":
        return STANDALONE
    if res == "replica-set":
        return REPLICA_SET
    if res == "sharded-cluster":
        return SHARDED_CLUSTER
    if res == "atlas-deployment":
        return ATLAS_DEPLOYMENT
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


def marshal_deployment(components: List[Dict]) -> AnyDeployment:
    if len(components) == 0:
        raise DeploymentNotFound()
    deployment_type = transform_deployment_type(components[0].get("tomodo-type"))
    if deployment_type == "Replica Set":
        return ReplicaSet.from_container_details(details=components)
    elif deployment_type == "Sharded Cluster":
        return ShardedCluster.from_container_details(details=components)
    elif deployment_type == ATLAS_DEPLOYMENT:
        return AtlasDeployment.from_container_details(details=components[0])
    elif deployment_type == "Standalone":
        return Mongod.from_container_details(details=components[0])


def _read_mongo_version_from_container(container: Container) -> str:
    return next(
        (
            var.split("=")[1] for var in container.attrs.get("Config", {}).get("Env", []) if
            var.startswith("MONGO_VERSION=")
        ),
        None
    )


def extract_details_from_containers(containers) -> List[Dict]:
    container_details = []
    for container in containers:
        if container.labels.get("tomodo-type") == ATLAS_DEPLOYMENT:
            mongo_version = container.labels.get("tomodo-mongodb-version")
        else:
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


def list_deployments_in_markdown_table(deployments: Dict[str, Deployment], include_stopped: bool = True):
    headers = ["Name", "Type", "Status", "Containers", "Version", "Port(s)"]
    rows = [
        "| " + "|".join(headers) + " |",
        "| " + "|".join(["------" for _ in range(len(headers))]) + " |",
    ]
    for name in deployments.keys():
        depl = deployments.get(name)
        rows.append(depl.as_markdown_table_row(name))
    return "\n".join(rows)


class Reader:
    def __init__(self, docker_client: Union[DockerClient, None] = None):
        self.docker_client = docker_client or docker.from_env()

    def describe_all(self, include_stopped: bool = False) -> List[str]:
        deployments: Dict[str, Deployment] = self.get_all_deployments(include_stopped=include_stopped)
        descriptions = []
        for deployment_name in deployments.keys():
            descriptions.append(deployments[deployment_name].as_markdown_table())
        return descriptions

    def describe_by_name(self, name: str, include_stopped: bool = False) -> str:
        deployment: Deployment = self.get_deployment_by_name(name, include_stopped=include_stopped)
        return deployment.as_markdown_table()

    def _get_containers(self, name: str = None, include_stopped: bool = False) -> List[Dict]:
        container_filters = {"label": f"{SOURCE_KEY}={SOURCE_VALUE}"}
        if name:
            container_filters = {"label": f"tomodo-group={name}"}
        containers = self.docker_client.containers.list(filters=container_filters, all=include_stopped)
        return extract_details_from_containers(containers=containers)

    def get_all_deployments(self, include_stopped: bool = False) -> Dict[
        str,
        Union[Mongod, ReplicaSet, ShardedCluster]
    ]:
        container_details = self._get_containers(include_stopped=include_stopped)
        unmarshalled = _key_by(container_details, "tomodo-group")
        return {
            deployment_name: marshal_deployment(unmarshalled[deployment_name])
            for deployment_name in unmarshalled.keys()
        }

    def get_deployment_by_name(self, name: str, include_stopped: bool = False) -> AnyDeployment:
        container_details = self._get_containers(name=name, include_stopped=include_stopped)
        return marshal_deployment(container_details)
