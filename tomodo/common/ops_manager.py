import logging

from rich.console import Console

from tomodo import Provisioner, ProvisionerConfig

DOCKER_ENDPOINT_CONFIG_VER = "1.43"

console = Console()
logger = logging.getLogger("rich")


class OpsManagerProvisioner(Provisioner):
    def __init__(self, config: ProvisionerConfig):
        super().__init__(config)
