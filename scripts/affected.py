#!/usr/bin/env python3
"""Determine which workspace packages are affected by a change.

Compares the current branch against a base ref (default: origin/main),
maps changed files to workspace packages, and expands to include transitive
dependents. Outputs structured JSON with tool-specific paths.

Usage:
    python scripts/affected.py                     # diff vs origin/main
    python scripts/affected.py --base HEAD~1       # diff vs previous commit
    python scripts/affected.py --all               # force all packages

Output:
    {
      "all": false,
      "packages": ["shared"],
      "lint_paths": ["libs/shared"],
      "src_paths": ["libs/shared/src"],
      "test_paths": ["libs/shared"]
    }
"""

import argparse
import json
import pathlib
import subprocess
import sys
import tomllib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Files that, when changed, affect ALL packages.
INFRA_PATTERNS = (
    "pyproject.toml",
    ".python-version",
    "uv.lock",
    "scripts/",
    ".github/",
    "Makefile",
    ".pre-commit-config.yaml",
)


def load_toml(path: pathlib.Path) -> dict:
    return tomllib.loads(path.read_text())


def parse_dep_name(dep: str) -> str:
    return dep.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("!")[0].split(";")[0].strip()


def discover_members() -> dict[str, pathlib.Path]:
    """Return {package_name: pyproject.toml path} for all workspace members."""
    members: dict[str, pathlib.Path] = {}
    for toml_path in sorted(ROOT.rglob("*/pyproject.toml")):
        if toml_path.parent == ROOT:
            continue
        data = load_toml(toml_path)
        name = data.get("project", {}).get("name")
        if name:
            members[name] = toml_path
    return members


def build_reverse_deps(
    members: dict[str, pathlib.Path],
) -> dict[str, list[str]]:
    """Build a reverse dependency map: package -> packages that depend on it."""
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
        print(
            f"Warning: git diff failed: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return []
    return [f for f in result.stdout.strip().split("\n") if f]


def is_infra_file(filepath: str) -> bool:
    """Check if a file is an infrastructure file that affects all packages."""
    # Root-level pyproject.toml (not member ones)
    if filepath == "pyproject.toml":
        return True
    return any(
        filepath == pattern or filepath.startswith(pattern) for pattern in INFRA_PATTERNS if pattern != "pyproject.toml"
    )


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


def build_output(
    members: dict[str, pathlib.Path],
    affected: set[str],
    run_all: bool,
) -> dict:
    """Build structured output with tool-specific paths."""
    packages = sorted(affected)
    lint_paths = []
    src_paths = []
    test_paths = []

    for name in packages:
        pkg_dir = members[name].parent.relative_to(ROOT)
        lint_paths.append(str(pkg_dir))
        test_paths.append(str(pkg_dir))
        src_dir = pkg_dir / "src"
        if src_dir.exists():
            src_paths.append(str(src_dir))
        else:
            src_paths.append(str(pkg_dir))

    return {
        "all": run_all,
        "packages": packages,
        "lint_paths": lint_paths,
        "src_paths": src_paths,
        "test_paths": test_paths,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect affected workspace packages")
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base ref to diff against (default: origin/main)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="force_all",
        help="Force all packages to be affected",
    )
    args = parser.parse_args()

    members = discover_members()

    if args.force_all:
        output = build_output(members, set(members.keys()), run_all=True)
        print(json.dumps(output, indent=2))
        return

    changed_files = get_changed_files(args.base)

    # Check for infra changes
    infra_changed = any(is_infra_file(f) for f in changed_files)

    if infra_changed:
        output = build_output(members, set(members.keys()), run_all=True)
    else:
        directly_changed: set[str] = set()
        for f in changed_files:
            pkg = file_to_package(f, members)
            if pkg:
                directly_changed.add(pkg)

        reverse_deps = build_reverse_deps(members)
        affected = expand_dependents(directly_changed, reverse_deps)
        output = build_output(members, affected, run_all=False)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
