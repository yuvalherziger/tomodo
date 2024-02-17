import secrets
from typing import Dict
from unittest.mock import Mock

from docker.models.containers import Container

from tomodo.common.models import Mongod, ReplicaSet, ShardedCluster
from tomodo.common.reader import marshal_deployment, Reader


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
        assert isinstance(deployment, ReplicaSet), "Not a replica set"
        member_count = len(deployment.members)
        assert deployment.mongo_version == mongo_version, "Unexpected mongo version"
        assert deployment.last_known_state == "running", "Unexpected state"
        assert deployment.start_port == 27017, "Unexpected start port"
        assert member_count == replicas, "Unexpected replica count"

    @staticmethod
    def test_get_deployment_by_name_sharded_cluster(reader_client: Mock):
        depl_name = "unit-test"
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
                    "Id": "container_id",
                    "State": "running",
                    "Config": {
                        "Labels": {
                            "source": "tomodo", "tomodo-arbiter": "0",
                            "tomodo-container-data-dir": f"/data/{depl_name}-cfg-svr-{i}",
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
                    "Id": "container_id",
                    "State": "running",
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
                        "Id": "container_id",
                        "State": "running",
                        "Config": {
                            "Labels": {
                                "source": "tomodo", "tomodo-arbiter": "0",
                                "tomodo-container-data-dir": f"/data/{depl_name}-sh-{sh}-{i}",
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
        reader_client.containers.list.return_value = [
            *config_server_containers, *mongos_containers, *mongod_containers
        ]
        reader = Reader()
        deployment = reader.get_deployment_by_name(depl_name)
        assert isinstance(deployment, ShardedCluster), "Not a sharded cluster"
        assert deployment.mongo_version == mongo_version, "Unexpected mongo version"
        assert deployment.last_known_state == "running", "Unexpected state"
        assert deployment.config_svr_replicaset.start_port == cfg_start_port, "Unexpected config server start port"
        assert len(deployment.shards) == shards, "Unexpected shard count"
        assert len(deployment.config_svr_replicaset.members) == shards, "Unexpected config server count"
        assert len(deployment.routers) == mongos, "Unexpected mongos count"
        for i in range(shards):
            assert len(deployment.shards[i].members) == shards, f"Unexpected member count in shard {i}"

    @staticmethod
    def test_get_all_deployments(reader_client: Mock):
        sa_depl_name = "unit-test-sa"
        mongo_version = "7.0.0"
        rs_depl_name = "unit-test-rs"
        replicas = 5
        reader_client.containers.list.return_value = [
            Container(
                attrs={
                    "Name": sa_depl_name,
                    "Id": "container_id",
                    "State": "running",
                    "Config": {
                        "Labels": {
                            "source": "tomodo", "tomodo-arbiter": "0",
                            "tomodo-container-data-dir": f"/data/{sa_depl_name}-db",
                            "tomodo-data-dir": f"/var/tmp/tomodo/data/{sa_depl_name}-db", "tomodo-group": sa_depl_name,
                            "tomodo-name": sa_depl_name, "tomodo-port": "1000", "tomodo-role": "standalone",
                            "tomodo-shard-count": "2", "tomodo-shard-id": "0", "tomodo-type": "Standalone"
                        },
                        "Env": [f"MONGO_VERSION={mongo_version}"]
                    }
                }
            ),
            *[Container(
                attrs={
                    "Name": "mongos_name",
                    "Id": "container_id",
                    "State": "running",
                    "Config": {
                        "Labels": {
                            "source": "tomodo", "tomodo-arbiter": "0",
                            "tomodo-container-data-dir": f"/data/{rs_depl_name}-db-{i}",
                            "tomodo-data-dir": f"/var/tmp/tomodo/data/{rs_depl_name}-db-{i}", "tomodo-group": rs_depl_name,
                            "tomodo-name": f"{rs_depl_name}-{i}", "tomodo-port": str(27016 + i), "tomodo-role": "rs-member",
                            "tomodo-shard-count": "2", "tomodo-shard-id": "0", "tomodo-type": "Replica Set"
                        },
                        "Env": [f"MONGO_VERSION={mongo_version}"]
                    }
                }
            )
                for i in range(1, replicas + 1)]
        ]
        reader = Reader()
        deployments = reader.get_all_deployments()
        assert isinstance(deployments, Dict), "Unexpected returned value type"
        assert len(deployments.keys()) == 2, "Unexpected deployment count"
        assert isinstance(deployments[sa_depl_name], Mongod)
        assert isinstance(deployments[rs_depl_name], ReplicaSet)

