"""Exercise the runner mirror-list correction without touching system apt state."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("ci_apt_mirror", Path(__file__).resolve().parents[2] / "tools/ci_apt_mirror.py")
mirror = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mirror)


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "apt-mirrors.txt"

    def test_hosted_runner_mirror_failover_and_idempotence(self):
        remaining = "https://archive.ubuntu.com/ubuntu/\tpriority:2\nhttps://security.ubuntu.com/ubuntu/\tpriority:3\n"
        self.path.write_text("http://azure.archive.ubuntu.com/ubuntu/\tpriority:1\n" + remaining)
        mirror.configure(self.path)
        self.assertEqual(self.path.read_text(), remaining)
        mirror.configure(self.path)
        self.assertEqual(self.path.read_text(), remaining)

    def test_unknown_mirror_list_fails_without_mutation(self):
        original = "http://azure.archive.ubuntu.com/ubuntu/\tpriority:1\nhttps://unrelated.example/ubuntu/\n"
        self.path.write_text(original)
        with self.assertRaisesRegex(ValueError, "expected Canonical HTTPS archive"):
            mirror.configure(self.path)
        self.assertEqual(self.path.read_text(), original)

    def test_preserves_comments_and_unrelated_entries(self):
        original = "# mirror note\n\nhttps://archive.ubuntu.com/ubuntu/\tpriority:2\nhttps://example.org/ubuntu/\tpriority:9\n"
        self.path.write_text(original)
        mirror.configure(self.path)
        self.assertEqual(self.path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
