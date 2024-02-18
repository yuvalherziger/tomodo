import json
import logging
from typing import Union
from unittest.mock import Mock, patch, MagicMock

import pytest
from _pytest.logging import LogCaptureFixture
from typer.testing import CliRunner

from tomodo import TOMODO_VERSION
from tomodo.cmd import cli
from tomodo.common.errors import EmptyDeployment, InvalidDeploymentType
from tomodo.common.models import Mongod, ReplicaSet


class TestCmd:

    @staticmethod
    def test_version(cmd_client: Mock):
        engine = "24.0.7"
        platform = "Docker Desktop 4.24.0 (123456)"
        runner = CliRunner()
        expected = {
            "tomodo_version": TOMODO_VERSION,
            "docker_version": {
                "engine": engine,
                "platform": platform
            }
        }
        cmd_client.version.return_value = {
            "Version": engine,
            "Platform": {
                "Name": platform
            }
        }
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert json.loads(result.stdout) == expected

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_with_docker_not_running(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_deployment.return_value = None
        docker_running_patch.return_value = False
        result = CliRunner().invoke(cli, ["stop", "--name", "foo", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.stop_deployment.assert_not_called()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_by_name_with_auto_confirm(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_deployment.return_value = None
        result = CliRunner().invoke(cli, ["stop", "--name", "foo", "--auto-confirm"])
        assert result.exit_code == 0
        mock_cleaner_instance.stop_deployment.assert_called_once()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_by_name_confirmed_positive(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_deployment.return_value = None
        result = CliRunner().invoke(cli, ["stop", "--name", "foo"], input="y\n")
        assert result.exit_code == 0
        mock_cleaner_instance.stop_deployment.assert_called_once()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_by_name_confirmed_negative(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_deployment.return_value = None
        result = CliRunner().invoke(cli, ["stop", "--name", "foo"], input="n\n")
        assert result.exit_code == 0
        mock_cleaner_instance.stop_deployment.assert_not_called()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_by_name_not_found(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                    caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_deployment.side_effect = EmptyDeployment()
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["stop", "--name", "foo", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.stop_deployment.assert_called_once()
        assert "A deployment named 'foo' doesn't exist" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_by_name_raised_tomodo_error(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                              caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_deployment.side_effect = InvalidDeploymentType("InvalidDeployment")
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["stop", "--name", "foo", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.stop_deployment.assert_called_once()
        assert "InvalidDeployment" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_by_name_raised_general_error(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                               caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_deployment.side_effect = ZeroDivisionError()
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["stop", "--name", "foo", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.stop_deployment.assert_called_once()
        assert "Could not stop your deployment - an error has occurred" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_all_with_auto_confirm(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_all_deployments.return_value = None
        result = CliRunner().invoke(cli, ["stop", "--auto-confirm"])
        assert result.exit_code == 0
        mock_cleaner_instance.stop_all_deployments.assert_called_once()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_all_confirmed_positive(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_all_deployments.return_value = None
        result = CliRunner().invoke(cli, ["stop"], input="y\n")
        assert result.exit_code == 0
        mock_cleaner_instance.stop_all_deployments.assert_called_once()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_all_confirmed_negative(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_all_deployments.return_value = None
        result = CliRunner().invoke(cli, ["stop"], input="n\n")
        assert result.exit_code == 0
        mock_cleaner_instance.stop_all_deployments.assert_not_called()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_all_raised_tomodo_error(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                          caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_all_deployments.side_effect = InvalidDeploymentType("InvalidDeployment")
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["stop", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.stop_all_deployments.assert_called_once()
        assert "InvalidDeployment" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_stop_all_raised_general_error(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                           caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.stop_all_deployments.side_effect = ZeroDivisionError()
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["stop", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.stop_all_deployments.assert_called_once()
        assert "Could not stop your deployments - an error has occurred" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Starter")
    @patch("tomodo.cmd.is_docker_running")
    def test_start(docker_running_patch: MagicMock, starter_patch: MagicMock):
        mock_starter_instance = starter_patch.return_value
        mock_starter_instance.start_deployment.return_value = None
        result = CliRunner().invoke(cli, ["start", "--name", "foo"])
        assert result.exit_code == 0
        mock_starter_instance.start_deployment.assert_called_once()

    @staticmethod
    @patch("tomodo.cmd.Starter")
    @patch("tomodo.cmd.is_docker_running")
    def test_start_not_found(docker_running_patch: MagicMock, starter_patch: MagicMock, caplog: LogCaptureFixture):
        mock_starter_instance = starter_patch.return_value
        mock_starter_instance.start_deployment.side_effect = EmptyDeployment()
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["start", "--name", "foo"])
        assert result.exit_code == 1
        mock_starter_instance.start_deployment.assert_called_once()
        assert "A deployment named 'foo' doesn't exist" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Starter")
    @patch("tomodo.cmd.is_docker_running")
    def test_start_raises_tomodo_error(docker_running_patch: MagicMock, starter_patch: MagicMock,
                                       caplog: LogCaptureFixture):
        mock_starter_instance = starter_patch.return_value
        mock_starter_instance.start_deployment.side_effect = InvalidDeploymentType("InvalidDeployment")
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["start", "--name", "foo"])
        assert result.exit_code == 1
        mock_starter_instance.start_deployment.assert_called_once()
        assert "InvalidDeployment" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_by_name_with_auto_confirm(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_deployment.return_value = None
        result = CliRunner().invoke(cli, ["remove", "--name", "foo", "--auto-confirm"])
        assert result.exit_code == 0
        mock_cleaner_instance.delete_deployment.assert_called_once()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_by_name_confirmed_positive(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_deployment.return_value = None
        result = CliRunner().invoke(cli, ["remove", "--name", "foo"], input="y\n")
        assert result.exit_code == 0
        mock_cleaner_instance.delete_deployment.assert_called_once()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_by_name_confirmed_negative(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_deployment.return_value = None
        result = CliRunner().invoke(cli, ["remove", "--name", "foo"], input="n\n")
        assert result.exit_code == 0
        mock_cleaner_instance.delete_deployment.assert_not_called()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_by_name_not_found(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                      caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_deployment.side_effect = EmptyDeployment()
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["remove", "--name", "foo", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.delete_deployment.assert_called_once()
        assert "A deployment named 'foo' doesn't exist" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_by_name_raised_tomodo_error(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                                caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_deployment.side_effect = InvalidDeploymentType("InvalidDeployment")
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["remove", "--name", "foo", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.delete_deployment.assert_called_once()
        assert "InvalidDeployment" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_by_name_raised_general_error(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                                 caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_deployment.side_effect = ZeroDivisionError()
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["remove", "--name", "foo", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.delete_deployment.assert_called_once()
        assert "Could not remove your deployment - an error has occurred" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_all_with_auto_confirm(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_all_deployments.return_value = None
        result = CliRunner().invoke(cli, ["remove", "--auto-confirm"])
        assert result.exit_code == 0
        mock_cleaner_instance.delete_all_deployments.assert_called_once()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_all_confirmed_positive(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_all_deployments.return_value = None
        result = CliRunner().invoke(cli, ["remove"], input="y\n")
        assert result.exit_code == 0
        mock_cleaner_instance.delete_all_deployments.assert_called_once()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_all_confirmed_negative(docker_running_patch: MagicMock, cleaner_patch: MagicMock):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_all_deployments.return_value = None
        result = CliRunner().invoke(cli, ["remove"], input="n\n")
        assert result.exit_code == 0
        mock_cleaner_instance.delete_all_deployments.assert_not_called()

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_all_raised_tomodo_error(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                            caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_all_deployments.side_effect = InvalidDeploymentType("InvalidDeployment")
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["remove", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.delete_all_deployments.assert_called_once()
        assert "InvalidDeployment" in caplog.text

    @staticmethod
    @patch("tomodo.cmd.Cleaner")
    @patch("tomodo.cmd.is_docker_running")
    def test_remove_all_raised_general_error(docker_running_patch: MagicMock, cleaner_patch: MagicMock,
                                             caplog: LogCaptureFixture):
        mock_cleaner_instance = cleaner_patch.return_value
        mock_cleaner_instance.delete_all_deployments.side_effect = ZeroDivisionError()
        with caplog.at_level(logging.INFO):
            result = CliRunner().invoke(cli, ["remove", "--auto-confirm"])
        assert result.exit_code == 1
        mock_cleaner_instance.delete_all_deployments.assert_called_once()
        assert "Could not remove your deployments - an error has occurred" in caplog.text

    @staticmethod
    @pytest.mark.parametrize(
        "fmt, exc",
        [
            ("json", None),
            ("yaml", None),
            ("table", None),
            ("json", InvalidDeploymentType()),
            ("json", KeyError())]
    )
    @patch("tomodo.cmd.Reader")
    @patch("tomodo.cmd.list_deployments_in_markdown_table")
    @patch("tomodo.cmd.is_docker_running")
    def test_list(docker_running_patch: MagicMock,
                  list_deployments_in_markdown_table_patch: MagicMock,
                  reader_patch: MagicMock,
                  fmt: str,
                  exc: Union[Exception, None],
                  mongod: Mongod,
                  replica_set: ReplicaSet):
        mock_reader_instance = reader_patch.return_value
        if not exc:
            if fmt == "table":
                list_deployments_in_markdown_table_patch.return_value = "#"
            else:
                mock_reader_instance.get_all_deployments.return_value = {
                    mongod.name: mongod,
                    replica_set.name: replica_set
                }
        else:
            mock_reader_instance.get_all_deployments.side_effect = exc
        result = CliRunner().invoke(cli, ["list", "--output", fmt])
        assert result.exit_code == (1 if exc else 0)
        if fmt == "table":
            list_deployments_in_markdown_table_patch.assert_called_once()
        else:
            mock_reader_instance.get_all_deployments.assert_called_once()
    @staticmethod
    @pytest.mark.parametrize("exc", [None, InvalidDeploymentType(), ValueError()])
    @patch("tomodo.cmd.Reader")
    @patch("tomodo.cmd.Provisioner")
    @patch("tomodo.cmd.is_docker_running")
    def test_provision(docker_running_patch: MagicMock,
                       provisioner_patch: MagicMock,
                       reader_patch: MagicMock,
                       exc: Union[Exception, None],
                       mongod: Mongod,
                       replica_set: ReplicaSet):
        mock_reader_instance = reader_patch.return_value
        mock_reader_instance.get_deployment_by_name.return_value = None
        mock_provisioner_instance = provisioner_patch.return_value
        if not exc:
            mock_provisioner_instance.provision.return_value = None
        else:
            mock_provisioner_instance.provision.side_effect = exc
        result = CliRunner().invoke(cli, ["provision", "--sharded"])
        mock_provisioner_instance.provision.assert_called_once()
        assert result.exit_code == (1 if exc else 0)

    ##################################################################################################

    @staticmethod
    @pytest.mark.parametrize(
        "fmt, exc, by_name",
        [
            ("json", None, True),
            ("yaml", None, True),
            ("table", None, True),
            ("json", EmptyDeployment(), True),
            ("json", InvalidDeploymentType(), True),
            ("json", KeyError(), True),
            ("json", None, False),
            ("yaml", None, False),
            ("table", None, False),
            ("json", InvalidDeploymentType(), False),
            ("json", KeyError(), False),
        ]
    )
    @patch("tomodo.cmd.Reader")
    @patch("tomodo.cmd.is_docker_running")
    def test_describe(docker_running_patch: MagicMock,
                      reader_patch: MagicMock,
                      fmt: str,
                      exc: Union[Exception, None],
                      by_name: bool,
                      mongod: Mongod,
                      replica_set: ReplicaSet):
        mock_reader_instance = reader_patch.return_value
        args = ["describe", "--output", fmt]
        if by_name:
            args.extend(["--name", replica_set.name])
            if not exc:
                if fmt == "table":
                    mock_reader_instance.describe_by_name.return_value = "#"
                else:
                    mock_reader_instance.get_deployment_by_name.return_value = replica_set
            else:
                mock_reader_instance.get_deployment_by_name.side_effect = exc
        else:
            if not exc:
                if fmt == "table":
                    mock_reader_instance.describe_all.return_value = ["#", "#"]
                else:
                    mock_reader_instance.get_all_deployments.return_value = {
                        mongod.name: mongod,
                        replica_set.name: replica_set
                    }
            else:
                mock_reader_instance.get_all_deployments.side_effect = exc

        result = CliRunner().invoke(cli, args)
        assert result.exit_code == (1 if exc else 0)
        if by_name:
            if fmt == "table":
                mock_reader_instance.describe_by_name.assert_called_once()
            else:
                mock_reader_instance.get_deployment_by_name.assert_called_once()
        else:
            if fmt == "table":
                mock_reader_instance.describe_all.assert_called_once()
            else:
                mock_reader_instance.get_all_deployments.assert_called_once()
