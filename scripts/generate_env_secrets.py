from __future__ import annotations

import argparse
import secrets
import string
from pathlib import Path


SECRET_KEYS = {
    "BASIC_AUTH_PASSWORD": 32,
    "ADMIN_PASSWORD": 32,
    "POSTGRES_PASSWORD": 32,
}
ALPHABET = string.ascii_letters + string.digits


def generate_secret(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def replace_values(content: str, keys: set[str]) -> str:
    lines = content.splitlines()
    found: set[str] = set()
    result: list[str] = []
    for line in lines:
        key, separator, _ = line.partition("=")
        if separator and key in keys:
            result.append(f"{key}={generate_secret(SECRET_KEYS[key])}")
            found.add(key)
        else:
            result.append(line)
    for key in sorted(keys - found):
        result.append(f"{key}={generate_secret(SECRET_KEYS[key])}")
    return "\n".join(result).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or rotate local environment secrets.")
    parser.add_argument("--output", type=Path, default=Path(".env"))
    parser.add_argument("--template", type=Path, default=Path(".env.example"))
    parser.add_argument(
        "--rotate",
        action="append",
        choices=sorted(SECRET_KEYS),
        default=[],
        help="Rotate this key in an existing file. May be specified more than once.",
    )
    args = parser.parse_args()

    if args.output.exists():
        keys = set(args.rotate)
        if not keys:
            raise SystemExit(
                f"{args.output} already exists; use --rotate KEY to change selected secrets."
            )
        content = args.output.read_text(encoding="utf-8-sig")
    else:
        if not args.template.is_file():
            raise SystemExit(f"Template not found: {args.template}")
        content = args.template.read_text(encoding="utf-8-sig")
        template_keys = {
            line.partition("=")[0]
            for line in content.splitlines()
            if line.partition("=")[1]
        }
        keys = set(SECRET_KEYS).intersection(template_keys)
        if not keys:
            raise SystemExit(f"Template contains no supported secret keys: {args.template}")

    temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
    temporary.write_text(replace_values(content, keys), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(args.output)
    args.output.chmod(0o600)
    print(f"Updated {args.output}: {', '.join(sorted(keys))}")


if __name__ == "__main__":
    main()
