import os
from typing import Dict, Union, List
from urllib.parse import urlparse, quote, urlunparse

from ruamel.yaml import YAML, yaml_object

from tomodo.common.models import Deployment

yaml = YAML()

Deployments = Dict[str, Deployment]


@yaml_object(yaml)
class TomodoState(object):
    deployments: Deployments = {}

    def __init__(self, path: str, deployments: Deployments = None):
        self.path = path
        self.deployments = deployments or {}

    @staticmethod
    def from_file(file_path: str) -> "TomodoState":
        with open(file_path, "r") as file:
            data = yaml.load(file)
        return TomodoState(**data)

    def write_to_disk(self) -> None:
        with open(self.path, "w") as file:
            yaml.dump(self, file)


@yaml_object(yaml)
class UpgradeConfig(object):
    def __init__(
            self,
            target_version: str,
            hostname: str,
            image_registry_name: str = "mongo",
            standalone: bool = False,
            container_creation_retries: int = 5,
            container_creation_delay: int = 5,
            mongodb_operation_retries: int = 5,
            mongodb_operation_delay: int = 5,
            image_tag_mapping: Union[Dict[str, str], None] = None,
            username: Union[str, None] = None,
            password: Union[str, None] = None,
            lagging_fcv: bool = True,
            container_name: str = None,
            force_auth_on_exec: bool = False,
            log_file_path: Union[str, None] = None,
            state_file_path: str = "./.tomodo-state.json",
            begin_with_current_latest: bool = False,
            log_level: str = "INFO"
    ):
        if not hostname.startswith("mongodb://") and not hostname.startswith("mongodb+srv://"):
            raise ValueError("Invalid hostname - the MongoDB hostname must start with a valid MongoDB scheme")

        self.target_version = str(target_version)
        self.localhost = "mongodb://localhost:27017"
        self.standalone = standalone
        self.hostname = hostname
        self.image_registry_name = image_registry_name
        self.container_creation_retries = container_creation_retries
        self.container_creation_delay = container_creation_delay
        self.mongodb_operation_retries = mongodb_operation_retries
        self.mongodb_operation_delay = mongodb_operation_delay
        self.image_tag_mapping = image_tag_mapping
        self.container_name = container_name
        self.force_auth_on_exec = force_auth_on_exec
        self.username = username
        self.password = password
        self.lagging_fcv = lagging_fcv
        self.log_file_path = log_file_path
        self.state_file_path = state_file_path
        self.begin_with_current_latest = begin_with_current_latest
        self.log_level = log_level
        self.parse_hostname()

    def parse_hostname(self) -> None:
        components = urlparse(self.hostname)
        netloc = components.netloc
        localhost = "localhost"
        if self.username and self.password:
            netloc = f"{self.username}:{quote(self.password)}@{components.hostname}"
            if components.port:
                netloc = f"{netloc}:{components.port}"
            localhost = f"{self.username}:{quote(self.password)}@localhost"
        else:
            if components.username and components.password:
                self.username = components.username
                self.password = components.password
        if components.port:
            localhost = f"{localhost}:{components.port}"
        self.hostname = urlunparse((
            components.scheme or "mongodb",
            netloc,
            components.path,
            components.params,
            components.query,
            components.fragment,
        ))
        self.localhost = urlunparse((
            components.scheme or "mongodb",
            localhost,
            "",
            "",
            "",
            "",
        ))

    @staticmethod
    def from_file(file_path: str) -> "UpgradeConfig":
        with open(file_path, "r") as file:
            data = yaml.load(file)
        data["password"] = os.environ.get("MONGODB_PASSWORD", data.get("password"))
        return UpgradeConfig(**data)


class ProvisionerConfig:

    def __init__(self, standalone: bool = False, replica_set: bool = False, replicas: int = 3, shards: int = 2,
                 arbiter: bool = False, name: str = "replicaset", priority: bool = False,
                 sharded: bool = False, port: int = 27017, config_servers: int = 1, mongos: int = 1,
                 auth: bool = False, username: str = None, password: str = None, auth_db: str = "admin",
                 auth_roles: List[str] = None, image_repo: str = "mongo", image_tag: str = "7.0",
                 append_to_hosts: bool = False, network_name: str = "mongo_network"):
        self.standalone = standalone
        self.replica_set = replica_set
        self.replicas = replicas
        self.shards = shards
        self.arbiter = arbiter
        self.name = name
        self.priority = priority
        self.sharded = sharded
        self.port = port
        self.config_servers = config_servers
        self.mongos = mongos
        self.auth = auth
        self.username = username
        self.password = password
        self.auth_db = auth_db
        self.auth_roles = auth_roles or ["dbAdminAnyDatabase", "readWriteAnyDatabase", "userAdminAnyDatabase",
                                         "clusterAdmin"]
        self.image_repo = image_repo
        self.image_tag = image_tag
        self.append_to_hosts = append_to_hosts
        self.network_name = network_name

    @property
    def is_auth_enabled(self) -> bool:
        return self.username is not None and self.password is not None

    @staticmethod
    def from_file(file_path: str) -> "ProvisionerConfig":
        with open(file_path, "r") as file:
            data = yaml.load(file)
        data["password"] = os.environ.get("MONGODB_PASSWORD", data.get("password"))
        return ProvisionerConfig(**data)
