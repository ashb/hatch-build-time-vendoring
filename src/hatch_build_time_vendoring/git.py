import os
import shlex
import subprocess
from dataclasses import dataclass
from enum import Enum, auto


class FileStatus(Enum):
    MODIFIED = auto()
    UNTRACKED = auto()
    STAGED = auto()
    DELETED = auto()
    RENAMED = auto()
    COPIED = auto()


@dataclass(frozen=True)
class GitStatusEntry:
    status: FileStatus
    filepath: str
    original_filepath: str | None = None  # For renamed/copied files


def _unquote_filepath(filepath: str) -> str:
    """
    Unquote a filepath from git status output.

    Git quotes filenames that contain spaces or special characters.
    This function handles the unquoting using shlex.
    """
    # Use shlex to properly unquote the string
    return shlex.split(filepath)[0]


def parse_git_status_porcelain(output: str) -> list[GitStatusEntry]:
    """
    Parse git status --porcelain=v1 output and return modified/untracked files.

    Git status --porcelain=v1 format:
    - First character: index status
    - Second character: worktree status
    - Rest: filepath (with optional -> for renames)

    We care about:
    - Modified files (M in worktree position)
    - Untracked files (??)
    - Deleted files (D in worktree position)

    We ignore:
    - Fully staged files (status in index position only, worktree clean)
    """
    entries = []

    for line in output.split("\n"):
        if not line:
            continue

        # Parse the two-character status code
        index_status = line[0]
        worktree_status = line[1]
        filepath_part = line[3:]  # Skip the two status chars and space

        # Skip fully staged files (index has changes, worktree is clean)
        if index_status != " " and worktree_status == " ":
            continue

        original = None
        if " -> " in filepath_part:
            original, filepath_part = filepath_part.split(" -> ", 1)
            original = _unquote_filepath(original)
        filepath_part = _unquote_filepath(filepath_part)

        # Handle untracked files
        match (index_status, worktree_status):
            case ("?", "?"):
                entries.append(GitStatusEntry(status=FileStatus.UNTRACKED, filepath=filepath_part))
            case (_, "M"):
                entries.append(GitStatusEntry(status=FileStatus.MODIFIED, filepath=filepath_part, original_filepath=original))
            case (_, "D"):
                entries.append(GitStatusEntry(status=FileStatus.DELETED, filepath=filepath_part))
            case (_, "R"):
                entries.append(GitStatusEntry(status=FileStatus.RENAMED, filepath=filepath_part, original_filepath=original))
            case ("R", wt) if wt != " ":
                entries.append(GitStatusEntry(status=FileStatus.RENAMED, filepath=filepath_part, original_filepath=original))
            case (_, "C"):
                entries.append(GitStatusEntry(status=FileStatus.COPIED, filepath=filepath_part, original_filepath=original))
            case ("C", wt) if wt != " ":
                entries.append(GitStatusEntry(status=FileStatus.COPIED, filepath=filepath_part, original_filepath=original))

    return entries


def get_modified_and_untracked_files(repo_path: str | os.PathLike = ".") -> list[GitStatusEntry]:
    """
    Get modified and untracked files from git status.

    Args:
        repo_path: Path to the git repository (default: current directory)

    Returns:
        List of GitStatusEntry objects for modified and untracked files

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", os.fspath(repo_path)], cwd=repo_path, capture_output=True, text=True, check=True
        )
        return parse_git_status_porcelain(result.stdout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git command failed: {e.stderr}") from e


def filter_by_status(entries: list[GitStatusEntry], *statuses: FileStatus) -> list[GitStatusEntry]:
    """Filter entries by specific file statuses."""
    return [entry for entry in entries if entry.status in statuses]


def get_filepaths(entries: list[GitStatusEntry]) -> list[str]:
    """Extract just the filepaths from status entries."""
    return [entry.filepath for entry in entries]


# Example usage
if __name__ == "__main__":
    # Get all modified and untracked files
    files = get_modified_and_untracked_files()

    print("Modified and untracked files:")
    for entry in files:
        if entry.original_filepath:
            print(f"  {entry.status.name.lower()}: {entry.original_filepath} -> {entry.filepath}")
        else:
            print(f"  {entry.status.name.lower()}: {entry.filepath}")

    # Get only modified files
    modified_files = filter_by_status(files, FileStatus.MODIFIED)
    print(f"\nModified files: {get_filepaths(modified_files)}")

    # Get only untracked files
    untracked_files = filter_by_status(files, FileStatus.UNTRACKED)
    print(f"Untracked files: {get_filepaths(untracked_files)}")
