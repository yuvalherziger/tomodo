import logging
import platform
from typing import Union

import requests
from docker.models.containers import Container
from docker.types import NetworkingConfig, EndpointConfig
from rich.console import Console
from rich.markdown import Markdown

from tomodo import Provisioner, OpsManagerConfig, Reader
from tomodo.common.errors import PortsTakenException
from tomodo.common.models import ReplicaSet, Mongod
from tomodo.common.util import with_retry, is_port_range_available

DOCKER_ENDPOINT_CONFIG_VER = "1.43"

console = Console()
logger = logging.getLogger("rich")
OM_REPO = "ghcr.io/yuvalherziger/tomodo-mms"
OM_TAG = "main"
APP_DB_VERSION = "7.0"

READINESS_MAX_ATTEMPTS = 20
READINESS_DELAY = 15


class OpsManagerProvisioner(Provisioner):
    def __init__(self, config: OpsManagerConfig):
        self.om_config = config
        super().__init__(config=config.app_db_config)

    def create_om_container(self, app_db: Union[ReplicaSet, Mongod]) -> Container:
        app_db_hostname = app_db.hostname
        logger.info("Creating Ops Manager server using the following App DB: '%s'", app_db_hostname)
        environment = [
            f"APPDB_HOST={app_db_hostname}",
            f"MMS_PORT={self.om_config.port}"
        ]
        networking_config = NetworkingConfig(
            endpoints_config={
                self.network.name: EndpointConfig(version=DOCKER_ENDPOINT_CONFIG_VER, aliases=[self.om_config.name])
            }
        )
        return self.docker_client.containers.run(
            f"{OM_REPO}:{OM_TAG}",
            detach=True,
            ports={f"{self.om_config.port}/tcp": self.om_config.port},
            platform=f"linux/{platform.machine()}",
            network=self.network.id,
            hostname=self.om_config.name,
            name=self.om_config.name,
            networking_config=networking_config,
            environment=environment,
            labels={
                "source": "tomodo",
                "tomodo-name": self.om_config.name,
                "tomodo-group": self.om_config.name,
                "tomodo-parent": self.om_config.name,
                "tomodo-port": str(self.om_config.port),
                "tomodo-network": self.network.name,
                "tomodo-role": "ops-manager",
                "tomodo-type": "ops-manager"
            }
        )

    def create_app_db(self) -> Union[ReplicaSet, Mongod]:
        logger.info("Creating Ops Manager's App DB")
        app_db = self.provision(deployment_getter=Reader().get_deployment_by_name, print_summary=False)
        return app_db

    @with_retry(max_attempts=READINESS_MAX_ATTEMPTS, delay=READINESS_DELAY)
    def wait_for_ops_manager_readiness(self) -> None:
        try:
            resp = requests.get(
                f"http://localhost:{self.om_config.port}/api/public/v1.0"
            )
            if resp.status_code in [200, 401]:
                logger.info("Ops Manager is ready!")
                return
        except Exception as e:
            logger.debug(str(e))

        logger.info("[Polling] Ops Manager isn't ready yet; waiting %d seconds before the next retry", READINESS_DELAY)
        raise Exception("Ops Manager isn't ready yet")

    def create(self) -> None:
        if not is_port_range_available(tuple(range(self.om_config.port, self.om_config.port + 1))):
            raise PortsTakenException("At least one desired port is taken; existing")
        logger.info("Provisioning MongoDB Ops Manager; be advised that the image is quite big (>2 GB)")
        app_db: Union[ReplicaSet, Mongod] = self.create_app_db()
        self.check_and_pull_image(image_name=f"{OM_REPO}:{OM_TAG}")
        self.create_om_container(app_db=app_db)
        logger.info(
            "Ops Manager creating! Note that it might take Ops Manager several minutes "
            "before it's ready to accept requests - hang tight."
        )
        self.wait_for_ops_manager_readiness()
        self.print_ops_manager_summary()

    def print_ops_manager_summary(self):
        markdown = Markdown(f"""
-------------------------

**Connect to your Ops Manager instance:**

You'll be prompted to register your first admin account via the UI:
[http://localhost:{self.om_config.port}/account/register](http://localhost:{self.om_config.port}/account/register)

-------------------------

**Add nodes for deployments:**

Generate an agent API key (see here: [https://www.mongodb.com/docs/ops-manager/current/tutorial/manage-agent-api-key/](https://www.mongodb.com/docs/ops-manager/current/tutorial/manage-agent-api-key/))
and then use it with `tomodo` to provision new servers in Ops Manager.  For example:

```shell
tomodo ops-manager add-server {self.om_config.name} --count 3 --project-id <PROJECT_ID> --api-key <AGENT_API_KEY>
```

-------------------------
""", justify="full")

        console.print(markdown)
