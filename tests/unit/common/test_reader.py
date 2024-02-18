import secrets
from typing import Dict, List
from unittest.mock import Mock

from docker.models.containers import Container

from tomodo.common.errors import InvalidDeploymentType, EmptyDeployment
from tomodo.common.models import Mongod, ReplicaSet, ShardedCluster
from tomodo.common.reader import marshal_deployment, Reader, list_deployments_in_markdown_table


class TestReader:

    @staticmethod
    def test_marshal_deployment_with_invalid_type(reader_client: Mock):
        container_name = "unit-test"
        container_id = "0123456789abcdef"
        state = "running"
        container = Container(
            attrs={
                "Name": container_name,
                "Id": container_id,
                "State": state,
            }
        )
        component = {
            "tomodo-type": "MySQL",
            "tomodo-container": container,
            "tomodo-mongo-version": "7.0.0",
            "tomodo-port": "27017",
            "tomodo-name": container_name,
            "tomodo-container-id": container_id,
            "tomodo-data-dir": "/path/to/data",
            "tomodo-container-data-dir": "/path/to/data",
            "tomodo-arbiter": "0",
        }
        raised = False
        try:
            deployment = marshal_deployment(components=[component])
        except InvalidDeploymentType:
            raised = True
        assert raised, "Expected exception not raised"

    @staticmethod
    def test_marshal_empty_deployment(reader_client: Mock):
        raised = False
        try:
            deployment = marshal_deployment(components=[])
        except EmptyDeployment:
            raised = True
        assert raised, "Expected exception not raised"

    @staticmethod
    def test_marshal_deployment_as_standalone(reader_client: Mock):
        container_name = "unit-test"
        container_id = "0123456789abcdef"
        state = "running"
        container = Container(
            attrs={
                "Name": container_name,
                "Id": container_id,
                "State": state,
            }
        )
        component = {
            "tomodo-type": "Standalone",
            "tomodo-container": container,
            "tomodo-mongo-version": "7.0.0",
            "tomodo-port": "27017",
            "tomodo-name": container_name,
            "tomodo-container-id": container_id,
            "tomodo-data-dir": "/path/to/data",
            "tomodo-container-data-dir": "/path/to/data",
            "tomodo-arbiter": "0",
        }
        deployment = marshal_deployment(components=[component])
        assert isinstance(deployment, Mongod)
        assert deployment.port == 27017
        assert deployment.hostname == container_name
        assert deployment.container_id == container_id[:12]
        assert deployment.last_known_state == "running"

    @staticmethod
    def test_marshal_deployment_as_replica_set(reader_client: Mock):
        container_name = "unit-test-rs"
        start_port = 27017
        replicas = 5
        container_ids = [
            secrets.token_hex(32)
            for _ in range(replicas)
        ]
        state = "running"
        containers = [
            Container(
                attrs={
                    "Name": f"{container_name}-{i + 1}",
                    "Id": container_ids[i],
                    "State": state,
                }
            ) for i in range(replicas)
        ]
        components = [{
            "tomodo-type": "Replica Set",
            "tomodo-container": containers[i],
            "tomodo-mongo-version": "7.0.0",
            "tomodo-port": str(start_port + i),
            "tomodo-name": container_name,
            "tomodo-container-id": container_ids[i],
            "tomodo-data-dir": f"/path/to/data-{i + 1}",
            "tomodo-container-data-dir": f"/path/to/data-{i + 1}",
            "tomodo-arbiter": "0",
        } for i in range(replicas)]
        deployment = marshal_deployment(components=components)
        assert isinstance(deployment, ReplicaSet)
        assert deployment.port_range == f"{start_port}-{start_port + replicas - 1}"

    @staticmethod
    def test_get_deployment_by_name_standalone(standalone_container: Container, reader_client: Mock):
        depl_name = "unit-test-sa"
        mongo_version = "7.0.0"
        reader_client.containers.list.return_value = [standalone_container]
        reader = Reader()
        deployment = reader.get_deployment_by_name(depl_name)
        assert isinstance(deployment, Mongod)
        assert deployment.mongo_version == mongo_version
        assert isinstance(deployment.as_markdown_table(), str)
        assert isinstance(deployment.as_markdown_table_row(name=deployment.name), str)
        assert deployment.last_known_state == "running"

    @staticmethod
    def test_get_deployment_by_name_replica_set(replica_set_containers: List[Container], reader_client: Mock):
        depl_name = "unit-test-rs"
        mongo_version = "6.0.0"
        replicas = 3
        reader_client.containers.list.return_value = replica_set_containers
        reader = Reader()
        deployment = reader.get_deployment_by_name(depl_name)
        assert isinstance(deployment, ReplicaSet), "Not a replica set"
        member_count = len(deployment.members)
        assert deployment.mongo_version == mongo_version, "Unexpected mongo version"
        assert deployment.last_known_state == "running", "Unexpected state"
        assert deployment.start_port == 27017, "Unexpected start port"
        assert deployment.hostname == "mongodb://unit-test-rs-1:27017,unit-test-rs-2:27018,unit-test-rs-3:27019/" \
                                      "?replicaSet=unit-test-rs", "Unexpected hostname"
        assert isinstance(deployment.as_markdown_table(), str)
        assert member_count == replicas, "Unexpected replica count"

    @staticmethod
    def test_get_deployment_by_name_sharded_cluster(sharded_cluster_containers: List[Container], reader_client: Mock):
        depl_name = "unit-test-sc"
        mongo_version = "5.0.0"
        mongos = 2
        shards = 3
        cfg_start_port = 2000
        reader_client.containers.list.return_value = sharded_cluster_containers
        reader = Reader()
        deployment = reader.get_deployment_by_name(depl_name)
        assert isinstance(deployment, ShardedCluster), "Not a sharded cluster"
        assert deployment.mongo_version == mongo_version, "Unexpected mongo version"
        assert deployment.last_known_state == "running", "Unexpected state"
        assert deployment.config_svr_replicaset.start_port == cfg_start_port, "Unexpected config server start port"
        assert len(deployment.shards) == shards, "Unexpected shard count"
        assert len(deployment.config_svr_replicaset.members) == shards, "Unexpected config server count"
        assert len(deployment.routers) == mongos, "Unexpected mongos count"
        assert deployment.container_count == 14
        assert deployment.port_range == "2000-2013"
        assert isinstance(deployment.as_markdown_table(), str)
        assert isinstance(deployment.as_dict(detailed=False), Dict)
        assert isinstance(deployment.as_dict(detailed=True), Dict)
        for i in range(shards):
            assert len(deployment.shards[i].members) == shards, f"Unexpected member count in shard {i}"

    @staticmethod
    def test_get_all_deployments(standalone_container: Container, replica_set_containers: List[Container],
                                 reader_client: Mock):
        sa_depl_name = "unit-test-sa"
        rs_depl_name = "unit-test-rs"
        reader_client.containers.list.return_value = [
            standalone_container,
            *replica_set_containers
        ]
        reader = Reader()
        deployments = reader.get_all_deployments()
        assert isinstance(deployments, Dict), "Unexpected returned value type"
        assert len(deployments.keys()) == 2, "Unexpected deployment count"
        assert isinstance(deployments[sa_depl_name], Mongod)
        assert isinstance(deployments[rs_depl_name], ReplicaSet)

    @staticmethod
    def test_describe_by_name(sharded_cluster_containers: List[Container], reader_client: Mock):
        depl_name = "unit-test-sc"
        reader_client.containers.list.return_value = sharded_cluster_containers
        reader = Reader()
        description = reader.describe_by_name(name=depl_name)
        assert isinstance(description, str), "Not a sharded cluster"

    @staticmethod
    def test_describe_all(standalone_container: Container, replica_set_containers: List[Container],
                          reader_client: Mock):
        sa_depl_name = "unit-test-sa"
        rs_depl_name = "unit-test-rs"
        reader_client.containers.list.return_value = [
            standalone_container,
            *replica_set_containers
        ]
        reader = Reader()
        descriptions = reader.describe_all()
        assert isinstance(descriptions, List), "Unexpected returned value type"

    @staticmethod
    def test_list_deployments_in_markdown_table(mongod, replica_set, reader_client: Mock):
        reader = Reader()
        md_table = list_deployments_in_markdown_table({
            mongod.name: mongod,
            replica_set.name: replica_set,
        })
        assert isinstance(md_table, str), "Unexpected returned value type"
