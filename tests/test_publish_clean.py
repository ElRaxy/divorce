#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""Keep private details and untranslated wording out of published files."""

from fnmatch import fnmatch
import os
from pathlib import Path
import re
import subprocess
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    re.compile("Vanguard" + "IA"),
    re.compile("Anuu" + "bis"),
    re.compile("/Use" + "rs/"),
    re.compile(r"\b" + "al" + "ex" + r"\b", re.IGNORECASE),
    re.compile(r"\b" + "q" + "ue" + r"\b"),
    re.compile(r"\b" + "l" + "os" + r"\b"),
    re.compile(r"\b" + "pa" + "ra" + r"\b"),
)


def published_files():
    try:
        available = subprocess.run(
            ["git", "-C", str(REPOSITORY), "rev-parse"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False, timeout=15,
        ).returncode == 0
    except OSError:
        available = False
    if available:
        result = subprocess.run(
            ["git", "-C", str(REPOSITORY), "ls-files", "--others", "--cached",
             "--exclude-standard", "-z"],
            capture_output=True, check=True, timeout=15,
        )
        return sorted({REPOSITORY / os.fsdecode(name)
                       for name in result.stdout.split(b"\0") if name})

    patterns = [line.strip() for line in
                (REPOSITORY / ".gitignore").read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")]

    def ignored(path, directory):
        relative = path.relative_to(REPOSITORY).as_posix()
        excluded = False
        for pattern in patterns:
            negate = pattern.startswith("!")
            pattern = pattern[1:] if negate else pattern
            if pattern.endswith("/") and not directory:
                continue
            pattern = pattern.rstrip("/")
            anchored = pattern.startswith("/") or "/" in pattern
            candidate = relative if anchored else path.name
            if fnmatch(candidate, pattern.lstrip("/")):
                excluded = not negate
        return excluded

    files = []
    for directory, names, filenames in os.walk(REPOSITORY):
        root = Path(directory)
        names[:] = [name for name in names
                    if name != ".git" and not ignored(root / name, True)]
        files.extend(root / name for name in filenames
                     if name != ".git" and not ignored(root / name, False))
    return sorted(files)


class PublishCleanTests(unittest.TestCase):
    def test_published_text_has_no_private_or_untranslated_terms(self):
        matches = []
        for path in published_files():
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(content.splitlines(), 1):
                for pattern in FORBIDDEN:
                    for match in pattern.finditer(line):
                        relative = path.relative_to(REPOSITORY).as_posix()
                        matches.append(f"{relative}:{number}:{match.group()}")
        self.assertEqual(matches, [], "\n" + "\n".join(matches))


if __name__ == "__main__":
    unittest.main()
