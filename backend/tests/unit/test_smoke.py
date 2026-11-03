"""T001 smoke test: the package is installed and importable."""


def test_package_imports() -> None:
    import hiretitan

    assert hiretitan.__version__
