from typing import List, Dict

from docker.models.containers import Container


class Deployment:
    name: str = None
    last_known_state: str = None
    container_count: int = 0
    deployment_type: str = "Deployment"
    mongo_version: str = None
    port_range: str = ""

    def as_dict(self, detailed: bool = False) -> Dict:
        return {
            "name": self.name,
            "deployment_type": self.deployment_type,
            "state": self.last_known_state,
            "containers": self.container_count,
            "mongo_version": self.mongo_version,
            "port_range": self.port_range,
        }

    def as_markdown_table_row(self, name: str) -> str:
        cells = [name, self.deployment_type, self.last_known_state, str(self.container_count),
                 self.mongo_version or "unknown", self.port_range]
        return "| " + "|".join(cells) + " |"

    def as_markdown_table(self) -> str:
        raise NotImplementedError


class Mongod(Deployment):
    port: int
    hostname: str
    name: str
    container_id: str = None
    last_known_state: str
    host_data_dir: str = None
    container_data_dir: str = None
    container_count = 1
    deployment_type: str = "Standalone"

    def __init__(self,
                 port: int,
                 hostname: str,
                 name: str,
                 _type: str = "mongod",
                 container_id: str = None,
                 last_known_state: str = None,
                 host_data_dir: str = None,
                 container_data_dir: str = None,
                 container: Container = None,
                 deployment_type: str = "Standalone",
                 mongo_version: str = None):
        self.port = port
        self.hostname = hostname
        self.name = name
        self.type = _type
        self.container_id = container_id
        self.last_known_state = last_known_state
        self.host_data_dir = host_data_dir
        self.container_data_dir = container_data_dir
        self.container = container
        self.deployment_type = deployment_type
        self.mongo_version = mongo_version

    @property
    def labels(self):
        return {
            attr: str(getattr(self, attr))
            for attr in dir(self)
            if not attr.startswith("__") and not callable(getattr(self, attr))
        }

    @property
    def port_range(self) -> str:
        return str(self.port)

    def as_markdown_table(self) -> str:
        headers = ["Name", "Port", "Type", "Hostname", "Container ID"]
        rows = [
            f"**{self.name} (standalone):**",
            "| " + " | ".join(headers) + " |",
            "| " + "|".join(["------" for _ in range(len(headers))]) + " |",
        ]
        cells = [
            self.name,
            str(self.port),
            "mongod",
            f"{self.name}:{self.port}",
            self.container_id or "N\A"
        ]
        rows.append("| " + "|".join(cells) + " |")
        return "\n".join(rows)

    def as_dict(self, detailed: bool = False) -> Dict:
        if not detailed:
            return super().as_dict(detailed=False)
        return {
            "name": self.name,
            "deployment_type": self.deployment_type,
            "state": self.last_known_state,
            "containers": self.container_count,
            "mongo_version": self.mongo_version,
            "port": self.port,
            "host_data_dir": self.host_data_dir,
            "container_data_dir": self.container_data_dir,
            "container": {
                "id": self.container.short_id,
                "image": str(self.container.image),
                "ports": self.container.ports,
            }
        }


class Mongos(Mongod):
    pass


class ConfigServer(Mongod):
    pass


class ReplicaSet(Deployment):
    members: List[Mongod] = None
    name: str = None
    start_port: int = None
    size: int = 3
    container_count: int = 3
    deployment_type: str = "Replica Set"

    def __init__(self, name: str = None, start_port: int = None, members: List[Mongod] = None, size: int = 3):
        self.members = members
        self.name = name
        self.start_port = start_port
        self.size = size
        self.container_count = size

    @property
    def hostname(self) -> str:
        hosts = ",".join([f"{m.name}:{m.port}" for m in self.members])
        return f"mongodb://{hosts}/?replicaSet={self.name}"

    @property
    def config_db(self) -> str:
        hosts = ",".join([f"{m.name}:{m.port}" for m in self.members])
        return f"{self.name}/{hosts}"

    @property
    def port_range(self) -> str:
        return "-".join([str(self.start_port), str(self.start_port + self.size - 1)])

    def as_markdown_table(self) -> str:
        headers = ["Name", "Port", "Type", "Hostname", "Container ID"]
        rows = [
            f"**{self.name} (replica set):**",
            "| " + " | ".join(headers) + " |",
            "| " + "|".join(["------" for _ in range(len(headers))]) + " |",
        ]
        for member in self.members:
            cells = [
                member.name,
                str(member.port),
                member.type,
                f"{member.name}:{member.port}",
                member.container_id or "N\A"
            ]
            rows.append("| " + "|".join(cells) + " |")
        return "\n".join(rows)

    def as_dict(self, detailed: bool = False) -> Dict:
        if not detailed:
            return super().as_dict(detailed=False)
        return {
            "name": self.name,
            "deployment_type": self.deployment_type,
            "state": self.last_known_state,
            "containers": self.container_count,
            "mongo_version": self.mongo_version,
            "port_range": self.port_range,
            "size": self.size,
            "members": [
                member.as_dict(detailed=True) for member in self.members
            ]
        }


class Shard(ReplicaSet):
    shard_id: int = None

    def __init__(self, shard_id: int, **kwargs):
        super().__init__(**kwargs)
        self.shard_id = shard_id


class ShardedCluster(Deployment):
    name: str = None
    config_svr_replicaset: ReplicaSet = None
    routers: List[Mongos] = None
    shards: List[Shard] = None
    deployment_type: str = "Sharded Cluster"

    def __init__(self,
                 config_svr_replicaset: ReplicaSet = None,
                 routers: List[Mongos] = None,
                 shards: List[Shard] = None,
                 name: str = None,
                 mongo_version: str = None
                 ):
        self.config_svr_replicaset = config_svr_replicaset
        self.routers = routers
        self.shards = shards
        self.name = name
        self.mongo_version = mongo_version

    @property
    def container_count(self) -> int:
        config_svr = self.config_svr_replicaset.container_count if self.config_svr_replicaset else 0
        routers = len(self.routers) if self.routers else 0
        shard_members = len(self.shards) * self.shards[0].container_count if self.shards and len(self.shards) else 0
        return routers + config_svr + shard_members

    @property
    def port_range(self) -> str:
        if len(self.config_svr_replicaset.members):
            start_port = self.config_svr_replicaset.members[0].port
            return "-".join([str(start_port), str(start_port + self.container_count - 1)])
        return ""

    def as_markdown_table(self) -> str:
        headers = ["Name", "Port", "Type", "Hostname", "Container ID"]
        rows = [
            f"**{self.name} (sharded cluster):**",
            "| " + " | ".join(headers) + " |",
            "| " + "|".join(["------" for _ in range(len(headers))]) + " |",
        ]
        for config_server in self.config_svr_replicaset.members:
            cells = [
                config_server.name,
                str(config_server.port),
                "mongod (config)",
                f"{config_server.name}:{config_server.port}",
                config_server.container_id or "N/A",
            ]
            rows.append("| " + "|".join(cells) + " |")
        for router in self.routers:
            cells = [
                router.name,
                str(router.port),
                "mongos",
                f"{router.name}:{router.port}",
                router.container_id or "N/A",
            ]
            rows.append("| " + "|".join(cells) + " |")

        for shard in self.shards:
            for member in shard.members:
                cells = [
                    member.name,
                    str(member.port),
                    "mongod",
                    f"{member.name}:{member.port}",
                    member.container_id or "N/A",
                ]
                rows.append("| " + "|".join(cells) + " |")
        return "\n".join(rows)

    def as_dict(self, detailed: bool = False) -> Dict:
        if not detailed:
            return super().as_dict()
        return {
            "name": self.name,
            "deployment_type": self.deployment_type,
            "state": self.last_known_state,
            "containers": self.container_count,
            "mongo_version": self.mongo_version,
            "port_range": self.port_range,
            "routers": [
                router.as_dict(detailed=True) for router in self.routers
            ],
            "config_servers_replica_set": self.config_svr_replicaset.as_dict(detailed=True),
            "shards": [
                shard.as_dict(detailed=True) for shard in self.shards
            ],
        }
