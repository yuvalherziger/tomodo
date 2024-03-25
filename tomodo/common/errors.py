class TomodoError(Exception):
    pass


class DeploymentNotFound(TomodoError):
    pass


class DeploymentNameCollision(TomodoError):
    pass


class InvalidDeploymentType(TomodoError):
    def __init__(self, deployment_type: str = None):
        self.deployment_type = deployment_type


class InvalidConfiguration(TomodoError):
    pass


class PortsTakenException(TomodoError):
    pass


class InvalidShellException(TomodoError):
    pass


class MongoDBImageNotFound(TomodoError):

    def __init__(self, image: str = None):
        self.image = image

    def __str__(self) -> str:
        return f"The image {self.image + ' ' if self.image else ''}could not be pulled."


class BlueprintDeploymentNotFound(TomodoError):
    def __init__(self, deployment_name: str, forced_snapshot: bool = False):
        self.deployment_name = deployment_name
        self.forced_snapshot = forced_snapshot

    def __str__(self) -> str:
        if self.forced_snapshot:
            return f"The deployment '{self.deployment_name}' is not running now."
        else:
            return f"The deployment '{self.deployment_name}' doesn't have an existing snapshot, nor is it running now."
