from typing import List, Dict, Union

from tomodo import ProvisionerConfig, Provisioner, Reader
from tomodo.common.models import Mongod, ReplicaSet, ShardedCluster, AtlasDeployment


def provision_standalone_instance(name: str = None,
                                  port: int = 27017,
                                  auth: bool = False, username: str = None, password: str = None,
                                  auth_db: str = "admin",
                                  auth_roles: List[str] = None, image_repo: str = "mongo",
                                  image_tag: str = "latest",
                                  network_name: str = "mongo_network") -> Mongod:
    """
    Provisions and returns a standalone instance of MongoDB

    :param name:            The deployment's name; auto-generated if not provided
    :param port:            The deployment port
    :param auth:            Whether to enable authentication
    :param username:        Optional authentication username
    :param password:        Optional authentication password
    :param auth_db:         Authorization DB (currently ignored)
    :param auth_roles:      Default authentication roles (currently ignored)
    :param image_repo:      The MongoDB image name/repo
    :param image_tag:       The MongoDB image tag, which determines the MongoDB version to install
    :param network_name:    The Docker network to provision the deployment in; will create a new one or use an existing
                            one with the same name if such network exists
    :return:                Mongod instance
    """
    config = ProvisionerConfig(
        standalone=True,
        name=name,
        port=port,
        auth=auth,
        username=username,
        password=password,
        auth_db=auth_db,
        auth_roles=auth_roles,
        image_repo=image_repo,
        image_tag=image_tag,
        network_name=network_name
    )
    provisioner = Provisioner(config=config)
    reader = Reader()
    return provisioner.provision(deployment_getter=reader.get_deployment_by_name)


def provision_atlas_instance(name: str = None,
                             port: int = 27017, version: str = "7.0",
                             username: str = None, password: str = None,
                             image_repo: str = "ghcr.io/yuviherziger/tomodo",
                             image_tag: str = "main",
                             network_name: str = "mongo_network") -> AtlasDeployment:
    """
    Provisions and returns a standalone instance of MongoDB

    :param name:            The deployment's name; auto-generated if not provided
    :param port:            The deployment port
    :param version          The MongoDB version to install
    :param username:        Optional authentication username
    :param password:        Optional authentication password
    :param image_repo:      The MongoDB Atlas CLI image name/repo
    :param image_tag:       The MongoDB Atlas CLI  image tag
    :param network_name:    The Docker network to provision the deployment in; will create a new one or use an existing
                            one with the same name if such network exists
    :return:                AtlasDeployment instance
    """
    config = ProvisionerConfig(
        atlas=True,
        name=name,
        port=port,
        username=username,
        password=password,
        image_repo=image_repo,
        image_tag=image_tag,
        network_name=network_name,
        atlas_version=version
    )
    provisioner = Provisioner(config=config)
    reader = Reader()
    return provisioner.provision(deployment_getter=reader.get_deployment_by_name)


def provision_replica_set(replicas: int = 3, arbiter: bool = False, name: str = None, priority: bool = False,
                          port: int = 27017, auth: bool = False, username: str = None, password: str = None,
                          auth_db: str = "admin", auth_roles: List[str] = None, image_repo: str = "mongo",
                          image_tag: str = "latest", network_name: str = "mongo_network") -> ReplicaSet:
    """
    Provisions and returns a replica set instance of MongoDB

    :param replicas:        The number of replica set nodes to provision
    :param arbiter:         Add an arbiter node to a replica set
    :param name:            The deployment's name; auto-generated if not provided
    :param priority:        Priority (currently ignored)
    :param port:            The deployment port
    :param auth:            Whether to enable authentication
    :param username:        Admin username
    :param password:        Admin password
    :param auth_db:         Authorization DB (currently ignored)
    :param auth_roles:      Default authentication roles (currently ignored)
    :param image_repo:      The MongoDB image name/repo
    :param image_tag:       The MongoDB image tag, which determines the MongoDB version to install
    :param network_name:    The Docker network to provision the deployment in; will create a new one or use an existing
                            one with the same name if such network exists
    :return:                ReplicaSet instance
    """
    config = ProvisionerConfig(
        replica_set=True,
        replicas=replicas,
        arbiter=arbiter,
        name=name,
        priority=priority,
        port=port,
        auth=auth,
        username=username,
        password=password,
        auth_db=auth_db,
        auth_roles=auth_roles,
        image_repo=image_repo,
        image_tag=image_tag,
        network_name=network_name
    )
    provisioner = Provisioner(config=config)
    reader = Reader()
    return provisioner.provision(deployment_getter=reader.get_deployment_by_name)


def provision_sharded_cluster(replicas: int = 3, shards: int = 2,
                              arbiter: bool = False, name: str = None, priority: bool = False,
                              port: int = 27017, config_servers: int = 1, mongos: int = 1,
                              auth: bool = False, username: str = None, password: str = None, auth_db: str = "admin",
                              auth_roles: List[str] = None, image_repo: str = "mongo", image_tag: str = "latest",
                              network_name: str = "mongo_network") -> ShardedCluster:
    """
    Provisions and returns a sharded cluster instance of MongoDB

    :param replicas:
    :param shards:
    :param arbiter:
    :param name:
    :param priority:
    :param port:
    :param config_servers:
    :param mongos:
    :param auth:
    :param username:
    :param password:
    :param auth_db:
    :param auth_roles:
    :param image_repo:
    :param image_tag:
    :param network_name:
    :return:
    """
    config = ProvisionerConfig(
        sharded=True,
        replicas=replicas,
        shards=shards,
        config_servers=config_servers,
        mongos=mongos,
        arbiter=arbiter,
        name=name,
        priority=priority,
        port=port,
        auth=auth,
        username=username,
        password=password,
        auth_db=auth_db,
        auth_roles=auth_roles,
        image_repo=image_repo,
        image_tag=image_tag,
        network_name=network_name
    )
    provisioner = Provisioner(config=config)
    reader = Reader()
    return provisioner.provision(deployment_getter=reader.get_deployment_by_name)


def get_deployment(name: str, include_stopped: bool = True) -> Union[Mongod, ReplicaSet, ShardedCluster]:
    """
    Get a deployment by name.

    :param name:            The deployment's name (required)
    :param include_stopped: Whether to include stopped deployments in the lookup
    :return:                A Deployment instance
    """
    reader = Reader()
    return reader.get_deployment_by_name(name=name, include_stopped=include_stopped)


def list_deployments(include_stopped: bool = False) -> Dict[str, Union[Mongod, ReplicaSet, ShardedCluster]]:
    """
    List all deployments.

    :param include_stopped: Whether to include stopped deployments in the lookup
    :return:                A dictionary of deployments keyed by their names
    """
    reader = Reader()
    return reader.get_all_deployments(include_stopped=include_stopped)
