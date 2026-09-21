from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from urllib.parse import quote


OUTPUT_DIR = Path("/out")
EXCLUDED_PACKAGES = {"lan-party-game-finder-backend", "pip"}
LICENSE_PREFIXES = ("license", "copying", "notice", "authors")


def license_name(distribution: importlib.metadata.Distribution) -> str:
    metadata = distribution.metadata
    expression = metadata.get("License-Expression")
    if expression:
        return expression.strip()

    declared = (metadata.get("License") or "").strip()
    if declared and declared.upper() != "UNKNOWN":
        return " ".join(declared.split())

    classifiers = metadata.get_all("Classifier") or []
    licenses = [
        classifier.removeprefix("License :: ").strip()
        for classifier in classifiers
        if classifier.startswith("License :: ")
    ]
    return " OR ".join(licenses) or "UNKNOWN"


def package_url(distribution: importlib.metadata.Distribution) -> str:
    urls = distribution.metadata.get_all("Project-URL") or []
    for preferred_label in ("Source", "Repository", "Homepage"):
        for value in urls:
            label, separator, url = value.partition(",")
            if separator and label.strip().lower() == preferred_label.lower():
                return url.strip()
    return (distribution.metadata.get("Home-page") or "").strip()


def license_documents(distribution: importlib.metadata.Distribution) -> list[Path]:
    documents: list[Path] = []
    for relative_path in distribution.files or []:
        if not relative_path.name.lower().startswith(LICENSE_PREFIXES):
            continue
        path = Path(distribution.locate_file(relative_path))
        if path.is_file():
            documents.append(path)
    return sorted(set(documents), key=lambda path: str(path).casefold())


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    distributions = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "").strip()
        if not name or name.casefold() in EXCLUDED_PACKAGES:
            continue
        distributions.append(distribution)
    distributions.sort(key=lambda distribution: distribution.metadata["Name"].casefold())

    inventory = ["package\tversion\tlicense\tsource"]
    notices = [
        "Backend dependency license documents",
        "====================================",
        "",
        "Generated from the exact Python environment used to build the backend.",
        "",
    ]
    components = []

    for distribution in distributions:
        name = distribution.metadata["Name"]
        license_value = license_name(distribution)
        inventory.append(
            "\t".join(
                (
                    name,
                    distribution.version,
                    license_value.replace("\t", " "),
                    package_url(distribution).replace("\t", " ") or "-",
                )
            )
        )
        components.append(
            {
                "type": "library",
                "name": name,
                "version": distribution.version,
                "purl": f"pkg:pypi/{quote(name.casefold(), safe='-._')}@{quote(distribution.version, safe='-._+')}",
                "licenses": [{"license": {"name": license_value}}],
            }
        )
        for document in license_documents(distribution):
            notices.extend(
                (
                    "",
                    "-" * 78,
                    f"{name} {distribution.version}: {document.name}",
                    "-" * 78,
                    document.read_text(encoding="utf-8", errors="replace").rstrip(),
                )
            )

    (OUTPUT_DIR / "backend-dependencies.tsv").write_text(
        "\n".join(inventory) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "backend-dependency-licenses.txt").write_text(
        "\n".join(notices) + "\n", encoding="utf-8"
    )
    (OUTPUT_DIR / "backend.cdx.json").write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.5",
                "version": 1,
                "metadata": {
                    "component": {
                        "type": "application",
                        "name": "lan-party-game-finder-backend",
                        "version": "0.1.0",
                    }
                },
                "components": components,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
