import secrets
from typing import List, Any, Dict, Tuple
from unittest.mock import Mock, MagicMock

import pytest
from docker.models.containers import Container
from docker.models.images import Image
from docker.models.networks import Network

from tomodo import models


def docker_client(mocker, module: str) -> Mock:
    mock_docker_client = Mock()
    mocker.patch(module, return_value=mock_docker_client)
    return mock_docker_client


@pytest.fixture
def provisioner_client(mocker) -> Mock:
    return docker_client(mocker, "tomodo.common.provisioner.docker.from_env")


@pytest.fixture
def cmd_client(mocker) -> Mock:
    return docker_client(mocker, "tomodo.cmd.docker.from_env")


@pytest.fixture
def reader_client(mocker) -> Mock:
    return docker_client(mocker, "tomodo.common.reader.docker.from_env")


@pytest.fixture
def cleaner_client(mocker) -> Mock:
    return docker_client(mocker, "tomodo.common.cleaner.docker.from_env")


@pytest.fixture
def starter_client(mocker) -> Mock:
    return docker_client(mocker, "tomodo.common.starter.docker.from_env")


@pytest.fixture
def util_client(mocker) -> Mock:
    return docker_client(mocker, "tomodo.common.util.docker.from_env")


@pytest.fixture
def docker_network() -> Network:
    network_name = "unit-test-net"
    network_id = "0123456789abcdef"
    return Network(attrs={
        "Name": network_name,
        "Id": network_id,
    })


@pytest.fixture
def socket(mocker) -> Mock:
    socket_mock = Mock()
    mocker.patch("tomodo.common.util.socket.socket", return_value=socket_mock)
    return socket_mock


@pytest.fixture
def standalone_container() -> Container:
    depl_name = "unit-test-sa"
    mongo_version = "7.0.0"
    return Container(
        attrs={
            "Name": depl_name,
            "Id": secrets.token_hex(32),
            "State": "running",
            "Image": None,
            "Config": {
                "Labels": {
                    "source": "tomodo", "tomodo-arbiter": "0",
                    "tomodo-container-data-dir": "/data/db",
                    "tomodo-data-dir": f"/var/tmp/tomodo/data/{depl_name}-db", "tomodo-group": depl_name,
                    "tomodo-name": depl_name, "tomodo-port": "27017", "tomodo-role": "standalone",
                    "tomodo-shard-count": "2", "tomodo-shard-id": "0", "tomodo-type": "Standalone"
                },
                "Env": [f"MONGO_VERSION={mongo_version}"]
            }
        }
    )


@pytest.fixture
def mongod(standalone_container: Container) -> models.Mongod:
    depl_name = "unit-test-sa"
    mongo_version = "7.0.0"
    return models.Mongod(
        port=27017,
        name=depl_name,
        hostname=depl_name,
        container_id=secrets.token_hex(32),
        last_known_state="running",
        host_data_dir=f"/var/tmp/tomodo/data/{depl_name}-db",
        container_data_dir=f"/data/{depl_name}-db",
        mongo_version=mongo_version,
        container=standalone_container
    )


@pytest.fixture
def atlas_deployment(standalone_container: Container) -> models.AtlasDeployment:
    depl_name = "unit-test-atlas"
    mongo_version = "7.0.0"
    # TODO: Create Atlas container fixture.
    return models.AtlasDeployment(
        port=27017,
        name=depl_name,
        hostname=depl_name,
        container_id=secrets.token_hex(32),
        last_known_state="running",
        mongo_version=mongo_version,
        container=standalone_container
    )


@pytest.fixture
def replica_set(replica_set_containers: List[Container]) -> models.ReplicaSet:
    depl_name = "unit-test-rs"
    mongo_version = "6.0.0"
    start_port = 27017
    replicas = 3
    return models.ReplicaSet(
        name=depl_name,
        start_port=start_port,
        size=replicas,
        members=[
            models.Mongod(
                port=27017 + i - 1,
                name=f"{depl_name}-{i}",
                hostname=f"{depl_name}-{i}",
                container_id=secrets.token_hex(32),
                last_known_state="running",
                host_data_dir=f"/var/tmp/tomodo/data/{depl_name}-db-{i}",
                container_data_dir=f"/data/{depl_name}-db-{i}",
                mongo_version=mongo_version,
                container=replica_set_containers[i - 1]
            )
            for i in range(1, replicas + 1)
        ]
    )


@pytest.fixture
def config_svr_replicaset() -> models.ReplicaSet:
    deployment_name = "unit-test"
    container_id = secrets.token_hex(32)
    config_db = f"{deployment_name}-cfg"

    return models.ReplicaSet(members=[
        models.Mongod(name=f"{config_db}-1", port=27017, hostname=f"{config_db}-1"),
        models.Mongod(name=f"{config_db}-2", port=27018, hostname=f"{config_db}-2"),
        models.Mongod(name=f"{config_db}-3", port=27019, hostname=f"{config_db}-3"),
    ])


@pytest.fixture
def cleaner_os_path(mocker) -> Mock:
    os_mock = Mock()
    mocker.patch("tomodo.common.cleaner.os.path", return_value=os_mock)
    return os_mock


@pytest.fixture
def cleaner_shutil(mocker) -> Mock:
    shutil_mock = Mock()
    mocker.patch("tomodo.common.cleaner.shutil", return_value=shutil_mock)
    return shutil_mock


@pytest.fixture
def replica_set_containers() -> List[Container]:
    depl_name = "unit-test-rs"
    mongo_version = "6.0.0"
    replicas = 3
    return [
        Container(
            attrs={
                "Name": "mongos_name",
                "Id": secrets.token_hex(32),
                "State": "running",
                "Image": Image(attrs={
                    "RepoTags": ["mongo:latest"]
                }),
                "Config": {
                    "Labels": {
                        "source": "tomodo", "tomodo-arbiter": "0",
                        "tomodo-container-data-dir": "/data/db",
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


@pytest.fixture
def sharded_cluster_containers() -> List[Container]:
    depl_name = "unit-test-sc"
    mongo_version = "5.0.0"
    mongos = 2
    shards = 3
    replicas = 3
    config_servers = 3
    cfg_start_port = 2000
    mongos_start_port = cfg_start_port + config_servers
    shards_start_port = mongos_start_port + mongos

    config_server_containers = [
        Container(
            attrs={
                "Name": f"{depl_name}-cfg-svr-{i}",
                "Id": secrets.token_hex(32),
                "State": "running",
                "Image": Image(attrs={
                    "RepoTags": ["mongo:latest"]
                }),
                "Config": {
                    "Labels": {
                        "source": "tomodo", "tomodo-arbiter": "0",
                        "tomodo-container-data-dir": "/data/db",
                        "tomodo-data-dir": f"/var/tmp/tomodo/data/{depl_name}-cfg-svr-{i}",
                        "tomodo-group": depl_name,
                        "tomodo-name": f"{depl_name}-cfg-svr-{i}", "tomodo-port": cfg_start_port + i - 1,
                        "tomodo-role": "cfg-svr",
                        "tomodo-shard-count": str(shards), "tomodo-shard-id": "0", "tomodo-type": "Sharded Cluster"
                    },
                    "Env": [f"MONGO_VERSION={mongo_version}"]
                }
            }
        )
        for i in range(1, config_servers + 1)
    ]

    mongos_containers = [
        Container(
            attrs={
                "Name": f"{depl_name}-mongos-{i}",
                "Id": secrets.token_hex(32),
                "State": "running",
                "Image": Image(attrs={
                    "RepoTags": ["mongo:latest"]
                }),
                "Config": {
                    "Labels": {
                        "source": "tomodo",
                        "tomodo-group": depl_name,
                        "tomodo-name": f"{depl_name}-mongos-{i}", "tomodo-port": mongos_start_port + i - 1,
                        "tomodo-role": "mongos",
                        "tomodo-shard-count": str(shards), "tomodo-shard-id": "0", "tomodo-type": "Sharded Cluster"
                    },
                    "Env": [f"MONGO_VERSION={mongo_version}"]
                }
            }
        )
        for i in range(1, mongos + 1)
    ]
    mongod_containers = []
    for sh in range(1, shards + 1):
        mongod_containers.extend([
            Container(
                attrs={
                    "Name": f"{depl_name}-sh-{sh}-{i}",
                    "Id": secrets.token_hex(32),
                    "State": "running",
                    "Image": Image(attrs={
                        "RepoTags": ["mongo:latest"]
                    }),
                    "Config": {
                        "Labels": {
                            "source": "tomodo", "tomodo-arbiter": "0",
                            "tomodo-container-data-dir": "/data/db",
                            "tomodo-data-dir": f"/var/tmp/tomodo/data/{depl_name}-sh-{sh}-{i}",
                            "tomodo-group": depl_name,
                            "tomodo-name": f"{depl_name}-sh-{sh}-{i}",
                            "tomodo-port": shards_start_port + ((sh - 1) * replicas) + i,
                            "tomodo-role": "rs-member",
                            "tomodo-shard-count": str(shards), "tomodo-shard-id": str(sh),
                            "tomodo-type": "Sharded Cluster"
                        },
                        "Env": [f"MONGO_VERSION={mongo_version}"]
                    }
                }
            )
            for i in range(1, replicas + 1)
        ])
    return [
        *config_server_containers, *mongos_containers, *mongod_containers
    ]


def assert_partial_call(expected_args: Tuple[Any], expected_kwargs: Dict[str, Any], function_mock: Mock):
    function_mock.assert_called_once()
    actual_args, actual_kwargs = function_mock.call_args
    for arg in expected_args:
        assert arg in actual_args
    for kwarg in expected_kwargs.keys():
        if isinstance(actual_kwargs.get(kwarg), MagicMock) or isinstance(actual_kwargs.get(kwarg), Mock):
            continue
        assert actual_kwargs.get(kwarg) == expected_kwargs.get(kwarg)
