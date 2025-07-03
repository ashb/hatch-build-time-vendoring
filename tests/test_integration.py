"""
Integration tests for hatch-build-time-vendoring plugin using actual Hatch builds.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from .utils import build_project


def get_plugin_path():
    """Get the path to the plugin directory."""
    # Get the current file's directory and go up one level
    return str(Path(__file__).parent.parent.absolute())


def test_build_with_vendoring(project_dir):
    """
    Test building a package with the vendoring plugin.

    This test:
    1. Sets up a test package that uses hatch-build-time-vendoring
    2. Runs hatch build
    3. Checks that vendored files are in the wheel but not in source
    """
    build_project()

    # Check that dist directory was created and contains files
    dist_dir = project_dir / "dist"
    assert dist_dir.exists(), "dist directory not created"

    wheel_files = list(dist_dir.glob("*.whl"))
    sdist_files = list(dist_dir.glob("*.tar.gz"))

    assert wheel_files, "No wheel file was created"
    assert sdist_files, "No sdist file was created"

    # Verify the vendor directory exists in the wheel
    import zipfile

    with zipfile.ZipFile(wheel_files[0]) as wheel:
        wheel_files_list = wheel.namelist()
        # Look for vendored files (any file in the _vendor directory)
        vendor_files = [f for f in wheel_files_list if "/_vendor/" in f]
        assert vendor_files, "No vendored files found in wheel"

        # Check specifically for urllib3
        urllib3_files = [f for f in wheel_files_list if "urllib3" in f]
        assert urllib3_files, "urllib3 not found in wheel"

    # Verify the vendor directory was cleaned up from source
    vendor_dir = project_dir / "src" / "my_app" / "_vendor"
    assert not vendor_dir.exists(), "Vendor directory not cleaned up"

    # Verify git status is clean
    git_status = subprocess.run(
        ["git", "status", "--porcelain", "src"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    assert not git_status.stdout.strip(), "Git working directory not clean after build"


@pytest.mark.skipif(shutil.which("git") is None, reason="Git not available")
def test_build_with_uncommitted_changes(project_dir):
    """
    Test that build fails when there are uncommitted changes in vendor directory.
    """
    # Create vendor directory with a file to simulate previous vendoring
    vendor_dir = project_dir / "src" / "my_app" / "_vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)

    (vendor_dir / "test_file.py").write_text("# Test file\n")

    # Build should fail due to uncommitted changes
    with pytest.raises(Exception, match="Uncommitted changes"):
        build_project()


@pytest.mark.skipif(shutil.which("git") is None, reason="Git not available")
def test_build_with_allow_uncommitted_changes(project_dir):
    """
    Test that build succeeds with uncommitted changes when abort-on-changed-files is false.
    """
    # Update pyproject.toml to allow uncommitted changes
    pyproject_path = project_dir / "pyproject.toml"
    content = pyproject_path.read_text()

    # Add abort-on-changed-files = false
    content = content.replace(
        "[tool.hatch.build.hooks.vendoring]",
        "[tool.hatch.build.hooks.vendoring]\nabort-on-changed-files = false",
    )

    pyproject_path.write_text(content)

    # Commit the updated pyproject.toml
    subprocess.run(["git", "add", "pyproject.toml"], check=True, capture_output=True, cwd=project_dir)
    subprocess.run(
        ["git", "commit", "-m", "Allow uncommitted changes"],
        check=True,
        capture_output=True,
        cwd=project_dir,
    )

    # Create vendor directory with a file to simulate previous vendoring
    vendor_dir = project_dir / "src" / "my_app" / "_vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)

    (vendor_dir / "test_file.py").write_text("# Test file\n")

    # Run hatch build - should succeed despite uncommitted changes
    build_project()

    # Check that dist directory was created and contains files
    dist_dir = project_dir / "dist"
    assert dist_dir.exists(), "dist directory not created"

    # Verify the vendor directory was cleaned up from source
    assert not vendor_dir.exists(), "Vendor directory not cleaned up"
