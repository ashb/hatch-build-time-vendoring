"""Register hooks for the plugin."""

from hatchling.plugin import hookimpl


@hookimpl
def hatch_register_build_hook():
    """Get the hook implementation."""
    from hatch_build_time_vendoring.plugin import VendoringBuildHook

    return VendoringBuildHook
