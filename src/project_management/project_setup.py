import os
import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel

# The project setup document maps each project code to the folder holding its documents
PROJECTS_SETUP_PATH = Path(os.environ.get("PROJECTS_SETUP_PATH", "projects.yaml"))


class ProjectSetup(BaseModel):
    code: str
    name: str
    folder: Path
    input_dir: Path
    output_dir: Path


def _git(folder: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {folder}: {result.stderr.strip()}")
    return result.stdout.strip()


def load_project_setup(code: str, setup_path: Path = PROJECTS_SETUP_PATH) -> ProjectSetup:
    """Look up the project code in the setup document and check its folder is in a git repository."""
    if not setup_path.is_file():
        raise ValueError(f"Project setup document not found: {setup_path}")
    projects = (yaml.safe_load(setup_path.read_text()) or {}).get("projects") or {}
    if code not in projects:
        raise ValueError(f"Unknown project code {code!r}. Known projects: {', '.join(projects) or 'none'}.")

    config = projects[code]
    if not config.get("folder"):
        raise ValueError(f"Project {code} has no 'folder' in {setup_path}.")
    # A relative folder is relative to the setup document, not to the current directory
    folder = (setup_path.parent / Path(config["folder"]).expanduser()).resolve()
    if not folder.is_dir():
        raise ValueError(f"Folder of project {code} not found: {folder}")
    try:
        _git(folder, "rev-parse", "--show-toplevel")
    except RuntimeError:
        raise ValueError(f"Folder of project {code} is not in a git repository: {folder}")

    return ProjectSetup(
        code=code,
        name=config.get("name", code),
        folder=folder,
        input_dir=folder / config.get("input_dir", "input"),
        output_dir=folder / config.get("output_dir", "output"),
    )


def commit_changes(project: ProjectSetup, paths: list[str], message: str) -> str:
    """Commit only the given files in the project's repository and return the commit hash."""
    _git(project.folder, "add", "--", *paths)
    if not _git(project.folder, "diff", "--cached", "--name-only", "--", *paths):
        return ""
    _git(project.folder, "commit", "-m", message, "--", *paths)
    return _git(project.folder, "rev-parse", "--short", "HEAD")
