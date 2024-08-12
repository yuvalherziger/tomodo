import logging
import platform
from typing import List
from unittest.mock import Mock, patch, MagicMock, mock_open

import docker
import pytest
from _pytest.logging import LogCaptureFixture
from docker.models.containers import Container
from docker.models.networks import Network

from tests.unit.conftest import assert_partial_call
from tomodo import Provisioner, ProvisionerConfig
from tomodo.common.errors import InvalidConfiguration, DeploymentNameCollision, DeploymentNotFound
from tomodo.common.models import ReplicaSet, Mongod, Deployment


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
        provisioner_client.images.get.side_effect = ValueError()
        provisioner_client.images.pull.return_value = image
        unexpected_exception_raised = False

        try:
            provisioner.check_and_pull_image(image_name=image_name)
        except ValueError:
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
    def test_create_mongos_container(caplog: LogCaptureFixture,
                                     provisioner_client: Mock,
                                     docker_network: Network):
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
    @patch("os.path")
    @patch("os.makedirs")
    def test_create_mongod_container(makedirs_patch: MagicMock,
                                     path_patch: MagicMock,
                                     caplog: LogCaptureFixture,
                                     standalone_container: Container,
                                     provisioner_client: Mock,
                                     docker_network: Network):
        name = "unit-test-sa"
        port = 27017
        host_data_path = f"/var/tmp/tomodo/data/{name}-db"
        path_patch.join.return_value = host_data_path
        path_patch.abspath.return_value = host_data_path
        makedirs_patch.return_value = None
        provisioner_client.containers.run.return_value = standalone_container
        provisioner = Provisioner(
            config=ProvisionerConfig(name=name, port=port, network_name=docker_network.name)
        )
        provisioner.network = docker_network
        with caplog.at_level(logging.INFO):
            container = provisioner.create_mongod_container(
                port=port,
                name=name
            )
        assert_partial_call(
            function_mock=provisioner_client.containers.run,
            expected_args=("mongo:latest",),
            expected_kwargs=dict(
                detach=True,
                ports={"27017/tcp": 27017},
                platform=f"linux/{platform.machine()}",
                network="0123456789abcdef",
                hostname="unit-test-sa",
                name="unit-test-sa",
                command=[
                    "mongod",
                    "--bind_ip_all",
                    "--port",
                    "27017",
                    "--dbpath",
                    "/data/db",
                    "--logpath",
                    "/data/db/mongod.log"
                ],
                environment=[],
                labels={
                    "source": "tomodo",
                    "tomodo-name": "unit-test-sa",
                    "tomodo-group": "unit-test-sa",
                    "tomodo-port": "27017",
                    "tomodo-role": "standalone",
                    "tomodo-type": "Standalone",
                    "tomodo-data-dir": host_data_path,
                    "tomodo-container-data-dir": "/data/db",
                    "tomodo-shard-id": "0",
                    "tomodo-shard-count": "2",
                    "tomodo-arbiter": "0",
                    "tomodo-ephemeral": "0"
                }
            )
        )

    @staticmethod
    @patch("os.path")
    @patch("os.makedirs")
    def test_create_mongod_container_cfg_svr(makedirs_patch: MagicMock,
                                             path_patch: MagicMock,
                                             caplog: LogCaptureFixture,
                                             sharded_cluster_containers: List[Container],
                                             provisioner_client: Mock,
                                             docker_network: Network):
        name = "unit-test-sc"
        port = 27017
        host_data_path = f"/var/tmp/tomodo/data/{name}-db"
        path_patch.join.return_value = host_data_path
        path_patch.abspath.return_value = host_data_path
        makedirs_patch.return_value = None
        provisioner_client.containers.run.return_value = sharded_cluster_containers[0]
        provisioner = Provisioner(
            config=ProvisionerConfig(name=name, sharded=True, port=port, network_name=docker_network.name)
        )
        provisioner.network = docker_network
        with caplog.at_level(logging.INFO):
            container = provisioner.create_mongod_container(
                port=port,
                name=name,
                config_svr=True,
                replset_name=f"{name}-cfg-svr"
            )
        assert_partial_call(
            function_mock=provisioner_client.containers.run,
            expected_args=("mongo:latest",),
            expected_kwargs=dict(
                detach=True,
                ports={"27017/tcp": 27017},
                platform=f"linux/{platform.machine()}",
                network="0123456789abcdef",
                hostname=name,
                name=name,
                command=[
                    "mongod",
                    "--bind_ip_all",
                    "--port",
                    "27017",
                    "--dbpath",
                    "/data/db",
                    "--logpath",
                    "/data/db/mongod.log",
                    "--configsvr",
                    "--replSet",
                    f"{name}-cfg-svr"
                ],
                environment=[],
                labels={
                    "source": "tomodo",
                    "tomodo-name": name,
                    "tomodo-group": name,
                    "tomodo-port": "27017",
                    "tomodo-role": "cfg-svr",
                    "tomodo-type": "Sharded Cluster",
                    "tomodo-data-dir": host_data_path,
                    "tomodo-container-data-dir": f"/data/db",
                    "tomodo-shard-id": "0",
                    "tomodo-shard-count": "2",
                    "tomodo-arbiter": "0",
                    "tomodo-ephemeral": "0"
                }
            )
        )

    @staticmethod
    @patch("os.path")
    @patch("os.makedirs")
    def test_create_mongod_container_replica_set(makedirs_patch: MagicMock,
                                                 path_patch: MagicMock,
                                                 caplog: LogCaptureFixture,
                                                 replica_set_containers: List[Container],
                                                 provisioner_client: Mock,
                                                 docker_network: Network):
        name = "unit-test-sc"
        port = 27017
        host_data_path = f"/var/tmp/tomodo/data/{name}-db"
        path_patch.join.return_value = host_data_path
        path_patch.abspath.return_value = host_data_path
        makedirs_patch.return_value = None
        provisioner_client.containers.run.return_value = replica_set_containers[0]
        provisioner = Provisioner(
            config=ProvisionerConfig(name=name, replica_set=True, port=port, network_name=docker_network.name)
        )
        provisioner.network = docker_network
        with caplog.at_level(logging.INFO):
            container = provisioner.create_mongod_container(
                port=port,
                name=name,
                replset_name=name
            )
        assert_partial_call(
            function_mock=provisioner_client.containers.run,
            expected_args=("mongo:latest",),
            expected_kwargs=dict(
                detach=True,
                ports={"27017/tcp": 27017},
                platform=f"linux/{platform.machine()}",
                network="0123456789abcdef",
                hostname=name,
                name=name,
                command=[
                    "mongod",
                    "--bind_ip_all",
                    "--port",
                    "27017",
                    "--dbpath",
                    "/data/db",
                    "--logpath",
                    "/data/db/mongod.log",
                    "--replSet",
                    name
                ],
                environment=[],
                labels={
                    "source": "tomodo",
                    "tomodo-name": name,
                    "tomodo-group": name,
                    "tomodo-port": "27017",
                    "tomodo-role": "rs-member",
                    "tomodo-type": "Replica Set",
                    "tomodo-data-dir": host_data_path,
                    "tomodo-container-data-dir": "/data/db",
                    "tomodo-shard-id": "0",
                    "tomodo-shard-count": "2",
                    "tomodo-arbiter": "0",
                    "tomodo-ephemeral": "0"
                }
            )
        )

    @staticmethod
    @pytest.mark.parametrize("authenticated, key_exists", [(False, False), (True, False), (True, True)])
    @patch("os.chmod")
    @patch("os.path")
    @patch("os.makedirs")
    def test_create_mongod_container_shard(makedirs_patch: MagicMock,
                                           path_patch: MagicMock,
                                           chmod_patch: MagicMock,
                                           authenticated: bool,
                                           key_exists: bool,
                                           caplog: LogCaptureFixture,
                                           sharded_cluster_containers: List[Container],
                                           provisioner_client: Mock,
                                           docker_network: Network):
        name = "unit-test-sc"
        port = 27017
        host_data_path = f"/var/tmp/tomodo/data/{name}-db"
        path_patch.join.return_value = host_data_path
        path_patch.abspath.return_value = host_data_path
        makedirs_patch.return_value = None
        provisioner_client.containers.run.return_value = sharded_cluster_containers[0]
        username = None
        password = None
        if authenticated:
            username = "username"
            password = "password"
            path_patch.isfile.return_value = key_exists
        provisioner = Provisioner(
            config=ProvisionerConfig(
                name=name, sharded=True, port=port, network_name=docker_network.name,
                username=username, password=password
            )
        )
        provisioner.network = docker_network
        cmd_extra = []
        environment = []
        with caplog.at_level(logging.INFO):
            with patch("builtins.open", mock_open()) as mocked_keyfile:
                container = provisioner.create_mongod_container(
                    port=port,
                    name=name,
                    replset_name=f"{name}-sh-01"
                )
                if authenticated:
                    environment = ["MONGO_INITDB_ROOT_USERNAME=username", "MONGO_INITDB_ROOT_PASSWORD=password"]
                    cmd_extra = ["--keyFile", "/etc/mongo/mongo_keyfile"]
                    if not key_exists:
                        mocked_keyfile().write.assert_called_once()
        assert_partial_call(
            function_mock=provisioner_client.containers.run,
            expected_args=("mongo:latest",),
            expected_kwargs=dict(
                detach=True,
                ports={"27017/tcp": 27017},
                platform=f"linux/{platform.machine()}",
                network="0123456789abcdef",
                hostname=name,
                name=name,
                command=[
                    "mongod",
                    "--bind_ip_all",
                    "--port",
                    "27017",
                    "--dbpath",
                    "/data/db",
                    "--logpath",
                    "/data/db/mongod.log",
                    *cmd_extra,
                    "--shardsvr",
                    "--replSet",
                    f"{name}-sh-01",
                ],
                environment=environment,
                labels={
                    "source": "tomodo",
                    "tomodo-name": name,
                    "tomodo-group": name,
                    "tomodo-port": "27017",
                    "tomodo-role": "rs-member",
                    "tomodo-type": "Sharded Cluster",
                    "tomodo-data-dir": host_data_path,
                    "tomodo-container-data-dir": "/data/db",
                    "tomodo-shard-id": "0",
                    "tomodo-shard-count": "2",
                    "tomodo-arbiter": "0",
                    "tomodo-ephemeral": "0"
                }
            )
        )

    @staticmethod
    def test_provision_fails_with_multiple_types(caplog: LogCaptureFixture,
                                                 provisioner_client: Mock,
                                                 docker_network: Network
                                                 ):
        raised = False
        try:
            provisioner = Provisioner(
                config=ProvisionerConfig(
                    sharded=True, standalone=True
                )
            )
            provisioner.provision(deployment_getter=None)
        except InvalidConfiguration:
            raised = True
        assert raised, "Exception not raised when expected"

    @staticmethod
    def test_provision_fails_for_arbiter_standalone(caplog: LogCaptureFixture,
                                                    provisioner_client: Mock,
                                                    docker_network: Network
                                                    ):
        raised = False
        try:
            provisioner = Provisioner(
                config=ProvisionerConfig(
                    standalone=True, arbiter=True
                )
            )
            provisioner.provision(deployment_getter=None)
        except InvalidConfiguration:
            raised = True
        assert raised, "Exception not raised when expected"

    @staticmethod
    def test_provision_fails_with_name_collision(caplog: LogCaptureFixture,
                                                 provisioner_client: Mock,
                                                 docker_network: Network
                                                 ):
        raised = False
        try:
            provisioner = Provisioner(
                config=ProvisionerConfig(
                    standalone=True
                )
            )
            provisioner.provision(deployment_getter=lambda x: x)
        except DeploymentNameCollision:
            raised = True
        assert raised, "Exception not raised when expected"

    @staticmethod
    @patch("tomodo.common.provisioner.is_port_range_available")
    @patch("os.path")
    @patch("os.makedirs")
    def test_provision_standalone(makedirs_patch: MagicMock,
                                  path_patch: MagicMock,
                                  is_port_range_available_patch: MagicMock,
                                  caplog: LogCaptureFixture,
                                  standalone_container: Container,
                                  provisioner_client: Mock,
                                  docker_network: Network
                                  ):
        config = ProvisionerConfig(
            standalone=True
        )
        host_data_path = f"/var/tmp/tomodo/data/{config.name}-db"
        image_name = "mongo:latest"
        image = Mock(name=image_name)
        provisioner_client.images.get.return_value = image
        provisioner_client.networks.list.return_value = [docker_network]
        makedirs_patch.return_value = None
        path_patch.normcase.return_value = ""
        provisioner_client.containers.run.return_value = standalone_container

        def deployment_getter(name: str):
            raise DeploymentNotFound

        raised = False

        provisioner = Provisioner(config=config)
        provisioner.network = docker_network
        with patch.object(Provisioner, "wait_for_mongod_readiness", return_value=None) as readiness_mock:
            # with patch.object(Provisioner, "print_connection_details", return_value=None):
            #     deployment: Deployment = provisioner.provision(deployment_getter=deployment_getter)
            #     readiness_mock.assert_called_once()
            deployment: Deployment = provisioner.provision(deployment_getter=deployment_getter)
            readiness_mock.assert_called_once()
        assert isinstance(deployment, Mongod)

    @staticmethod
    @patch("tomodo.common.provisioner.is_port_range_available")
    @patch("tomodo.common.provisioner.run_mongo_shell_command")
    @patch("os.path")
    @patch("os.makedirs")
    def test_provision_replica_set(makedirs_patch: MagicMock,
                                   path_patch: MagicMock,
                                   run_mongo_shell_command_patch: MagicMock,
                                   is_port_range_available_patch: MagicMock,
                                   caplog: LogCaptureFixture,
                                   replica_set_containers: List[Container],
                                   provisioner_client: Mock,
                                   docker_network: Network
                                   ):
        config = ProvisionerConfig(
            replica_set=True,
            username="username",
            password="password"
        )
        host_data_path = f"/var/tmp/tomodo/data/{config.name}-db"
        image_name = "mongo:latest"
        image = Mock(name=image_name)
        provisioner_client.images.get.return_value = image
        provisioner_client.networks.list.return_value = [docker_network]
        makedirs_patch.return_value = None
        path_patch.normcase.return_value = ""
        provisioner_client.containers.run.side_effect = replica_set_containers

        def deployment_getter(name: str):
            raise DeploymentNotFound

        raised = False

        provisioner = Provisioner(config=config)
        provisioner.network = docker_network
        with patch.object(Provisioner, "wait_for_mongod_readiness", return_value=None) as readiness_mock:
            deployment: Deployment = provisioner.provision(deployment_getter=deployment_getter)
            assert readiness_mock.call_count == 3
        assert isinstance(deployment, ReplicaSet)

    @staticmethod
    @patch("tomodo.common.provisioner.run_mongo_shell_command")
    def test_wait_for_mongod_readiness_ready(run_mongo_shell_command_patch: MagicMock,
                                             mongod: Mongod,
                                             caplog: LogCaptureFixture):
        config = ProvisionerConfig(standalone=True)
        run_mongo_shell_command_patch.return_value = (0, "1", None)
        provisioner = Provisioner(config=config)
        with caplog.at_level(logging.INFO):
            provisioner.wait_for_mongod_readiness(mongod=mongod)
        assert f"Server {mongod.name} is ready to accept connections" in caplog.text

    @staticmethod
    @patch("tomodo.common.provisioner.run_mongo_shell_command")
    def test_wait_for_mongod_readiness_eventually_ready(run_mongo_shell_command_patch: MagicMock,
                                                        mongod: Mongod,
                                                        caplog: LogCaptureFixture):
        config = ProvisionerConfig(standalone=True)
        run_mongo_shell_command_patch.side_effect = [(0, "A", None), (0, "0", None), (0, "1", None)]
        provisioner = Provisioner(config=config)
        with caplog.at_level(logging.DEBUG):
            provisioner.wait_for_mongod_readiness(mongod=mongod)
        assert f"Server {mongod.name} is not ready to accept connections" in caplog.text
        assert f"Server {mongod.name} is ready to accept connections" in caplog.text
