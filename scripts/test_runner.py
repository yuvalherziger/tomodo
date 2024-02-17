import pytest


def run_tests(coverage_report: str, verbose: bool):
    opts = [
        "tests/unit",
        "--cov",
        "./tomodo",
        f"--cov-report={coverage_report}"
    ]
    if verbose:
        opts.append("--verbose")
    pytest.main(opts)


def ci():
    return run_tests(coverage_report="xml", verbose=False)


def local():
    return run_tests(coverage_report="html", verbose=True)
