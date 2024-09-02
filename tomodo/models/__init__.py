from typing import List

from docker.models.containers import Container

from tomodo.common.errors import InvalidDeploymentType
from tomodo.models.deployment import (
    Deployment, Standalone,
    ReplicaSet, ShardedCluster,
    Atlas, OpsManager,
    OpsManagerDeploymentServer
)


def deployment_factory(containers: List[Container]) -> Deployment:
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
