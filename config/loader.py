import logging
from pathlib import Path
from typing import Any
from config.config import Config
from platformdirs import user_config_dir
import tomli
from utils.errors import ConfigError
CONFIG_FILE_NAME = "config.toml"

logger = logging.getLogger(__name__)


def get_config_dir() -> Path:
    return Path(user_config_dir("agentic-cli"))


def get_system_config_path() -> Path:
    return get_config_dir()/CONFIG_FILE_NAME


def _parse_toml(path: Path):
    try:
        with open(path, 'rb') as f:
            return tomli.load(f)  # returns a dict
    except tomli.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {path}: {e}", config_file=str(path)) from e
    except (OSError, IOError) as e:
        raise ConfigError(f"failed to read config file {path} : {e}", config_file=str(path)) from e


def _get_project_config(cwd: Path) -> Path | None:
    current = cwd.resolve()
    agent_dir = current/'.agentic-cli'

    if agent_dir.is_dir():
        config_file = agent_dir/CONFIG_FILE_NAME
        if config_file.is_file():
            return config_file

    return None


def load_config(cwd: Path | None) -> Config:
    cwd = cwd or Path.cwd()
    # system config file -> config.yaml file se sab configs extract kar sakte hai
    system_path = get_system_config_path()

    config_dict: dict[str, Any] = {}

    if system_path.is_file():
        try:
            config_dict = _parse_toml(system_path)
        except ConfigError:
            logger.warning(f"skipping invalid system config: {system_path}")

        project_path = _get_project_config(cwd)
        # merge project config dict with main config dict
        if project_path:
            try:
                project_config_dict = _parse_toml(project_path)
            except ConfigError:
                logger.warning(f"skipping invalid system config: {system_path}")
