import PyInstaller.__main__
from pathlib import Path

here = Path(__file__).parent.absolute()
path_to_main = str(here / "cmd.py")


def install():
    PyInstaller.__main__.run([
        path_to_main,
        '--onefile',
        '--console',
        '--name', 'tomodo',
    ])
