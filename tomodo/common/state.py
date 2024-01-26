import os

from tomodo.common.config import TomodoState

DEFAULT_CONFIG_DIR = "~/.config/tomodo"
CONFIG_FILE = "state.yaml"


def resolve_dir(state_dir: str = DEFAULT_CONFIG_DIR) -> str:
    if state_dir.startswith("~/"):
        return os.path.expanduser(state_dir)
    return os.path.abspath(state_dir)


def create_state_dir(state_dir: str = DEFAULT_CONFIG_DIR) -> None:
    os.makedirs(resolve_dir(state_dir), exist_ok=True)


def get_last_known_state(state_dir: str = DEFAULT_CONFIG_DIR) -> TomodoState:
    file_path = os.path.join(resolve_dir(state_dir), CONFIG_FILE)
    try:
        last_known_state = TomodoState.from_file(file_path)
    except FileNotFoundError:
        create_state_dir(state_dir)
        return TomodoState(path=file_path, instances={})
    return last_known_state
