from tomodo.common.config import UpgradeConfig


class TestConfig:

    @staticmethod
    def test_basic_config():
        config = UpgradeConfig(target_version="7.0", hostname="mongodb://localhost")
        assert config is not None
        assert config.hostname == "mongodb://localhost"

    @staticmethod
    def test_srv_hostname():
        config = UpgradeConfig(target_version="7.0", hostname="mongodb+srv://localhost:27018")
        assert config.hostname == "mongodb+srv://localhost:27018"

    @staticmethod
    def test_separate_hostname_and_creds():
        config = UpgradeConfig(
            target_version="7.0",
            hostname="mongodb://localhost:27017",
            username="john",
            password="password"
        )
        assert config.hostname == "mongodb://john:password@localhost:27017"

    @staticmethod
    def test_url_with_creds():
        config = UpgradeConfig(
            target_version="7.0",
            hostname="mongodb://jayne:password@localhost:27017"
        )
        assert config.hostname == "mongodb://jayne:password@localhost:27017"
        assert config.username == "jayne"
        assert config.password == "password"
        assert config.localhost == "mongodb://localhost:27017"

    @staticmethod
    def test_with_invalid_hostname():
        raised = False
        try:
            _ = UpgradeConfig(
                target_version="7.0",
                hostname="localhost:27017"
            )
        except ValueError as e:
            raised = True
            assert str(e) == "Invalid hostname - the MongoDB hostname must start with a valid MongoDB scheme"
        assert raised, "A ValueError wasn't raised on an invalid hostname"
