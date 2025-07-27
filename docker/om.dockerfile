#
# THIS IMAGE IS A SLIGHT MODIFICATION OF https://github.com/mongodb-labs/omida/
#
FROM ubuntu:22.04

ARG JDK_ARM64_BINARY=https://download.oracle.com/java/17/archive/jdk-17.0.11_linux-aarch64_bin.tar.gz
ARG VERSION=8.0.11

ENV VERSION=${VERSION}

USER root
WORKDIR /root

# Copy the setup scripts
COPY ./docker/scripts /root/scripts

RUN apt-get update \
     && export DEBIAN_FRONTEND=noninteractive \
     && apt-get -y install --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        iproute2 \
        jq \
        netcat \
        net-tools \
        ssh \
        vim \
     && apt-get clean -y \
     && update-ca-certificates

# Run args
ARG APPDB_HOST
ARG MMS_PORT=9080
ARG MMS_SSL_PORT=9443

ARG TARGETARCH
RUN /root/scripts/dl-om.sh --version "$VERSION"

CMD MMS_PORT=$MMS_PORT MMS_SSL_PORT=$MMS_SSL_PORT /root/scripts/config-om.sh --appdb "$APPDB_HOST" \
    && /root/mongodb-mms/bin/start-mongodb-mms --enc-key-path /etc/mongodb-mms/gen.key \
    && tail -n 1000 -F /root/mongodb-mms/etc/mongodb-mms/data/logs/mms0-startup.log /root/mongodb-mms/etc/mongodb-mms/data/logs/mms0.log