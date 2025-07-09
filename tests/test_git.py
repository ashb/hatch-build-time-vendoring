import subprocess
from unittest.mock import MagicMock, patch

import pytest

from hatch_build_time_vendoring.git import (
    FileStatus,
    GitStatusEntry,
    get_modified_and_untracked_files,
    parse_git_status_porcelain,
)


def get_filepaths(entries: list[GitStatusEntry]) -> list[str]:
    """Extract just the filepaths from status entries."""
    return [entry.filepath for entry in entries]


@pytest.fixture
def sample_entries():
    """Sample git status entries for testing."""
    return [
        GitStatusEntry(FileStatus.MODIFIED, "modified.py"),
        GitStatusEntry(FileStatus.UNTRACKED, "untracked.py"),
        GitStatusEntry(FileStatus.DELETED, "deleted.py"),
        GitStatusEntry(FileStatus.RENAMED, "renamed.py", "old.py"),
    ]


@pytest.fixture
def mock_successful_git_run():
    """Mock successful git command execution."""
    with patch("hatch_build_time_vendoring.git.subprocess.run", autospec=True) as mock_run:
        mock_result = MagicMock()
        mock_result.stdout = "?? test.py\n M another.py"
        mock_run.return_value = mock_result
        yield mock_run


@pytest.fixture
def mock_failed_git_run():
    """Mock failed git command execution."""
    with patch("hatch_build_time_vendoring.git.subprocess.run", autospec=True) as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, ["git", "status"], stderr="Not a git repository")
        yield mock_run


# Test functions for parsing git status porcelain output
def test_parse_empty_output():
    """Test parsing empty git status output returns empty list."""
    output = ""

    result = parse_git_status_porcelain(output)

    assert result == []


@pytest.mark.parametrize(
    ("output", "expected"),
    (
        pytest.param("?? file.py", [GitStatusEntry(FileStatus.UNTRACKED, "file.py")], id="untracked"),
        pytest.param(" M file.py", [GitStatusEntry(FileStatus.MODIFIED, "file.py")], id="modified"),
        pytest.param(" D file.py", [GitStatusEntry(FileStatus.DELETED, "file.py")], id="deleted"),
        pytest.param("A file.py", [], id="fully-staged"),
        pytest.param("M file.py", [], id="staged-modified"),
        pytest.param("MM file.py", [GitStatusEntry(FileStatus.MODIFIED, "file.py")], id="staged-and-modified"),
        pytest.param("AM file.py", [GitStatusEntry(FileStatus.MODIFIED, "file.py")], id="added-and-modified"),
        pytest.param("R  old.py -> file.py", [], id="renamed-and-staged"),
        pytest.param(
            "RM old.py -> file.py", [GitStatusEntry(FileStatus.MODIFIED, "file.py", "old.py")], id="renamed-and-modified"
        ),
        pytest.param("UU old.py", [], id="conflicted"),
    ),
)
def test_parse_untracked_file(output, expected):
    result = parse_git_status_porcelain(output)

    assert result == expected


def test_parse_multiple_files():
    """Test parsing multiple files with different statuses ignores staged-only files."""
    # Arrange
    output = """?? untracked.py
 M modified.py
 D deleted.py
A  staged.py
MM staged_and_modified.py"""

    # Act
    result = parse_git_status_porcelain(output)

    # Assert
    assert len(result) == 4  # staged.py should be ignored

    statuses = [entry.status for entry in result]
    filepaths = [entry.filepath for entry in result]

    assert FileStatus.UNTRACKED in statuses
    assert FileStatus.MODIFIED in statuses
    assert FileStatus.DELETED in statuses
    assert "untracked.py" in filepaths
    assert "modified.py" in filepaths
    assert "deleted.py" in filepaths
    assert "staged_and_modified.py" in filepaths
    assert "staged.py" not in filepaths


def test_parse_mixed_index_worktree_statuses():
    """Test parsing files with different index and worktree statuses."""
    # Arrange
    output = """AM added_and_modified.py
RM renamed_and_modified.py -> new_name.py
CM copied_and_modified.py -> copy_name.py"""

    # Act
    result = parse_git_status_porcelain(output)

    # Assert
    assert len(result) == 3

    # Check that all have modified status (since worktree has M)
    for entry in result:
        assert entry.status in [FileStatus.MODIFIED, FileStatus.RENAMED, FileStatus.COPIED]


# Test functions for git command execution
def test_successful_git_command(mock_successful_git_run):
    """Test successful git status command execution returns parsed entries."""
    # Act
    result = get_modified_and_untracked_files()

    # Assert
    mock_successful_git_run.assert_called_once_with(
        ["git", "status", "--porcelain=v1", "."], cwd=".", capture_output=True, text=True, check=True
    )

    assert len(result) == 2
    assert result[0].status == FileStatus.UNTRACKED
    assert result[1].status == FileStatus.MODIFIED


def test_git_command_failure(mock_failed_git_run):
    """Test git command failure raises RuntimeError with appropriate message."""
    # Act & Assert
    with pytest.raises(RuntimeError, match="Git command failed") as exc_info:
        get_modified_and_untracked_files()
    assert isinstance(exc_info.value.__cause__, subprocess.CalledProcessError)


def test_integration_with_real_git_status_format():
    """Test integration with realistic git status --porcelain=v1 output."""
    # Arrange
    output = """?? .gitignore
 M README.md
 D old_file.txt
A  new_staged_file.py
MM src/main.py
R  old_name.py -> src/new_name.py
C  template.py -> src/copy.py
 M "file with spaces.txt"
?? "another spaced file.py" """

    # Act
    all_entries = parse_git_status_porcelain(output)

    # Assert
    assert len(all_entries) == 6  # new_staged_file.py should be ignored

    # Check specific entries
    filepaths = get_filepaths(all_entries)
    assert ".gitignore" in filepaths
    assert "README.md" in filepaths
    assert "old_file.txt" in filepaths
    assert "src/main.py" in filepaths
    assert "src/new_name.py" not in filepaths
    assert "src/copy.py" not in filepaths
    assert "file with spaces.txt" in filepaths
    assert "another spaced file.py" in filepaths
    assert "new_staged_file.py" not in filepaths
