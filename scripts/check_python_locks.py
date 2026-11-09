"""Validate direct requirements, hash coverage and runtime/dev pin consistency offline."""
import re
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def locked(path):
    result = {}
    content = path.read_text()
    if re.search(r"(?:https?://|git\+|--index-url|--extra-index-url|--trusted-host)", content):
        raise ValueError(f"{path.name}: index URLs/direct references must not be embedded in locks")
    for line in content.replace("\\\n", " ").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line.split(" --hash=", 1)[0].strip())
        pins = list(requirement.specifier)
        if requirement.url or len(pins) != 1 or pins[0].operator != "==" or "*" in pins[0].version:
            raise ValueError(f"{path.name}: each dependency must have an exact version")
        if not re.search(r"--hash=sha256:[a-f0-9]{64}(?:\s|$)", line):
            raise ValueError(f"{path.name}: every dependency needs a SHA-256 hash")
        name = canonicalize_name(requirement.name)
        if name in result:
            raise ValueError(f"{path.name}: duplicate dependency pin")
        result[name] = pins[0].version
    if not result:
        raise ValueError(f"{path.name}: empty dependency lock")
    return result


def check_inputs(path, pins, seen=None):
    seen = set() if seen is None else seen
    if path in seen:
        raise ValueError("Cyclic requirement inputs")
    seen = seen | {path}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-c "):
            continue  # Shared runtime constraints are checked against the complete dev lock below.
        if line.startswith("-r "):
            check_inputs(path.parent / line[3:].strip(), pins, seen)
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        if requirement.url:
            raise ValueError("Direct references are not supported in audited input files")
        version = pins.get(canonicalize_name(requirement.name))
        if version is None or not requirement.specifier.contains(version):
            raise ValueError(f"{path.name}: lock does not satisfy a direct requirement")


def main():
    runtime = locked(ROOT / "backend/requirements.txt")
    dev = locked(ROOT / "backend/requirements-dev.txt")
    tools = locked(ROOT / "ci/security-requirements.txt")
    for relative, pins in (("backend/requirements.in", runtime), ("backend/requirements-dev.in", dev), ("ci/security-requirements.in", tools)):
        check_inputs(ROOT / relative, pins)
    if any(dev.get(name) != version for name, version in runtime.items()):
        raise ValueError("Runtime and test dependency pins differ; regenerate both locks")
    print(f"Validated hashed locks: {len(runtime)} runtime, {len(dev)} test, {len(tools)} security-tool dependencies.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(f"Dependency lock check failed: {error}", file=sys.stderr)
        sys.exit(1)
