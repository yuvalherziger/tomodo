#!/usr/bin/env bash

#
# THIS SCRIPT IS A SLIGHT MODIFICATION OF https://github.com/mongodb-labs/omida/
#

HTTP_PORT=${MMS_PORT:-9080}
HTTPS_PORT=${MMS_SSL_PORT:-9443}

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
    local appdb=
    while [[ "$#" -gt 0 ]]; do
        case "$1" in
            --appdb) appdb="${2-}"; shift 2 ;;
            * ) echo "Invalid configuration option: '$1'"; return 1 ;;
        esac
    done

    local conf="/root/mongodb-mms/conf/conf-mms.properties"
    _replace_property_in_file "/root/mongodb-mms/conf/conf-mms.properties" "mongo.mongoUri" "${appdb}"
    _replace_property_in_file "/root/mongodb-mms/conf/conf-mms.properties" "mms.centralUrl" "http://$(ifconfig eth0 | grep -oP 'inet \K\S+'):${HTTP_PORT}"

    # Configure backup head
    local backup_dir="/root/mongodb-mms/head"
    mkdir -p "${backup_dir}" && echo "Created directory: ${backup_dir}..."
    chmod -R 0777 "${backup_dir}"
    _replace_property_in_file "$conf" "rootDirectory" "${backup_dir}/"

    # Configure ports
    _replace_property_in_file "/root/mongodb-mms/conf/mms.conf" "BASE_PORT" "${HTTP_PORT}"
    _replace_property_in_file "/root/mongodb-mms/conf/mms.conf" "BASE_SSL_PORT" "${HTTPS_PORT}"

    # Define and create the release automation dir, if not defined
    local automation_release_dir="/root/mongodb-mms/mongodb-releases/"
    mkdir -p "${automation_release_dir}"
    chmod -R 0777 "${automation_release_dir}"
    _replace_property_in_file "$conf" "automation.versions.directory" "${automation_release_dir}"

    echo "Skipping Ops Manager Registration Wizard..."
    echo
    _replace_property_in_file "$conf" "mms.ignoreInitialUiSetup" "true"
    _replace_property_in_file "$conf" "mms.fromEmailAddr" "noreply@example.com"
    _replace_property_in_file "$conf" "mms.replyToEmailAddr" "noreply@example.com"
    _replace_property_in_file "$conf" "mms.adminEmailAddr" "noreply@example.com"
    _replace_property_in_file "$conf" "mms.mail.transport" "smtp"
    _replace_property_in_file "$conf" "mms.mail.hostname" "127.0.0.1"
    _replace_property_in_file "$conf" "mms.mail.port" "25"
    _replace_property_in_file "$conf" "mms.mail.ssl" "false"

    echo "Generating an encryption key"
    echo "WARNING: this is highly insecure, DO NOT IN PRODUCTION!"
    echo
    /root/mongodb-mms/bin/mms-gen-key
}

main "$@"