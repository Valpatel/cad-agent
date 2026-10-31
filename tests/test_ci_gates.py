"""The merge gates in tools/ci_gates.py: branch flow, review verdicts, release versions."""
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("ci_gates", Path(__file__).parents[1] / "tools" / "ci_gates.py")
gates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gates)

HEAD = "a188011" + "0" * 33


def review(verdict, sha=HEAD, when="2026-10-31T20:00:00Z", who="OWNER", extra=""):
    return {"author_association": who, "submitted_at": when,
            "body": f"Summary.{extra}\n<!-- cad-review verdict={verdict} sha={sha} -->"}


@pytest.mark.parametrize("base,head,same,ok", [
    ("main", "dev", True, True),
    ("main", "feat/x", True, False),
    ("main", "dev", False, False),          # a fork's branch called dev
    ("dev", "feat/site", True, True),
    ("dev", "fix/holes-countersink", True, True),
    ("dev", "vendor-update/kicad-happy-2fd9aa0", True, True),
    ("dev", "release/v0.5.0", True, True),
    ("dev", "my-change", True, False),
    ("dev", "main", True, False),
    ("dev", "patch-1", False, True),        # forks: the outside-contribution checks apply instead
    ("feat/site", "feat/site-fix", True, True),
])
def test_branch_flow(base, head, same, ok):
    assert gates.branch_flow(base, head, same)[0] is ok


def test_review_gate_needs_a_verdict():
    ok, msg = gates.review_gate([{"author_association": "OWNER", "submitted_at": "x", "body": "LGTM"}], "dev", HEAD)
    assert not ok and "no review verdict" in msg


def test_latest_verdict_wins():
    first, later = "2026-10-31T10:00:00Z", "2026-10-31T12:00:00Z"
    assert not gates.review_gate([review("pass", when=first), review("block", when=later)], "dev", HEAD)[0]
    assert gates.review_gate([review("block", when=first), review("pass", when=later)], "dev", HEAD)[0]


def test_untrusted_reviews_do_not_count():
    assert not gates.review_gate([review("pass", who="NONE"), review("pass", who="CONTRIBUTOR")], "dev", HEAD)[0]
    assert not gates.review_gate([review("pass", who="FIRST_TIME_CONTRIBUTOR")], "dev", HEAD)[0]


def test_release_prs_need_a_pass_on_the_head_commit():
    old = "1234567" + "0" * 33
    assert gates.review_gate([review("pass", sha=old)], "dev", HEAD)[0]           # dev: stale pass is enough
    ok, msg = gates.review_gate([review("pass", sha=old)], "main", HEAD)
    assert not ok and "head commit" in msg
    assert gates.review_gate([review("pass", sha=HEAD[:7])], "main", HEAD)[0]      # short sha accepted


def test_quoted_marker_in_a_later_line_is_the_one_that_counts():
    body = review("pass")["body"] + "\n<!-- cad-review verdict=block sha=" + HEAD + " -->"
    assert not gates.review_gate([{"author_association": "OWNER", "submitted_at": "t", "body": body}], "dev", HEAD)[0]


PY = 'name = "cad-agent"\nversion = "{}"\n'


def test_release_gate():
    log = "# Changelog\n\n## v0.5.0 (2026-11-01)\n\n- things\n"
    assert gates.release_gate(PY.format("0.5.0"), PY.format("0.4.2"), log)[0]
    assert not gates.release_gate(PY.format("0.4.2"), PY.format("0.4.2"), log)[0]         # no bump
    assert not gates.release_gate(PY.format("0.4.10"), PY.format("0.5.0"), log)[0]        # numeric, not string order
    assert not gates.release_gate(PY.format("0.5.0"), PY.format("0.4.2"), "## v0.5.0 (unreleased)\n")[0]
    with pytest.raises(ValueError):
        gates.parse_version("[project]\n")


def test_cli_reads_the_event(tmp_path, monkeypatch, capsys):
    event = {"pull_request": {"number": 1, "base": {"ref": "dev", "repo": {"full_name": "o/r"}},
                              "head": {"ref": "my-change", "sha": HEAD, "repo": {"full_name": "o/r"}}}}
    (tmp_path / "event.json").write_text(json.dumps(event))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))
    assert gates.main(["branch-flow"]) == 1
    assert capsys.readouterr().out.startswith("FAIL")


def test_repo_version_parses():
    gates.parse_version((Path(__file__).parents[1] / "pyproject.toml").read_text())
