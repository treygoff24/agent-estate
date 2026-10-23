#!/usr/bin/env python3
"""Read-only test/coverage inventory for a repository.

Outputs Markdown by default, or JSON with --json. Uses only stdlib and does not
modify the target tree.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".next", "dist", "build", "target",
    ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "coverage", "htmlcov", "playwright-report", "test-results", ".turbo",
}

MANIFESTS = [
    "package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lockb",
    "tsconfig.json", "vite.config.ts", "vite.config.js", "vitest.config.ts", "vitest.config.js",
    "jest.config.ts", "jest.config.js", "playwright.config.ts", "playwright.config.js",
    "cypress.config.ts", "cypress.config.js", "next.config.ts", "next.config.js", "next.config.mjs",
    "pyproject.toml", "pytest.ini", "tox.ini", "noxfile.py", "requirements.txt",
    "Cargo.toml", "Cargo.lock", "nextest.toml", "Makefile", "justfile", "Taskfile.yml",
]

TEST_NAME_PARTS = (
    ".test.", ".spec.", "_test.", "test_", "tests.rs", ".feature",
)

TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "e2e", "integration"}

CONFIG_HINTS = {
    "vitest": ["vitest.config.ts", "vitest.config.js"],
    "jest": ["jest.config.ts", "jest.config.js"],
    "playwright": ["playwright.config.ts", "playwright.config.js"],
    "cypress": ["cypress.config.ts", "cypress.config.js"],
    "next": ["next.config.ts", "next.config.js", "next.config.mjs"],
    "pytest": ["pytest.ini", "pyproject.toml", "tox.ini"],
    "rust": ["Cargo.toml"],
}


def is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def read_toml(path: Path) -> dict[str, Any] | None:
    if tomllib is None:
        return None
    try:
        return tomllib.loads(path.read_text())
    except Exception:
        return None


def likely_test(path: Path) -> bool:
    name = path.name.lower()
    if any(part in name for part in TEST_NAME_PARTS):
        return True
    if any(parent.lower() in TEST_DIR_NAMES for parent in path.parts):
        suffix = path.suffix.lower()
        return suffix in {".js", ".jsx", ".ts", ".tsx", ".py", ".rs", ".feature"}
    return False


def collect(root: Path) -> dict[str, Any]:
    root = root.resolve()
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if is_skipped(current.relative_to(root) if current != root else Path(".")):
            continue
        for filename in filenames:
            path = current / filename
            if not is_skipped(path.relative_to(root)):
                files.append(path)

    manifest_paths = sorted({rel(root / name, root) for name in MANIFESTS if (root / name).exists()})
    workflow_paths = sorted(rel(p, root) for p in (root / ".github" / "workflows").glob("*") if p.is_file())
    test_files = sorted(rel(p, root) for p in files if likely_test(p))

    package_json = read_json(root / "package.json") if (root / "package.json").exists() else None
    pyproject = read_toml(root / "pyproject.toml") if (root / "pyproject.toml").exists() else None
    cargo = read_toml(root / "Cargo.toml") if (root / "Cargo.toml").exists() else None

    package_scripts = package_json.get("scripts", {}) if isinstance(package_json, dict) else {}
    test_like_scripts = {
        k: v for k, v in package_scripts.items()
        if any(word in k.lower() or word in str(v).lower() for word in ["test", "coverage", "e2e", "playwright", "cypress", "vitest", "jest"])
    }

    detected: list[str] = []
    names = {p.name for p in files}
    rels = {rel(p, root) for p in files}
    if package_json:
        deps = {}
        for key in ["dependencies", "devDependencies", "peerDependencies"]:
            val = package_json.get(key, {}) if isinstance(package_json, dict) else {}
            if isinstance(val, dict):
                deps.update(val)
        if "next" in deps or any(x.startswith("app/") for x in rels):
            detected.append("Next.js")
        if "react" in deps:
            detected.append("React")
        if "typescript" in deps or "tsconfig.json" in names:
            detected.append("TypeScript")
        if any(k in deps for k in ["vitest", "jest", "@playwright/test", "cypress", "@testing-library/react", "msw"]):
            detected.append("JS/TS tests")
        else:
            detected.append("JavaScript/Node")
    if pyproject or (root / "requirements.txt").exists() or any(p.suffix == ".py" for p in files):
        detected.append("Python")
    if cargo:
        detected.append("Rust")

    config_hints = {
        key: [name for name in patterns if (root / name).exists()]
        for key, patterns in CONFIG_HINTS.items()
    }
    config_hints = {k: v for k, v in config_hints.items() if v}

    likely_surfaces = {
        "next_app_routes": sorted(p for p in rels if p.startswith("app/") and Path(p).name in {"page.tsx", "page.ts", "route.ts", "route.js", "layout.tsx", "layout.ts", "middleware.ts", "proxy.ts"}),
        "pages_api_routes": sorted(p for p in rels if p.startswith("pages/api/")),
        "python_entrypoints": sorted(p for p in rels if p.endswith(".py") and (Path(p).name in {"main.py", "app.py", "cli.py"} or "scripts/" in p)),
        "rust_bins": [],
    }
    if cargo:
        bins = cargo.get("bin", []) if isinstance(cargo, dict) else []
        if isinstance(bins, list):
            likely_surfaces["rust_bins"] = [str(b.get("name", b)) for b in bins]
        elif isinstance(bins, dict):
            likely_surfaces["rust_bins"] = [str(bins.get("name", "<unnamed>"))]

    return {
        "root": str(root),
        "detected_stacks": sorted(set(detected)),
        "manifests": manifest_paths,
        "config_hints": config_hints,
        "package_test_like_scripts": test_like_scripts,
        "workflows": workflow_paths,
        "test_file_count": len(test_files),
        "test_files_sample": test_files[:80],
        "likely_surfaces": {k: v[:80] for k, v in likely_surfaces.items() if v},
    }


def print_markdown(data: dict[str, Any]) -> None:
    print("# Test inventory")
    print(f"\nRoot: `{data['root']}`")
    print("\n## Detected stacks")
    for stack in data["detected_stacks"] or ["unknown"]:
        print(f"- {stack}")
    print("\n## Manifests/configs")
    for item in data["manifests"] or ["none found"]:
        print(f"- `{item}`")
    print("\n## Test-like package scripts")
    scripts = data["package_test_like_scripts"]
    if scripts:
        for key, value in scripts.items():
            print(f"- `{key}`: `{value}`")
    else:
        print("- none found")
    print("\n## CI workflows")
    for item in data["workflows"] or ["none found"]:
        print(f"- `{item}`")
    print(f"\n## Test files ({data['test_file_count']})")
    for item in data["test_files_sample"] or ["none found"]:
        print(f"- `{item}`")
    print("\n## Likely behavior surfaces")
    surfaces = data["likely_surfaces"]
    if surfaces:
        for key, values in surfaces.items():
            print(f"\n### {key}")
            for value in values:
                print(f"- `{value}`")
    else:
        print("- none inferred")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=".", help="Repo/workspace root to inspect")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args()
    data = collect(Path(args.path))
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print_markdown(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
