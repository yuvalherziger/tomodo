from typing import List

from ruamel.yaml import YAML
from unique_names_generator import get_random_name
from unique_names_generator.data import ADJECTIVES, ANIMALS

yaml = YAML()


class ProvisionerConfig:

    def __init__(self, standalone: bool = False, replica_set: bool = False, replicas: int = 3, shards: int = 2,
                 arbiter: bool = False, name: str = None, priority: bool = False, atlas: bool = False,
                 sharded: bool = False, port: int = 27017, config_servers: int = 1, mongos: int = 1,
                 auth: bool = False, username: str = None, password: str = None, auth_db: str = "admin",
                 auth_roles: List[str] = None, image_repo: str = "mongo", image_tag: str = "latest",
                 network_name: str = "mongo_network", ephemeral: bool = False):
        self.standalone = standalone
        self.replica_set = replica_set
        self.replicas = replicas
        self.atlas = atlas
        self.shards = shards
        self.arbiter = arbiter
        self.name = name or get_random_name(combo=[ADJECTIVES, ANIMALS], separator="-", style="lowercase")
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
        self.network_name = network_name
        self.ephemeral = ephemeral

    @property
    def is_auth_enabled(self) -> bool:
        return self.username is not None and self.password is not None


class OpsManagerConfig:

    def __init__(self, app_db_config: ProvisionerConfig, name: str = None, port: int = 9080):
        self.name = name or get_random_name(combo=[ADJECTIVES, ANIMALS], separator="-", style="lowercase")
        self.port = port
        app_db_config.name = f"{self.name}-app-db"
        self.app_db_config = app_db_config


class AgentConfig:

    def __init__(self, om_name: str, project_id: str, api_key: str):
        self.om_name = om_name
        self.project_id = project_id
        self.api_key = api_key


class OpsManagerServerConfig:

    def __init__(self, agent_config: AgentConfig, name: str = None, port: int = 9080,
                 count: int = 1):
        self.name = name or get_random_name(combo=[ADJECTIVES, ANIMALS], separator="-", style="lowercase")
        self.port = port
        self.agent_config = agent_config
        self.count = count
