import logging
import os
import shutil
from typing import Dict

import docker
from docker.models.containers import Container

from tomodo.common.models import ReplicaSet, ShardedCluster, Mongod, Deployment, AtlasDeployment
from tomodo.common.reader import Reader

logger = logging.getLogger("rich")


class Cleaner:

    def __init__(self):
        self.docker_client = docker.from_env()
        self.reader = Reader(docker_client=self.docker_client)

    def stop_deployment(self, name: str):
        deployment = self.reader.get_deployment_by_name(name, include_stopped=True)
        logger.info("This action will stop the '%s' deployment", name)
        if isinstance(deployment, ReplicaSet):
            for member in deployment.members:
                logger.info("Stopping replica set member in container %s", member.container_id)
                self._stop_container(member.container_id)
        elif isinstance(deployment, ShardedCluster):
            for router in deployment.routers:
                logger.info("Stopping mongos router in container %s", router.container_id)
                self._stop_container(router.container_id)
            for shard in deployment.shards:
                for member in shard.members:
                    logger.info("Stopping shard replica set member in container %s", member.container_id)
                    self._stop_container(member.container_id)
            for member in deployment.config_svr_replicaset.members:
                logger.info("Stopping config server replica set member in container %s", member.container_id)
                self._stop_container(member.container_id)
        elif isinstance(deployment, AtlasDeployment):
            logger.error("Currently, it's not possible to stop Atlas local deployments with tomodo. "
                         f"If you'd like to stop it, run 'tomodo remove --name {deployment.name}'")
        elif isinstance(deployment, Mongod):
            logger.info("Stopping standalone instance in container %s", deployment.container_id)
            self._stop_container(deployment.container_id)

    def stop_all_deployments(self) -> None:
        deployments: Dict[str, Deployment] = self.reader.get_all_deployments(include_stopped=False)
        names = deployments.keys()
        logger.info("This action will stop all of the following deployments: %s", ", ".join(names))
        for name in names:
            self.stop_deployment(name)

    def delete_all_deployments(self) -> None:
        deployments: Dict[str, Deployment] = self.reader.get_all_deployments(include_stopped=True)
        names = deployments.keys()
        logger.info("This action will delete all of the following deployments: %s", ", ".join(names))
        for name in names:
            self.delete_deployment(name)

    def delete_deployment(self, name: str) -> None:
        deployment = self.reader.get_deployment_by_name(name, include_stopped=True)
        logger.info("This action will delete the '%s' deployment permanently, including its data", name)
        if isinstance(deployment, ReplicaSet):
            for member in deployment.members:
                logger.info("Deleting replica set member in container %s", member.container_id)
                self._delete_container(member.container_id, member.host_data_dir)
        elif isinstance(deployment, ShardedCluster):
            for router in deployment.routers:
                logger.info("Deleting mongos router in container %s", router.container_id)
                self._delete_container(router.container_id)
            for shard in deployment.shards:
                for member in shard.members:
                    logger.info("Deleting shard replica set member in container %s", member.container_id)
                    self._delete_container(member.container_id, member.host_data_dir)
            for member in deployment.config_svr_replicaset.members:
                logger.info("Deleting config server replica set member in container %s", member.container_id)
                self._delete_container(member.container_id, member.host_data_dir)
        elif isinstance(deployment, AtlasDeployment):
            logger.info("Deleting Atlas deployment in container %s", deployment.container_id)
            self._delete_container(deployment.container_id)
        elif isinstance(deployment, Mongod):
            logger.info("Deleting standalone instance in container %s", deployment.container_id)
            self._delete_container(deployment.container_id, deployment.host_data_dir)

    def _stop_container(self, container_id: str) -> None:
        container = self.docker_client.containers.get(container_id)
        if container.status == "running":
            container.stop()
            logger.info("Container %s stopped", container_id)
        else:
            logger.info("Container %s isn't running", container_id)

    def _delete_container(self, container_id: str, data_path: str = None):
        container: Container = self.docker_client.containers.get(container_id)
        container.remove(force=True)
        if data_path is not None:
            logger.info("The following data directory will be deleted: '%s'", data_path)
            if os.path.exists(data_path):
                try:
                    shutil.rmtree(data_path)
                    logger.info("Directory '%s' has been successfully deleted", data_path)
                except Exception as e:
                    logger.error("An error occurred while trying to remove '%s'", data_path)
            else:
                logger.warning("Directory '%s' does not exist", data_path)
