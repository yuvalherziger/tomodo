from pathlib import Path

import PyInstaller.__main__

here = Path(__file__).parent.absolute()
path_to_main = str(here / "cmd.py")


def install_amd64():
    install("amd64")


def install_arm64():
    install("arm64")


def install(platform: str):
    PyInstaller.__main__.run([
        path_to_main,
        "--onedir",
        "--console",
        "--name", "tomodo",
        "--distpath", f"dist-{platform}",
        "--target-architecture", platform if platform == "arm64" else "x86_64"
    ])
