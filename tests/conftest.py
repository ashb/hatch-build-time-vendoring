import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner as __CliRunner


class CliRunner(__CliRunner):
    def __init__(self, command):
        super().__init__()
        self._command = command

    def __call__(self, *args, **kwargs):
        # Exceptions should always be handled
        kwargs.setdefault("catch_exceptions", False)

        return self.invoke(self._command, args, **kwargs)


@pytest.fixture(scope="session")
def plugin_dir(tmp_path_factory, request):
    directory = tmp_path_factory.mktemp("plugin")
    shutil.copytree(request.config.rootpath, directory, dirs_exist_ok=True)

    return directory.resolve()


@pytest.fixture
def project_dir(tmp_path_factory, plugin_dir, monkeypatch):
    """Create a temporary project directory for testing."""

    tmpdir = tmp_path_factory.mktemp("my-app")
    monkeypatch.chdir(tmpdir)

    # Create project structure
    create_project_structure(tmpdir, plugin_dir)

    # Initialize git repository
    subprocess.run(["git", "init"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], check=True, capture_output=True)

    yield tmpdir


def create_project_structure(project_dir, plugin_dir):
    """Create a basic project structure for testing."""
    # Create directories
    src_dir = Path(project_dir) / "src" / "my_app"
    src_dir.mkdir(parents=True)

    # Create pyproject.toml
    pyproject_content = f"""
[build-system]
requires = ["hatchling", "hatch-build-time-vendoring @ {plugin_dir.as_uri()}"]
build-backend = "hatchling.build"

[project]
name = "my-app"
description = "Test package for hatch-build-time-vendoring"
requires-python = ">={sys.version_info[0]}"
dependencies = []
dynamic = ["version"]

[tool.hatch.version]
path = "src/my_app/__init__.py"

[tool.hatch.build.hooks.vendoring]
vendoring-args = ["--verbose"]

[tool.vendoring]
destination = "src/my_app/_vendor"
requirements = "vendor-requirements.txt"
namespace = "my_app._vendor"

[tool.vendoring.transformations]
substitute = [
    {{match = "import urllib3", replace = "from my_app._vendor import urllib3"}},
]
"""
    project_dir.joinpath("pyproject.toml").write_text(pyproject_content)
    project_dir.joinpath("vendor-requirements.txt").write_text("urllib3==2.0.4\n")
    src_dir.joinpath("__init__.py").write_text("""
from . import demo
__version__ = "1.2.3"
""")
    src_dir.joinpath("demo.py").write_text("""
# This will be imported from vendored code after building
from testpkg._vendor import urllib3

def get_version():
    return urllib3.__version__
""")
