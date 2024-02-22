from typing import List
from unittest.mock import patch, MagicMock

from docker.models.containers import Container

from tomodo.common.models import Mongod, ReplicaSet, ShardedCluster
from tomodo.common.reader import extract_details_from_containers
from tomodo.functional import provision_standalone_instance, provision_replica_set, provision_sharded_cluster


class TestFunctional:

    @staticmethod
    @patch("tomodo.functional.Reader")
    @patch("tomodo.functional.Provisioner")
    def test_provision_standalone_instance(
            provisioner_patch: MagicMock,
            reader_patch: MagicMock,
            mongod: Mongod
    ):
        mock_provisioner_instance = provisioner_patch.return_value
        mock_provisioner_instance.provision.return_value = mongod
        res = provision_standalone_instance(
            name=mongod.name,
            port=mongod.port
        )
        mock_provisioner_instance.provision.assert_called_once()
        provisioner_patch.assert_called_once()
        assert isinstance(res, Mongod)

    @staticmethod
    @patch("tomodo.functional.Reader")
    @patch("tomodo.functional.Provisioner")
    def test_provision_replica_set(
            provisioner_patch: MagicMock,
            reader_patch: MagicMock,
            replica_set: ReplicaSet
    ):
        mock_provisioner_instance = provisioner_patch.return_value
        mock_provisioner_instance.provision.return_value = replica_set
        res = provision_replica_set(
            name=replica_set.name,
            port=replica_set.start_port
        )
        mock_provisioner_instance.provision.assert_called_once()
        provisioner_patch.assert_called_once()
        assert isinstance(res, ReplicaSet)

    @staticmethod
    @patch("tomodo.functional.Reader")
    @patch("tomodo.functional.Provisioner")
    def test_provision_sharded_cluster(
            provisioner_patch: MagicMock,
            reader_patch: MagicMock,
            sharded_cluster_containers: List[Container]
    ):
        sharded_cluster = ShardedCluster.from_container_details(
            details=extract_details_from_containers(sharded_cluster_containers))
        mock_provisioner_instance = provisioner_patch.return_value
        mock_provisioner_instance.provision.return_value = sharded_cluster
        res = provision_sharded_cluster(
            name=sharded_cluster.name
        )
        mock_provisioner_instance.provision.assert_called_once()
        provisioner_patch.assert_called_once()
        assert isinstance(res, ShardedCluster)
