"""Reject images whose installed dependencies do not match the project manifest."""

from importlib import metadata
from pathlib import Path
import tomllib

from packaging.requirements import Requirement


def dependency_errors(project: dict) -> list[str]:
    requirements = [
        *project.get("dependencies", []),
        *project.get("optional-dependencies", {}).get("dev", []),
    ]
    errors = []
    for declaration in requirements:
        requirement = Requirement(declaration)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            installed = metadata.version(requirement.name)
        except metadata.PackageNotFoundError:
            errors.append(f"{requirement}: not installed")
            continue
        if not requirement.specifier.contains(installed, prereleases=True):
            errors.append(f"{requirement}: installed {installed}")
    return errors


def main() -> None:
    project_path = Path(__file__).with_name("pyproject.toml")
    with project_path.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    errors = dependency_errors(project)
    if errors:
        raise SystemExit(
            "Installed dependencies do not match pyproject.toml:\n"
            + "\n".join(f"- {error}" for error in errors)
            + "\nRegenerate backend/requirements.lock before building the image."
        )
    print("Installed runtime and test dependencies match pyproject.toml.")


if __name__ == "__main__":
    main()
