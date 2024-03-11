import logging

import docker

from tomodo.common.models import ReplicaSet, ShardedCluster, Mongod, AtlasDeployment
from tomodo.common.reader import Reader

logger = logging.getLogger("rich")


class Starter:

    def __init__(self):
        self.docker_client = docker.from_env()
        self.reader = Reader(docker_client=self.docker_client)

    def start_deployment(self, name: str):
        deployment = self.reader.get_deployment_by_name(name, include_stopped=True)
        logger.info("This action will start the '%s' deployment", name)
        if isinstance(deployment, ReplicaSet):
            for member in deployment.members:
                logger.info("Starting container %s", member.container_id)
                self.docker_client.containers.get(member.container_id).start()
            logger.info("Deployment %s is starting up", name)
        elif isinstance(deployment, ShardedCluster):
            for member in deployment.config_svr_replicaset.members:
                logger.info("Starting config server replica set member in container %s", member.container_id)
                self.docker_client.containers.get(member.container_id).start()
            for router in deployment.routers:
                logger.info("Starting mongos router in container %s", router.container_id)
                self.docker_client.containers.get(router.container_id).start()
            for shard in deployment.shards:
                for member in shard.members:
                    logger.info("Starting shard replica set member in container %s", member.container_id)
                    self.docker_client.containers.get(member.container_id).start()
        elif isinstance(deployment, AtlasDeployment):
            logger.warning("Currently, local Atlas deployments cannot be stopped and can therefore not be restarted "
                           "properly. Expect this action to have undesired side-effects.")
            logger.info("Starting container %s", deployment.container_id)
            self.docker_client.containers.get(deployment.container_id).start()
        elif isinstance(deployment, Mongod):
            logger.info("Starting container %s", deployment.container_id)
            self.docker_client.containers.get(deployment.container_id).start()