import re
from collections import defaultdict
from typing import List, Optional, Dict

import requests


def list_tags(repo: str = "mongo", page: int = 1, page_size: int = 100, must_include: Optional[str] = None,
              must_exclude: Optional[str] = None) -> List[str]:
    img_tags = []
    url = f"https://hub.docker.com/v2/repositories/library/{repo}/tags"
    params = {"page_size": page_size, "page": page}
    while True:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            raise Exception("Could not list tags from Docker Hub")

        data = response.json()
        img_tags.extend(
            [tag.get("name") for tag in data.get("results") if
             (not must_include or must_include in tag.get("name")) and (
                     not must_exclude or must_exclude not in tag.get("name"))])
        next_page = data["next"]

        if not next_page:
            break

        params["page"] += 1
    return img_tags


def group_tags_by_minor_version(tags: List[str]) -> Dict[str, List[str]]:
    tags.sort(reverse=True)
    version_dict = defaultdict(list)
    minor_version_pattern = re.compile(r"^(\d+\.\d+)")
    major_version_pattern = re.compile(r"^(\d+)")
    non_versions = []
    for tag in tags:
        minor_version_match = minor_version_pattern.match(tag)
        major_version_match = major_version_pattern.match(tag)

        if minor_version_match:
            minor_version = minor_version_match.group(1)
            version_dict[minor_version].append(tag)
        elif major_version_match:
            major_version = major_version_match.group(1)
            version_dict[major_version].append(tag)
        else:
            non_versions.append(tag)
    if len(non_versions):
        version_dict["others"] = non_versions
    return dict(version_dict)
