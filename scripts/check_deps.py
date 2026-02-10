#!/usr/bin/env python3
"""Monorepo workspace lint: enforce structural conventions.

Checks:
  1. No external dependencies in members (must be in root)
  2. No member-level .python-version files
  3. requires-python must match root
  4. No circular workspace dependencies
  5. Consistent build-backend (uv_build)
  6. Apps can only depend on libs (not other apps)
  7. Libs cannot depend on apps
  8. No [tool.uv.sources] in root pyproject.toml
  9. No [tool.ruff] or [tool.pytest] overrides in members
 10. No optional-dependencies in members
 11. Package naming convention enforcement
"""

import pathlib
import sys
import tomllib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
REQUIRED_BUILD_BACKEND = "uv_build"


def load_toml(path: pathlib.Path) -> dict:
    return tomllib.loads(path.read_text())


def get_root_config() -> dict:
    return load_toml(ROOT / "pyproject.toml")


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


def classify_member(toml_path: pathlib.Path) -> str | None:
    """Return 'app' or 'lib' based on directory location."""
    rel = toml_path.relative_to(ROOT)
    parts = rel.parts
    if parts[0] == "apps":
        return "app"
    elif parts[0] == "libs":
        return "lib"
    return None


def parse_dep_name(dep: str) -> str:
    """Extract the base package name from a dependency specifier."""
    return dep.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("!")[0].split(";")[0].strip()


def check_no_external_deps(members: dict[str, pathlib.Path], workspace_names: set[str]) -> list[str]:
    """Check 1: members may only depend on other workspace members."""
    errors = []
    for name, path in members.items():
        data = load_toml(path)
        for dep in data.get("project", {}).get("dependencies", []):
            base = parse_dep_name(dep)
            if base not in workspace_names:
                rel = path.relative_to(ROOT)
                errors.append(f"{name}: external dependency '{dep}' must be in root pyproject.toml, not {rel}")
    return errors


def check_no_member_python_version(members: dict[str, pathlib.Path]) -> list[str]:
    """Check 2: no member-level .python-version files."""
    errors = []
    for name, path in members.items():
        pyver = path.parent / ".python-version"
        if pyver.exists():
            errors.append(f"{name}: remove {pyver.relative_to(ROOT)} — use the root .python-version only")
    return errors


def check_requires_python(members: dict[str, pathlib.Path], root_requires: str) -> list[str]:
    """Check 3: requires-python must match root."""
    errors = []
    for name, path in members.items():
        data = load_toml(path)
        member_req = data.get("project", {}).get("requires-python", "")
        if member_req and member_req != root_requires:
            errors.append(f"{name}: requires-python '{member_req}' doesn't match root '{root_requires}'")
    return errors


def check_no_cycles(members: dict[str, pathlib.Path], workspace_names: set[str]) -> list[str]:
    """Check 4: no circular dependencies between workspace members."""
    # Build adjacency list
    graph: dict[str, list[str]] = defaultdict(list)
    for name, path in members.items():
        data = load_toml(path)
        for dep in data.get("project", {}).get("dependencies", []):
            base = parse_dep_name(dep)
            if base in workspace_names:
                graph[name].append(base)

    # DFS cycle detection
    visited: set[str] = set()
    in_stack: set[str] = set()
    cycles: list[str] = []

    def dfs(node: str, path: list[str]) -> None:
        if node in in_stack:
            cycle_start = path.index(node)
            cycle = " → ".join([*path[cycle_start:], node])
            cycles.append(f"circular dependency: {cycle}")
            return
        if node in visited:
            return
        visited.add(node)
        in_stack.add(node)
        path.append(node)
        for neighbor in graph.get(node, []):
            dfs(neighbor, path)
        path.pop()
        in_stack.remove(node)

    for name in members:
        if name not in visited:
            dfs(name, [])

    return cycles


def check_build_backend(members: dict[str, pathlib.Path]) -> list[str]:
    """Check 5: all members must use the same build-backend."""
    errors = []
    for name, path in members.items():
        data = load_toml(path)
        backend = data.get("build-system", {}).get("build-backend", "")
        if backend != REQUIRED_BUILD_BACKEND:
            errors.append(f"{name}: build-backend is '{backend}', expected '{REQUIRED_BUILD_BACKEND}'")
    return errors


def check_dependency_direction(members: dict[str, pathlib.Path], workspace_names: set[str]) -> list[str]:
    """Check 6 & 7: apps can only depend on libs; libs cannot depend on apps."""
    errors = []
    app_names = set()
    lib_names = set()

    for name, path in members.items():
        kind = classify_member(path)
        if kind == "app":
            app_names.add(name)
        elif kind == "lib":
            lib_names.add(name)

    for name, path in members.items():
        kind = classify_member(path)
        data = load_toml(path)
        for dep in data.get("project", {}).get("dependencies", []):
            base = parse_dep_name(dep)
            if base not in workspace_names:
                continue
            if kind == "app" and base in app_names:
                errors.append(
                    f"{name} (app): cannot depend on '{base}' (another app) — apps should only depend on libs"
                )
            if kind == "lib" and base in app_names:
                errors.append(f"{name} (lib): cannot depend on '{base}' (an app) — libs must not depend on apps")
    return errors


def check_no_root_sources() -> list[str]:
    """Check 8: root pyproject.toml should not have [tool.uv.sources]."""
    data = get_root_config()
    if data.get("tool", {}).get("uv", {}).get("sources"):
        return [
            "root pyproject.toml should not have [tool.uv.sources] — workspace source resolution belongs in members"
        ]
    return []


def check_no_member_tool_overrides(members: dict[str, pathlib.Path]) -> list[str]:
    """Check 9: members should not override [tool.ruff] or [tool.pytest]."""
    errors = []
    for name, path in members.items():
        data = load_toml(path)
        tool = data.get("tool", {})
        if "ruff" in tool:
            errors.append(f"{name}: remove [tool.ruff] — ruff config must be in root pyproject.toml only")
        if "pytest" in tool:
            errors.append(f"{name}: remove [tool.pytest] — pytest config must be in root pyproject.toml only")
    return errors


def check_no_member_optional_deps(members: dict[str, pathlib.Path]) -> list[str]:
    """Check 10: members should not have [project.optional-dependencies]."""
    errors = []
    for name, path in members.items():
        data = load_toml(path)
        if data.get("project", {}).get("optional-dependencies"):
            errors.append(
                f"{name}: remove [project.optional-dependencies] — extras must be centralized in root pyproject.toml"
            )
    return errors


def check_naming_convention(members: dict[str, pathlib.Path]) -> list[str]:
    """Check 11: package names must match their directory name."""
    errors = []
    for name, path in members.items():
        expected_dir_name = path.parent.name
        if name != expected_dir_name:
            errors.append(f"{name}: package name doesn't match directory name '{expected_dir_name}'")
    return errors


def main() -> None:
    root_data = get_root_config()
    root_requires = root_data.get("project", {}).get("requires-python", "")
    members = discover_members()
    workspace_names = set(members.keys())

    all_errors: list[str] = []

    checks = [
        ("External Dependencies", check_no_external_deps(members, workspace_names)),
        ("Python Version Files", check_no_member_python_version(members)),
        ("Python Version Spec", check_requires_python(members, root_requires)),
        ("Circular Dependencies", check_no_cycles(members, workspace_names)),
        ("Build Backend", check_build_backend(members)),
        ("Dependency Direction", check_dependency_direction(members, workspace_names)),
        ("Root Sources", check_no_root_sources()),
        ("Tool Config Overrides", check_no_member_tool_overrides(members)),
        ("Optional Dependencies", check_no_member_optional_deps(members)),
        ("Naming Convention", check_naming_convention(members)),
    ]

    for label, errors in checks:
        if errors:
            print(f"\n── {label} ──")
            for err in errors:
                print(f"  ❌ {err}")
            all_errors.extend(errors)

    if all_errors:
        print(f"\n💡 {len(all_errors)} issue(s) found. Fix the errors above.")
        sys.exit(1)
    else:
        print("✅ All workspace checks passed.")


if __name__ == "__main__":
    main()
