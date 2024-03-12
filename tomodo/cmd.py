import io
import logging
from enum import Enum
from sys import exit
from typing import Dict

import docker
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.syntax import Syntax
from ruamel.yaml import YAML

from tomodo import TOMODO_VERSION
from tomodo.cli import provision, tags
from tomodo.common.cleaner import Cleaner
from tomodo.common.errors import DeploymentNotFound, TomodoError
from tomodo.common.models import Deployment
from tomodo.common.reader import Reader, list_deployments_in_markdown_table
from tomodo.common.starter import Starter
from tomodo.common.util import AnonymizingFilter, check_docker

console = Console()
yaml = YAML()

cli = typer.Typer(no_args_is_help=True)

log_handler = RichHandler(show_path=False)
log_handler.addFilter(AnonymizingFilter())

logging.basicConfig(
    level=logging.INFO, format="%(message)s", datefmt="%Y-%m-%dT%H:%M:%S.%f %z", handlers=[log_handler]
)

logger = logging.getLogger("rich")


class LogLevel(str, Enum):
    INFO = "INFO"
    DEBUG = "DEBUG"


class OutputFormat(str, Enum):
    JSON = "json"
    TABLE = "table"
    YAML = "yaml"


class Replicas(str, Enum):
    ONE = 1
    THREE = 3
    FIVE = 5
    SEVEN = 7


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


cli.add_typer(provision.cli, name="provision")
cli.add_typer(tags.cli, name="tags")


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
            help="Exclude stopped deployments (if '--name' is not provided)"
        ),
        output: OutputFormat = typer.Option(
            default=OutputFormat.TABLE,
            help="Output format"
        )
):
    check_docker()
    reader = Reader()

    if name:
        try:
            if output == OutputFormat.JSON:
                deployment = reader.get_deployment_by_name(name, include_stopped=True)
                console.print_json(data=deployment.as_dict(detailed=True))
            elif output == OutputFormat.YAML:
                yaml_str = io.StringIO()
                deployment = reader.get_deployment_by_name(name, include_stopped=True)
                yaml.dump(data=deployment.as_dict(detailed=True),
                          stream=yaml_str)
                yaml_syntax = Syntax(yaml_str.getvalue(), "yaml")
                console.print(yaml_syntax)
            else:
                markdown = Markdown(reader.describe_by_name(name, include_stopped=True))
                console.print(markdown)
        except DeploymentNotFound:
            logger.error("A deployment named '%s' doesn't exist", name)
            exit(1)
        except TomodoError as e:
            logger.error(str(e))
            exit(1)
        except Exception as e:
            logger.exception("Could not describe your deployment - an error has occurred")
            exit(1)
    else:
        try:
            if output == OutputFormat.JSON:
                deployments = reader.get_all_deployments(include_stopped=True)
                console.print_json(data={name: deployments[name].as_dict(detailed=True) for name in deployments.keys()})
            elif output == OutputFormat.YAML:
                deployments = reader.get_all_deployments(include_stopped=True)
                yaml_str = io.StringIO()
                yaml.dump(data={name: deployments[name].as_dict(detailed=True) for name in deployments.keys()},
                          stream=yaml_str)
                yaml_syntax = Syntax(yaml_str.getvalue(), "yaml")
                console.print(yaml_syntax)
            else:
                for description in reader.describe_all(include_stopped=exclude_stopped):
                    markdown = Markdown(description)
                    console.print(markdown)
        except TomodoError as e:
            logger.error(str(e))
            exit(1)
        except Exception as e:
            logger.exception("Could not describe your deployments - an error has occurred")
            exit(1)


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
        except typer.Abort:
            pass
        except DeploymentNotFound:
            logger.error("A deployment named '%s' doesn't exist", name)
            exit(1)
        except TomodoError as e:
            logger.error(str(e))
            exit(1)
        except Exception as e:
            logger.exception("Could not stop your deployment - an error has occurred")
            exit(1)
    else:
        try:
            if auto_confirm is True:
                cleaner.stop_all_deployments()
            else:
                if typer.confirm(f"Stop all deployments?"):
                    cleaner.stop_all_deployments()
                else:
                    raise typer.Abort()
        except typer.Abort:
            pass
        except TomodoError as e:
            logger.error(str(e))
            exit(1)
        except Exception as e:
            logger.exception("Could not stop your deployments - an error has occurred")
            exit(1)


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
        except DeploymentNotFound:
            logger.error("A deployment named '%s' doesn't exist", name)
            exit(1)
        except TomodoError as e:
            logger.error(str(e))
            exit(1)


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
        except typer.Abort:
            pass
        except DeploymentNotFound:
            logger.error("A deployment named '%s' doesn't exist", name)
            exit(1)
        except TomodoError as e:
            logger.error(str(e))
            exit(1)
        except Exception as e:
            logger.exception("Could not remove your deployment - an error has occurred")
            exit(1)
    else:
        try:
            if auto_confirm is True:
                cleaner.delete_all_deployments()
            else:
                if typer.confirm(f"Delete all deployments?"):
                    cleaner.delete_all_deployments()
                else:
                    raise typer.Abort()
        except typer.Abort:
            pass
        except TomodoError as e:
            logger.error(str(e))
            exit(1)
        except Exception as e:
            logger.exception("Could not remove your deployments - an error has occurred")
            exit(1)


@cli.command(
    help="List deployments",
    no_args_is_help=False,
    name="list")
def list_(
        exclude_stopped: bool = typer.Option(
            default=False,
            help="Exclude stopped deployments",
        ),
        output: OutputFormat = typer.Option(
            default=OutputFormat.TABLE,
            help="Output format"
        )
):
    check_docker()
    reader = Reader()
    try:
        deployments: Dict[str, Deployment] = reader.get_all_deployments(include_stopped=not exclude_stopped)
        if output == OutputFormat.JSON:
            console.print_json(data={name: deployments[name].as_dict() for name in deployments.keys()})
        elif output == OutputFormat.YAML:
            yaml_str = io.StringIO()
            yaml.dump(data={name: deployments[name].as_dict() for name in deployments.keys()},
                      stream=yaml_str)
            yaml_syntax = Syntax(yaml_str.getvalue(), "yaml")
            console.print(yaml_syntax)
        else:
            markdown = Markdown(
                list_deployments_in_markdown_table(deployments, include_stopped=not exclude_stopped),
            )
            console.print(markdown)
    except TomodoError as e:
        logger.error(str(e))
        exit(1)
    except Exception as e:
        logger.exception("Could not list your deployments - an error has occurred")
        exit(1)


def run():
    cli()


if __name__ == "__main__":
    run()
