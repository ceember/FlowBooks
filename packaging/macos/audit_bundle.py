#!/usr/bin/env python3
"""Audit a frozen macOS app's architecture and native-library closure."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from prepare_bundle import resource_framework_links

REQUIRED_LIBRARIES = {
    "libfontconfig.1.dylib",
    "libgobject-2.0.0.dylib",
    "libharfbuzz-subset.0.dylib",
    "libharfbuzz.0.dylib",
    "libpango-1.0.dylib",
    "libpangoft2-1.0.dylib",
}
ALLOWED_ABSOLUTE_PREFIXES = ("/System/Library/", "/usr/lib/")


def _run(*args: str) -> str:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _dependencies(path: Path) -> list[str]:
    install_name_lines = _run("otool", "-D", str(path)).splitlines()[1:]
    install_name = install_name_lines[0].strip() if install_name_lines else None
    lines = _run("otool", "-L", str(path)).splitlines()[1:]
    dependencies = [line.strip().split(" (", 1)[0] for line in lines if line.strip()]
    return [dependency for dependency in dependencies if dependency != install_name]


def _rpaths(path: Path) -> list[str]:
    output = _run("otool", "-l", str(path))
    return re.findall(r"^\s*path (.+?) \(offset \d+\)$", output, re.MULTILINE)


def _expand_path(
    value: str,
    loader_dir: Path,
    executable_dir: Path,
) -> Path | None:
    if value == "@loader_path":
        return loader_dir
    if value.startswith("@loader_path/"):
        return loader_dir / value.removeprefix("@loader_path/")
    if value == "@executable_path":
        return executable_dir
    if value.startswith("@executable_path/"):
        return executable_dir / value.removeprefix("@executable_path/")
    if value.startswith("/"):
        return Path(value)
    return None


def _resolve_dependency(
    dependency: str,
    image: Path,
    executable_dir: Path,
) -> Path | None:
    loader_dir = image.parent
    direct = _expand_path(dependency, loader_dir, executable_dir)
    if direct is not None:
        return direct.resolve() if direct.exists() else None
    if not dependency.startswith("@rpath/"):
        return None

    suffix = dependency.removeprefix("@rpath/")
    for raw_rpath in _rpaths(image):
        base = _expand_path(raw_rpath, loader_dir, executable_dir)
        if base is None:
            continue
        candidate = base / suffix
        if candidate.exists():
            return candidate.resolve()
    return None


def audit_bundle(app: Path, expected_arch: str) -> str:
    if not app.is_dir() or app.suffix != ".app":
        raise ValueError(f"not an app bundle: {app}")

    report = []
    failures = []
    bundled_names = set()
    macho_count = 0
    executable_dir = app / "Contents" / "MacOS"
    app_root = app.resolve()

    reverse_links = resource_framework_links(app)
    for link in reverse_links:
        failures.append(
            f"{link.relative_to(app)}: Resources link points into Frameworks"
        )

    for path in sorted(app.rglob("*")):
        bundled_names.add(path.name)
        if path.is_symlink():
            resolved = path.resolve(strict=False)
            if not resolved.exists():
                failures.append(f"{path.relative_to(app)}: broken symbolic link")
            try:
                resolved.relative_to(app_root)
            except ValueError:
                failures.append(
                    f"{path.relative_to(app)}: symbolic link escapes app bundle"
                )
            continue
        if not path.is_file():
            continue
        description = _run("file", "-b", str(path))
        if "Mach-O" not in description:
            continue

        macho_count += 1
        architectures = _run("lipo", "-archs", str(path)).split()
        relative = path.relative_to(app)
        report.append(f"{relative}\tarchitectures={','.join(architectures)}")
        if expected_arch not in architectures:
            failures.append(f"{relative}: missing {expected_arch} slice")

        for dependency in _dependencies(path):
            report.append(f"  {dependency}")
            if dependency.startswith("/") and not dependency.startswith(
                ALLOWED_ABSOLUTE_PREFIXES
            ):
                failures.append(f"{relative}: external dependency {dependency}")
            elif dependency.startswith("@"):
                resolved = _resolve_dependency(dependency, path, executable_dir)
                if resolved is None:
                    failures.append(
                        f"{relative}: unresolved bundled dependency {dependency}"
                    )
                else:
                    try:
                        resolved_relative = resolved.relative_to(app.resolve())
                    except ValueError:
                        failures.append(
                            f"{relative}: dependency resolves outside bundle: "
                            f"{dependency} -> {resolved}"
                        )
                    else:
                        report.append(f"    resolved={resolved_relative}")
            elif not dependency.startswith(ALLOWED_ABSOLUTE_PREFIXES):
                failures.append(f"{relative}: unsupported dependency {dependency}")

    if macho_count == 0:
        failures.append("bundle contains no Mach-O files")
    for library in sorted(REQUIRED_LIBRARIES - bundled_names):
        failures.append(f"required bundled library missing: {library}")

    report.append(f"mach_o_count={macho_count}")
    if failures:
        report.extend(f"ERROR: {failure}" for failure in failures)
        raise RuntimeError("\n".join(report))
    return "\n".join(report) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("--expected-arch", default="arm64")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(
        audit_bundle(args.app, args.expected_arch),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
