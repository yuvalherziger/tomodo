import io
import logging
from enum import Enum
from typing import List, Dict, Union

import docker
from docker import DockerClient
from docker.models.containers import Container
from rich.console import Console

from tomodo.common.errors import DeploymentNotFound, InvalidDeploymentType
from tomodo.common.models import (Deployment, Mongod, ReplicaSet, ShardedCluster, AtlasDeployment, OpsManagerInstance,
                                  OpsManagerDeploymentServerGroup)

io = io.StringIO()

console = Console(file=io)
logger = logging.getLogger("rich")

SOURCE_KEY = "source"
SOURCE_VALUE = "tomodo"

class DeploymentType(Enum):
    STANDALONE = "Standalone"
    REPLICA_SET = "Replica Set"
    SHARDED_CLUSTER = "Sharded Cluster"
    ATLAS_DEPLOYMENT = "Atlas Deployment"
    OPS_MANAGER = "Ops Manager"
    OPS_MANAGER_DEPLOYMENT_SERVER = "Ops Manager Deployment Server"

AnyDeployment = Union[
    Mongod, ReplicaSet, ShardedCluster, AtlasDeployment, OpsManagerInstance, OpsManagerDeploymentServerGroup
]


def transform_deployment_type(depl: str) -> DeploymentType:
    res = depl.replace(" ", "-").replace("_", "-").lower()
    if res == "standalone":
        return DeploymentType.STANDALONE
    if res == "replica-set":
        return DeploymentType.REPLICA_SET
    if res == "sharded-cluster":
        return DeploymentType.SHARDED_CLUSTER
    if res == "atlas-deployment":
        return DeploymentType.ATLAS_DEPLOYMENT
    if res == "ops-manager":
        return DeploymentType.OPS_MANAGER
    if res == "ops-manager-deployment-server":
        return DeploymentType.OPS_MANAGER_DEPLOYMENT_SERVER
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
    if deployment_type == DeploymentType.REPLICA_SET:
        return ReplicaSet.from_container_details(details=components)
    elif deployment_type == DeploymentType.SHARDED_CLUSTER:
        return ShardedCluster.from_container_details(details=components)
    elif deployment_type == DeploymentType.ATLAS_DEPLOYMENT:
        return AtlasDeployment.from_container_details(details=components[0])
    elif deployment_type == DeploymentType.STANDALONE:
        return Mongod.from_container_details(details=components[0])
    elif deployment_type == DeploymentType.OPS_MANAGER:
        return OpsManagerInstance.from_container_details(details=components[0])
    elif deployment_type == DeploymentType.OPS_MANAGER_DEPLOYMENT_SERVER:
        return OpsManagerDeploymentServerGroup.from_container_details(details=components[0])


def _read_mongo_version_from_container(container: Container, var_name: str = "MONGO_VERSION") -> str:
    return next(
        (
            var.split("=")[1] for var in container.attrs.get("Config", {}).get("Env", []) if
            var.startswith(f"{var_name}=")
        ),
        None
    )


def extract_details_from_containers(containers) -> List[Dict]:
    container_details = []
    for container in containers:
        if container.labels.get("tomodo-type") == DeploymentType.ATLAS_DEPLOYMENT.value:
            mongo_version = container.labels.get("version")
        elif container.labels.get("tomodo-type") == "ops-manager":
            mongo_version = _read_mongo_version_from_container(container, "VERSION")
        else:
            mongo_version = _read_mongo_version_from_container(container, "MONGO_VERSION")
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

    def _get_containers(self, name: str = None, include_stopped: bool = False, get_group: bool = True) -> List[Dict]:
        container_filters = {"label": f"{SOURCE_KEY}={SOURCE_VALUE}"}
        if name:
            label = "tomodo-group" if get_group else "tomodo-name"
            container_filters = {"label": f"{label}={name}"}
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

    def get_deployment_by_name(self, name: str, include_stopped: bool = False, get_group: bool = True) -> AnyDeployment:
        container_details = self._get_containers(name=name, include_stopped=include_stopped, get_group=get_group)
        return marshal_deployment(container_details)
