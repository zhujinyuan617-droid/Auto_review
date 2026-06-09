def test_engine_bridge_exposes_build_clean_package():
    from autoreview_app import engine_bridge

    # engine_bridge must have put Document_Decomposer/src on sys.path and
    # imported the engine's deterministic package builder.
    assert callable(engine_bridge.build_clean_package)
    assert callable(engine_bridge.build_package_from_pdf)
