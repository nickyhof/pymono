#!/usr/bin/env python3
"""Generate a Mermaid dependency graph of all workspace members.

Outputs the graph to stdout and optionally writes docs/dependency-graph.md.
"""

import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_toml(path: pathlib.Path) -> dict:
    return tomllib.loads(path.read_text())


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


def classify(toml_path: pathlib.Path) -> str:
    rel = toml_path.relative_to(ROOT)
    if rel.parts[0] == "apps":
        return "app"
    return "lib"


def parse_dep_name(dep: str) -> str:
    return dep.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("!")[0].split(";")[0].strip()


def build_graph() -> str:
    members = discover_members()
    workspace_names = set(members.keys())

    # Classify members
    apps: list[str] = []
    libs: list[str] = []
    for name, path in members.items():
        if classify(path) == "app":
            apps.append(name)
        else:
            libs.append(name)

    # Build edges
    edges: list[tuple[str, str]] = []
    for name, path in members.items():
        data = load_toml(path)
        for dep in data.get("project", {}).get("dependencies", []):
            base = parse_dep_name(dep)
            if base in workspace_names:
                edges.append((name, base))

    # Generate Mermaid
    lines = ["graph TD"]

    # Style subgraphs
    if apps:
        lines.append("    subgraph Apps")
        for app in sorted(apps):
            lines.append(f"        {app}[{app}]:::app")
        lines.append("    end")

    if libs:
        lines.append("    subgraph Libs")
        for lib in sorted(libs):
            lines.append(f"        {lib}[{lib}]:::lib")
        lines.append("    end")

    # Edges
    for src, dst in sorted(edges):
        lines.append(f"    {src} --> {dst}")

    # Styling
    lines.append("")
    lines.append("    classDef app fill:#4a9eff,stroke:#2670c4,color:#fff")
    lines.append("    classDef lib fill:#50c878,stroke:#2e8b57,color:#fff")

    return "\n".join(lines)


def main() -> None:
    graph = build_graph()
    print(graph)

    # Write to docs/
    docs_dir = ROOT / "docs"
    docs_dir.mkdir(exist_ok=True)
    out = docs_dir / "dependency-graph.md"
    out.write_text(f"# Dependency Graph\n\n```mermaid\n{graph}\n```\n")
    print(f"\n✅ Written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
