import logging
from contextlib import ExitStack
from typing import List
from unittest.mock import Mock, patch

from _pytest.logging import LogCaptureFixture
from docker.models.containers import Container

from tomodo.common.starter import Starter


class TestStarter:

    @staticmethod
    def test_start_deployment_standalone(starter_client: Mock, standalone_container: Container,
                                         caplog: LogCaptureFixture):
        depl_name = "unit-test-sa"
        starter_client.containers.list.return_value = [standalone_container]
        starter_client.containers.get.return_value = standalone_container
        container_id = standalone_container.short_id
        starter = Starter()
        with patch.object(standalone_container, "start") as mock_start:
            with caplog.at_level(logging.INFO):
                starter.start_deployment(name=depl_name)
                mock_start.assert_called_once()
                assert f"Starting container {container_id}" in caplog.text

    @staticmethod
    def test_start_deployment_replica_set(starter_client: Mock, replica_set_containers: List[Container],
                                          caplog: LogCaptureFixture):
        depl_name = "unit-test-sa"
        starter_client.containers.list.return_value = replica_set_containers
        starter_client.containers.get.side_effect = replica_set_containers

        starter = Starter()
        with caplog.at_level(logging.INFO):
            with ExitStack() as stack:
                mocks = [stack.enter_context(patch.object(container, "start")) for container in replica_set_containers]
                container_ids = [container.short_id for container in replica_set_containers]
                starter.start_deployment(name=depl_name)
            for mock_start in mocks:
                mock_start.assert_called_once()

        for container_id in container_ids:
            assert f"Starting container {container_id}" in caplog.text
        assert f"Deployment {depl_name} is starting up" in caplog.text

    @staticmethod
    def test_start_deployment_sharded_cluster(starter_client: Mock, sharded_cluster_containers: List[Container],
                                              caplog: LogCaptureFixture):
        depl_name = "unit-test-sa"
        starter_client.containers.list.return_value = sharded_cluster_containers
        starter_client.containers.get.side_effect = sharded_cluster_containers

        starter = Starter()
        with caplog.at_level(logging.INFO):
            with ExitStack() as stack:
                mocks = [stack.enter_context(patch.object(container, "start")) for container in
                         sharded_cluster_containers]
                container_ids = [container.short_id for container in sharded_cluster_containers]
                starter.start_deployment(name=depl_name)
            for mock_start in mocks:
                mock_start.assert_called_once()

        assert f"Starting config server replica" in caplog.text
        assert f"Starting mongos router" in caplog.text
        assert f"Starting shard replica set member" in caplog.text
