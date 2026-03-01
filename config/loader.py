from pathlib import Path
from config.config import Config


def load_config(cwd: Path | None) -> Config:
    cwd = cwd or Path.cwd()
