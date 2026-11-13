"""Exercise the runner correction without touching system apt state."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import http.server
import threading
import subprocess
import shutil
import os
import re
import shlex
import time

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
CORRECTED = ORIGINAL.replace(mirror.AZURE, mirror.PREFERRED)
# Observed verbatim URI/priority order in full job 131436221538, 2026-11-12.
OBSERVED_EC2 = "http://us-east-2.ec2.archive.ubuntu.com/ubuntu/\tpriority:1\n" + FALLBACKS
# Fields captured by the bounded diagnostic in full job 131567345145.
# Comments/blank lines are not a reconstruction of its original source bytes.
OBSERVED_SPLIT_SECURITY = SOURCE.replace(" noble-security", "") + "\n" + SOURCE.replace(
    mirror.MIRROR, "http://security.ubuntu.com/ubuntu").replace(
    "noble noble-updates noble-backports noble-security", "noble-security")


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
        self.assertEqual(self.path.read_text(), CORRECTED)
        mirror.configure(self.path, self.source)
        self.assertEqual(self.path.read_text(), CORRECTED)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_observed_ec2_profile_preserves_sources_and_is_idempotent(self):
        import contextlib
        import io
        self.path.write_text(OBSERVED_EC2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            mirror.configure(self.path, self.source)
        expected = "https://mirror.pilotfiber.com/ubuntu/\tpriority:1\n" + FALLBACKS
        self.assertEqual(self.path.read_text(), expected)
        self.assertEqual(self.source.read_text(), SOURCE)
        self.assertIn("input primary: http://us-east-2.ec2.archive.ubuntu.com/ubuntu/", output.getvalue())
        mirror.configure(self.path, self.source)
        self.assertEqual(self.path.read_text(), expected)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_observed_ec2_comments_and_spacing_are_preserved(self):
        original = "# hosted mirrors\n\n  " + OBSERVED_EC2.replace("\t", "   ")
        expected = original.replace("http://us-east-2.ec2.archive.ubuntu.com/ubuntu/",
                                    "https://mirror.pilotfiber.com/ubuntu/")
        self.path.write_text(original)
        mirror.configure(self.path, self.source)
        self.assertEqual(self.path.read_text(), expected)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_observed_split_security_preserves_source_and_is_idempotent(self):
        for original in (ORIGINAL, OBSERVED_EC2, CORRECTED):
            with self.subTest(primary=original.splitlines()[0]):
                self.path.write_text(original)
                self.source.write_text(OBSERVED_SPLIT_SECURITY)
                mirror.configure(self.path, self.source)
                self.assertEqual(self.path.read_text(), CORRECTED)
                self.assertEqual(self.source.read_text(), OBSERVED_SPLIT_SECURITY)
                mirror.configure(self.path, self.source)
                self.assertEqual(self.path.read_text(), CORRECTED)
                self.assertEqual(self.source.read_text(), OBSERVED_SPLIT_SECURITY)

    def test_split_security_rejects_changed_uri_and_incomplete_or_unsigned_profiles(self):
        uri = "http://security.ubuntu.com/ubuntu"
        source = OBSERVED_SPLIT_SECURITY
        mutants = [source.replace(uri, alternative) for alternative in (
            uri + "/", uri.replace("http:", "https:"), uri + "?x=1", uri + "#fragment",
            uri.replace("security.ubuntu.com", "security.ubuntu.com.evil.example"),
            uri.replace("http://", "http://user@"), uri.replace("/ubuntu", "/other"),
            uri + " " + mirror.MIRROR)]
        mutants += [source.replace("noble-security", "noble-proposed"),
                    source.replace("noble noble-updates noble-backports", "noble noble-updates"),
                    source.replace("noble noble-updates noble-backports", "noble noble-updates noble-backports noble-security"),
                    source.replace("Types: deb", "Types: deb-src"),
                    source.replace("/usr/share/keyrings/ubuntu-archive-keyring.gpg", "/tmp/key.gpg"),
                    source.replace("main universe", "main main"),
                    source + "Trusted: yes\n", source + "Enabled: no\n",
                    source + "\n" + source.split("\n\n")[1],
                    source.replace(mirror.MIRROR, uri),
                    source.replace("noble noble-updates noble-backports", "noble") +
                    "\n" + SOURCE.replace("noble noble-updates noble-backports noble-security", "noble-updates noble-backports")]
        for mutant in mutants:
            with self.subTest(source=mutant):
                self.path.write_text(ORIGINAL)
                self.source.write_text(mutant)
                with self.assertRaises(ValueError):
                    mirror.configure(self.path, self.source)
                self.assertEqual(self.path.read_text(), ORIGINAL)
                self.assertEqual(self.source.read_text(), mutant)

    def test_observed_ec2_is_not_a_wildcard_or_a_mixed_profile(self):
        uri = "http://us-east-2.ec2.archive.ubuntu.com/ubuntu/"
        mutants = [OBSERVED_EC2.replace("us-east-2", "us-east-1"),
                   OBSERVED_EC2.replace(".ubuntu.com/", ".ubuntu.com.evil.example/"),
                   OBSERVED_EC2.replace(uri, uri.replace("http://", "http://user@")),
                   OBSERVED_EC2.replace(uri, uri + "?extra=1"),
                   OBSERVED_EC2.replace(uri, uri.replace("http:", "https:")),
                   OBSERVED_EC2.replace(uri, uri.rstrip("/")),
                   OBSERVED_EC2.replace("priority:1", "priority:99"),
                   OBSERVED_EC2 + ORIGINAL.splitlines(keepends=True)[0],
                   OBSERVED_EC2 + CORRECTED.splitlines(keepends=True)[0],
                   OBSERVED_EC2 + OBSERVED_EC2.splitlines(keepends=True)[0],
                   OBSERVED_EC2.replace(FALLBACKS, "")]
        for mutant in mutants:
            with self.subTest(mutant=mutant):
                self.path.write_text(mutant)
                with self.assertRaises(ValueError):
                    mirror.configure(self.path, self.source)
                self.assertEqual(self.path.read_text(), mutant)
                self.assertEqual(self.source.read_text(), SOURCE)

    def test_observed_ec2_still_requires_complete_signed_active_sources(self):
        for mutant in [SOURCE.replace("noble-security", ""), SOURCE + "Trusted: yes\n",
                       SOURCE.replace("/usr/share/keyrings/ubuntu-archive-keyring.gpg", "/tmp/other.gpg"),
                       SOURCE.replace(mirror.MIRROR, "https://archive.ubuntu.com/ubuntu/")]:
            with self.subTest(source=mutant):
                self.path.write_text(OBSERVED_EC2)
                self.source.write_text(mutant)
                with self.assertRaises(ValueError):
                    mirror.configure(self.path, self.source)
                self.assertEqual(self.path.read_text(), OBSERVED_EC2)
                self.assertEqual(self.source.read_text(), mutant)

    def test_unknown_mirror_entries_fail_without_mutation(self):
        mutants = [ORIGINAL.replace("priority:1", "priority:99"),
                   ORIGINAL.replace("priority:2", "priority:garbage"),
                   ORIGINAL.replace("priority:3", "priority:2"),
                   ORIGINAL.replace("https://archive.ubuntu.com", "https://other.example"),
                   ORIGINAL + FALLBACKS, ORIGINAL.replace(FALLBACKS, ""),
                   CORRECTED.replace("priority:1", "priority:99"),
                   CORRECTED + ORIGINAL.splitlines(keepends=True)[0]]
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

    def test_rejection_reports_actual_profile_without_mutation(self):
        unknown = ORIGINAL.replace("priority:1", "priority:99")
        self.path.write_text(unknown)
        with self.assertRaises(ValueError) as caught:
            mirror.configure(self.path, self.source)
        detail = str(caught.exception)
        self.assertIn('"uri": "http://azure.archive.ubuntu.com/ubuntu/"', detail)
        self.assertIn('"priority": "priority:99"', detail)
        self.assertIn('"line": 3', detail)
        self.assertEqual(self.path.read_text(), unknown)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_rejection_omits_credentials_queries_paths_and_extra_fields(self):
        unknown = "https://alice:private-password@mirror.example/private-path?private-query#private-fragment private-priority private-extra\n" + FALLBACKS
        self.path.write_text(unknown)
        with self.assertRaises(ValueError) as caught:
            mirror.configure(self.path, self.source)
        detail = str(caught.exception)
        for secret in ("alice", "private-password", "private-path", "private-query", "private-fragment", "private-priority", "private-extra"):
            self.assertNotIn(secret, detail)
        self.assertIn('"uri": "https://mirror.example<other-path>"', detail)
        self.assertIn('"fields": 3', detail)
        self.assertEqual(self.path.read_text(), unknown)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_rejection_diagnostics_are_bounded_and_handle_malformed_uris(self):
        self.assertIn("<malformed-uri>", mirror.mirror_profile("https://[bad priority:1\n"))
        import json
        records = json.loads(mirror.mirror_profile("# note\n\n" + ORIGINAL * 20))
        self.assertEqual(len(records), 12)
        self.assertEqual(records[0]["line"], 3)

    def test_source_rejection_records_the_input_without_mutation_or_success(self):
        import contextlib
        import io
        import json
        # Synthetic source, not a claim about the unretained #649 runner file.
        rejected = SOURCE.replace(mirror.MIRROR, "https://archive.ubuntu.com/ubuntu/")
        self.source.write_text(rejected)
        error, output = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(error), contextlib.redirect_stdout(output):
            with self.assertRaises(ValueError) as caught:
                mirror.configure(self.path, self.source)
        self.assertEqual(str(caught.exception), "active Ubuntu source must use the expected mirror file")
        record = json.loads(error.getvalue().split("observed=", 1)[1])
        self.assertEqual(next(x for x in record["fields"] if x["field"] == "uris")["values"],
                         ["https://archive.ubuntu.com/ubuntu/"])
        self.assertEqual(self.path.read_text(), ORIGINAL)
        self.assertEqual(self.source.read_text(), rejected)
        self.assertEqual(output.getvalue(), "")

    def test_source_visibility_does_not_admit_another_mirror_file(self):
        import contextlib
        import io
        rejected = SOURCE.replace(mirror.MIRROR, "mirror+file:/etc/apt/mirrors/ubuntu.list")
        self.source.write_text(rejected)
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(ValueError):
            mirror.configure(self.path, self.source)
        self.assertIn("mirror+file:/etc/apt/mirrors/ubuntu.list", error.getvalue())
        self.assertEqual(self.path.read_text(), ORIGINAL)
        self.assertEqual(self.source.read_text(), rejected)

    def test_source_diagnostic_redacts_credentials_queries_unknown_values_and_paths(self):
        text = SOURCE.replace(mirror.MIRROR,
                              "https://alice:private-password@mirror.example/private-path?private-query#private-fragment")
        text += "Private-field: private-extra\nSigned-By: /tmp/private-keyring\n"
        detail = mirror.source_profile(text)
        for secret in ("alice", "private-password", "private-path", "private-query", "private-fragment",
                       "Private-field", "private-extra", "private-keyring"):
            self.assertNotIn(secret, detail)
        self.assertIn("https://mirror.example<other-path>", detail)
        self.assertIn("<other-field>", detail)
        self.assertNotIn("private-home", mirror.source_profile("URIs: mirror+file:/home/private-home/list\n"))

    def test_source_diagnostic_is_bounded_and_preserves_continuation_shape(self):
        import json
        record = json.loads(mirror.source_profile("URIs: mirror+file:/etc/apt/apt-mirrors.txt\n https://[bad #private\n"))
        self.assertTrue(record["fields"][1]["continuation"])
        self.assertEqual(record["fields"][1]["values"], ["<malformed-uri>", "<malformed-uri>"])
        detail = mirror.source_profile(SOURCE * 100)
        self.assertLessEqual(len(detail), 8000)
        self.assertTrue(json.loads(detail)["truncated"])
        self.assertLessEqual(len(json.loads(detail)["fields"]), 24)

    def test_valid_source_does_not_emit_rejection_evidence(self):
        import contextlib
        import io
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            mirror.configure(self.path, self.source)
        self.assertEqual(error.getvalue(), "")

    # Canonical cloud-init template at 179c69886be4c8e7e93bf22c34e97bf03e142b22,
    # specialized to noble and the runner-images mirror URI transformation.
    def test_split_producer_stanzas_and_explicit_enabled_are_accepted(self):
        first = SOURCE.replace(" noble-security", "")
        second = SOURCE.replace("noble noble-updates noble-backports noble-security", "noble-security")
        producer = first + "Enabled: yes\n\n" + second
        self.source.write_text(producer)
        mirror.configure(self.path, self.source)
        self.assertEqual(self.path.read_text(), CORRECTED)
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
        self.assertEqual(self.path.read_text(), "# mirror note\n\n" + CORRECTED)


@unittest.skipUnless(shutil.which("apt-get"), "requires the existing apt transport; never installs packages")
class TransportTests(unittest.TestCase):
    def test_workflow_transport_reaches_fallback_and_still_rejects_unsigned_metadata(self):
        import pwd  # this test is skipped on platforms without apt
        requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.server.stall, self.path))
                if self.server.stall:
                    time.sleep(20)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"not-signed-metadata\n")

            def log_message(self, *args):
                pass

        servers = []
        try:
            for stall in (True, False):
                server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                server.stall = stall
                threading.Thread(target=server.serve_forever, daemon=True).start()
                servers.append(server)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "lists/partial").mkdir(parents=True)
                (root / "cache").mkdir()
                mirrors = root / "mirrors.txt"
                mirrors.write_text("".join(f"http://127.0.0.1:{server.server_port}/\tpriority:{i + 1}\n"
                                           for i, server in enumerate(servers)))
                source = root / "source.list"
                source.write_text(f"deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] mirror+file:{mirrors} control main\n")
                workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
                options = shlex.split(re.search(r"apt_options=\(([^)]*)\)", workflow)[1])
                # All state/cache/source paths are temporary; this only downloads loopback index metadata.
                command = ["apt-get", "-o", f"Dir::Etc::sourcelist={source}", "-o", "Dir::Etc::sourceparts=-",
                           "-o", f"Dir::State::lists={root}/lists", "-o", f"Dir::Cache={root}/cache",
                           "-o", f"APT::Sandbox::User={pwd.getpwuid(os.getuid()).pw_name}",
                           "-o", "Acquire::http::Proxy::127.0.0.1=DIRECT",
                           *options, "update"]
                result = subprocess.run(command, text=True, capture_output=True, timeout=25)
                self.assertTrue(any(not stalled for stalled, _ in requests), result.stdout + result.stderr)
                self.assertEqual(result.returncode, 100, result.stdout + result.stderr)
                self.assertIn("not signed", result.stderr)
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
