import abc
import inspect
import json
import logging
import re
import uuid
import time
from io import StringIO
from sys import exit
from typing import Dict, List, Union

import docker
from docker.errors import APIError
from docker.models.containers import Container
from docker.models.images import Image
from pymongo.errors import AutoReconnect, ServerSelectionTimeoutError
from rich.console import Console
from rich.table import Table

from tomodo.common.config import UpgradeConfig
from tomodo.common.util import parse_semver, with_retry

UPGRADE_VERSION_PATH = {
    "3.6": "4.0",
    "4.0": "4.2",
    "4.2": "4.4",
    "4.4": "5.0",
    "5.0": "6.0",
    "6.0": "7.0",
}

io = StringIO()

mongo_cpp_log_re = "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}\+[0-9]{4}\s+[A-Z]\s+.*$"

console = Console(file=io)
logger = logging.getLogger("rich")


def get_next_upgrade_target(src_ver: str, begin_with_current_latest: bool = False) -> str:
    """
    Given a source MongoDB version, gets the next appropriate version to upgrade to (e.g., 3.6 --> 4.0)
    If begin_with_current_latest is True, it will return the latest version of the source version
    (e.g., 3.6.18 --> 3.6.24)

    :param src_ver:                     Source version
    :param begin_with_current_latest:   Whether to get source version's latest stable version.
    :return:                            Next upgrade version
    """
    src_major, src_minor, src_patch = parse_semver(src_ver)
    src_min_ver = f"{src_major}.{src_minor}"
    if begin_with_current_latest:
        latest_major, latest_minor, latest_patch = get_full_version_from_mongo_image(src_min_ver)
        if latest_patch != src_patch:
            return f"{latest_major}.{latest_minor}.{latest_patch}"
    return UPGRADE_VERSION_PATH.get(src_min_ver)


def get_upgrade_path(hostname: str, current_version: str, target_version: str,
                     begin_with_current_latest: bool = False) -> List[str]:
    """
    Given a MongoDB instance's hostname, its current version, and a target upgrade version,
    will calculate the full upgrade path from the current version to the upgrade version.

    :param hostname:                    MongoDB hostname
    :param current_version:             MongoDB instance's current version
    :param target_version:              Target MongoDB version
    :param begin_with_current_latest:   Whether the first upgrade should be to the current minor version's latest
                                        stable patch
    :return:                            A list of version in the upgrade path
    """
    logger.info("This will upgrade %s from %s to %s", hostname, current_version, target_version)
    done = False
    current_source_ver = current_version
    path = []
    target_maj, target_min, target_patch = parse_semver(target_version)
    while not done:
        next_upgrade_target = get_next_upgrade_target(current_source_ver, begin_with_current_latest)
        next_maj, next_min, next_patch = parse_semver(next_upgrade_target)
        if next_min == target_min and next_maj == target_maj:
            next_upgrade_target = target_version
            done = True
        begin_with_current_latest = False
        current_source_ver = next_upgrade_target
        path.append(next_upgrade_target)
    return path


def get_full_version_from_mongo_image(minor_version: str, image_repo_name: str = "mongo") -> (int, int, int):
    docker_client = docker.from_env()
    image: Image = docker_client.images.get(f"{image_repo_name}:{minor_version}")
    if not image:
        image = docker_client.images.pull(repository=image_repo_name, image_tag=minor_version)
    env_vars = {}
    for env in image.attrs.get("ContainerConfig", {}).get("Env", []):
        [key, val] = env.split("=", 1)
        env_vars[key] = val
    try:
        return parse_semver(env_vars["MONGO_VERSION"])
    except KeyError:
        logger.error("Could not extract the full version from image %s", ",".join(image.tags))
        exit(1)


def get_primary(members: List) -> Dict:
    for m in members:
        state_str: str = m.get("stateStr")
        if state_str == "PRIMARY":
            return m
    raise Exception("Primary node could not be found")


def get_rs_members_table(members: any, title: str = "Replica Set Members") -> str:
    io.truncate(0)
    console.file.truncate(0)
    table = Table(title=title)
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Health")
    table.add_column("Uptime")
    for m in members:
        table.add_row(m.get("name"), m.get("stateStr"), str(int(m.get("health"))), str(m.get("uptime")))
    console.print(table)
    output = console.file.getvalue()
    return output


def generate_upgrader(config: UpgradeConfig) -> any:
    mdb_retries = config.mongodb_operation_retries
    mdb_delay = config.mongodb_operation_delay
    docker_retries = config.container_creation_retries
    docker_delay = config.container_creation_delay

    # TODO: 'Exception' is a catch-all, once we determine most edge cases,
    #       'Exception' can be removed.
    mdb_retryable = (AutoReconnect, ServerSelectionTimeoutError, AssertionError, Exception)
    docker_retryable = (APIError, Exception)

    class Upgrader:

        def __init__(self, _config: UpgradeConfig):
            self.config = _config
            # Register undecorated methods for the state file:
            self._get_mongodb_version = self.get_mongodb_version.__wrapped__
            self._check_mongodb_readiness = self.check_mongodb_readiness.__wrapped__
            self._get_fcv = self.get_fcv.__wrapped__

        def run_mongo_shell_command(self, mongo_cmd: str, shell: str = "mongosh",
                                    serialize_json: bool = False, container_id: str = None) -> (int, str, str):
            """
            Run a MongoDB command in a Docker container.

            :param mongo_cmd:       The mongo/mongosh command to run and/or evaluate
            :param shell:           The MongoDB shell to use
            :param serialize_json:  Whether the output should be JSON-serialized.
            :param container_id:    Optional container ID
            :return:                A tuple with the exist code (int) and the output (str)
            """
            host = self.config.localhost
            docker_client = docker.from_env()
            container: Container = docker_client.containers.get(container_id or self.config.container_name)
            container_id = container.short_id
            if not container:
                raise Exception(f"Could not find the container '{self.config.container_name}'")

            # First check if the desired MongoDB shell exists in the container:
            shell_check_exit_code, _ = container.exec_run(cmd=["which", shell])
            if shell_check_exit_code != 0:
                if shell != "mongo":
                    logger.debug(
                        "The '%s' shell could not be found in the container. Checking for the legacy 'mongo' shell",
                        shell)
                    shell = "mongo"
                    shell_check_exit_code, _ = container.exec_run(cmd=["which", shell])
                if shell_check_exit_code != 0:
                    logger.error("The '%s' shell could not be found in the container.", shell)
                    # No valid shell --> error out:
                    exit(1)
            # If the output needs to be JSON-serialized by the tool, it's required to stringify it with mongosh:
            if shell == "mongosh" and serialize_json:
                mongo_cmd = f"JSON.stringify({mongo_cmd})"
            cmd = [shell, host, "--quiet", "--norc", "--eval", mongo_cmd]
            command_exit_code: int
            command_output: bytes
            command_exit_code, command_output = container.exec_run(cmd=cmd)
            caller = inspect.stack()[1][3]
            logger.debug("Docker-exec [%s]: command output: %s", caller, command_output.decode("utf-8").strip())
            logger.debug("Docker-exec [%s]: command exit code: %d", caller, command_exit_code)
            return command_exit_code, self.cleanup_mongo_output(command_output.decode("utf-8").strip()), container_id

        @with_retry(max_attempts=mdb_retries, delay=mdb_delay, retryable_exc=mdb_retryable)
        def get_mongodb_version(self, write_state: bool = True) -> str:
            """
            Get running MongoDB version

            :return:    MongoDB version string
            """
            exit_code, server_version, _ = self.run_mongo_shell_command(mongo_cmd="db.version()")
            if exit_code != 0:
                raise Exception("Could not read the MongoDB version")
            parse_semver(server_version)  # <-- or fail
            return server_version

        def cleanup_mongo_output(self, output: str) -> str:
            """
            Cleans up the Mongo shell output from mongod logs, to make it safer to parse the output.

            :param output:  Sanitize the mongo shell output.
            :return:
            """
            return "\n".join(
                row for row in output.split("\n") if
                not re.match(mongo_cpp_log_re, row)
            )

        @with_retry(max_attempts=mdb_retries, delay=mdb_delay, retryable_exc=mdb_retryable)
        def list_rs_members(self) -> List[Dict]:
            """
            List members of a MongoDB Replica Set

            :return:     List of members returned from the underlying admin command
            """
            mongo_cmd = "rs.status().members.map(m =>" \
                        "({ name: m.name, stateStr: m.stateStr, health: m.health, uptime: m.uptime }))"
            exit_code, members_str, _ = self.run_mongo_shell_command(mongo_cmd=mongo_cmd, serialize_json=True)
            if exit_code != 0:
                raise Exception("Could not list the Replica Set members")
            return json.loads(members_str)

        @with_retry(max_attempts=mdb_retries, delay=mdb_delay, retryable_exc=(AssertionError,))
        def assert_rs_member_state(self, members: List[Dict], member_name: str, expected_state: str = "SECONDARY"):
            """
            Assert whether a Replica Set member is in a certain state. Use it to verify
            a safe state to shut down a secondary member from a Replica Set without risking data loss.

            :param members:         Dictionary of MongoDB members from rs.status()
            :param member_name:     Searched member name
            :param expected_state:  Expected state (i.e., SECONDARY or PRIMARY)
            :return:
            :raises (AssertionError, ValueError)
            """
            member = None
            for m in members:
                if member_name == m.get("name"):
                    member = m
                    assert m.get("stateStr") == expected_state, f"Expected {member_name} to be {expected_state}"
                    break

            if not member:
                raise ValueError("Member %s could not be found in the Replica Set", member_name)
            logger.info("Confirmed that %s is now %s", member_name, expected_state)

        @with_retry(max_attempts=mdb_retries, delay=mdb_delay, retryable_exc=mdb_retryable)
        def set_fcv(self, target_version: str) -> None:
            """
            Set the Feature Compatibility Version of a MongoDB instance to a target version

            :param target_version:  Target FCV
            :return:
            """
            target_fcv = target_version
            if len(target_version.split(".")) > 2:
                target_fcv = ".".join(target_version.split(".")[:-1])
            logger.info("Setting FCV for %s to %s", self.config.container_name, target_fcv)
            cmd_dict = {
                "setFeatureCompatibilityVersion": target_fcv,
                "writeConcern": {"wtimeout": 5000}
            }
            mj, _, _ = parse_semver(target_version)
            # Setting the FCV is interactive starting with MongoDB 7.0:
            if mj >= 7:
                cmd_dict["confirm"] = True
            mongo_cmd = f"db.adminCommand({json.dumps(cmd_dict)})"
            exit_code, members_str, _ = self.run_mongo_shell_command(mongo_cmd=mongo_cmd)
            if exit_code != 0:
                raise Exception("Could not set the FCV")
            logger.info("Now configured with FCV %s", target_fcv)

        @with_retry(max_attempts=mdb_retries, delay=mdb_delay, retryable_exc=mdb_retryable)
        def make_primary_step_down(self, member_name: str) -> bool:
            """
            Make the primary node of a multi-member Replica Set step down as PRIMARY

            :param member_name: The Replica Set member name
            :return:            True if the command succeeded.
            """

            # TODO: Won't be compatible with multi-node replica sets now with Docker exec
            #       for versions >=6.0 (mongo vs. mongosh). Need to fix.
            logger.info("Making %s step down", member_name)
            self.run_mongo_shell_command(mongo_cmd="rs.stepDown()")
            return True

        @with_retry(max_attempts=25, delay=5, retryable_exc=docker_retryable)
        def wait_for_container_to_stop(self, container_id: str) -> None:
            """
            Poll a container by ID and raise an exception until it stops.

            :param container_id:
            :return:
            :raises: AssertionError
            """
            logging.info("Checking if container %s stopped", container_id)
            docker_client = docker.from_env()
            container: Container = docker_client.containers.get(container_id)
            if container.status != "exited":
                logging.info("Container %s is still running. Checking whether mongod is still running", container_id)
                mongod_running = self.is_process_running(container_id=container_id, command="mongod")
                if mongod_running:
                    logging.info("Container %s still has a running mongod process", container_id)
                    raise AssertionError(f"Container {container_id} and/or mongod is still running")
                else:
                    logging.info("Container %s no longer has a mongod process running. Stopping the container",
                                 container_id)
                    container.stop()
            logging.info("Container %s stopped", container_id)

        @with_retry(max_attempts=25, delay=5, retryable_exc=docker_retryable)
        def is_process_running(self, container_id: str, command: str) -> bool:
            """
            Check whether a process running in a container by container ID

            :param container_id:    The Docker container ID
            :param command:         The command the proces is running

            :return:
            :raises: AssertionError
            """
            logging.info("Checking if container %s stopped", container_id)
            docker_client = docker.from_env()
            container: Container = docker_client.containers.get(container_id)
            processes: Union[Dict, str] = container.top()
            for process in processes["Processes"]:
                # Top always returns the command in the 8th column/element
                current_command = process[7]
                if current_command.split(" ")[0] == command:
                    return True
            return False

        def shut_down_member(self, member_name: str = None, container_id: str = None, version: str = None) -> None:
            """
            Shut down a MongoDB instance properly

            :param member_name:     Replica Set member name
            :param container_id:    Docker container ID
            :param version:         MongoDB version
            :return:
            """
            mongo_cmd = f"db.getSiblingDB(\"admin\").shutdownServer({{force:true}})"
            exit_code, output, container_id = self.run_mongo_shell_command(mongo_cmd=mongo_cmd,
                                                                           container_id=container_id)

            logger.info("MongoDB instance %s is being shut down (exit code %d)", member_name, exit_code)
            self.wait_for_container_to_stop(container_id)

        @with_retry(max_attempts=mdb_retries, delay=mdb_delay, retryable_exc=mdb_retryable)
        def check_mongodb_readiness(self, write_state: bool = True) -> None:
            """
            Poll a MongoDB instance for readiness

            :param write_state:    Whether to write the state file
            :return:                None
            """
            log_level = logging.INFO if write_state else logging.DEBUG
            logger.log(log_level, "Checking the readiness of %s", self.config.container_name)

            mongo_cmd = "db.runCommand({ping: 1}).ok"
            exit_code, output, _ = self.run_mongo_shell_command(mongo_cmd=mongo_cmd)

            try:
                is_ready = int(output) == 1

            except:
                is_ready = False
            if not is_ready:
                logger.log(log_level, "Server %s is not ready to accept connections", self.config.localhost)
                if write_state:
                    self.write_state()
                raise Exception("Server isn't ready")
            logger.log(log_level, "Server %s is ready to accept connections", self.config.localhost)
            if write_state:
                self.write_state()

        @with_retry(max_attempts=mdb_retries, delay=mdb_delay, retryable_exc=mdb_retryable)
        def get_fcv(self, write_state: bool = True) -> str:
            """
            Get the FCV of a MongoDB instance
            :param write_state:
            :return:         FCV string
            """
            log_level = logging.INFO if write_state else logging.DEBUG
            logger.log(log_level, "Getting the FCV of %s", self.config.container_name)
            mongo_cmd = "db.adminCommand({getParameter: 1, featureCompatibilityVersion: 1})" \
                        ".featureCompatibilityVersion.version"
            exit_code, fcv, _ = self.run_mongo_shell_command(mongo_cmd=mongo_cmd)
            if exit_code != 0:
                raise Exception("Could not read FCV")
            try:
                parse_semver(fcv)
            except ValueError:
                pass
            finally:
                if write_state:
                    self.write_state()
            return fcv

        def assert_fcv(self, hostname: str, expected: str) -> None:
            """
            Asserts whether a given MongoDB instance has the expected input FCV.

            :param hostname:    MongoDB hostname
            :param expected:    Expected FCV to assert
            :return:
            :raises: AssertionError
            """
            url = self.config.hostname
            logger.info("Validating FCV for %s", url)
            actual = self.get_fcv()
            assert actual == expected, f"Expected FCV to be {expected}, actually {actual}"

        @with_retry(max_attempts=docker_retries, delay=docker_delay, retryable_exc=docker_retryable)
        def get_deployment_containers(self, container_search_term: str) -> List[Container]:
            """
            Get all containers whose name contains the given search term

            :param container_search_term:   The container search term
            :return:                        List of containers
            """
            docker_client = docker.from_env()
            containers = []
            for container in docker_client.containers.list(all=True):
                if container_search_term.lower() in container.attrs.get("Name").lower():
                    containers.append(container)
            return containers

        @with_retry(max_attempts=docker_retries, delay=docker_delay, retryable_exc=docker_retryable)
        def restart_container(self, container_id: str) -> None:
            """
            Restart a Docker container, with retries
            :param container_id: the ID of the container to restart
            :return:
            """
            docker_client = docker.from_env()
            container: Container = docker_client.containers.get(container_id)
            if not container:
                raise Exception(f"Container with the ID of {container_id} could not be found")
            container.restart(timeout=10)

        @with_retry(max_attempts=docker_retries, delay=docker_delay, retryable_exc=docker_retryable)
        def upgrade_container(self, old_container: Container, target_version) -> (str, str):
            """

            :param old_container:   The old container to stop and remove
            :param target_version:  The desired new version for the new container
            :return:                A tuple with the new container ID and its image tag
            """

            docker_client = docker.from_env()
            image_tag = target_version
            if self.config.image_tag_mapping:
                if target_version in self.config.image_tag_mapping:
                    image_tag = self.config.image_tag_mapping.get(target_version)
                else:
                    [maj_v, min_v, _] = parse_semver(target_version)
                    maj_min = f"{maj_v}.{min_v}"
                    if maj_min in self.config.image_tag_mapping:
                        image_tag = self.config.image_tag_mapping.get(maj_min)

            networks: Dict = old_container.attrs.get("NetworkSettings", {}).get("Networks")
            network_name = None
            if networks:
                network_name = list(networks.keys())[0]
            intermediate_name = str(uuid.uuid4())
            docker_client.containers.get(old_container.short_id).rename(f"{old_container.name}-{intermediate_name}")
            ports = old_container.attrs.get("HostConfig", {}).get("PortBindings")
            container_id = old_container.short_id
            command = [old_container.attrs.get("Path"), *old_container.attrs.get("Args")]

            environment_vars_lst: List = old_container.attrs.get("Config", {}).get("Env")

            # Later versions of MongoDB will fail without WiredTiger as their storage engine:
            if "--storageEngine" not in command:
                command = [*command, "--storageEngine", "wiredTiger"]
            name = old_container.name
            old_container.stop()

            # Will not pull the image unless 'platform' kwarg is specified:
            new_container = docker_client.containers.run(
                image=f"{self.config.image_registry_name}:{image_tag}",
                detach=True,
                volumes_from=[container_id],
                ports=ports,
                command=command,
                name=name,
                network=network_name or None,
                environment=environment_vars_lst
            )
            old_container.remove()
            return new_container.short_id, new_container.attrs.get("Config", {}).get("Image")

        def upgrade(self, member_name: str, target_version: str) -> (str, str):
            """
            Upgrade a container to a target version.

            :param member_name:     The RS member name
            :param target_version:  The version to upgrade to
            :return:                A tuple with the new container ID and its image tag
            """
            container_name = member_name.split(":")[0]
            containers = self.get_deployment_containers(container_name)
            if len(containers) != 1:
                raise Exception(f"Could not find exactly one container under the name '{container_name}'")
            container: Container = containers[0]
            return self.upgrade_container(old_container=container, target_version=target_version)

        def upgrade_replica_set(self, current_version: str, target_version: str):
            """
            Perform a single upgrade of a Replica Set from one version to another

            :param current_version: The current MongoDB version
            :param target_version:  The target MongoDB version (MAJ.MIN or MAJ.MIN.PATCH)
            :return:
            """
            logger.info("Starting a rolling restart")
            # cmj = Current Major
            # cmn = Current Minor
            cmj, cmn, _ = parse_semver(current_version)
            members = self.list_rs_members()
            logger.info(get_rs_members_table(members))
            primary = None
            secondaries = []
            for m in members:
                state_str: str = m.get("stateStr")
                if state_str == "PRIMARY":
                    primary = {**m, "upgraded": False}
                elif state_str == "SECONDARY":
                    secondaries.append({**m, "upgraded": False})
                else:
                    logger.info("%s is unhealthy; state: %s", m.get("name"), state_str)
            if not primary:
                logger.error("No primary in the Replica Set!")
                exit(1)
            members_state: List[Dict] = [primary, *secondaries]
            is_single_node = False

            current_fcv = self.get_fcv()
            current_minor_version = f"{cmj}.{cmn}"

            # Here we're making sure we're not skipping a version with the FCV
            # e.g., upgrading to 4.2 with an FCV of 3.6:
            if current_fcv != current_minor_version:
                logging.info("Current FCV: %s, current (minor) version: %s. Aligning before the upgrade",
                             current_fcv, current_minor_version)
                self.set_fcv(self.config.hostname, current_minor_version)
                self.check_mongodb_readiness()

            for i, member in enumerate(members_state):
                member_name: str = member.get("name")

                current_primary = get_primary(members)
                if len(members_state) == 1:
                    logger.info("Single-node Replica Set: no need to make the primary step down")
                    is_single_node = True
                elif current_primary.get("name") != member_name:
                    logger.info("Not a primary; no need to step down")
                else:
                    self.make_primary_step_down(member_name)
                    self.assert_rs_member_state(
                        members=self.list_rs_members(),
                        member_name=member_name,
                        expected_state="SECONDARY"
                    )
                hostname = self.config.hostname if is_single_node else member_name

                self.shut_down_member(member_name=self.config.container_name or member_name, version=current_version)
                if is_single_node:
                    logger.info(
                        "Upgrading %s. The Replica Set will be offline for the duration of the container upgrade",
                        hostname)
                else:
                    logger.info("Restarting %s.", hostname)

                # The actual container upgrade happens here:
                container_id, tag = self.upgrade(
                    member_name=self.config.container_name or member_name,
                    target_version=target_version
                )

                self.write_state()

                members_state[i]["container_id"] = container_id
                logger.info("New container ID: %s with image tag %s", container_id, tag)
                self.check_mongodb_readiness()

                self.write_state()

                members = self.list_rs_members()
                logger.info(get_rs_members_table(members, title="Current RS state"))

            logger.info("All member containers were upgraded successfully")
            logger.info("Setting Replica Set FCV to %s", target_version)

            # tmj = Target Major
            # tmn = Target Minor
            tmj, tmn, _ = parse_semver(target_version)

            if self.config.lagging_fcv is False:
                self.set_fcv(
                    target_version=target_version
                )

            # Example:
            # If lagging_fcv is False, we expect MongoDB 6.0 to have a FCV of 6.0
            # If lagging_fcv is True, we're ok with MongoDB 6.0 running with FCV 5.0
            expected_fcv = f"{cmj}.{cmn}" if self.config.lagging_fcv else f"{tmj}.{tmn}"

            self.assert_fcv(
                hostname=self.config.hostname,
                expected=expected_fcv
            )
            self.write_state()

            for member in members_state:
                hostname = self.config.hostname if is_single_node else member.get("name")
                self.check_mongodb_readiness()

            # RS-level validations:
            self.check_mongodb_readiness()
            # TODO: Remove redundant check:
            expected_fcv = f"{cmj}.{cmn}" if self.config.lagging_fcv else f"{tmj}.{tmn}"
            self.assert_fcv(
                hostname=self.config.hostname,
                expected=expected_fcv
            )
            self.write_state()

        def write_state(self, exit_code: int = None):
            """
            This method writes a state JSON file indicating the current state of the Replica Set.

            :param exit_code:
            :return:
            """
            docker_client = docker.from_env()
            container: Container = docker_client.containers.get(self.config.container_name)
            try:
                version = self._get_mongodb_version(self, write_state=False)
                mj, mn, pt = parse_semver(version)
                version = f"{mj}.{mn}.{pt}"
            except Exception as e:
                version = "unknown"
            accepting_connections = True
            try:
                self._check_mongodb_readiness(self, write_state=False)
            except Exception as e:
                accepting_connections = False
            try:
                fcv = self._get_fcv(self, write_state=False)
                mj, mn, _ = parse_semver(fcv)
                fcv = f"{mj}.{mn}"
            except Exception as e:
                fcv = "unknown"
            state = {
                "time": int(time.time()),
                "container_id": container.short_id,
                "last_known_status": container.status,
                "image_tags": container.image.tags,
                "mongodb_version": version,
                "accepting_connections": accepting_connections,
                "fcv": fcv,
            }
            if exit_code is not None:
                state["exit_code"] = exit_code

            with open(self.config.state_file_path, "w") as state_file:
                json.dump(state, state_file, indent=2)

    return Upgrader(_config=config)
