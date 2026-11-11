"""Exercise the runner correction without touching system apt state."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("ci_apt_mirror", Path(__file__).resolve().parents[2] / "tools/ci/apt_mirror.py")
mirror = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mirror)
SOURCE = """Types: deb
URIs: mirror+file:/etc/apt/apt-mirrors.txt
Suites: noble noble-updates noble-backports noble-security
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
"""
FALLBACKS = "https://archive.ubuntu.com/ubuntu/\tpriority:2\nhttps://security.ubuntu.com/ubuntu/\tpriority:3\n"
ORIGINAL = "http://azure.archive.ubuntu.com/ubuntu/\tpriority:1\n" + FALLBACKS


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "apt-mirrors.txt"
        self.source = Path(self.directory.name) / "ubuntu.sources"
        self.path.write_text(ORIGINAL)
        self.source.write_text(SOURCE)

    def test_hosted_runner_failover_and_idempotence_preserve_sources(self):
        mirror.configure(self.path, self.source)
        self.assertEqual(self.path.read_text(), FALLBACKS)
        mirror.configure(self.path, self.source)
        self.assertEqual(self.path.read_text(), FALLBACKS)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_unknown_mirror_entries_fail_without_mutation(self):
        mutants = [ORIGINAL.replace("priority:1", "priority:99"),
                   ORIGINAL.replace("priority:2", "priority:garbage"),
                   ORIGINAL.replace("priority:3", "priority:2"),
                   ORIGINAL.replace("https://archive.ubuntu.com", "https://other.example"),
                   ORIGINAL + FALLBACKS, ORIGINAL.replace(FALLBACKS, "")]
        for mutant in mutants:
            with self.subTest(mutant=mutant):
                self.path.write_text(mutant)
                with self.assertRaises(ValueError):
                    mirror.configure(self.path, self.source)
                self.assertEqual(self.path.read_text(), mutant)
                self.assertEqual(self.source.read_text(), SOURCE)

    def test_inactive_or_unknown_source_fails_before_mirror_mutation(self):
        mutants = [SOURCE.replace(mirror.MIRROR, mirror.AZURE),
                   SOURCE.replace(mirror.MIRROR, "https://archive.ubuntu.com/ubuntu/"),
                   SOURCE + "Enabled: no\n", "# " + SOURCE.replace("\n", "\n# "),
                   SOURCE.replace("Signed-By:", "Unknown:"),
                   SOURCE.replace("Types: deb", "Types: deb-src"),
                   SOURCE.replace("noble", "jammy"),
                   SOURCE.replace("/usr/share/keyrings/ubuntu-archive-keyring.gpg", "/tmp/other.gpg"),
                   SOURCE + "Enabled: maybe\n",
                   SOURCE.replace("noble-security", "noble-proposed"),
                   SOURCE.replace("main universe", "main main"),
                   SOURCE.replace("noble-security", ""),
                   SOURCE + "Trusted: yes\n"]
        for mutant in mutants:
            with self.subTest(mutant=mutant):
                self.source.write_text(mutant)
                with self.assertRaises(ValueError):
                    mirror.configure(self.path, self.source)
                self.assertEqual(self.path.read_text(), ORIGINAL)
                self.assertEqual(self.source.read_text(), mutant)

    # Canonical cloud-init template at 179c69886be4c8e7e93bf22c34e97bf03e142b22,
    # specialized to noble and the runner-images mirror URI transformation.
    def test_split_producer_stanzas_and_explicit_enabled_are_accepted(self):
        first = SOURCE.replace(" noble-security", "")
        second = SOURCE.replace("noble noble-updates noble-backports noble-security", "noble-security")
        producer = first + "Enabled: yes\n\n" + second
        self.source.write_text(producer)
        mirror.configure(self.path, self.source)
        self.assertEqual(self.path.read_text(), FALLBACKS)
        self.assertEqual(self.source.read_text(), producer)

    def test_runner_release_profile_is_derived_and_rejects_other_images(self):
        release = {"ID": "ubuntu", "VERSION_ID": "24.04", "VERSION_CODENAME": "noble"}
        self.assertEqual(mirror.runner_codename(release), "noble")
        for key, value in [("ID", "debian"), ("VERSION_ID", "22.04"), ("VERSION_CODENAME", "jammy")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                mirror.runner_codename({**release, key: value})

    def test_comments_and_whitespace_preserved(self):
        original = "# mirror note\n\n" + ORIGINAL
        self.path.write_text(original)
        mirror.configure(self.path, self.source)
        self.assertEqual(self.path.read_text(), "# mirror note\n\n" + FALLBACKS)


if __name__ == "__main__":
    unittest.main()
