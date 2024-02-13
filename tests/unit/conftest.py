from unittest.mock import Mock

import pytest
from docker.models.networks import Network


def docker_client(mocker, module: str) -> Mock:
    mock_docker_client = Mock()
    mocker.patch(module, return_value=mock_docker_client)
    return mock_docker_client


@pytest.fixture
def provisioner_client(mocker) -> Mock:
    return docker_client(mocker, "tomodo.common.provisioner.docker.from_env")


@pytest.fixture
def reader_client(mocker) -> Mock:
    module: str = "common.reader"
    return docker_client(mocker, "tomodo.common.reader.docker.from_env")


@pytest.fixture
def docker_network() -> Network:
    network_name = "unit-test-net"
    network_id = "0123456789abcdef"
    return Network(attrs={
        "Name": network_name,
        "Id": network_id,
    })
