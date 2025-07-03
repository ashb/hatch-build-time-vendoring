"""
Hatch build hook plugin for vendoring dependencies during build.

This plugin runs the vendoring tool before building packages and then
uses git to clean up the vendored files afterward, ensuring they only
exist during the build process.
"""

import os
import shutil
import subprocess
from functools import wraps
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class VendoringBuildHook(BuildHookInterface):
    """Build hook that vendors dependencies during the build process."""

    PLUGIN_NAME = "vendoring"

    vendor_path: Path | None = None
    vendor_dir: str | None

    def __init__(self, root: str, config: dict[str, Any], *args, **kwargs) -> None:
        super().__init__(root, config, *args, **kwargs)
        self.abort_on_changed_files = config.get("abort-on-changed-files", True)

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Initialize the build hook by running vendoring."""
        # Determine the vendor directory path from vendoring configuration
        self._determine_vendor_path()

        # Run vendoring tool to create vendored dependencies
        if self.target_name != "sdist" and Path(self.root, "PKG-INFO").exists():
            # When you do `build mydist/` it will build the sdist, and then build the wheel from that.
            # In this case we want to avoid running vendoring again for the wheel build
            self.app.display_info(f"Skipping vendoring as we appear to be building {self.target_name} from an extracted sdist")
            self.vendor_path = None
            return

        # Check for uncommitted changes in vendor directory
        if self.vendor_path and self.vendor_path.exists():
            self._check_for_uncommitted_changes()
        self._run_vendoring()

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        """Clean up vendored files after the build is complete using git."""
        if self.vendor_path and self.vendor_path.exists():
            self.app.display_info(f"Cleaning vendored files from {self.vendor_path} using git")
            self._git_clean_vendor_dir()

    def _determine_vendor_path(self) -> None:
        """Determine the vendor directory path from vendoring configuration."""
        try:
            # Use tomli for Python < 3.11, otherwise use tomllib
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib

            with Path(self.root, "pyproject.toml").open("rb") as f:
                pyproject = tomllib.load(f)

            self.vendor_dir = pyproject.get("tool", {}).get("vendoring", {}).get("destination")

            if self.vendor_dir:
                self.vendor_path = Path(self.root) / self.vendor_dir
                self.app.display_info(f"Determined vendor directory: {self.vendor_path}")
            else:
                self.app.display_warning("Could not determine vendor directory from vendoring config")
                self.app.display_warning("Vendored files will not be cleaned up after build")
        except Exception as e:
            self.app.display_error(f"Error determining vendor directory: {e}")
            self.app.display_warning("Vendored files will not be cleaned up after build")

    def _check_for_uncommitted_changes(self) -> None:
        """Check for uncommitted changes in vendor directory."""
        if not self._is_git_repo():
            self.app.display_warning("Not a git repository. Cannot check for uncommitted changes.")
            return

        untracked_files, modified_files = self._get_uncommitted_changes()

        if untracked_files or modified_files:
            message = f"Uncommitted changes detected in vendor directory: {self.vendor_dir}"

            if untracked_files:
                untracked_msg = "Untracked files:\n  - " + "\n  - ".join(untracked_files)
                self.app.display_warning(untracked_msg)

            if modified_files:
                modified_msg = "Modified files:\n  - " + "\n  - ".join(modified_files)
                self.app.display_warning(modified_msg)

            self.app.display_warning(message)

            if self.abort_on_changed_files:
                raise RuntimeError(
                    f"Uncommitted changes in vendor directory: {self.vendor_dir}. "
                    "Commit or stash these changes before building, or set "
                    "abort-on-changed-files = false in plugin config to ignore."
                )

    def _run_vendoring(self) -> None:
        """Run the vendoring tool to vendor dependencies."""

        if not shutil.which("pip"):
            # No pip, lets see if we have `uvx` instead

            if not shutil.which("uvx"):
                raise RuntimeError("One of `pip` and `uvx` must exist in PATH")
            import vendoring.utils

            orig_run = vendoring.utils.run

            @wraps(orig_run)
            def run(command: list[str], **kwargs):
                if command[0] == "pip":
                    command[0:1] = ["uvx", "pip"]
                return orig_run(command, **kwargs)

            vendoring.utils.run = run

        # This must happen after we have monkey patched the fns, else it won't get the right imports
        import vendoring.cli

        old = Path.cwd()
        os.chdir(self.root)
        try:
            ctx = vendoring.cli.main.make_context("vendoring", args=["sync"])
            # Let this throw an exception
            ctx.forward(vendoring.cli.sync, verbose=True)
            return
        finally:
            os.chdir(old)

    def _git_clean_vendor_dir(self) -> None:
        """Clean up vendor directory using git commands."""
        if not self._is_git_repo():
            self.app.display_warning("Not a git repository. Cannot clean using git.")
            self.app.display_warning(f"Vendored files in {self.vendor_path} will remain after build.")
            return

        try:
            # Remove untracked files in vendor directory
            git_clean_cmd = ["git", "clean", "-fdx", "--", str(self.vendor_dir)]
            self.app.display_info(f"Running: {' '.join(git_clean_cmd)}")
            subprocess.run(git_clean_cmd, cwd=self.root, check=True, capture_output=True)

            # Reset any tracked files to their original state
            git_checkout_cmd = ["git", "checkout", "--", str(self.vendor_dir)]
            self.app.display_info(f"Running: {' '.join(git_checkout_cmd)}")
            subprocess.run(git_checkout_cmd, cwd=self.root, check=True, capture_output=True)

            self.app.display_info("Successfully cleaned vendor directory using git")
        except subprocess.CalledProcessError as e:
            self.app.display_error(f"Git clean failed: {e}")
            if e.stdout:
                self.app.display_error(f"Stdout: {e.stdout.decode('utf-8')}")
            if e.stderr:
                self.app.display_error(f"Stderr: {e.stderr.decode('utf-8')}")
            self.app.display_warning(f"Vendored files in {self.vendor_path} may remain after build.")

    def _is_git_repo(self) -> bool:
        """Check if the project is a git repository."""
        try:
            subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.root,
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _get_uncommitted_changes(self) -> tuple[list[str], list[str]]:
        """Get lists of untracked and modified files in vendor directory."""
        untracked_files = []
        modified_files = []

        if not self.vendor_dir:
            return untracked_files, modified_files

        try:
            # Get untracked files in vendor directory
            cmd = ["git", "ls-files", "--others", "--exclude-standard", self.vendor_dir]
            result = subprocess.run(cmd, cwd=self.root, check=True, capture_output=True, text=True)
            if result.stdout:
                untracked_files = [line.strip() for line in result.stdout.splitlines()]

            # Get modified files in vendor directory
            cmd = ["git", "diff", "--name-only", "--", self.vendor_dir]
            result = subprocess.run(cmd, cwd=self.root, check=True, capture_output=True, text=True)
            if result.stdout:
                modified_files = [line.strip() for line in result.stdout.splitlines()]

            # Get staged files in vendor directory
            cmd = ["git", "diff", "--name-only", "--cached", "--", self.vendor_dir]
            result = subprocess.run(cmd, cwd=self.root, check=True, capture_output=True, text=True)
            if result.stdout:
                modified_files.extend([line.strip() for line in result.stdout.splitlines()])

        except subprocess.SubprocessError:
            self.app.display_warning("Could not check for uncommitted changes in vendor directory")

        return untracked_files, modified_files
