"""
Tests for the hatch-build-time-vendoring plugin.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hatch_build_time_vendoring.plugin import VendoringBuildHook


@pytest.fixture
def mock_root(tmp_path):
    """Fixture to provide a mock root directory."""
    return tmp_path


@pytest.fixture
def mock_vendor_path(mock_root):
    """Fixture to provide a mock vendor path."""
    return mock_root / "src" / "_vendor"


@pytest.fixture()
def mock_pyproject(tmp_path):
    """Fixture to provide mock pyproject.toml content."""

    (tmp_path / "pyproject.toml").write_text("""
[tool.vendoring]
destination = "src/_vendor"
requirements = "vendor-requirements.txt"
namespace = "mypackage._vendor"
""")


@pytest.fixture()
def mock_toml_load(mock_pyproject):
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    with patch.object(tomllib, "load") as mock_load:
        yield mock_load


@pytest.fixture
def hook(mock_root):
    """Fixture to provide a hook instance."""
    return VendoringBuildHook(mock_root, {}, {}, {}, None, "sdist")


@pytest.mark.usefixtures("mock_pyproject")
class TestVendoringBuildHook:
    """Tests for the VendoringBuildHook class."""

    def test_initialization(self, mock_root):
        """Test that the hook initializes correctly."""
        # Default configuration
        hook = VendoringBuildHook(mock_root, {}, {}, {}, None, "sdist")
        assert hook.root == mock_root
        assert hook.abort_on_changed_files is True

        # Custom configuration
        hook = VendoringBuildHook(mock_root, {"abort-on-changed-files": False}, {}, {}, None, "sdist")
        assert hook.abort_on_changed_files is False

    def test_determine_vendor_path(self, hook, mock_vendor_path):
        """Test determining the vendor path from configuration."""

        hook._determine_vendor_path()

        assert hook.vendor_dir == "src/_vendor"
        assert hook.vendor_path == mock_vendor_path

    def test_determine_vendor_path_missing_config(self, mock_toml_load, hook):
        """Test determining the vendor path when config is missing."""
        mock_toml_load.return_value = {"tool": {}}

        hook._determine_vendor_path()

        assert hook.vendor_dir is None
        assert hook.vendor_path is None

    @patch("subprocess.run")
    def test_is_git_repo_true(self, mock_run, hook):
        """Test checking if directory is a git repo when it is."""
        mock_run.return_value = MagicMock(returncode=0)

        assert hook._is_git_repo() is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_is_git_repo_false(self, mock_run, hook):
        """Test checking if directory is a git repo when it isn't."""
        mock_run.side_effect = subprocess.SubprocessError()

        assert hook._is_git_repo() is False
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_get_uncommitted_changes(self, mock_run, hook):
        """Test getting uncommitted changes."""
        # Set up the vendor directory
        hook.vendor_dir = "src/_vendor"

        # Mock responses for the three git commands
        mock_run.side_effect = [
            # Untracked files
            MagicMock(stdout="src/_vendor/file1.py\nsrc/_vendor/file2.py", returncode=0),
            # Modified files
            MagicMock(stdout="src/_vendor/file3.py", returncode=0),
            # Staged files
            MagicMock(stdout="src/_vendor/file4.py", returncode=0),
        ]

        untracked, modified = hook._get_uncommitted_changes()

        assert untracked == ["src/_vendor/file1.py", "src/_vendor/file2.py"]
        assert modified == ["src/_vendor/file3.py", "src/_vendor/file4.py"]
        assert mock_run.call_count == 3

    @patch.object(VendoringBuildHook, "_get_uncommitted_changes")
    @patch.object(VendoringBuildHook, "_is_git_repo")
    def test_check_for_uncommitted_changes_clean(self, mock_is_git_repo, mock_get_changes, hook):
        """Test checking for uncommitted changes when everything is clean."""
        mock_is_git_repo.return_value = True
        mock_get_changes.return_value = ([], [])

        # Should not raise any exceptions
        hook._check_for_uncommitted_changes()

    @patch.object(VendoringBuildHook, "_get_uncommitted_changes")
    @patch.object(VendoringBuildHook, "_is_git_repo")
    def test_check_for_uncommitted_changes_with_changes(self, mock_is_git_repo, mock_get_changes, hook):
        """Test checking for uncommitted changes when there are changes."""
        mock_is_git_repo.return_value = True
        mock_get_changes.return_value = (["file1.py"], ["file2.py"])
        hook.vendor_dir = "src/_vendor"
        hook.abort_on_changed_files = True

        # Should raise RuntimeError
        with pytest.raises(RuntimeError):
            hook._check_for_uncommitted_changes()

    @patch.object(VendoringBuildHook, "_get_uncommitted_changes")
    @patch.object(VendoringBuildHook, "_is_git_repo")
    def test_check_for_uncommitted_changes_with_changes_not_aborting(self, mock_is_git_repo, mock_get_changes, hook):
        """Test checking for uncommitted changes with abort disabled."""
        mock_is_git_repo.return_value = True
        mock_get_changes.return_value = (["file1.py"], ["file2.py"])
        hook.vendor_dir = "src/_vendor"
        hook.abort_on_changed_files = False

        # Should not raise any exceptions
        hook._check_for_uncommitted_changes()

    @patch("subprocess.run")
    @patch("pathlib.Path.exists")
    @patch.object(VendoringBuildHook, "_is_git_repo")
    def test_git_clean_vendor_dir(self, mock_is_git_repo, mock_exists, mock_run, hook, mock_vendor_path):
        """Test git cleaning the vendor directory."""
        hook.vendor_dir = "src/_vendor"
        hook.vendor_path = mock_vendor_path
        mock_exists.return_value = True

        hook._git_clean_vendor_dir()

        assert mock_run.call_count == 2
        # Check first call (git clean)
        clean_call = mock_run.call_args_list[0]
        assert clean_call[0][0][0:3] == ["git", "clean", "-fdx"]
        assert clean_call[0][0][-1] == "src/_vendor"

        # Check second call (git checkout)
        checkout_call = mock_run.call_args_list[1]
        assert checkout_call[0][0][0:3] == ["git", "checkout", "--"]
        assert checkout_call[0][0][-1] == "src/_vendor"

    @patch.object(VendoringBuildHook, "_is_git_repo")
    def test_git_clean_not_git_repo(self, mock_is_git_repo, hook):
        """Test git cleaning when not in a git repo."""
        mock_is_git_repo.return_value = False
        hook.vendor_path = Path("/mock/path")

        # Should not raise, just warn
        hook._git_clean_vendor_dir()

    @patch.object(VendoringBuildHook, "_run_vendoring")
    @patch.object(VendoringBuildHook, "_check_for_uncommitted_changes")
    def test_initialize(self, mock_check, mock_run, hook):
        """Test initialize method."""
        with patch("pathlib.Path.exists", return_value=True):
            hook.initialize("1.0.0", {})

        mock_check.assert_called_once()
        mock_run.assert_called_once()

    @patch.object(VendoringBuildHook, "_git_clean_vendor_dir")
    def test_finalize(self, mock_git_clean, hook, mock_vendor_path):
        """Test finalize method."""
        hook.vendor_path = mock_vendor_path

        with patch("pathlib.Path.exists", return_value=True):
            hook.finalize("1.0.0", {}, "artifact.whl")

        mock_git_clean.assert_called_once()

    @patch.object(VendoringBuildHook, "_git_clean_vendor_dir")
    @patch("pathlib.Path.exists")
    def test_finalize_no_vendor_path(self, mock_exists, mock_git_clean, hook):
        """Test finalize method when vendor path is None."""
        hook.vendor_path = None

        hook.finalize("1.0.0", {}, "artifact.whl")

        mock_git_clean.assert_not_called()
