import logging
import os
from enum import Enum
from sys import exit
from typing import List

import docker
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from unique_names_generator import get_random_name
from unique_names_generator.data import ADJECTIVES, ANIMALS

from tomodo.common import TOMODO_VERSION
from tomodo.common.cleaner import Cleaner
from tomodo.common.config import UpgradeConfig, ProvisionerConfig
from tomodo.common.errors import EmptyDeployment
from tomodo.common.provisioner import Provisioner
from tomodo.common.reader import Reader
from tomodo.common.starter import Starter
from tomodo.common.upgrader import generate_upgrader, get_upgrade_path, get_rs_members_table
from tomodo.common.util import parse_2d_separated_string, AnonymizingFilter, parse_semver, is_docker_running

console = Console()

cli = typer.Typer()

log_handler = RichHandler(show_path=False)
log_handler.addFilter(AnonymizingFilter())

logging.basicConfig(
    level=logging.INFO, format="%(message)s", datefmt="%Y-%m-%dT%H:%M:%S.%f %z", handlers=[log_handler]
)

logger = logging.getLogger("rich")


class LogLevel(str, Enum):
    INFO = "INFO"
    DEBUG = "DEBUG"


def check_docker():
    if not is_docker_running():
        logger.error("The Docker daemon isn't running")
        exit(1)


@cli.command(help="Print tomodo's version")
def version():
    docker_ver = docker.from_env().version()
    console.print_json(data={
        "tomodo_version": TOMODO_VERSION,
        "docker_version": {
            "engine": docker_ver.get("Version"),
            "platform": docker_ver.get("Platform", {}).get("Name")
        }
    })


@cli.command(
    help="Upgrade a standalone MongoDB instance or a MongoDB Replica Set to a target version.",
    no_args_is_help=True)
def upgrade(
        hostname: str = typer.Option(
            default=None,
            help="The MongoDB connection string to the Replica Set or standalone instance"
        ),
        target_version: str = typer.Option(
            default=None,
            help="The target MongoDB version to upgrade to"
        ),
        config_path: str = typer.Option(
            default=None,
            help="Path to YAML configuration file"
        ),
        standalone: bool = typer.Option(
            default=False,
            help="Use it the target instance is a standalone instance (not a Replica Set)"
        ),
        lagging_fcv: bool = typer.Option(
            default=True,
            help="Use lagging FCV to allow a burn-in period after the upgrade, with an FCV of the previous "
                 "MongoDB version. This is a recommended approach in case of unexpected application incompatibilities. "
                 "If set to --no-lagging-fcv, the FCV will always be set to the same version MongoDB "
                 "is being upgraded to. Read more here: "
                 "https://www.mongodb.com/docs/v6.0/reference/command/setFeatureCompatibilityVersion/"
        ),
        begin_with_current_latest: bool = typer.Option(
            default=False,
            help="Use --begin-with-current-latest to upgrade safely to the latest version of the current "
                 "minor version from which you're starting the upgrade. For example, starting from 3.6.18 "
                 "won't upgrade to 4.0, but first to the latest version of 3.6. \n"
                 "If using --image_tag_mapping or --image_registry_name, the mapped tag of the latest version tag "
                 "(e.g., mongo:3.6) will have to be present on the machine."
        ),
        force_auth_on_exec: bool = typer.Option(
            default=False,
            help="Whether Docker exec commands should be forced to use credentials, if applicable"
        ),
        image_registry_name: str = typer.Option(
            default="mongo",
            help="Image registry name to use. Omit to pull the default 'mongo:tag' repo"
        ),
        container_creation_retries: int = typer.Option(
            default=10,
            help="How many times the container creation should be retried"
        ),
        container_creation_delay: int = typer.Option(
            default=10,
            help="# of seconds to wait between each failed container creation"
        ),
        mongodb_operation_retries: int = typer.Option(
            default=10,
            help="How many times any MongoDB operation should be retried"
        ),
        mongodb_operation_delay: int = typer.Option(
            default=10,
            help="# of seconds to wait between each failed MongoDB operation"
        ),
        image_tag_mapping: str = typer.Option(
            default=None,
            help="Override the default image tags. (ex. '4.0=4.0-custom,4.2=4.2-custom')",
        ),
        username: str = typer.Option(
            default=None,
            help="MongoDB username",
        ),
        password: str = typer.Option(
            default=None,
            help="MongoDB password. Preferably, use the MONGODB_PASSWORD environment variable instead.",
        ),
        container_name: str = typer.Option(
            default=None,
            help="The name of the container to upgrade (in single-node Replica Sets and standalone deployments)"
        ),
        log_file_path: str = typer.Option(
            default=None,
            help="Path to log file. If not provided, logs will be streamed to stdout."
        ),
        state_file_path: str = typer.Option(
            default="./.tomodo-state.json",
            help="Write the upgrade state to a file."
        ),
        explain: bool = typer.Option(
            default=False,
            help="Do not upgrade, just analyze the MongoDB instance and the configuration "
                 "to print an explanation of the upgrade plan."
        ),
        log_level: LogLevel = typer.Option(
            LogLevel.INFO,
            help="Log level. Set to DEBUG for more verbose logs"
        ),
):
    check_docker()
    if not config_path:
        if password:
            logger.warning(
                "Avoid passing the password as an argument. Use the MONGODB_PASSWORD environment variable instead."
            )
        elif os.environ.get("MONGODB_PASSWORD"):
            password = os.environ["MONGODB_PASSWORD"]
        if not lagging_fcv:
            logger.warning("Running with --no-lagging-fcv: Downgrading could be more complex. \n"
                           "Enabling backwards-incompatible features can complicate the downgrade process "
                           "since you must remove any persisted backwards-incompatible features before you downgrade"
                           )
        else:
            logger.info("Running with --lagging-fcv: each upgrade will keep the replica member(s) with the FCV "
                        "of the previous MongoDB version to allow a burn-in period.")
        if image_registry_name or image_tag_mapping:
            logger.warning(
                "Running an upgrade with --image_registry_name or --image_tag_mapping: this means that "
                "all images in the upgrade path have to be pulled and present on the docker host in advance, or "
                "the upgrade might fail."
            )

        config = UpgradeConfig(
            target_version=target_version,
            hostname=hostname,
            image_registry_name=image_registry_name,
            standalone=standalone,
            container_creation_retries=container_creation_retries,
            container_creation_delay=container_creation_delay,
            mongodb_operation_retries=mongodb_operation_retries,
            mongodb_operation_delay=mongodb_operation_delay,
            image_tag_mapping=parse_2d_separated_string(image_tag_mapping),
            username=username,
            password=password,
            lagging_fcv=lagging_fcv,
            container_name=container_name,
            force_auth_on_exec=force_auth_on_exec,
            log_file_path=log_file_path,
            state_file_path=state_file_path,
            begin_with_current_latest=begin_with_current_latest,
            log_level=log_level
        )
    else:
        if hostname or target_version:
            logger.error("You cannot specify a --hostname or --target-version alongside --config-path")
            exit(1)
        config = UpgradeConfig.from_file(file_path=config_path)
    if config.log_file_path:
        file_handler = logging.FileHandler(config.log_file_path)
        file_handler.addFilter(AnonymizingFilter())
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        file_handler.setLevel(logging.INFO if config.log_level == LogLevel.INFO else logging.DEBUG)
        logger.addHandler(file_handler)
    if config.log_level == LogLevel.DEBUG:
        logger.setLevel(logging.DEBUG)
        logger.debug("Log level set to DEBUG. Logs will be more verbose")

    upgrader = generate_upgrader(config=config)
    current_version = upgrader.get_mongodb_version()

    # A series of basic validations to ensure the upgrade configuration makes sense:
    current_maj, current_min, current_patch = parse_semver(current_version)
    target_maj, target_min, target_patch = parse_semver(config.target_version)
    if current_maj == target_maj and current_min == target_min and current_patch == target_patch:
        logger.error("The current version and the target version are identical; check your configuration (%s -> %s).",
                     current_version, config.target_version)
        exit(1)

    if current_maj == target_maj and current_min == target_min and target_patch is not None and current_patch > target_patch:
        logger.error("The current version is ahead of the target version; check your configuration (%s -> %s).",
                     current_version, config.target_version)
        exit(1)

    if current_maj == target_maj and current_min > target_min:
        logger.error("The current version is ahead of the target version; check your configuration (%s -> %s).",
                     current_version, config.target_version)
        exit(1)

    if current_maj > target_maj:
        logger.error("The current version is ahead of the target version; check your configuration (%s -> %s).",
                     current_version, config.target_version)
        exit(1)
    if current_maj == target_maj and current_min == target_min and not config.begin_with_current_latest:
        error_msg = "The current and target versions are the same minor versions - " \
                    "you can run this upgrade only with the '--begin-with-current-latest' parameter."
        logger.error(error_msg)
        exit(1)

    upgrade_path: List[str] = get_upgrade_path(
        begin_with_current_latest=begin_with_current_latest,
        hostname=config.hostname,
        current_version=current_version,
        target_version=config.target_version
    )

    logger.info(
        "The upgrade path is %s --> %s. %d upgrade(s) will be performed serially.",
        current_version,
        " --> ".join(upgrade_path),
        len(upgrade_path)
    )
    if explain:
        members = upgrader.list_rs_members()
        logger.info(get_rs_members_table(members))
        logger.info("Done explaining upgrade plan - goodbye.")
        exit(0)
    if not standalone:
        for next_version in upgrade_path:
            logger.info("Now upgrading Replica Set from version %s to %s", current_version, next_version)
            upgrader.upgrade_replica_set(
                current_version=current_version,
                target_version=next_version
            )
            logger.info("Upgraded to %s successfully.", next_version)
            current_version = upgrader.get_mongodb_version()

        upgrader.write_state(exit_code=0)
    else:
        # TODO: implement standalone (non-rs) upgrade
        logger.error("Standalone upgrades aren't supported yet")
        exit(1)


@cli.command(
    help="Print an upgrade plan for a standalone MongoDB instance or a MongoDB Replica Set to a target version.",
    no_args_is_help=True)
def explain():
    raise NotImplementedError("'explain' is not implemented")


@cli.command(
    help="Provision a MongoDB standalone instance or cluster.",
    no_args_is_help=True)
def provision(
        standalone: bool = typer.Option(
            default=False,
            help=""
        ),
        replica_set: bool = typer.Option(
            default=False,
            help=""
        ),
        sharded: bool = typer.Option(
            default=False,
            help=""
        ),
        replicas: int = typer.Option(
            default=3,
            help=""
        ),
        shards: int = typer.Option(
            default=2,
            help=""
        ),
        arbiter: bool = typer.Option(
            default=False,
            help=""
        ),
        name: str = typer.Option(
            default=None,
            help=""
        ),
        priority: bool = typer.Option(
            default=False,
            help=""
        ),
        port: int = typer.Option(
            default=27017,
            min=0,
            max=65535,
            help=""
        ),
        config_servers: int = typer.Option(
            default=1,
            help=""
        ),
        mongos: int = typer.Option(
            default=1,
            help=""
        ),
        auth: bool = typer.Option(
            default=False,
            help=""
        ),
        username: str = typer.Option(
            default=None,
            help=""
        ),
        password: str = typer.Option(
            default=None,
            help=""
        ),
        auth_db: str = typer.Option(
            default=None,
            help=""
        ),
        auth_roles: str = typer.Option(
            default="dbAdminAnyDatabase readWriteAnyDatabase userAdminAnyDatabase clusterAdmin",
            help=""
        ),
        image_repo: str = typer.Option(
            default="mongo",
            help=""
        ),
        image_tag: str = typer.Option(
            default="7.0",
            help=""
        ),
        append_to_hosts: bool = typer.Option(
            default=False,
            help=""
        ),
        network_name: str = typer.Option(
            default="mongo_network",
            help=""
        )
):
    check_docker()
    name = name or get_random_name(combo=[ADJECTIVES, ANIMALS], separator="-", style="lowercase")
    config = ProvisionerConfig(
        standalone=standalone, replica_set=replica_set, replicas=replicas, shards=shards,
        arbiter=arbiter, name=name, priority=priority,
        sharded=sharded, port=port, config_servers=config_servers, mongos=mongos,
        auth=auth, username=username, password=password, auth_db=auth_db,
        auth_roles=auth_roles.split(" "), image_repo=image_repo, image_tag=image_tag,
        append_to_hosts=append_to_hosts, network_name=network_name
    )
    provisioner = Provisioner(config=config)
    provisioner.provision()


@cli.command(
    help="Describe running deployments",
    no_args_is_help=False)
def describe(
        name: str = typer.Option(
            default=None,
            help="Deployment name (optional). Prints all tomodo deployments if not specified"
        ),
        exclude_stopped: bool = typer.Option(
            default=False,
            help="Exclude stopped deployments (if '--name' not provided)"
        ),
):
    check_docker()
    reader = Reader()

    if name:
        try:
            markdown = Markdown(reader.describe_by_name(name, include_stopped=True))
            console.print(markdown)
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
    else:
        for description in reader.describe_all(include_stopped=exclude_stopped):
            markdown = Markdown(description)
            console.print(markdown)


@cli.command(
    help="Stop running deployments",
    no_args_is_help=False)
def stop(
        name: str = typer.Option(
            default=None,
            help="Deployment name (optional). Stops all deployments if not specified."
        ),
        auto_confirm: bool = typer.Option(
            default=False,
            help="Don't prompt for confirmation"
        )
):
    check_docker()
    cleaner = Cleaner()
    if name:
        try:
            if auto_confirm is True:
                cleaner.stop_deployment(name)
            else:
                if typer.confirm(f"Stop deployment '{name}'?"):
                    cleaner.stop_deployment(name)
                else:
                    raise typer.Abort()
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
    else:
        if auto_confirm is True:
            cleaner.stop_all_deployments()
        else:
            if typer.confirm(f"Stop all deployments?"):
                cleaner.stop_all_deployments()
            else:
                raise typer.Abort()


@cli.command(
    help="Start a non-running deployment",
    no_args_is_help=False)
def start(
        name: str = typer.Option(
            help="Deployment name."
        ),
):
    check_docker()
    starter = Starter()
    if name:
        try:
            starter.start_deployment(name)
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
    else:
        raise NotImplementedError


@cli.command(
    help="Remove running deployments permanently",
    no_args_is_help=False)
def remove(
        name: str = typer.Option(
            default=None,
            help="Deployment name (optional). Removes all deployments if not specified."
        ),
        auto_confirm: bool = typer.Option(
            default=False,
            help="Don't prompt for confirmation"
        )
):
    check_docker()
    cleaner = Cleaner()
    if name:
        try:
            if auto_confirm is True:
                cleaner.delete_deployment(name)
            else:
                if typer.confirm(f"Delete deployment '{name}'?"):
                    cleaner.delete_deployment(name)
                else:
                    raise typer.Abort()
        except EmptyDeployment:
            logger.error("A deployment named '%s' doesn't exist", name)
    else:
        if auto_confirm is True:
            cleaner.delete_all_deployments()
        else:
            if typer.confirm(f"Delete all deployments?"):
                cleaner.delete_all_deployments()
            else:
                raise typer.Abort()


@cli.command(
    help="List deployments",
    no_args_is_help=False,
    name="list")
def list_(
        exclude_stopped: bool = typer.Option(
            default=False,
            help="Exclude stopped deployments"
        ),
):
    check_docker()
    reader = Reader()
    markdown = Markdown(reader.list_all())
    console.print(markdown)


def run():
    cli()


if __name__ == "__main__":
    run()
