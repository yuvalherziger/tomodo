import logging
from unittest.mock import Mock

import docker
import pytest
from _pytest.logging import LogCaptureFixture

from tomodo.common.util import parse_2d_separated_string, parse_semver, anonymize_connection_string, \
    is_port_range_available, is_docker_running, with_retry, AnonymizingFilter

global divider


class TestUtil:

    @staticmethod
    @pytest.mark.parametrize("_str, delimiter_1, delimiter_2, expected",
                             [
                                 ("1=a,2=b,3=c", ",", "=", {"1": "a", "2": "b", "3": "c"}),
                                 ("1 = a,2 = b", ",", "=", {"1": "a", "2": "b"}),
                                 (None, ",", "=", None)
                             ])
    def test_parse_2d_separated_string(_str, delimiter_1, delimiter_2, expected):
        actual = parse_2d_separated_string(_str, delimiter_1, delimiter_2)
        assert expected == actual

    @staticmethod
    @pytest.mark.parametrize("version, expected, expected_exception",
                             [
                                 ("3.6.13", (3, 6, 13), None),
                                 ("4.0", (4, 0, None), None),
                                 ("foo.bar", None, ValueError),
                             ])
    def test_parse_semver(version, expected, expected_exception):
        try:
            actual = parse_semver(version)
            assert expected == actual
        except Exception as e:
            assert isinstance(e, expected_exception)

    @staticmethod
    @pytest.mark.parametrize("input_str, expected_str",
                             [
                                 ("mongodb://localhost", "mongodb://localhost"),
                                 ("mongodb://localhost:27017", "mongodb://localhost:27017"),
                                 ("mongodb://username:password@localhost:27017",
                                  "mongodb://username:************@localhost:27017"),
                             ])
    def test_anonymize_connection_string(input_str, expected_str):
        assert expected_str == anonymize_connection_string(input_str)

    @staticmethod
    def test_is_port_range_available_positive(socket: Mock):
        port_range = (27017, 27018, 27019)
        socket.connect_ex.return_value = 1
        socket.close.return_value = None
        assert is_port_range_available(port_range=port_range, host="localhost")

    @staticmethod
    def test_is_port_range_available_negative(socket: Mock):
        port_range = (27017, 27018, 27019)
        socket.connect_ex.return_value = 0
        socket.close.return_value = None
        assert not is_port_range_available(port_range=port_range, host="localhost")

    @staticmethod
    def test_is_docker_running_positive(util_client: Mock):
        util_client.ping.return_value = None
        assert is_docker_running()

    @staticmethod
    def test_is_docker_running_negative(util_client: Mock):
        util_client.ping.side_effect = docker.errors.APIError("")
        assert not is_docker_running()

    @staticmethod
    def test_with_retry_decorator_eventually_succeeds():
        @with_retry(max_attempts=5, delay=0, retryable_exc=(ZeroDivisionError,))
        def test_function(may_fail_times):
            if may_fail_times[0] > 0:
                may_fail_times[0] -= 1
                _ = 1 / 0
            return 1

        assert test_function([4]) == 1

    @staticmethod
    def test_with_retry_decorator_eventually_fails():
        @with_retry(max_attempts=5, delay=0, retryable_exc=(ZeroDivisionError,))
        def test_function(may_fail_times):
            if may_fail_times[0] > 0:
                may_fail_times[0] -= 1
                _ = 1 / 0
            return 1

        raised = False
        try:
            test_function([5])
        except ZeroDivisionError:
            raised = True
        assert raised

    @staticmethod
    def test_with_retry_decorator_eventually_fails_and_ignored():
        @with_retry(max_attempts=5, delay=0, retryable_exc=(ZeroDivisionError,), ignore=True)
        def test_function(may_fail_times):
            if may_fail_times[0] > 0:
                may_fail_times[0] -= 1
                _ = 1 / 0
            return 1

        raised = False
        try:
            res = test_function([5])
            assert res is None
        except ZeroDivisionError:
            raised = True
        assert not raised

    @staticmethod
    def test_with_retry_decorator_fails_with_non_retryable():
        @with_retry(max_attempts=2, delay=0, retryable_exc=(ZeroDivisionError,))
        def test_function(may_fail_times):
            if may_fail_times[0] > 0:
                may_fail_times[0] -= 1
                raise ValueError
            return 1

        raised = False
        try:
            res = test_function([4])
        except ValueError:
            raised = True
        assert raised

    @staticmethod
    def test_anonymizing_filter(caplog: LogCaptureFixture):
        logger = logging.getLogger("test_logger")
        logger.setLevel(logging.DEBUG)
        logger.handlers = []
        stream_handler = logging.StreamHandler()
        logger.addHandler(stream_handler)
        logger.addFilter(AnonymizingFilter())
        with caplog.at_level(logging.INFO):
            logger.info(
                "Your hostname is %s", "mongodb://username:password@localhost:27017"
            )

            logger.info(
                "Your hostname is %s", {"hostname": "mongodb://username:password@localhost:27017"}
            )
            logger.info(
                "Your hostname is %s", {"some_int": 1}
            )
        assert "username:password" not in caplog.text
        assert "username:************" in caplog.text
