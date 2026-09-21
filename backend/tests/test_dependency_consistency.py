from importlib import metadata

import check_dependencies


def test_rejects_stale_runtime_and_test_dependencies(monkeypatch):
    installed = {"fastapi": "0.138.2", "pytest": "9.1.0"}
    monkeypatch.setattr(check_dependencies.metadata, "version", installed.__getitem__)
    project = {
        "dependencies": ["fastapi==0.141.1"],
        "optional-dependencies": {"dev": ["pytest==9.1.1"]},
    }
    assert check_dependencies.dependency_errors(project) == [
        "fastapi==0.141.1: installed 0.138.2",
        "pytest==9.1.1: installed 9.1.0",
    ]


def test_reports_missing_dependency(monkeypatch):
    def missing(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(check_dependencies.metadata, "version", missing)
    assert check_dependencies.dependency_errors({"dependencies": ["httpx==0.28.1"]}) == [
        "httpx==0.28.1: not installed"
    ]


def test_accepts_matching_versions_and_skips_inapplicable_markers(monkeypatch):
    installed = {"psycopg": "3.3.6", "pytest": "9.1.1"}
    monkeypatch.setattr(check_dependencies.metadata, "version", installed.__getitem__)
    project = {
        "dependencies": ["psycopg[binary]==3.3.6", "missing; python_version < '3.0'"],
        "optional-dependencies": {"dev": ["pytest==9.1.1"]},
    }
    assert check_dependencies.dependency_errors(project) == []
