from typing import List, Union


class Deployment:
    last_known_state: str = None
    container_count: int = 0
    deployment_type: str = "Deployment"
    mongo_version: str = None
    port_range: str = ""


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
                 container_data_dir: str = None):
        self.port = port
        self.hostname = hostname
        self.name = name
        self.type = _type
        self.container_id = container_id
        self.last_known_state = last_known_state
        self.host_data_dir = host_data_dir
        self.container_data_dir = container_data_dir

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


class Shard(ReplicaSet):
    shard_id: int = None

    def __init__(self, shard_id: int, **kwargs):
        super().__init__(**kwargs)
        self.shard_id = shard_id


class ShardedCluster(Deployment):
    config_svr_replicaset: ReplicaSet = None
    routers: List[Mongos] = None
    shards: List[Shard] = None
    deployment_type: str = "Sharded Cluster"

    def __init__(self,
                 config_svr_replicaset: ReplicaSet = None,
                 routers: List[Mongos] = None,
                 shards: List[Shard] = None
                 ):
        self.config_svr_replicaset = config_svr_replicaset
        self.routers = routers
        self.shards = shards

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
