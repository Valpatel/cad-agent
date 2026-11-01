"""The review-packet pictures on the site (docs/img/packets, made by tools/site-packet-pictures.py) stay tied to the run
that drew them: the folder holds exactly the planned pictures, SOURCE.json records each one, the clean bench passed
every gate with the counts the review site's snapshot shows, each seed failed its own gate, and every caption on a
seeded picture says it is seeded and names the seed. No CAD kernel: the bench's seeds are read from its source."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "packets"
BENCH = ROOT / "tests" / "fixtures" / "gate_bench"


def _tool():
    spec = importlib.util.spec_from_file_location("site_packet_pictures", ROOT / "tools" / "site-packet-pictures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                     # imports nothing heavy at module level
    return mod


def _seeds() -> dict:
    """The bench's SEEDS, read as a literal from build.py (importing it needs CadQuery)."""
    tree = ast.parse((BENCH / "build.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "SEEDS":
            return ast.literal_eval(node.value)
    raise AssertionError("tests/fixtures/gate_bench/build.py has no SEEDS")


def _source() -> dict:
    return json.loads((OUT / "SOURCE.json").read_text())


def _figures():
    """(page, figure) for every figure on the site that shows a packet picture. YAML reads the key `on` as True."""
    for page, spec in yaml.safe_load((ROOT / "docs" / "pages.yaml").read_text()).items():
        if isinstance(spec, dict):
            for f in [*(spec.get("figures") or []), *([spec["hero"]] if spec.get("hero") else [])]:
                if str(f.get("img", "")).startswith("docs/img/packets/"):
                    yield page, f


def test_the_folder_holds_exactly_the_planned_pictures_and_each_is_recorded():
    tool = _tool()
    planned = tool.planned()
    assert len(planned) == len(set(planned))
    assert sorted(p.name for p in OUT.glob("*.webp")) == sorted(planned)
    src = _source()
    assert sorted(src["pictures"]) == sorted(planned)
    assert sorted(src["scenarios"]) == sorted(tool.SCENARIOS)
    for name, rec in src["pictures"].items():
        assert tool.picture_name(rec["scenario"], rec["section"], rec["view"]) == name
        assert rec["view"] in tool.SCENARIOS[rec["scenario"]]["views"][rec["section"]]
        assert rec["caption"] and rec["section_hash"]
        assert bool(rec["findings"]) == (rec["view"] == "findings")


def test_the_clean_bench_passed_with_the_review_sites_counts_and_each_seed_failed_its_gate():
    seeds, src = _seeds(), _source()
    snapshot = {f.stem: json.loads(f.read_text()) for f in (BENCH / "site_snapshot" / "gates").glob("*.json")}
    clean = src["scenarios"]["clean"]
    assert clean["seed"] is None and clean["gates"]
    assert set(clean["gates"]) == set(snapshot)
    for gate, v in clean["gates"].items():
        assert v["status"] == "pass" and not v["findings"], gate
        assert v["counts"] == snapshot[gate]["counts"], f"{gate}: the pictures and the review site's snapshot differ"
    for name, sc in src["scenarios"].items():
        if sc["seed"] is None:
            continue
        seed = seeds[sc["seed"]]
        assert (sc["what"], sc["seeded_gate"]) == (seed["what"], seed["gate"]), name
        assert sc["gates"][seed["gate"]]["status"] == "fail", f"{name}: the seed did not fail its own gate"


def test_a_seeded_picture_says_so_and_names_its_seed():
    src = _source()
    seen = set()
    for page, f in _figures():
        name = f["img"].removeprefix("docs/img/packets/")
        assert name in src["pictures"], f"{page}: {name} is not a recorded packet picture"
        seen.add(name)
        seed = src["scenarios"][src["pictures"][name]["scenario"]]["seed"]
        assert f[True] == "fixture", f"{page}: {name} is the gate bench, a test fixture"
        if seed:
            assert "seeded" in f["caption"].lower() and seed in f["caption"], f"{page}: {name} shows the {seed} seed"
        else:
            assert "seeded failure" not in f["caption"].lower(), f"{page}: {name} is the bench as built"
    assert seen, "no page shows a packet picture"


def test_the_record_names_no_local_path():
    text = (OUT / "SOURCE.json").read_text()
    for marker in ("/home/", "/Users/", "/tmp/", "C:\\\\"):
        assert marker not in text
