#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""Install the standalone skill or a losslessly removable instruction block."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

START = b"<!-- divorce:start -->"
END = b"<!-- divorce:end -->"
MARKER = ".divorce-installed"
MANIFEST = ".divorce-install-manifest"
BLOCK = """<!-- divorce:start -->

## divorce: native web standards

- Stop at the first adequate solution: omit unnecessary work, reuse the project, use native HTML, use CSS before JavaScript, reuse installed dependencies, then write the smallest code and a small test for logic.
- Never trim accessibility, input validation at trust boundaries, or error handling that prevents data loss.
- Use buttons for actions, links for navigation, details/summary for disclosure, dialog or Popover for temporary tasks, and labelled native form controls. ARIA refines native semantics; no ARIA is better than wrong ARIA.
- Check the actual DOM from library primitives. Use native state pseudo-classes, ordered headings (one h1, no skipped levels), and header/nav/main/footer landmarks once each.
- Prefer gap, inset, aspect-ratio, grid/subgrid, container queries, logical properties and 100dvh; use root colour tokens, color-mix(), and light-dark() with color-scheme. Animate transform/opacity with a prefers-reduced-motion path.
- Default to features shipped in Blink and WebKit; guard newer features with @supports and provide fallbacks for single-engine enhancements.
- Cite the relevant spec section; distinguish conventions and keep the project convention. Source order: WHATWG HTML, W3C/CSSWG, WAI-ARIA/APG, WCAG 2.2, MDN.
- Gate script (absolute path): {gate}
- Before saying done, run python3 with that gate path: html on served HTML (URL or built file), axe-snippet in the rendered page, axe on its captured JSON, or check --html INPUT --axe JSON_FILE for both. The default --axe-max-impact serious rejects serious/critical violations.
- Exit 0 means pass, 1 fail, 2 not_measured; 2 is never a pass. Quote JSON counts and messages. Install Nu HTML Checker with scripts/install-vnu.sh if needed.
- Automated checks cover only part of WCAG. Check keyboard Tab/Enter/Space/Escape and focus return, inspect the page, and report gate results, manual checks, unchecked items and remaining risk.

<!-- divorce:end -->"""
HELP = """Usage: install.sh [--claude|--codex|--agents-md FILE] [--project DIR]
                  [--dry-run] [--force] [--uninstall] [-h|--help]
Install divorce for Claude (default), Codex, or an agent instruction file.
--project DIR   Install in DIR/.claude/skills/divorce (Claude only).
--force         Replace an existing skill installation.
--uninstall     Remove a marked installation or the instruction block.
--dry-run       Print each action with would: without writing anything.
Instruction blocks own all their whitespace; an appended start marker may
adjoin an existing final line so uninstall restores the original bytes.
"""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        if "not allowed with argument" in message:
            message = "Choose only one installation mode."
        elif message == "argument --agents-md: expected one argument":
            message = "--agents-md requires a file."
        elif message == "argument --project: expected one argument":
            message = "--project requires a directory."
        elif message.startswith("unrecognized arguments: "):
            message = "Unknown argument: " + message.split(": ", 1)[1].split()[0]
        raise ValueError(message)

    def format_help(self):
        return HELP


def parse_arguments(argv):
    parser = Parser(
        prog="install.sh", allow_abbrev=False,
        description="Install divorce for Claude (default), Codex, or an agent instruction file.",
        epilog="Instruction blocks own all their whitespace; an appended start marker may "
               "adjoin an existing final line so uninstall restores the original bytes.",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--claude", action="store_true")
    modes.add_argument("--codex", action="store_true")
    modes.add_argument("--agents-md", metavar="FILE")
    parser.add_argument("--project", metavar="DIR", help="Install in DIR/.claude/skills/divorce (Claude only).")
    parser.add_argument("--force", action="store_true", help="Replace an existing skill installation.")
    parser.add_argument("--uninstall", action="store_true", help="Remove a marked installation or the instruction block.")
    parser.add_argument("--dry-run", action="store_true", help="Print each action with would: without writing anything.")
    args = parser.parse_args(argv)
    if sum(arg in ("--claude", "--codex", "--agents-md") for arg in argv) > 1:
        parser.error("Choose only one installation mode.")
    if argv.count("--project") > 1:
        parser.error("Specify --project only once.")
    if args.project is not None and not args.project:
        parser.error("--project requires a directory.")
    if args.agents_md is not None and not args.agents_md:
        parser.error("--agents-md requires a file.")
    if args.project is not None and (args.codex or args.agents_md is not None):
        parser.error("--project is supported only with --claude.")
    return args


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def legacy_cksum(path):
    """Read pre-Python manifests without depending on the cksum executable."""
    table = []
    for value in range(256):
        crc = value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
        table.append(crc)
    crc = size = 0
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            for byte in block:
                crc = ((crc << 8) & 0xFFFFFFFF) ^ table[(crc >> 24) ^ byte]
    while size:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ table[(crc >> 24) ^ (size & 255)]
        size >>= 8
    return str(crc ^ 0xFFFFFFFF)


def optional_stat(path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def safe_status(destination, relative):
    current = destination
    parts = relative.split("/")
    for index, part in enumerate(parts):
        current = current / part
        info = optional_stat(current)
        if info is None:
            return "missing", None
        if stat.S_ISLNK(info.st_mode):
            return "modified", info
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            return "modified", info
    return "present", info


def walk_files(directory, include_directories=False):
    """Unlike rglob/os.walk defaults, listing failures must reach the caller."""
    for name in sorted(os.listdir(directory)):
        path = directory / name
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            if include_directories:
                yield path
            yield from walk_files(path, include_directories)
        else:
            yield path


def update_instructions(target, source, args):
    info = optional_stat(target)
    if info is not None and stat.S_ISLNK(info.st_mode):
        raise ValueError("Refusing to replace a symbolic-link instruction file.")
    if info is not None and not stat.S_ISREG(info.st_mode):
        raise ValueError("The instruction target must be a regular file.")
    content = target.read_bytes() if info is not None else b""
    start, end = content.find(START), content.find(END)
    if (content.count(START), content.count(END)) not in ((0, 0), (1, 1)) or end < start:
        raise ValueError("Malformed or duplicate divorce markers; the file was not changed.")
    block = b"" if args.uninstall else BLOCK.format(gate=source / "scripts" / "gate.py").encode()
    updated = content[:start] + block + content[end + len(END):] if start >= 0 else content + block
    if args.dry_run:
        if args.uninstall:
            print(f"would: remove the divorce block from {target}")
        else:
            print(f"would: create parent directory {target.parent} if needed")
            print(f"would: append or replace the divorce block in {target}")
        return
    if updated == content and (info is not None or args.uninstall):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".divorce-install.", dir=target.parent) as temporary:
        staged = Path(temporary) / "instructions"
        if info is not None:
            shutil.copy2(target, staged)
        staged.write_bytes(updated)
        os.replace(staged, target)


def install_skill(destination, source, args):
    if not source.is_dir():
        raise ValueError("Cannot find skills/divorce next to the installer.")
    existing = optional_stat(destination)
    if existing is not None and not args.force:
        raise ValueError("The destination already exists; use --force to replace it.")
    if args.dry_run:
        print(f"would: create parent directory {destination.parent} if needed")
        if existing is not None:
            print(f"would: replace existing destination {destination}")
        print(f"would: copy {source} to {destination}")
        print(f"would: write {destination / MARKER}")
        print(f"would: write {destination / MANIFEST}")
        return
    # Validate names before creating directories or replacing any existing skill.
    for path in walk_files(source, include_directories=True):
        if "\n" in str(path.relative_to(source)):
            raise ValueError("Cannot install a filename containing a newline.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".divorce-install.", dir=destination.parent) as temporary:
        staged = Path(temporary) / "skill"
        shutil.copytree(source, staged, symlinks=True)
        (staged / MARKER).write_bytes(b"divorce\n")
        entries = []
        for path in walk_files(staged):
            relative = path.relative_to(staged).as_posix()
            info = path.lstat()
            if relative != MANIFEST and stat.S_ISREG(info.st_mode):
                entries.append(f"{file_sha256(path)} {info.st_size} {relative}\n")
        (staged / MANIFEST).write_text("".join(entries), encoding="utf-8", errors="surrogateescape")
        if existing is not None:
            if stat.S_ISDIR(existing.st_mode):
                shutil.rmtree(destination)
            else:
                destination.unlink()
        os.replace(staged, destination)


def read_manifest(manifest):
    entries = {}
    content = manifest.read_bytes().decode("utf-8", "surrogateescape")
    for line in content.split("\n")[:-1] if content.endswith("\n") else content.split("\n"):
        match = re.fullmatch(r"([0-9a-f]{64}|[0-9]+) ([0-9]+) (.+)", line)
        if match is None:
            raise ValueError("Invalid installation manifest; no files were removed.")
        checksum, size, relative = match.groups()
        if (relative in entries or relative == MANIFEST or "\0" in relative or
                any(part in ("", ".", "..") for part in relative.split("/"))):
            raise ValueError("Invalid installation manifest; no files were removed.")
        entries[relative] = (checksum, int(size))
    if MARKER not in entries:
        raise ValueError("Invalid installation manifest; no files were removed.")
    return entries


def report_kept(relative, reason, dry_run):
    if dry_run:
        print(f"would: keep {relative} ({reason})")
    elif reason == "not installed by divorce":
        print(f"kept file not installed by divorce: {relative}", file=sys.stderr)
    else:
        print(f"kept {reason} file: {relative}", file=sys.stderr)


def uninstall_plan(destination, dry_run):
    root_info = optional_stat(destination)
    marker_info = optional_stat(destination / MARKER) if root_info is not None and stat.S_ISDIR(root_info.st_mode) else None
    if marker_info is None or not stat.S_ISREG(marker_info.st_mode):
        raise ValueError("Refusing to remove an installation without its .divorce-installed marker.")
    manifest = destination / MANIFEST
    manifest_info = optional_stat(manifest)
    if manifest_info is None or not stat.S_ISREG(manifest_info.st_mode):
        raise ValueError(f"Refusing to uninstall without .divorce-install-manifest; remove {destination} manually.")
    entries = read_manifest(manifest)
    remove, directories = [], set()
    if dry_run:
        print(f"would: remove marked installation {destination}")
    for relative, (checksum, size) in entries.items():
        path = destination / relative
        parent = path.parent
        while parent != destination:
            directories.add(parent)
            parent = parent.parent
        status, info = safe_status(destination, relative)
        if status == "present" and stat.S_ISREG(info.st_mode):
            actual = file_sha256(path)
            if len(checksum) != 64:
                actual = legacy_cksum(path)
            if actual == checksum and info.st_size == size:
                remove.append(path)
                if dry_run:
                    print(f"would: remove {relative}")
                continue
        report_kept(relative, "missing" if status == "missing" else "modified", dry_run)
    for path in walk_files(destination):
        relative = path.relative_to(destination).as_posix()
        if relative != MANIFEST and relative not in entries:
            report_kept(relative, "not installed by divorce", dry_run)
    return remove, sorted(directories, key=lambda path: (-len(path.parts), str(path)))


def finish_uninstall(destination):
    manifest = destination / MANIFEST
    remaining = [name for name in os.listdir(destination) if name != MANIFEST]
    if remaining:
        print(f"kept non-empty directory: {destination}", file=sys.stderr)
        manifest.unlink()
        return
    # Keep the manifest outside the directory until its rmdir has succeeded.
    descriptor, backup_name = tempfile.mkstemp(prefix=".divorce-manifest.", dir=destination.parent)
    os.close(descriptor)
    backup = Path(backup_name)
    try:
        os.replace(manifest, backup)
    except Exception:
        backup.unlink()
        raise
    try:
        os.rmdir(destination)
        backup.unlink()
    except Exception:
        destination.mkdir(exist_ok=True)
        os.replace(backup, manifest)
        raise


def uninstall_skill(destination, args):
    remove, directories = uninstall_plan(destination, args.dry_run)
    if args.dry_run:
        for directory in directories:
            print(f"would: remove directory {directory.relative_to(destination)} if empty")
        print("would: remove .divorce-install-manifest")
        print(f"would: remove directory {destination} if empty")
        return
    marker = destination / MARKER
    marker_bytes = marker.read_bytes()
    marker_removed = False
    try:
        for path in remove:
            if path != marker:
                path.unlink()
        for directory in directories:
            relative = directory.relative_to(destination).as_posix()
            status, info = safe_status(destination, relative)
            if status != "present" or not stat.S_ISDIR(info.st_mode):
                continue
            if os.listdir(directory):
                print(f"kept non-empty directory: {relative}", file=sys.stderr)
            else:
                os.rmdir(directory)
        if marker in remove:
            marker.unlink()
            marker_removed = True
        finish_uninstall(destination)
    except Exception:
        if marker_removed:
            marker.write_bytes(marker_bytes)
        raise


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 9):
        print("divorce: python3 (3.9+) is required", file=sys.stderr)
        return 1
    try:
        args = parse_arguments(list(sys.argv[1:] if argv is None else argv))
        source = Path(__file__).resolve().parent / "skills" / "divorce"
        if args.agents_md is not None:
            update_instructions(Path(args.agents_md).absolute(), source, args)
        else:
            if args.project is not None:
                destination = Path(args.project) / ".claude" / "skills" / "divorce"
            else:
                if "HOME" in os.environ and not os.environ["HOME"]:
                    raise ValueError("HOME is required for a user installation.")
                destination = Path.home() / (".codex" if args.codex else ".claude") / "skills" / "divorce"
            destination = destination.absolute()
            if args.uninstall:
                uninstall_skill(destination, args)
            else:
                install_skill(destination, source, args)
        return 0
    except SystemExit as error:
        return int(error.code)
    except Exception as error:
        print(f"divorce: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
