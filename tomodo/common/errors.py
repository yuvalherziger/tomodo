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
