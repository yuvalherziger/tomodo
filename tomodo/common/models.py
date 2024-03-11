from typing import List, Dict, Any

from docker.models.containers import Container


def port_sorter(c: Dict):
    return int(c.get("tomodo-port"))


def shard_and_port_sorter(c: Dict):
    return int(c.get("tomodo-shard-id", 0)) * int(c.get("tomodo-port", 0))


def split_into_chunks(lst: List[Any], y):
    chunk_size = len(lst) // y
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


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
        cells = [name, self.deployment_type, self.last_known_state or "unknown", str(self.container_count),
                 self.mongo_version or "unknown", self.port_range]
        return "| " + "|".join(cells) + " |"

    def as_markdown_table(self) -> str:
        raise NotImplementedError

    def stop(self, cleaner=None) -> None:
        from tomodo.common.cleaner import Cleaner
        cleaner = cleaner or Cleaner()
        cleaner.stop_deployment(name=self.name)

    def start(self, starter=None) -> None:
        from tomodo.common.starter import Starter
        starter = starter or Starter()
        starter.start_deployment(name=self.name)

    def remove(self, cleaner=None) -> None:
        from tomodo.common.cleaner import Cleaner
        cleaner = cleaner or Cleaner()
        cleaner.delete_deployment(name=self.name)


class Mongod(Deployment):
    port: int
    hostname: str
    name: str
    container_id: str = None
    last_known_state: str
    host_data_dir: str = None
    container_data_dir: str = None
    container_count = 1
    deployment_type: str = "mongod"
    is_arbiter: bool = False

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
                 deployment_type: str = "mongod",
                 mongo_version: str = None,
                 is_arbiter: bool = False):
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
        self.is_arbiter = is_arbiter

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
            self.container_id or "N/A"
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
            "is_arbiter": self.is_arbiter,
            "container": {
                "id": self.container.short_id,
                "image": str(self.container.image),
                "ports": self.container.ports,
            }
        }

    @staticmethod
    def from_container_details(details: Dict) -> "Mongod":
        container: Container = details.get("tomodo-container")
        mongo_version = details.get("tomodo-mongo-version")
        mongod = Mongod(
            port=int(details.get("tomodo-port", 0)),
            hostname=details.get("tomodo-name"),
            name=details.get("tomodo-name"),
            container_id=container.short_id,
            host_data_dir=details.get("tomodo-data-dir"),
            container_data_dir=details.get("tomodo-container-data-dir"),
            is_arbiter=details.get("tomodo-arbiter") == "1",
            container=container,
            deployment_type="Standalone"
        )
        mongod.mongo_version = mongo_version
        mongod.last_known_state = "running" if container.status == "running" else "stopped"
        return mongod


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

    def __init__(self, name: str = None, start_port: int = None, members: List[Mongod] = None, size: int = 3,
                 deployment_type: str = "Replica Set"):
        self.members = members
        self.name = name
        self.start_port = start_port
        self.size = size
        self.container_count = size
        self.deployment_type = deployment_type

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
                member.container_id or "N/A"
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

    @staticmethod
    def from_container_details(details: List[Dict]) -> "ReplicaSet":
        name = details[0].get("tomodo-group")
        mongo_version = details[0].get("tomodo-mongo-version")
        sorted_components = sorted(details, key=lambda c: int(c.get("tomodo-port")))
        stopped_containers = 0
        running_containers = 0
        members = []
        for component in sorted_components:
            container: Container = component.get("tomodo-container")
            mongod = Mongod(
                port=int(component.get("tomodo-port", 0)),
                hostname=component.get("tomodo-name"),
                name=component.get("tomodo-name"),
                container_id=component.get("tomodo-container-id"),
                host_data_dir=component.get("tomodo-data-dir"),
                container_data_dir=component.get("tomodo-container-data-dir"),
                is_arbiter=component.get("tomodo-arbiter") == "1",
                container=container,
                mongo_version=next(
                    (
                        var.split("=")[1] for var in container.attrs.get("Config", {}).get("Env", []) if
                        var.startswith("MONGO_VERSION=")
                    ),
                    None
                )
            )
            mongod.last_known_state = container.status
            members.append(mongod)

            if container.status == "running":
                running_containers += 1
            else:
                stopped_containers += 1
        replica_set = ReplicaSet(
            members=members,
            name=name,
            start_port=members[0].port,
            size=len(members)
        )
        if running_containers > 0:
            replica_set.last_known_state = "running"
        else:
            replica_set.last_known_state = "stopped"
        replica_set.mongo_version = mongo_version
        return replica_set


class AtlasDeployment(Mongod):
    deployment_type = "Atlas Deployment"

    @staticmethod
    def from_container_details(details: Dict) -> "AtlasDeployment":
        mongod = Mongod.from_container_details(details=details)
        atlas_depl = AtlasDeployment(
            port=mongod.port,
            hostname=mongod.hostname,
            name=mongod.name,
            container_id=mongod.container_id,
            container=mongod.container,
            deployment_type="Atlas Deployment"
        )
        atlas_depl.mongo_version = details.get("tomodo-mongo-version")
        atlas_depl.last_known_state = "running" if mongod.container.status == "running" else "stopped"
        return atlas_depl

    def stop(self, cleaner=None) -> None:
        raise NotImplementedError("Stopping and restarting Atlas deployments is currently not supported")

    def start(self, starter=None) -> None:
        raise NotImplementedError("Stopping and restarting Atlas deployments is currently not supported")


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
        self.routers = routers or []
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

    @staticmethod
    def from_container_details(details: List[Dict]) -> "ShardedCluster":
        name = details[0].get("tomodo-group")
        mongo_version = details[0].get("tomodo-mongo-version")
        config_svr_components = sorted([c for c in details if c.get("tomodo-role") == "cfg-svr"], key=port_sorter)
        mongos_components = sorted([c for c in details if c.get("tomodo-role") == "mongos"], key=port_sorter)
        shard_mongod_components = sorted([c for c in details if c.get("tomodo-role") == "rs-member"],
                                         key=shard_and_port_sorter)
        stopped_containers = 0
        running_containers = 0

        cfg_server_members = []
        for component in config_svr_components:
            container: Container = component.get("tomodo-container")
            mongod = Mongod(
                port=int(component.get("tomodo-port", 0)),
                hostname=component.get("tomodo-name"),
                name=component.get("tomodo-name"),
                container_id=component.get("tomodo-container-id"),
                host_data_dir=component.get("tomodo-data-dir"),
                container_data_dir=component.get("tomodo-container-data-dir"),
                is_arbiter=component.get("tomodo-arbiter") == "1",
                container=container
            )
            mongod.last_known_state = container.status
            cfg_server_members.append(mongod)
            if container.status == "running":
                running_containers += 1
            else:
                stopped_containers += 1
        config_svr_replicaset = ReplicaSet(
            members=cfg_server_members,
            name=name,
            start_port=cfg_server_members[0].port,
            size=len(cfg_server_members)
        )
        routers = []
        for component in mongos_components:
            container: Container = component.get("tomodo-container")
            mongos = Mongos(
                port=int(component.get("tomodo-port", 0)),
                hostname=component.get("tomodo-name"),
                name=component.get("tomodo-name"),
                container_id=component.get("tomodo-container-id"),
                deployment_type="mongos",
                _type="mongos",
                container=container
            )
            mongos.last_known_state = container.status
            routers.append(mongos)
            if container.status == "running":
                running_containers += 1
            else:
                stopped_containers += 1

        num_shards = int(shard_mongod_components[0].get("tomodo-shard-count", 0)) if len(shard_mongod_components) else 0
        shards = []
        if num_shards > 0:
            chunked_shard_components = split_into_chunks(shard_mongod_components, num_shards)
        else:
            chunked_shard_components = []
        for shard_components in chunked_shard_components:
            members = []
            for component in shard_components:
                container: Container = component.get("tomodo-container")
                mongod = Mongod(
                    port=int(component.get("tomodo-port", 0)),
                    hostname=component.get("tomodo-name"),
                    name=component.get("tomodo-name"),
                    container_id=component.get("tomodo-container-id"),
                    host_data_dir=component.get("tomodo-data-dir"),
                    container_data_dir=component.get("tomodo-container-data-dir"),
                    deployment_type="mongod",
                    is_arbiter=component.get("tomodo-arbiter", "0") == "1",
                    container=container,
                )
                mongod.last_known_state = container.status
                members.append(mongod)
                if container.status == "running":
                    running_containers += 1
                else:
                    stopped_containers += 1
            shards.append(
                Shard(
                    shard_id=int(shard_components[0].get("tomodo-shard-id", 0)),
                    members=members,
                    name=name,
                    size=len(shard_components),
                    start_port=int(shard_components[0].get("tomodo-port", 0)),
                    deployment_type="shard"
                )
            )

        sharded_cluster = ShardedCluster(
            config_svr_replicaset=config_svr_replicaset,
            routers=routers,
            shards=shards,
            name=name
        )
        if running_containers > 0:
            sharded_cluster.last_known_state = "running"
        else:
            sharded_cluster.last_known_state = "stopped"
        sharded_cluster.mongo_version = mongo_version
        return sharded_cluster
