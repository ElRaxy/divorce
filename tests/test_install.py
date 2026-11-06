#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""Installer contracts, isolated from the real home and working directory."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("divorce_install", REPOSITORY / "install.py")
install = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = install
SPEC.loader.exec_module(install)
START = b"<!-- divorce:start -->"
END = b"<!-- divorce:end -->"


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.repository = self.root / "checkout with spaces"
        self.repository.mkdir()
        shutil.copy2(REPOSITORY / "install.sh", self.repository / "install.sh")
        shutil.copy2(REPOSITORY / "install.py", self.repository / "install.py")
        shutil.copytree(REPOSITORY / "skills", self.repository / "skills")
        self.cwd = self.root / "unrelated working directory"
        self.cwd.mkdir()
        self.script = self.repository / "install.sh"
        environment = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        environment.start()
        self.addCleanup(environment.stop)
        location = mock.patch.object(install, "__file__", str(self.repository / "install.py"))
        location.start()
        self.addCleanup(location.stop)
        original_cwd = Path.cwd()
        os.chdir(self.cwd)
        self.addCleanup(os.chdir, original_cwd)

    def install(self, *arguments, expected=0):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = install.main(list(map(str, arguments)))
        process = SimpleNamespace(returncode=result, stdout=stdout.getvalue(), stderr=stderr.getvalue())
        self.assertEqual(result, expected, process.stdout + process.stderr)
        return process

    def test_shell_wrapper_invokes_python_from_checkout_with_spaces(self):
        self.assertTrue(os.access(self.script, os.X_OK))
        process = subprocess.run(
            [str(self.script), "--codex"],
            cwd=self.cwd, env=os.environ.copy(),
            capture_output=True, text=True, check=False, timeout=15,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assert_installed(self.home / ".codex" / "skills" / "divorce")
        self.assertFalse((self.home / ".claude").exists())
        self.assertEqual(list(self.cwd.iterdir()), [])

    def assert_installed(self, target):
        self.assertEqual((target / ".divorce-installed").read_text(), "divorce\n")
        source = self.repository / "skills" / "divorce"
        for path in source.rglob("*"):
            if path.is_file():
                self.assertEqual((target / path.relative_to(source)).read_bytes(), path.read_bytes())

    def snapshot(self):
        return {
            str(path.relative_to(self.root)): path.read_bytes() if path.is_file() else None
            for path in self.root.rglob("*")
        }

    def test_default_claude_install_uses_script_directory(self):
        self.install()
        self.assert_installed(self.home / ".claude" / "skills" / "divorce")
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_explicit_claude_install(self):
        self.install("--claude")
        self.assert_installed(self.home / ".claude" / "skills" / "divorce")

    def test_codex_install(self):
        self.install("--codex")
        self.assert_installed(self.home / ".codex" / "skills" / "divorce")
        self.assertFalse((self.home / ".claude").exists())

    def test_home_is_resolved_again_for_each_call(self):
        self.install()
        other_home = self.root / "second home"
        other_home.mkdir()
        with mock.patch.dict(os.environ, {"HOME": str(other_home)}):
            self.install()
        self.assert_installed(self.home / ".claude" / "skills" / "divorce")
        self.assert_installed(other_home / ".claude" / "skills" / "divorce")

    def test_unsupported_python_version_changes_nothing(self):
        before = self.snapshot()
        with mock.patch.object(sys, "version_info", (3, 8, 20)):
            result = self.install(expected=1)
        self.assertIn("3.9", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_project_install_with_relative_path(self):
        self.install("--project", "project with spaces")
        target = self.cwd / "project with spaces" / ".claude" / "skills" / "divorce"
        self.assert_installed(target)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_conflict_without_force_preserves_files(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        custom = target / "local-note"
        custom.write_bytes(b"keep this\n")
        before = self.snapshot()
        process = self.install(expected=1)
        self.assertIn("--force", process.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_force_replaces_existing_directory(self):
        target = self.home / ".claude" / "skills" / "divorce"
        target.mkdir(parents=True)
        (target / "unrelated").write_bytes(b"replace")
        self.install("--force")
        self.assertFalse((target / "unrelated").exists())
        self.assert_installed(target)

    def test_uninstall_requires_marker_even_with_force(self):
        target = self.home / ".claude" / "skills" / "divorce"
        target.mkdir(parents=True)
        (target / "keep").write_bytes(b"untouched")
        before = self.snapshot()
        process = self.install("--uninstall", "--force", expected=1)
        self.assertIn("marker", process.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_marked_installation(self):
        self.install("--codex")
        unrelated = self.home / ".codex" / "skills" / "other"
        unrelated.mkdir()
        (unrelated / "keep").write_bytes(b"untouched")
        self.install("--codex", "--uninstall")
        self.assertFalse((self.home / ".codex" / "skills" / "divorce").exists())
        self.assertEqual((unrelated / "keep").read_bytes(), b"untouched")

    def test_uninstall_keeps_modified_and_unrelated_files(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        (target / "local-note").write_bytes(b"keep this note\n")
        (target / "SKILL.md").write_bytes(b"custom skill instructions\n")
        result = self.install("--uninstall")
        self.assertEqual((target / "local-note").read_bytes(), b"keep this note\n")
        self.assertEqual((target / "SKILL.md").read_bytes(), b"custom skill instructions\n")
        self.assertEqual({path.relative_to(target) for path in target.rglob("*")},
                         {Path("local-note"), Path("SKILL.md")})
        self.assertIn("kept modified file: SKILL.md", result.stderr)
        self.assertIn("kept file not installed by divorce: local-note", result.stderr)

    def test_uninstall_unchanged_installation_removes_destination(self):
        source = self.repository / "skills" / "divorce"
        for directory in ("first folder", "second folder"):
            nested = source / directory / "nested"
            nested.mkdir(parents=True)
            (nested / "file with spaces").write_bytes(b"owned\n")
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        manifest = (target / ".divorce-install-manifest").read_text()
        self.assertIn(" .divorce-installed\n", manifest)
        self.assertNotIn(" .divorce-install-manifest\n", manifest)
        self.install("--uninstall")
        self.assertFalse(target.exists())

    def test_uninstall_accepts_legacy_posix_checksum(self):
        (self.repository / "skills" / "divorce" / "SKILL.md").write_bytes(b"123456789")
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        manifest = target / ".divorce-install-manifest"
        entries = manifest.read_text().splitlines()
        matching = [index for index, entry in enumerate(entries)
                    if entry.split(" ", 2)[2] == "SKILL.md"]
        self.assertEqual(len(matching), 1)
        # POSIX cksum reference vector; no external utility is needed at runtime.
        entries[matching[0]] = "930766865 9 SKILL.md"
        manifest.write_text("\n".join(entries) + "\n")
        self.install("--uninstall")
        self.assertFalse(target.exists())

    def test_uninstall_directory_listing_failure_keeps_manifest(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        manifest = target / ".divorce-install-manifest"
        original = manifest.read_bytes()
        before = self.snapshot()
        real_listdir = os.listdir

        def fail_listing(path):
            if Path(path) == target:
                raise PermissionError("injected directory listing failure")
            return real_listdir(path)

        with mock.patch.object(os, "listdir", side_effect=fail_listing):
            result = self.install("--uninstall", expected=1)
        self.assertIn("injected directory listing failure", result.stderr)
        self.assertEqual(manifest.read_bytes(), original)
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_manifest_read_failure_changes_nothing(self):
        self.install()
        manifest = self.home / ".claude" / "skills" / "divorce" / ".divorce-install-manifest"
        before = self.snapshot()
        real_read = Path.read_bytes

        def fail_manifest_read(path):
            if path == manifest:
                raise OSError("injected manifest read failure")
            return real_read(path)

        with mock.patch.object(Path, "read_bytes", fail_manifest_read):
            result = self.install("--uninstall", expected=1)
        self.assertIn("injected manifest read failure", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_execution_listing_failure_keeps_manifest_and_marker(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        blocked = target / "scripts" / "tests"
        manifest = target / ".divorce-install-manifest"
        original = manifest.read_bytes()
        real_listdir = os.listdir
        failures = []

        def fail_execution_listing(path):
            if Path(path) == blocked and not (target / "scripts" / "gate.py").exists():
                failures.append(path)
                raise PermissionError("injected execution listing failure")
            return real_listdir(path)

        with mock.patch.object(os, "listdir", side_effect=fail_execution_listing):
            result = self.install("--uninstall", expected=1)
        self.assertEqual(len(failures), 1)
        self.assertIn("injected execution listing failure", result.stderr)
        self.assertEqual(manifest.read_bytes(), original)
        self.assertEqual((target / ".divorce-installed").read_bytes(), b"divorce\n")
        self.assertTrue(blocked.is_dir())
        self.install("--uninstall")
        self.assertFalse(target.exists())

    def test_uninstall_hash_failure_after_first_hash_changes_nothing(self):
        self.install()
        before = self.snapshot()
        real_hash = install.file_sha256
        calls = []

        def fail_second_hash(path):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("injected hash failure")
            return real_hash(path)

        with mock.patch.object(install, "file_sha256", side_effect=fail_second_hash):
            result = self.install("--uninstall", expected=1)
        self.assertEqual(len(calls), 2)
        self.assertIn("injected hash failure", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_stat_failure_changes_nothing(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce" / "SKILL.md"
        before = self.snapshot()
        real_stat = Path.stat
        real_lstat = Path.lstat

        def fail_stat(path, *args, **kwargs):
            if path == target:
                raise PermissionError("injected stat failure")
            return real_stat(path, *args, **kwargs)

        def fail_lstat(path, *args, **kwargs):
            if path == target:
                raise PermissionError("injected stat failure")
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(Path, "stat", fail_stat), mock.patch.object(Path, "lstat", fail_lstat):
            result = self.install("--uninstall", expected=1)
        self.assertIn("injected stat failure", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_empty_directory_removal_failure_keeps_manifest(self):
        source = self.repository / "skills" / "divorce"
        nested = source / "folder with spaces" / "nested"
        nested.mkdir(parents=True)
        (nested / "owned-file").write_bytes(b"owned\n")
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        blocked = target / "folder with spaces" / "nested"
        manifest = target / ".divorce-install-manifest"
        original = manifest.read_bytes()
        real_rmdir = os.rmdir
        failures = []

        def fail_empty_directory(path, *args, **kwargs):
            if Path(path) == blocked:
                self.assertEqual(os.listdir(blocked), [])
                failures.append(path)
                raise PermissionError("injected empty directory removal failure")
            return real_rmdir(path, *args, **kwargs)

        with mock.patch.object(os, "rmdir", side_effect=fail_empty_directory):
            result = self.install("--uninstall", expected=1)
        self.assertEqual(len(failures), 1)
        self.assertIn("injected empty directory removal failure", result.stderr)
        self.assertEqual(manifest.read_bytes(), original)
        self.assertTrue(blocked.is_dir())

    def test_uninstall_root_removal_failure_keeps_manifest(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        manifest = target / ".divorce-install-manifest"
        original = manifest.read_bytes()
        real_rmdir = os.rmdir
        failures = []

        def fail_root(path, *args, **kwargs):
            if Path(path) == target:
                self.assertEqual(os.listdir(target), [])
                failures.append(path)
                raise PermissionError("injected root removal failure")
            return real_rmdir(path, *args, **kwargs)

        with mock.patch.object(os, "rmdir", side_effect=fail_root):
            result = self.install("--uninstall", expected=1)
        self.assertEqual(len(failures), 1)
        self.assertIn("injected root removal failure", result.stderr)
        self.assertEqual(manifest.read_bytes(), original)
        self.assertTrue(target.is_dir())
        self.install("--uninstall")
        self.assertFalse(target.exists())

    def test_uninstall_keeps_nested_user_content_and_modified_file(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        nested = target / "scripts" / "tests"
        note = nested / "local-note"
        modified = nested / "test_gate.py"
        note.write_bytes(b"keep this note\n")
        modified.write_bytes(b"custom gate tests\n")
        result = self.install("--uninstall")
        self.assertEqual(note.read_bytes(), b"keep this note\n")
        self.assertEqual(modified.read_bytes(), b"custom gate tests\n")
        self.assertTrue(nested.is_dir())
        self.assertTrue(nested.parent.is_dir())
        self.assertTrue(target.is_dir())
        self.assertFalse((target / ".divorce-install-manifest").exists())
        self.assertIn("kept modified file: scripts/tests/test_gate.py", result.stderr)
        self.assertIn("kept file not installed by divorce: scripts/tests/local-note", result.stderr)
        self.assertIn("directory", result.stderr)

    def test_uninstall_warns_about_missing_installed_file(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        (target / "SKILL.md").unlink()
        result = self.install("--uninstall")
        self.assertIn("SKILL.md", result.stderr)
        self.assertIn("missing", result.stderr)
        self.assertFalse(target.exists())

    def test_uninstall_without_manifest_changes_nothing(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        (target / ".divorce-install-manifest").unlink()
        before = self.snapshot()
        result = self.install("--uninstall", expected=1)
        self.assertIn("Refusing to uninstall without .divorce-install-manifest; remove ",
                      result.stderr)
        self.assertIn(" manually.", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_dry_run_reports_each_action_without_changes(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        (target / "local-note").write_bytes(b"keep this note\n")
        (target / "SKILL.md").write_bytes(b"custom skill instructions\n")
        before = self.snapshot()
        result = self.install("--dry-run", "--uninstall")
        self.assertIn("would: keep SKILL.md (modified)", result.stdout)
        self.assertIn("would: keep local-note (not installed by divorce)", result.stdout)
        self.assertIn("would: remove scripts/gate.py", result.stdout)
        self.assertIn("would: remove .divorce-install-manifest", result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_install_rejects_newline_filename_before_replacing_destination(self):
        self.install()
        source = self.repository / "skills" / "divorce"
        (source / "line\nbreak").write_bytes(b"unsupported filename\n")
        before = self.snapshot()
        result = self.install("--force", expected=1)
        self.assertIn("filename containing a newline", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_preserves_symlink_and_its_target(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        external = self.root / "external-skill"
        external.write_bytes((target / "SKILL.md").read_bytes())
        original = external.read_bytes()
        (target / "SKILL.md").unlink()
        (target / "SKILL.md").symlink_to(external)
        result = self.install("--uninstall")
        self.assertTrue((target / "SKILL.md").is_symlink())
        self.assertEqual(external.read_bytes(), original)
        self.assertIn("kept modified file: SKILL.md", result.stderr)

    def test_uninstall_does_not_follow_replaced_parent_directory(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        external = self.root / "external-scripts"
        (target / "scripts").rename(external)
        original = {path.relative_to(external): path.read_bytes()
                    for path in external.rglob("*") if path.is_file()}
        (target / "scripts").symlink_to(external, target_is_directory=True)
        result = self.install("--uninstall")
        self.assertTrue((target / "scripts").is_symlink())
        self.assertEqual({path.relative_to(external): path.read_bytes()
                          for path in external.rglob("*") if path.is_file()}, original)
        self.assertIn("kept modified file: scripts/gate.py", result.stderr)

    def test_uninstall_invalid_manifest_changes_nothing(self):
        self.install()
        target = self.home / ".claude" / "skills" / "divorce"
        manifest = target / ".divorce-install-manifest"
        manifest.write_text(manifest.read_text() + "0 0 ../outside\n")
        before = self.snapshot()
        self.install("--uninstall", expected=1)
        self.assertEqual(self.snapshot(), before)

    def test_uninstall_refuses_symlink_destination(self):
        unrelated = self.root / "unrelated-skill"
        unrelated.mkdir()
        (unrelated / ".divorce-installed").write_bytes(b"divorce\n")
        destination = self.home / ".claude" / "skills" / "divorce"
        destination.parent.mkdir(parents=True)
        destination.symlink_to(unrelated, target_is_directory=True)
        self.install("--uninstall", expected=1)
        self.assertTrue(destination.is_symlink())
        self.assertTrue((unrelated / ".divorce-installed").is_file())

    def test_agents_round_trip_preserves_original_bytes(self):
        originals = (
            b"", b"# Instructions\n", b"# Instructions\n\n",
            b"# Instructions\n\nLast line without newline",
            b"ends in n", b"line\r\n\r\nfinal\r\n",
            "# Instructions\n\nUnicode: café\n".encode(),
            b"binary: \xff\x00\xfe\r\nlast line",
        )
        for index, original in enumerate(originals):
            with self.subTest(original=original):
                target = self.root / f"AGENTS-{index}.md"
                target.write_bytes(original)
                self.install("--agents-md", target)
                first = target.read_bytes()
                self.assertTrue(first.startswith(original + START))
                self.assertEqual(first.count(START), 1)
                self.assertEqual(first.count(END), 1)
                gate = self.repository / "skills" / "divorce" / "scripts" / "gate.py"
                self.assertIn(str(gate).encode(), first)
                self.install("--agents-md", target)
                self.assertEqual(target.read_bytes(), first)
                self.install("--uninstall", "--agents-md", target)
                self.assertEqual(target.read_bytes(), original)

    def test_agents_replaces_block_in_place_and_preserves_suffix(self):
        target = self.root / "CLAUDE.md"
        prefix = b"# Before\n\n\xff\x00"
        suffix = b"\n\n# After\r\n\xfelast line without newline"
        target.write_bytes(prefix + START + b"\nold rules\n" + END + suffix)
        self.install("--agents-md", target)
        updated = target.read_bytes()
        self.assertTrue(updated.startswith(prefix + START))
        self.assertTrue(updated.endswith(END + suffix))
        self.assertNotIn(b"old rules", updated)
        self.install("--uninstall", "--agents-md", target)
        self.assertEqual(target.read_bytes(), prefix + suffix)

    def test_agents_creates_missing_file_and_parent(self):
        target = self.root / "new folder" / ".cursorrules"
        self.install("--agents-md", target)
        self.assertTrue(target.read_bytes().startswith(START))
        self.install("--uninstall", "--agents-md", target)
        self.assertEqual(target.read_bytes(), b"")

    def test_agents_uninstall_without_block_keeps_bytes(self):
        target = self.root / "AGENTS.md"
        original = b"keep\n\nlast line"
        target.write_bytes(original)
        self.install("--uninstall", "--agents-md", target)
        self.assertEqual(target.read_bytes(), original)
        missing = self.root / "absent" / "AGENTS.md"
        self.install("--uninstall", "--agents-md", missing)
        self.assertFalse(missing.parent.exists())

    def test_agents_refuses_malformed_or_duplicate_markers(self):
        target = self.root / "AGENTS.md"
        cases = (START, END, END + START, START + START + END,
                 START + END + END, START + END + START + END)
        for content in cases:
            for options in ((), ("--uninstall",), ("--dry-run",)):
                with self.subTest(content=content, options=options):
                    target.write_bytes(content)
                    self.install("--agents-md", target, *options, expected=1)
                    self.assertEqual(target.read_bytes(), content)

    def test_dry_run_never_writes(self):
        target = self.root / "absent" / "AGENTS.md"
        for options in ((), ("--codex",), ("--project", self.root / "project"),
                        ("--agents-md", target), ("--uninstall", "--agents-md", target)):
            with self.subTest(options=options):
                before = self.snapshot()
                result = self.install(*options, "--dry-run")
                self.assertTrue(result.stdout.splitlines())
                self.assertTrue(all(line.startswith("would:") for line in result.stdout.splitlines()))
                self.assertEqual(self.snapshot(), before)
        self.install()
        for options in (("--force",), ("--uninstall",)):
            before = self.snapshot()
            result = self.install(*options, "--dry-run")
            self.assertTrue(all(line.startswith("would:") for line in result.stdout.splitlines()))
            self.assertEqual(self.snapshot(), before)

    def test_invalid_arguments_are_usage_errors(self):
        for options in (("--unknown",), ("--agents-md",), ("--project",),
                        ("--project", "--dry-run"), ("--agents-md", "--force"),
                        ("--claude", "--codex"), ("--codex", "--project", "project"),
                        ("--agents-md", "AGENTS.md", "--project", "project")):
            with self.subTest(options=options):
                before = self.snapshot()
                self.install(*options, expected=1)
                self.assertEqual(self.snapshot(), before)

    def test_help_does_not_write(self):
        before = self.snapshot()
        self.assertIn("Usage:", self.install("--help").stdout)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
