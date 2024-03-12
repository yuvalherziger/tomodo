import logging
from sys import exit

import typer

from tomodo.common.tag_manager import list_tags, group_tags_by_minor_version
from tomodo.common.util import split_into_chunks

cli = typer.Typer(no_args_is_help=True, help="Find MongoDB image tags")
logger = logging.getLogger("rich")


@cli.command(
    help="List available tags",
    name="list"
)
def list_(
        image_repo: str = typer.Option(
            default="mongo",
            help="The MongoDB image name/repo (NOTE: you probably don't want to change it)"
        ),
        must_include: str = typer.Option(
            default=None,
            help="Filter results. Example: 'tomodo tags list --must-include 7.0'"
        ),
        must_exclude: str = typer.Option(
            default=None,
            help="Filter results. Example: 'tomodo tags list --must-exclude windows'"
        ),
        group: bool = typer.Option(
            default=True,
            help="Group results by minor versions"
        ),
):
    tags = list_tags(repo=image_repo, must_include=must_include, must_exclude=must_exclude)
    if group:
        grouped_tags = group_tags_by_minor_version(tags)
        for minor_ver in grouped_tags.keys():
            print(f"{minor_ver}:")
            for tag in grouped_tags[minor_ver]:
                print(f"  - {tag}")
    else:
        tags.sort(reverse=True)
        results_per_page = 30
        chunked_tags = split_into_chunks(tags, results_per_page)
        for chunk in chunked_tags:
            print("\n".join(chunk))
            if len(chunk) == results_per_page and typer.confirm(f"Show more?"):
                continue
            else:
                exit(0)
