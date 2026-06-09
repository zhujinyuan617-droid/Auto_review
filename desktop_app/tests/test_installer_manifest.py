from autoreview_app.packaging.installer_manifest import bundled_dependencies, consent_summary


def test_bundled_dependencies_are_lightweight():
    deps = bundled_dependencies()
    names = {d["name"] for d in deps}
    assert {"fastapi", "uvicorn", "pywebview", "pymupdf", "keyring"} <= names
    assert "docling" not in names
    assert all(d.get("purpose") for d in deps)


def test_consent_summary_lists_deps_and_requires_consent():
    summary = consent_summary()
    assert summary["consent_required"] is True
    assert len(summary["will_install"]) == len(bundled_dependencies())
    assert "docling" in summary["optional_later"].lower()
    assert summary["note"]
