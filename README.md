# hatch-build-time-vendoring

A Hatch build hook plugin that runs the `vendoring` tool to vendor dependencies
into your built packages (sdist and wheel) without keeping the vendored files
in your source tree. The plugin uses git commands to clean up the vendored
files after building.

## Usage

This plugin assumes you have already worked out how to run [vendoring] and want to run it automatically.

For example, in a `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling", "hatch-build-time-vendoring @ file:///Users/ash/code/python/hatch-build-time-vendoring-plugin"]
build-backend = "hatchling.build"

[tool.vendoring]
destination = "src/airflow/sdk/_vendor/"
requirements = "src/airflow/sdk/_vendor/vendor.txt"
namespace = "airflow.sdk._vendor"

protected-files = ["__init__.py", "README.rst", "vendor.txt", ".gitignore"]
```

[vendoring]: https://github.com/pradyunsg/vendoring
