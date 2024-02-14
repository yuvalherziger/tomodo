import secrets
from unittest.mock import Mock

from _pytest.logging import LogCaptureFixture
from docker.models.containers import Container

from tomodo.common.models import Mongod, ReplicaSet
from tomodo.common.reader import marshal_deployment


class TestReader:

    @staticmethod
    def test_get_deployment_by_name_standalone(caplog: LogCaptureFixture, reader_client: Mock):
        # reader_client.containers.list.return_value = [
        #     Container(
        #         attrs={
        #             "Name": mongos_name,
        #             "Id": container_id
        #         }
        #     )
        # ]
        assert True

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
