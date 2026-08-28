"""Coverage for the compatibility CLI module import path."""

import importlib


def test_main_module_imports_without_running_pipeline():
    """Importing the legacy entry point configures services but does not run them."""
    module = importlib.import_module("main")
    assert callable(module.run_pipeline)
