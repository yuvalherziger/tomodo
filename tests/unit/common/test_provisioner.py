import logging
import platform
from unittest.mock import Mock

import docker
from _pytest.logging import LogCaptureFixture
from docker.models.containers import Container
from docker.models.networks import Network

from tomodo import Provisioner, ProvisionerConfig
from tomodo.common.models import ReplicaSet, Mongod


class TestProvisioner:

    @staticmethod
    def test_config():
        config = ProvisionerConfig()
        assert not config.is_auth_enabled
        config = ProvisionerConfig(username="foo", password="bar")
        assert config.is_auth_enabled

    @staticmethod
    def test_check_and_pull_image_found_on_machine(caplog: LogCaptureFixture, provisioner_client):
        image_name = "mongo:latest"
        provisioner = Provisioner(config=ProvisionerConfig())
        image = Mock(name=image_name)
        provisioner_client.images.get.return_value = image
        unexpected_exception_raised = False
        try:
            with caplog.at_level(logging.INFO):
                provisioner.check_and_pull_image(image_name=image_name)
        except:
            unexpected_exception_raised = True
        assert not unexpected_exception_raised, "Expected no unknown exceptions"
        assert f"Image '{image_name}' was found locally" in caplog.text, "Expected a specific log entry"

    @staticmethod
    def test_check_and_pull_image_not_found_on_machine(caplog: LogCaptureFixture, provisioner_client):
        image_name = "mongo:latest"
        provisioner = Provisioner(config=ProvisionerConfig())
        image = Mock(name=image_name)
        provisioner_client.images.get.side_effect = docker.errors.ImageNotFound(
            message="Image not found"
        )
        provisioner_client.images.pull.return_value = image
        unexpected_exception_raised = False

        try:
            with caplog.at_level(logging.INFO):
                provisioner.check_and_pull_image(image_name=image_name)
        except:
            unexpected_exception_raised = True

        assert not unexpected_exception_raised, "Expected no unknown exceptions"
        assert f"Pulled image '{image_name}' successfully" in caplog.text, "Expected a specific log entry"

    @staticmethod
    def test_check_and_pull_image_raises_exception(provisioner_client):
        image_name = "mongo:latest"
        provisioner = Provisioner(config=ProvisionerConfig())
        image = Mock(name=image_name)
        provisioner_client.images.get.side_effect = docker.errors.InvalidRepository()
        provisioner_client.images.pull.return_value = image
        unexpected_exception_raised = False

        try:
            provisioner.check_and_pull_image(image_name=image_name)
        except docker.errors.InvalidRepository:
            unexpected_exception_raised = True

        assert unexpected_exception_raised, "Expected an exception to be raised"

    @staticmethod
    def test_get_network_found(caplog: LogCaptureFixture, provisioner_client, docker_network: Network):
        provisioner = Provisioner(config=ProvisionerConfig(network_name=docker_network.name))
        provisioner_client.networks.list.return_value = [docker_network]
        with caplog.at_level(logging.INFO):
            network = provisioner.get_network()
        assert docker_network.name == network.name, "Unexpected network name value"
        assert docker_network.short_id == network.short_id, "Unexpected network short_id value"
        assert f"At least one Docker network exists with the name '{docker_network.name}'. " \
               f"Picking the first one [id: {docker_network.short_id}]" in caplog.text

    @staticmethod
    def test_get_network_not_found_and_created(caplog: LogCaptureFixture, provisioner_client, docker_network: Network):
        provisioner = Provisioner(config=ProvisionerConfig(network_name=docker_network.name))
        provisioner_client.networks.list.return_value = []
        provisioner_client.networks.create.return_value = docker_network
        with caplog.at_level(logging.INFO):
            network = provisioner.get_network()
        assert docker_network.name == network.name, "Unexpected network name value"
        assert docker_network.short_id == network.short_id, "Unexpected network short_id value"
        assert f"Docker network '{docker_network.name}' " \
               f"was created [id: {docker_network.short_id}]" in caplog.text

    @staticmethod
    def test_create_mongos_container(caplog: LogCaptureFixture, provisioner_client, docker_network: Network):
        shards = 2
        deployment_name = "unit-test"
        container_id = "0123456789abcdef"
        provisioner = Provisioner(
            config=ProvisionerConfig(name=deployment_name, shards=shards, network_name=docker_network.name)
        )
        provisioner.network = docker_network
        port = 27020
        config_db = f"{deployment_name}-cfg"
        mongos_name = f"{deployment_name}-mongos-1"
        config_svr_replicaset = ReplicaSet(members=[
            Mongod(name=f"{config_db}-1", port=27017, hostname=f"{config_db}-1"),
            Mongod(name=f"{config_db}-2", port=27018, hostname=f"{config_db}-2"),
            Mongod(name=f"{config_db}-3", port=27019, hostname=f"{config_db}-3"),
        ])
        provisioner_client.containers.run.return_value = Container(
            attrs={
                "Name": mongos_name,
                "Id": container_id
            }
        )
        with caplog.at_level(logging.INFO):
            container = provisioner.create_mongos_container(
                port=port,
                name=mongos_name,
                config_svr_replicaset=config_svr_replicaset
            )
        assert container is not None, "Container not returned"
        assert container.short_id == container_id[:12], "Unexpected container short_id value"
        assert f"Port {port} will be exposed to your host" in caplog.text
        provisioner_client.containers.run.assert_called_once_with(
            "mongo:latest",
            detach=True,
            ports={f"{port}/tcp": port},
            platform=f"linux/{platform.machine()}",
            network="0123456789abcdef",
            hostname=mongos_name,
            name=mongos_name,
            command=["mongos", "--bind_ip_all", "--port", "27020", "--configdb",
                     "None/unit-test-cfg-1:27017,unit-test-cfg-2:27018,unit-test-cfg-3:27019"],
            networking_config={"EndpointsConfig": {docker_network.name: {"Aliases": [mongos_name]}}},
            labels={
                "source": "tomodo",
                "tomodo-name": mongos_name,
                "tomodo-group": deployment_name,
                "tomodo-port": str(port),
                "tomodo-role": "mongos",
                "tomodo-type": "Sharded Cluster",
                "tomodo-shard-count": str(shards),
            }
        )

    @staticmethod
    def test_create_mongod_container(caplog: LogCaptureFixture, provisioner_client, docker_network: Network):
        # TODO: implement test
        assert True
