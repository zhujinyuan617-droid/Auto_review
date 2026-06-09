def test_package_imports_and_has_version():
    import autoreview_app

    assert autoreview_app.__version__ == "0.1.0"
