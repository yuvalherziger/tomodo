#!/usr/bin/env bash
set -ueo pipefail

_find_om_archive_by_version() {
    if [[ "$#" -lt 4 ]]; then
        echo "Usage: _find_om_archive_by_version VERSION ARCH PACKAGE_FORMAT FILE_TYPE"
        echo "e.g.: _find_om_archive_by_version 4.0.0 x86_64 deb deb"
        echo
        exit 1
    fi
    VERSION="$1"
    ARCH="$2"
    PACKAGE_FORMAT="$3"
    FILE_TYPE="$4"

    # Download release archive
    curl -sLo "/tmp/ops_manager_release_archive.json" "https://info-mongodb-com.s3.amazonaws.com/com-download-center/ops_manager_release_archive.json"

    local result
    result=$(jq -r -c '.currentReleases[], .oldReleases[]
        | select( .version | contains("'"${VERSION}"'"))
        | .platform[] | select (.arch=="'"${ARCH}"'")
        | select ( .package_format | contains("'"${PACKAGE_FORMAT}"'"))
        | .packages.links[] | select(.name=="'"${FILE_TYPE}"'")
        | .download_link' < "/tmp/ops_manager_release_archive.json")
    echo "${result}"
}

_download_ops_manager() {
    # Parameter check
    if [[ "$#" -eq 0 ]]; then
        echo "The Ops Manager archive was not supplied!"
        echo "Usage: _download_ops_manager OPS_MANAGER_ARCHIVE"
        echo
        exit 1
    fi
    local archive="$1"
    local ext="$2"

    local local_file="ops_manager.${ext}"

    echo "Downloading Ops Manager: ${archive} to ${local_file}..."
    curl -sLo "${local_file}" "${archive}"
    echo "Downloaded ${archive} to ${local_file}..."
}

_replace_property_in_file() {
    # Parameter check
    if [[ "$#" -lt 3 ]]; then
        echo "Invalid call: '_replace_property_in_file $*'"
        echo "Usage: _replace_property_in_file FILENAME PROPERTY VALUE"
        echo
        exit 1
    fi

    # Set the new property
    temp_file=$(mktemp)
    grep -vE "^\\s*${2}\\s*=" "${1}" > "${temp_file}" # Export contents minus any lines containing the specified property
    echo "${2}=${3}" >> "${temp_file}"                # Set the new property value
    cat "${temp_file}" > "${1}"                       # Replace the contents of the original file, while preserving any permissions
    rm "${temp_file}"
    echo "Updated property in ${1}: ${2}=${3}"
}

main() {
    local version=
    local package=
    while [[ "$#" -gt 0 ]]; do
        case "$1" in
            --version) version="${2-}"; shift 2 ;;
            --package) package="${2-}"; shift 2 ;;
            * ) echo "Invalid configuration option: '$1'"; return 1 ;;
        esac
    done

    # Download Ops Manager
    local archive
    if [[ "$version" != "" ]]; then
        archive="$(_find_om_archive_by_version "$version" "x86_64" "deb" "tar.gz")"
        _download_ops_manager "$archive" "tar.gz"
    elif [[ "$package" != "" ]]; then
        _download_ops_manager "$package" "tar.gz"
    else
        echo
        echo "You must specify an Ops Manager version or a package link; aborting..."
        exit 1
    fi

    mkdir -p /root/mongodb-mms
    chmod -R 0777 /root/mongodb-mms
    tar -xzf "ops_manager.tar.gz" -C "/root/mongodb-mms" --strip-components 1
    rm -rf ops_manager.tar.gz

    # Download an ARM64 OpenJDK (this only happens if the Targeted Architecture is arm64)
    if [[ -n "${TARGETARCH+set}" && "$TARGETARCH" = "arm64" ]]; then
        echo "Replacing the JDK with an ARM64 version"
        # NOTE: This link may need to be manually updated in the future to match whatever JDK version Ops Manager uses
        test -z "${JDK_ARM64_BINARY+set}" && (echo && echo "JDK_ARM64_BINARY is not set, but is needed!" && echo && false)
        curl -sLo jdk11-arm64.tar.gz "$JDK_ARM64_BINARY"
        tar -xzf jdk11-arm64.tar.gz
        rm -rf jdk11-arm64.tar.gz
        rm -rf mongodb-mms/jdk
        mv jdk-* jdk
        mv jdk mongodb-mms/
    fi
}

main "$@"
