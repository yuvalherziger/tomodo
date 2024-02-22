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
