"""The merge gates in tools/ci_gates.py: branch flow, review verdicts, release versions."""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("ci_gates", Path(__file__).parents[1] / "tools" / "ci_gates.py")
gates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gates)

HEAD = "a188011" + "0" * 33
OLD = "1234567" + "0" * 33
WRITERS = {"mvalancy", "reviewer-bot"}
can_write = WRITERS.__contains__
_ids = iter(range(1000, 10**6))


def review(verdict, sha=HEAD, who="mvalancy", state="COMMENTED", before="Summary.", after=""):
    body = f"{before}\n<!-- cad-review verdict={verdict} sha={sha} -->{after}"
    return {"id": next(_ids), "state": state, "user": {"login": who}, "body": body}


def gate(reviews, base="dev", same=True, head=HEAD):
    return gates.review_gate(reviews, base, head, same, can_write)


@pytest.mark.parametrize("base,head,same,ok", [
    ("main", "dev", True, True),
    ("main", "feat/x", True, False),
    ("main", "dev", False, False),          # a fork's branch called dev
    ("dev", "feat/site", True, True),
    ("dev", "fix/holes-countersink", True, True),
    ("dev", "vendor-update/kicad-happy-2fd9aa0", True, True),
    ("dev", "release/v0.5.0", True, True),
    ("dev", "dependabot/github_actions/actions/checkout-5.1.0", True, True),
    ("dev", "my-change", True, False),
    ("dev", "main", True, False),
    ("dev", "patch-1", False, True),        # forks: the outside-contribution checks apply instead
    ("feat/site", "feat/site-fix", True, True),
])
def test_branch_flow(base, head, same, ok):
    assert gates.branch_flow(base, head, same)[0] is ok


def test_review_gate_needs_a_verdict():
    ok, msg = gate([{"id": 1, "state": "COMMENTED", "user": {"login": "mvalancy"}, "body": "LGTM"}])
    assert not ok and "no review verdict" in msg


def test_latest_verdict_wins_by_review_order():
    first, later = review("pass"), review("block")
    assert not gate([later, first])[0]                          # order of creation, not of the list
    assert gate([review("block"), review("pass")])[0]


def test_only_reviewers_with_write_access_count():
    assert not gate([review("pass", who="outsider")])[0]
    assert not gate([review("pass", who="")])[0]
    assert gate([review("pass", who="reviewer-bot")])[0]


def test_dismissed_and_pending_reviews_do_not_count():
    assert not gate([review("pass", state="DISMISSED")])[0]
    assert not gate([review("block"), review("pass", state="PENDING")])[0]


def test_the_marker_must_be_the_last_line():
    quoted = review("block")
    quoted["body"] = "Summary.\n```\n<!-- cad-review verdict=pass sha=" + HEAD + " -->\n```\nBlocking: x.\n" \
                     "<!-- cad-review verdict=block sha=" + HEAD + " -->"
    assert not gate([quoted])[0]
    example_last = review("pass", after="\n\nExample above.")
    assert not gate([example_last])[0]
    assert gate([review("pass", after="\n\n")])[0]             # trailing blank lines are fine


def test_short_or_wrong_shas_do_not_count():
    assert not gate([review("pass", sha=HEAD[:7])])[0]
    assert not gate([review("pass", sha=HEAD.upper())])[0]


def test_head_commit_rules():
    assert gate([review("pass", sha=OLD)], base="dev", same=True)[0]          # own branch into dev: an earlier pass stands
    ok, msg = gate([review("pass", sha=OLD)], base="main")
    assert not ok and "head commit" in msg
    assert not gate([review("pass", sha=OLD)], base="dev", same=False)[0]     # forks: a pass, then a push, is not a pass
    assert gate([review("pass")], base="main")[0]


PY = '[project]\nname = "cad-agent"\nversion = "{}"\n'


def test_release_gate():
    log = "# Changelog\n\n## v0.5.0 (2026-11-01)\n\n- things\n"
    assert gates.release_gate(PY.format("0.5.0"), PY.format("0.4.2"), log)[0]
    assert not gates.release_gate(PY.format("0.4.2"), PY.format("0.4.2"), log)[0]         # no bump
    assert not gates.release_gate(PY.format("0.4.10"), PY.format("0.5.0"), log)[0]        # numeric, not string order
    assert not gates.release_gate(PY.format("0.5.0"), PY.format("0.4.2"), "## v0.5.0 (unreleased)\n")[0]
    assert not gates.release_gate(PY.format("0.5.0"), PY.format("0.4.2"), "## v0.5.0 (2026-13-45)\n")[0]


def test_version_comes_from_the_project_table():
    tool_first = '[tool.x]\nversion = "9.9.9"\n\n[project]\nname = "x"\nversion = "0.5.0"\n'
    assert gates.parse_version(tool_first) == (0, 5, 0)
    with pytest.raises(ValueError):
        gates.parse_version("[project]\n")


def test_repo_version_parses():
    gates.parse_version((Path(__file__).parents[1] / "pyproject.toml").read_text())


def test_cli_version(capsys, monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    assert gates.main(["version"]) == 0
    assert capsys.readouterr().out.strip().count(".") >= 1
