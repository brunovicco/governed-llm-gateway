import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.secret_scan import ROOT, SecretScanError, committable_paths, main, scan_file

FAKE_OPENAI_KEY = "sk-" + "A1b2C3d4E5f6G7h8I9j0"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ("git", *args),
        cwd=cwd,
        check=True,
        capture_output=True,
    )


class CommittableEnumerationTests(unittest.TestCase):
    def test_ignored_files_are_never_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _git(root, "init", "--quiet")
            (root / ".gitignore").write_text(".env\nnode_modules/\n", encoding="utf-8")
            (root / ".env").write_text(f"OPENAI_API_KEY={FAKE_OPENAI_KEY}\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "vendored.js").write_text(FAKE_OPENAI_KEY, encoding="utf-8")
            _git(root, "add", ".gitignore")

            names = {path.name for path in committable_paths(root)}

        self.assertIn(".gitignore", names)
        self.assertNotIn(".env", names)
        self.assertNotIn("vendored.js", names)

    def test_tracked_and_unignored_untracked_files_are_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _git(root, "init", "--quiet")
            (root / "tracked.py").write_text("value = 1\n", encoding="utf-8")
            _git(root, "add", "tracked.py")
            (root / "staged_next.py").write_text("value = 2\n", encoding="utf-8")

            names = {path.name for path in committable_paths(root)}

        self.assertEqual(names, {"tracked.py", "staged_next.py"})

    def test_enumeration_fails_closed_outside_a_git_working_tree(self) -> None:
        with (
            tempfile.TemporaryDirectory() as raw,
            self.assertRaises(SecretScanError),
        ):
            committable_paths(Path(raw))

    def test_deleted_index_entries_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _git(root, "init", "--quiet")
            (root / "gone.py").write_text("value = 1\n", encoding="utf-8")
            _git(root, "add", "gone.py")
            (root / "gone.py").unlink()

            self.assertEqual(committable_paths(root), ())


class SecretPatternTests(unittest.TestCase):
    def test_reports_pattern_name_and_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "config.py"
            path.write_text(f"first = 1\nsecond = 2\nkey = '{FAKE_OPENAI_KEY}'\n", encoding="utf-8")

            self.assertEqual(scan_file(path), (("OpenAI-style key", 3),))

    def test_detects_each_supported_secret_shape(self) -> None:
        samples = {
            "AWS access key": "AKIA" + "ABCDEFGHIJKLMNOP",
            "private key": "-----BEGIN RSA PRIVATE" + " KEY-----",
            "GitHub token": "ghp_" + "A1b2C3d4E5f6G7h8I9j0",
        }
        with tempfile.TemporaryDirectory() as raw:
            for name, sample in samples.items():
                path = Path(raw) / f"{name.replace(' ', '_')}.txt"
                path.write_text(sample, encoding="utf-8")
                self.assertEqual(scan_file(path), ((name, 1),))

    def test_binary_and_oversized_files_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            binary = Path(raw) / "blob.bin"
            binary.write_bytes(b"\xff\xfe" + FAKE_OPENAI_KEY.encode("utf-8"))

            self.assertEqual(scan_file(binary), ())

    def test_clean_file_reports_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "clean.py"
            path.write_text("workload = 'rag.answer'\n", encoding="utf-8")

            self.assertEqual(scan_file(path), ())


class RepositoryScanTests(unittest.TestCase):
    def test_repository_has_no_committable_secrets(self) -> None:
        self.assertEqual(main(), 0)

    def test_repository_candidate_set_excludes_ignored_paths(self) -> None:
        relative = {path.relative_to(ROOT).as_posix() for path in committable_paths()}

        self.assertIn("scripts/secret_scan.py", relative)
        self.assertNotIn(".env", relative)
        self.assertFalse({name for name in relative if name.startswith(".venv/")})
        self.assertFalse({name for name in relative if "node_modules/" in name})


if __name__ == "__main__":
    unittest.main()
