import logging
from pathlib import Path
from typing import Any
from config.config import Config
from platformdirs import user_config_dir, user_data_dir
import tomli
from utils.errors import ConfigError


CONFIG_FILE_NAME = "config.toml"
AGENT_MD_FILE = "agent.md"

logger = logging.getLogger(__name__)


def get_config_dir() -> Path:
    # global config path dir -> ~/Library/Application Support/agentic-cli/config.toml (in macos) platform dirs is used to get global file access, the path is different on windows/linux
    return Path(user_config_dir("agentic-cli"))


def get_data_dir() -> Path:
    return Path(user_data_dir("agentic-cli"))


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
    # project config path -> nodebase/.agentic-cli/config.toml
    # specific to the current project only
    current = cwd.resolve()
    agent_dir = current/'.agentic-cli'

    if agent_dir.is_dir():
        config_file = agent_dir/CONFIG_FILE_NAME
        if config_file.is_file():
            return config_file

    return None


def _get_agent_md_file_content(cwd: Path) -> str | None:
    current = cwd.resolve()

    if current.is_dir():
        agent_md_file = current/AGENT_MD_FILE
        if agent_md_file.is_file():
            content = agent_md_file.read_text(encoding='utf-8')
            return content

    return None


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    # override dict ka hi chalega
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def load_config(cwd: Path | None) -> Config | None:
    cwd = cwd or Path.cwd()
    # system config file -> config.yaml file se sab configs extract kar sakte hai
    system_path = get_system_config_path()
    # this wont crash if the file doesnt exist (Path("doesnot-exist")) is valid, just p.open() p.close() read() aisa kuch kiya toh hi crash hoga, yaha par .is_file() false return kardega to issue nai hai

    # temp dict to collect data before validation
    config_dict: dict[str, Any] = {}
    config = None

    # even if the system_path doesn't exist, the code wont crash, as it checks if this is a file or not
    if system_path.is_file():
        try:
            project_config_dict = _parse_toml(system_path)
            config_dict = _merge_dicts(config_dict, project_config_dict)
        except ConfigError:
            logger.warning(f"skipping invalid system config: {system_path}")

        project_path = _get_project_config(cwd)
        # merge project config dict with main config dict
        if project_path:
            try:
                project_config_dict = _parse_toml(project_path)
                config_dict = _merge_dicts(config_dict, project_config_dict)
            except ConfigError:
                logger.warning(f"skipping invalid system config: {system_path}")

        if "cwd" not in config_dict:
            config_dict["cwd"] = cwd

        if "developer_instructions" not in config_dict:
            agent_md_content = _get_agent_md_file_content(cwd)
            if agent_md_content:
                config_dict["developer_instructions"] = agent_md_content

    config = None
    # if the user doesnt have a predefined config, then the config constructor is called to intialize with pydantic values
    try:
        # og config:Config passed (python object, not dict)
        config = Config(**config_dict)
    except Exception as e:
        raise ConfigError(f"invalid configuration: {e}") from e
    return config
