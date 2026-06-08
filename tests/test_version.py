"""The package exposes its version via ``crudadmin.__version__``."""

from importlib.metadata import version

import crudadmin


def test_version_attribute_matches_installed_metadata():
    assert crudadmin.__version__ == version("crudadmin")


def test_version_is_nonempty_string():
    assert isinstance(crudadmin.__version__, str)
    assert crudadmin.__version__


def test_version_exported_in_all():
    assert "__version__" in crudadmin.__all__
