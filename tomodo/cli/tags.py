import logging

import typer

from tomodo.common.tag_manager import list_tags

cli = typer.Typer(no_args_is_help=True, help="Find MongoDB image tags")
logger = logging.getLogger("rich")


@cli.command(
    help="List available tags",
    name="list"
)
def list_(
        version: str = typer.Option(
            default=None,
            help="Filter by version. Must be a valid semantic version (whole or partial). "
                 "Example: 'tomodo tags list --version 7.0.6'"
        )
):
    results_per_page = 40
    has_more = True
    page = 1
    while has_more:
        tags, has_more = list_tags(page=page, page_size=results_per_page, version=version)
        print("\n".join(tags))
        if has_more and typer.confirm(f"Show more?", default=True):
            page += 1
        else:
            has_more = False
