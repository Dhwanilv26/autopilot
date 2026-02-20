from pathlib import Path

# Path is a class to check for a subpath, remove extension from file name, works on all OS, checks and removes ../ and all

def resolve_path(base: str | Path, path: str | Path):
    # converting the input string to a path on all cases
    path = Path(path)
    if path.is_absolute():
        return path.resolve()
    # for relative paths, / auto joins the prefix
    return Path(base).resolve() / path
