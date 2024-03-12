import functools
import inspect
import io
import logging
import re
import socket
import time
from sys import exit
from typing import Tuple, Type, Dict, Union, List, Any

import docker
from docker.errors import APIError, DockerException
from docker.models.containers import Container
from rich.console import Console

from tomodo.common.config import ProvisionerConfig
from tomodo.common.errors import InvalidShellException
from tomodo.common.models import Mongod, AtlasDeployment

io = io.StringIO()

console = Console(file=io)
logger = logging.getLogger("rich")


def parse_2d_separated_string(_str: Union[str, None], delimiter_1: str = ",", delimiter_2: str = "="):
    if not _str:
        return None
    parsed: Dict = {}
    for mapping in _str.split(delimiter_1):
        [k, v] = mapping.split(delimiter_2)
        parsed[k.strip()] = v.strip()
    return parsed


def parse_semver(version_str: str) -> (int, int, int):
    try:
        [maj_v, min_v, patch] = version_str.split(".")
        return int(maj_v), int(min_v), int(patch)
    except ValueError:
        pass
    try:
        [maj_v, min_v] = version_str.split(".")
        return int(maj_v), int(min_v), None
    except ValueError:
        raise


def with_retry(max_attempts: int = 5, delay: int = 1, retryable_exc: Tuple[Type[Exception], ...] = (Exception,),
               ignore: bool = False):
    def retry_decorator(func):
        @functools.wraps(func)
        def retry_wrapper(*args, **kwargs):
            attempts = 0
            ex = None
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except retryable_exc as e:
                    ex = e
                    logger.debug("%s: Attempt %d/%d (%s)", func.__name__, attempts + 1, max_attempts, str(e))
                    attempts += 1
                    time.sleep(delay)
            logger.error("%s failed after %d attempts", func.__name__, max_attempts)
            if not ignore:
                if ex:
                    raise ex
                raise Exception(f"{func.__name__} failed after {max_attempts} attempts")
            return

        return retry_wrapper

    return retry_decorator


def anonymize_connection_string(connection_string: str) -> str:
    pattern = r"(mongodb(?:\+srv)?:\/\/[^:]+:)([^@]+)(@)"
    anonymized_connection_string = re.sub(pattern, r"\1************\3", connection_string)
    return anonymized_connection_string


def is_port_range_available(port_range: Tuple[int, ...], host: str = "localhost") -> bool:
    taken = False
    for port in port_range:
        sock = None

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((host, port))
            if result == 0:
                taken = True
                raise socket.error()
            else:
                logger.debug("Port %d is available on your host", port)
            sock.close()
        except socket.error:
            taken = True
            logger.error("Port %d is unavailable on your host", port)
            return False
        finally:
            if sock:
                sock.close()
            if taken:
                return False
    return True


class AnonymizingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = anonymize_connection_string(record.msg)
            if isinstance(record.args, dict):
                for k in record.args.keys():
                    record.args[k] = anonymize_connection_string(record.args[k])
            else:
                record.args = tuple(anonymize_connection_string(arg) for arg in record.args)
        except:
            pass
        return True


def run_mongo_shell_command(mongo_cmd: str, mongod: Mongod, shell: str = "mongosh",
                            serialize_json: bool = False, config: ProvisionerConfig = None) -> (int, str, str):
    docker_client = docker.from_env()
    container: Container = docker_client.containers.get(mongod.container_id)
    if not container:
        raise Exception(f"Could not find the container '{mongod.container_id}'")
    hostname = mongod.hostname
    is_atlas = isinstance(mongod, AtlasDeployment)
    # First check if the desired MongoDB shell exists in the container:
    if is_atlas:
        shell = "mongosh"
        hostname = "localhost"
    else:
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
                raise InvalidShellException
    # If the output needs to be JSON-serialized by the tool, it's required to stringify it with mongosh:
    if shell == "mongosh" and serialize_json:
        mongo_cmd = f"JSON.stringify({mongo_cmd})"
    cmd = [shell, hostname, "--quiet", "--norc", "--eval", mongo_cmd]
    if config and config.is_auth_enabled:
        cmd.extend(["--username", config.username])
        cmd.extend(["--password", config.password])
    if is_atlas:
        cmd.extend(["--port", str(mongod.port)])
    command_exit_code: int
    command_output: bytes
    command_exit_code, command_output = container.exec_run(cmd=cmd)
    caller = inspect.stack()[1][3]
    logger.debug("Docker-exec [%s]: command output: %s", caller, command_output.decode("utf-8").strip())
    logger.debug("Docker-exec [%s]: command exit code: %d", caller, command_exit_code)
    return command_exit_code, cleanup_mongo_output(command_output.decode("utf-8").strip()), mongod.container_id


mongo_cpp_log_re = "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}\+[0-9]{4}\s+[A-Z]\s+.*$"


def cleanup_mongo_output(output: str) -> str:
    """
    Cleans up the Mongo shell output from mongod logs, to make it safer to parse the output.

    :param output:  Sanitize the mongo shell output.
    :return:
    """
    return "\n".join(
        row for row in output.split("\n") if
        not re.match(mongo_cpp_log_re, row)
    )


def is_docker_running():
    try:
        client = docker.from_env()
        client.ping()
        return True
    except (APIError, DockerException):
        return False


def check_docker():
    if not is_docker_running():
        logger.error("The Docker daemon isn't running")
        exit(1)


def split_into_chunks(lst: List[Any], chunk_size: int = 20):
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]
