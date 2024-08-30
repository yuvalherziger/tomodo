FROM ubuntu:22.04

RUN apt-get update \
     && export DEBIAN_FRONTEND=noninteractive \
     && apt-get -y install --no-install-recommends curl ca-certificates \
     && apt-get clean -y \
     && update-ca-certificates

ARG OM_URL
ARG PROJECT_ID
ARG API_KEY
ARG PORT=27017

EXPOSE $PORT

CMD curl -OL ${OM_URL}/download/agent/automation/mongodb-mms-automation-agent-manager_107.0.10.8627-1_arm64.ubuntu2204.deb \
    && dpkg -i mongodb-mms-automation-agent-manager_107.0.10.8627-1_arm64.ubuntu2204.deb \
    && touch /etc/mongodb-mms/automation-agent.config \
    && echo "mmsGroupId=${PROJECT_ID}" >> /etc/mongodb-mms/automation-agent.config \
    && echo "mmsApiKey=${API_KEY}" >> /etc/mongodb-mms/automation-agent.config \
    && echo "mmsBaseUrl=${OM_URL}" >> /etc/mongodb-mms/automation-agent.config \
    && mkdir -p /data \
    && chown mongodb:mongodb /data \
    && ./opt/mongodb-mms-automation/bin/mongodb-mms-automation-agent -f /etc/mongodb-mms/automation-agent.config
    #&& systemctl start mongodb-mms-automation-agent.service
