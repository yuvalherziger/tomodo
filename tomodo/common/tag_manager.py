import datetime
import os
import re
from collections import defaultdict
from typing import List, Optional, Dict, Tuple

import requests
from pymongo import MongoClient, UpdateOne

from tomodo.common.util import parse_semver


def list_tags(page: int = 1, page_size: int = 40, version: Optional[str] = None) -> Tuple[List[str], bool]:
    url = "https://eu-central-1.aws.data.mongodb-api.com/app/stuff-yqgey/endpoint/imagetags"
    params = {}
    if page:
        params["page"] = str(page)
    if page_size:
        params["pageSize"] = str(page_size)
    if version is not None and len(version.strip()) > 0:
        params["version"] = version
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception("Could not list tags from Docker Hub")
    tags = response.json()
    return [t.get("tag") for t in tags[:-1]], len(tags) >= page_size + 1


def get_tags_from_dockerhub_api(repo: str = "mongo", page: int = 1, page_size: int = 100,
                                must_include: Optional[str] = None,
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


def load_tags():
    mongo_uri = os.environ.get("MONGO_URI")
    patch_version_pattern = re.compile(r"^(\d+\.\d+.\d+)")
    minor_version_pattern = re.compile(r"^(\d+\.\d+)")
    major_version_pattern = re.compile(r"^(\d+)")

    client = MongoClient(mongo_uri)
    grouped_tags: Dict[str, List[str]] = group_tags_by_minor_version(get_tags_from_dockerhub_api())
    updates = []
    db = client.get_database("tomodo")
    collection = db.get_collection("image_tags")
    for group in grouped_tags.keys():
        for tag in grouped_tags[group]:
            patch_version_match = patch_version_pattern.match(tag)
            minor_version_match = minor_version_pattern.match(tag)
            major_version_match = major_version_pattern.match(tag)
            major, minor, patch = None, None, None
            if patch_version_match:
                major, minor, patch = parse_semver(patch_version_match.group(1))
            elif minor_version_match:
                major, minor, patch = parse_semver(minor_version_match.group(1))
            elif major_version_match:
                major, minor, patch = int(major_version_match.group(1)), None, None

            updates.append(
                UpdateOne(
                    {
                        "tag": tag
                    },
                    {
                        "$set": {
                            "tag": tag,
                            "group": group,
                            "fragments": tag.split("-"),
                            "release_candidate": "-rc" in tag,
                            "major": major,
                            "minor": minor,
                            "patch": patch,
                            "imported_at": datetime.datetime.now(tz=datetime.timezone.utc),
                        }
                    },
                    upsert=True
                )
            )
    collection.bulk_write(updates)
