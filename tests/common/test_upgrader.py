from typing import List

import docker
import pytest
from pytest_mock import MockerFixture

from tomodo.common import upgrader
from tomodo.common.util import parse_semver


class TestUpgrader:

    @staticmethod
    @pytest.mark.parametrize("src, tgt, latest_first, expected",
                             [
                                 ("3.6", "4.0", False, ["4.0"]),
                                 ("3.6", "5.0", False, ["4.0", "4.2", "4.4", "5.0"]),
                                 ("3.6", "5.0", False, ["4.0", "4.2", "4.4", "5.0"]),
                                 ("3.6", "4.0", True, ["3.6.1000", "4.0"]),
                                 ("3.6", "6.0.2", True, ["3.6.1000", "4.0", "4.2", "4.4", "5.0", "6.0.2"]),
                                 ("3.6", "3.6.1000", True, ["3.6.1000"])
                             ])
    def test_get_upgrade_path(mocker: MockerFixture, src: str, tgt: str, latest_first: bool, expected: List[str]):
        if latest_first:
            mock = mocker.patch.object(upgrader, "get_full_version_from_mongo_image")
            mj, mn, _ = parse_semver(src)
            mock.return_value = mj, mn, 1000
        actual = upgrader.get_upgrade_path("hostname", src, tgt, latest_first)
        assert expected == actual, "Failed to assert the correct upgrade path"

    @staticmethod
    def test_get_full_version_from_mongo_image(mocker: MockerFixture):
        expected = 3, 6, 23
        docker_client = mocker.patch.object(docker, "from_env")

        class MockImage:
            attrs = {
                "ContainerConfig": {
                    "Env": [
                        "MONGO_VERSION=3.6.23"
                    ]
                }
            }
            tags = ["mongo:3.6.23"]

        class MockClient:
            images = {
                "mongo:3.6": MockImage()
            }

        docker_client.return_value = MockClient()
        actual = upgrader.get_full_version_from_mongo_image("3.6")
        assert expected == actual
