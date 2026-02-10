#!/usr/bin/env python3
"""Detect which workspace packages changed relative to a base branch.

Used by selective CI to only test affected packages (and their dependents).

Usage:
    python scripts/detect_changes.py --base origin/main
    python scripts/detect_changes.py --base HEAD~1

Outputs a JSON object:
    {"changed": ["shared", "myapp"], "test_paths": ["libs/shared", "apps/myapp"]}
"""

import argparse
import json
import pathlib
import subprocess
import sys
import tomllib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_toml(path: pathlib.Path) -> dict:
    return tomllib.loads(path.read_text())


def parse_dep_name(dep: str) -> str:
    return dep.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("!")[0].split(";")[0].strip()


def discover_members() -> dict[str, pathlib.Path]:
    members: dict[str, pathlib.Path] = {}
    for toml_path in sorted(ROOT.rglob("*/pyproject.toml")):
        if toml_path.parent == ROOT:
            continue
        data = load_toml(toml_path)
        name = data.get("project", {}).get("name")
        if name:
            members[name] = toml_path
    return members


def build_reverse_deps(members: dict[str, pathlib.Path]) -> dict[str, list[str]]:
    """Build a reverse dependency map: package -> list of packages that depend on it."""
    workspace_names = set(members.keys())
    reverse: dict[str, list[str]] = defaultdict(list)
    for name, path in members.items():
        data = load_toml(path)
        for dep in data.get("project", {}).get("dependencies", []):
            base = parse_dep_name(dep)
            if base in workspace_names:
                reverse[base].append(name)
    return reverse


def get_changed_files(base: str) -> list[str]:
    """Get files changed relative to base ref."""
    result = subprocess.run(
        ["git", "diff", "--name-only", base],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        print(f"Warning: git diff failed: {result.stderr.strip()}", file=sys.stderr)
        return []
    return [f for f in result.stdout.strip().split("\n") if f]


def file_to_package(filepath: str, members: dict[str, pathlib.Path]) -> str | None:
    """Map a changed file to its owning workspace package."""
    for name, toml_path in members.items():
        pkg_dir = str(toml_path.parent.relative_to(ROOT))
        if filepath.startswith(pkg_dir + "/") or filepath == pkg_dir:
            return name
    return None


def expand_dependents(changed: set[str], reverse_deps: dict[str, list[str]]) -> set[str]:
    """Expand changed set to include all transitive dependents."""
    result = set(changed)
    queue = list(changed)
    while queue:
        pkg = queue.pop()
        for dependent in reverse_deps.get(pkg, []):
            if dependent not in result:
                result.add(dependent)
                queue.append(dependent)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect changed workspace packages")
    parser.add_argument("--base", default="origin/main", help="Base ref to diff against")
    args = parser.parse_args()

    members = discover_members()
    changed_files = get_changed_files(args.base)

    # Check if root config changed (triggers full test)
    root_changed = any(
        f in ("pyproject.toml", ".python-version", "uv.lock") or f.startswith("scripts/") for f in changed_files
    )

    if root_changed:
        # Root config change: test everything
        affected = set(members.keys())
    else:
        # Map changed files to packages
        directly_changed = set()
        for f in changed_files:
            pkg = file_to_package(f, members)
            if pkg:
                directly_changed.add(pkg)

        # Expand to dependents
        reverse_deps = build_reverse_deps(members)
        affected = expand_dependents(directly_changed, reverse_deps)

    # Build test paths
    test_paths = []
    for name in sorted(affected):
        pkg_dir = str(members[name].parent.relative_to(ROOT))
        test_paths.append(pkg_dir)

    output = {"changed": sorted(affected), "test_paths": test_paths}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
