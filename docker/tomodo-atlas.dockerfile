ARG IMAGE_REPO=mongodb/atlas
ARG IMAGE_TAG=v1.15.1
FROM $IMAGE_REPO:$IMAGE_TAG
ARG MDBVERSION=7.0

ARG PORT=27017
ENV USERNAME=foo
ENV PASSWORD=bar
#ARG MDBVERSION

ENV PORT=27017
ENV NAME=atlas-deployment-0

# Run a dummy deployment to make the mongo binaries available for runtime
#RUN atlas deployments setup --help
RUN atlas deployments setup temp-depl --type LOCAL --bindIpAll --force --username foo --password bar --mdbVersion ${MDBVERSION} --skipMongosh

#RUN /bin/sh -c "atlas deployments delete ${NAME}"
RUN atlas deployments delete ${NAME}

#RUN atlas deployments setup $NAME --type local --bindIpAll --force \
#    ${USERNAME:+--username $USERNAME} \
#    ${PASSWORD:+--password $PASSWORD} \
#    ${MDBVERSION:+--mdbVersion $MDBVERSION} \
#    --port ${PORT} --skipMongosh

ENTRYPOINT atlas deployments setup --type local --bindIpAll --force \
    ${USERNAME:+--username $USERNAME} \
    ${PASSWORD:+--password $PASSWORD} \
    ${MDBVERSION:+--mdbVersion $MDBVERSION} \
    --port ${PORT} --skipMongosh & tail -f /dev/null

#CMD ["tail", "-f", "/dev/null"]
