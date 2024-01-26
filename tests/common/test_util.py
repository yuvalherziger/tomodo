import pytest

from tomodo.common.util import parse_2d_separated_string, parse_semver


class TestUtil:

    @staticmethod
    @pytest.mark.parametrize("_str, delimiter_1, delimiter_2, expected",
                             [
                                 ("1=a,2=b,3=c", ",", "=",  {"1": "a", "2": "b", "3": "c"}),
                                 ("1 = a,2 = b", ",", "=",  {"1": "a", "2": "b"}),
                             ])
    def test_parse_2d_separated_string(_str, delimiter_1, delimiter_2, expected):
        actual = parse_2d_separated_string(_str, delimiter_1, delimiter_2)
        assert expected == actual

    @staticmethod
    @pytest.mark.parametrize("version, expected",
                             [
                                 ("3.6.13", (3, 6, 13)),
                                 ("4.0", (4, 0, None)),
                             ])
    def test_parse_semver(version, expected):
        actual = parse_semver(version)
        assert expected == actual
