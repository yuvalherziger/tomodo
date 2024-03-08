FROM ubuntu:latest
ARG MDBVERSION=7.0

ARG PORT=27017
ENV USERNAME=foo
ENV PASSWORD=bar

ENV PORT=27017
ENV NAME=atlas-deployment-0

RUN apt-get update && apt-get install -y wget gnupg2 && wget -qO - https://pgp.mongodb.com/server-6.0.asc | apt-key add - && \
    echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/6.0 multiverse" \
    | tee /etc/apt/sources.list.d/mongodb-org-6.0.list && \
    apt-get update && \
    apt-get install -y mongodb-atlas

RUN ls -la '/tmp/' > /tmp/foo.txt

# Run a dummy deployment to make the mongo binaries available for runtime
#RUN atlas deployments setup --help
#
## rm -rf "/tmp/run-${UID}"
#RUN atlas deployment setup temp-depl --type LOCAL --bindIpAll --force --username foo --password bar --mdbVersion ${MDBVERSION} --skipMongosh
#
##RUN /bin/sh -c "atlas deployments delete ${NAME}"
#RUN atlas deployments delete temp-depl
#
##RUN atlas deployments setup $NAME --type local --bindIpAll --force \
##    ${USERNAME:+--username $USERNAME} \
##    ${PASSWORD:+--password $PASSWORD} \
##    ${MDBVERSION:+--mdbVersion $MDBVERSION} \
##    --port ${PORT} --skipMongosh
#
#ENTRYPOINT atlas deployments setup --type local --bindIpAll --force \
#    ${USERNAME:+--username $USERNAME} \
#    ${PASSWORD:+--password $PASSWORD} \
#    ${MDBVERSION:+--mdbVersion $MDBVERSION} \
#    --port ${PORT} --skipMongosh & tail -f /dev/null
#
##CMD ["tail", "-f", "/dev/null"]
