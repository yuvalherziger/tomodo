from dataclasses import dataclass, field
from typing import List

from unique_names_generator import get_random_name
from unique_names_generator.data import ADJECTIVES, ANIMALS


@dataclass
class ProvisionerConfig:
    name: str = None
    standalone: bool = False
    replica_set: bool = False
    replicas: int = 3
    shards: int = 2
    arbiter: bool = False
    priority: bool = False
    atlas: bool = False
    sharded: bool = False
    port: int = 27017
    config_servers: int = 1
    mongos: int = 1
    auth: bool = False
    username: str = None
    password: str = None
    auth_db: str = "admin"
    auth_roles: List[str] = None
    image_repo: str = "mongo"
    image_tag: str = "latest"
    network_name: str = "mongo_network"
    ephemeral: bool = False

    @property
    def is_auth_enabled(self) -> bool:
        return self.username is not None and self.password is not None

    def __post_init__(self):
        self.name = self.name or get_random_name(combo=[ADJECTIVES, ANIMALS], separator="-", style="lowercase")
        self.auth_roles = self.auth_roles or ["dbAdminAnyDatabase", "readWriteAnyDatabase", "userAdminAnyDatabase",
                                              "clusterAdmin"]


@dataclass
class OpsManagerConfig:
    app_db_config: ProvisionerConfig
    name: str = None
    port: int = 9080

    def __post_init__(self):
        self.app_db_config.name = f"{self.name}-app-db"
        self.name = self.name or get_random_name(combo=[ADJECTIVES, ANIMALS], separator="-", style="lowercase")


@dataclass
class AgentConfig:
    om_name: str
    project_id: str
    api_key: str


@dataclass
class OpsManagerServerConfig:
    agent_config: AgentConfig
    name: str = None
    port: int = 9080
    count: int = 1

    def __post_init__(self):
        self.name = self.name or get_random_name(combo=[ADJECTIVES, ANIMALS], separator="-", style="lowercase")
