import json
import random
import secrets

import pytest

from tomodo import ProvisionerConfig, Provisioner, Reader, Cleaner
from tomodo.common.errors import DeploymentNotFound
from tomodo.common.models import Deployment, Mongod
from tomodo.common.util import run_mongo_shell_command

db = "int_tst_db"
coll = "int_tst_coll"


def seed_collection_data(mongod: Mongod, config: ProvisionerConfig, num_docs: int = 10) -> (int, str, str):
    docs = json.dumps([{"doc_num": doc_num} for doc_num in range(num_docs)])
    cmd = f"db.getSiblingDB('{db}').{coll}.insertMany({docs})"
    return run_mongo_shell_command(mongo_cmd=cmd, mongod=mongod, config=config)


def get_doc_count(mongod: Mongod, config: ProvisionerConfig) -> int:
    cmd = f"db.getSiblingDB('{db}').{coll}.estimatedDocumentCount()"
    _, output, _ = run_mongo_shell_command(mongo_cmd=cmd, mongod=mongod, config=config)
    return int(output)


class TestDeploymentCreation:
    @staticmethod
    @pytest.mark.parametrize("image_tag", ["5.0", "6.0", "7.0", "latest"])
    @pytest.mark.parametrize("with_auth", [True, False])
    def test_standalone_provisioning(image_tag: str, with_auth: bool):
        port = random.randint(27000, 57000)
        suffix = secrets.token_hex(2)
        name = f"int-tst-{suffix}"
        username = None
        password = None
        if with_auth:
            username = "user"
            password = "password"
        try:
            config = ProvisionerConfig(
                name=name,
                port=port,
                standalone=True,
                image_tag=image_tag,
                username=username,
                password=password
            )
            provisioner = Provisioner(config=config)
            deployment: Deployment = provisioner.provision(
                deployment_getter=Reader().get_deployment_by_name
            )
            num_docs = 10
            assert isinstance(deployment, Mongod), "Not a standalone deployment"
            seed_collection_data(mongod=deployment, config=config, num_docs=num_docs)
            estimated_count = get_doc_count(mongod=deployment, config=config)
            assert estimated_count == num_docs, "Unexpected document count"
        except Exception as e:
            assert False, f"Provisioning failed. Exception {str(e)}"
        finally:
            cleaner = Cleaner()
            try:
                cleaner.delete_deployment(name=name)
            except DeploymentNotFound:
                pass

    @staticmethod
    @pytest.mark.parametrize("image_tag", ["5.0", "6.0", "7.0", "latest"])
    @pytest.mark.parametrize("replicas", [3, 5, 7])
    def test_replica_set_provisioning(image_tag: str, replicas: int):
        suffix = secrets.token_hex(2)
        port = random.randint(27000, 57000)
        name = f"int-tst-{suffix}"
        try:
            config = ProvisionerConfig(
                name=name,
                port=port,
                replica_set=True,
                replicas=replicas,
                image_tag=image_tag
            )
            provisioner = Provisioner(config=config)
            deployment: Deployment = provisioner.provision(
                deployment_getter=Reader().get_deployment_by_name
            )
            num_docs = 10
            assert isinstance(deployment, ReplicaSet), "Not a replica set deployment"
            mongod = deployment.members[0]
            seed_collection_data(mongod=mongod, config=config, num_docs=num_docs)
            estimated_count = get_doc_count(mongod=mongod, config=config)
            assert estimated_count == num_docs, "Unexpected document count"
        except Exception as e:
            assert False, f"Provisioning failed. Exception {str(e)}"
        finally:
            cleaner = Cleaner()
            try:
                cleaner.delete_deployment(name=name)
            except DeploymentNotFound:
                pass

    @staticmethod
    @pytest.mark.parametrize("image_tag", ["5.0", "6.0", "7.0", "latest"])
    @pytest.mark.parametrize("replicas", [3])
    @pytest.mark.parametrize("shards", [1, 3])
    @pytest.mark.parametrize("mongos", [1, 2])
    def test_sharded_cluster_provisioning(image_tag: str, replicas: int, shards: int, mongos: int):
        suffix = secrets.token_hex(2)
        name = f"int-tst-{suffix}"
        port = random.randint(27000, 57000)
        try:
            config = ProvisionerConfig(
                name=name,
                port=port,
                sharded=True,
                shards=shards,
                replicas=replicas,
                mongos=mongos,
                image_tag=image_tag
            )
            provisioner = Provisioner(config=config)
            deployment: Deployment = provisioner.provision(
                deployment_getter=Reader().get_deployment_by_name
            )
            num_docs = 10
            assert isinstance(deployment, ShardedCluster), "Not a sharded cluster deployment"
            mongos = deployment.routers[0]
            seed_collection_data(mongod=mongos, config=config, num_docs=num_docs)
            estimated_count = get_doc_count(mongod=mongos, config=config)
            assert estimated_count == num_docs, "Unexpected document count"
        except Exception as e:
            assert False, f"Provisioning failed. Exception {str(e)}"
        finally:
            cleaner = Cleaner()
            try:
                cleaner.delete_deployment(name=name)
            except DeploymentNotFound:
                pass
