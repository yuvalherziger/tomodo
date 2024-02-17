import secrets
from unittest.mock import Mock

from docker.models.containers import Container

from tomodo.common.models import Mongod, ReplicaSet
from tomodo.common.reader import marshal_deployment, split_into_chunks, Reader


class TestReader:

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
    def test_split_into_chunks():
        _input = [
            "shard-0-1", "shard-0-2", "shard-0-3",
            "shard-1-1", "shard-1-2", "shard-1-3",
            "shard-2-1", "shard-2-2", "shard-2-3",
        ]
        expected = [
            ["shard-0-1", "shard-0-2", "shard-0-3"],
            ["shard-1-1", "shard-1-2", "shard-1-3"],
            ["shard-2-1", "shard-2-2", "shard-2-3"],
        ]
        actual = split_into_chunks(_input, 3)
        assert expected == actual

    @staticmethod
    def test_get_deployment_by_name_standalone(reader_client: Mock):
        depl_name = "unit-test"
        mongo_version = "7.0.0"
        reader_client.containers.list.return_value = [
            Container(
                attrs={
                    "Name": depl_name,
                    "Id": "container_id",
                    "State": "running",
                    "Config": {
                        "Labels": {
                            "source": "tomodo", "tomodo-arbiter": "0",
                            "tomodo-container-data-dir": f"/data/{depl_name}-db",
                            "tomodo-data-dir": f"/var/tmp/tomodo/data/{depl_name}-db", "tomodo-group": depl_name,
                            "tomodo-name": depl_name, "tomodo-port": "27017", "tomodo-role": "standalone",
                            "tomodo-shard-count": "2", "tomodo-shard-id": "0", "tomodo-type": "Standalone"
                        },
                        "Env": [f"MONGO_VERSION={mongo_version}"]
                    }
                }
            )
        ]
        reader = Reader()
        deployment = reader.get_deployment_by_name(depl_name)
        assert isinstance(deployment, Mongod)
        assert deployment.mongo_version == mongo_version
        assert deployment.last_known_state == "running"

    @staticmethod
    def test_get_deployment_by_name_replica_set(reader_client: Mock):
        depl_name = "unit-test"
        mongo_version = "6.0.0"
        replicas = 3
        reader_client.containers.list.return_value = [
            Container(
                attrs={
                    "Name": "mongos_name",
                    "Id": "container_id",
                    "State": "running",
                    "Config": {
                        "Labels": {
                            "source": "tomodo", "tomodo-arbiter": "0",
                            "tomodo-container-data-dir": f"/data/{depl_name}-db-{i}",
                            "tomodo-data-dir": f"/var/tmp/tomodo/data/{depl_name}-db-{i}", "tomodo-group": depl_name,
                            "tomodo-name": f"{depl_name}-{i}", "tomodo-port": 27016 + i, "tomodo-role": "rs-member",
                            "tomodo-shard-count": "2", "tomodo-shard-id": "0", "tomodo-type": "Replica Set"
                        },
                        "Env": [f"MONGO_VERSION={mongo_version}"]
                    }
                }
            )
            for i in range(1, replicas + 1)
        ]
        reader = Reader()
        deployment = reader.get_deployment_by_name(depl_name)
        assert isinstance(deployment, ReplicaSet)
        assert deployment.mongo_version == mongo_version
        assert deployment.last_known_state == "running"
