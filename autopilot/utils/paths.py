from pathlib import Path

# Path is a class to check for a subpath, remove extension from file name, works on all OS, checks and removes ../ and all


def resolve_path(base: str | Path, path: str | Path):
    # converting the input string to a path on all cases
    path = Path(path)
    if path.is_absolute():
        return path.resolve()
    # for relative paths, / auto joins the prefix
    return Path(base).resolve() / path


def display_path_rel_to_cwd(path: Path, cwd: Path | None) -> str:
    try:
        p = Path(path)
    except Exception:
        return str(path)

    if cwd:
        try:
            return str(p.relative_to(cwd))
        except ValueError:
            pass

    return str(p)


def is_binary_file(path: str | Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, IOError):
        return False

# to check whether the parent directory already exists


def ensure_parent_directory(path: str | Path) -> Path:
    path = Path(path)
    # parents -> nested folder creation, not file (only folder)
    # exist_ok -> doesnt return a fileexists error if its already present
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
