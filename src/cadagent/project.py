"""The ``cad:`` section of a project's ``cad-agent.yaml``.

``cad-agent.yaml`` at the project root is the config; without one, the error
names any other YAML file there that has a ``cad:`` section. Example (see
``docs/toolkit.md`` for every field)::

    cad:
      name: my-enclosure
      title: My enclosure
      revision_from: cad/parameters.json:revision
      printer: {name: My printer, bed_mm: [256, 256, 256]}
      steps:
        - {name: build, run: cad/build.py, log: build.log}
        - {name: clearances, run: tools/check_clearances.py, needs: [build]}
      checks:
        - {id: clearances, title: Clearances, file: exports/clearances.json}
      dossier: dossier/project.yaml       # optional: the design dossier (docs/dossier.md)
      gates: {jobs: 2}                    # optional: how `cad-agent gates` runs (docs/gates.md "Running the gates")

Only ``cad:`` is read: other top-level sections are ignored, so the file can carry
other tools' settings too. Unknown keys inside ``cad:`` are kept in ``CadProject.unknown_keys``
so a typo is reportable instead of fatal.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

CONFIG_NAME = "cad-agent.yaml"

class CadConfigError(ValueError):
    """The ``cad:`` section is missing or malformed."""

@dataclass
class Step:
    name: str
    run: str
    log: Optional[str] = None
    timeout_s: int = 1800
    needs: List[str] = field(default_factory=list)

@dataclass
class Check:
    id: str
    title: str
    file: str
    pass_key: Union[str, List[str]] = "pass"
    evidence: List[str] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)

    @property
    def pass_keys(self) -> List[str]:
        return [self.pass_key] if isinstance(self.pass_key, str) else list(self.pass_key)

@dataclass
class Printer:
    name: str = ""
    bed_mm: Optional[Tuple[float, float, float]] = None

@dataclass
class PackageSpec:
    name: str = ""
    include: List[str] = field(default_factory=list)

@dataclass
class ServeSpec:
    host: str = "127.0.0.1"
    port: int = 0

@dataclass
class CadProject:
    root: Path
    name: str
    title: str = ""
    revision: str = ""
    revision_from: str = ""
    python: str = ""
    exports_dir: Path = Path("exports")
    preview_dir: Path = Path("preview")
    docs_dir: Path = Path("docs")
    steps: List[Step] = field(default_factory=list)
    parts_file: Path = Path("exports/geometry-checks.json")
    part_ids: Dict[str, str] = field(default_factory=dict)
    checks: List[Check] = field(default_factory=list)
    printer: Printer = field(default_factory=Printer)
    package: PackageSpec = field(default_factory=PackageSpec)
    serve: ServeSpec = field(default_factory=ServeSpec)
    html_pages: List[str] = field(default_factory=list)
    site: Dict[str, Any] = field(default_factory=dict)
    view: Dict[str, Any] = field(default_factory=dict)
    holes: Dict[str, Any] = field(default_factory=dict)
    slicer: Dict[str, Any] = field(default_factory=dict)
    explore: Dict[str, Any] = field(default_factory=dict)
    release: Dict[str, Any] = field(default_factory=dict)   # `cad-agent release` settings (cadagent.publish.release)
    dossier: Optional[Path] = None     # dossier/project.yaml, loaded by cadagent.review.dossier.load_project_dossier
    gates: Optional[Dict[str, Any]] = None   # `cad-agent gates` settings (cadagent.review.gates.run); None when absent
    unknown_keys: List[str] = field(default_factory=list)

    def resolve_revision(self) -> Optional[str]:
        """The literal ``revision``, else the value ``revision_from`` points at.

        None when ``revision_from`` names a file that does not exist yet (before
        the first build) or a key that is absent; callers show it as unknown.
        """
        if self.revision:
            return self.revision
        if not self.revision_from:
            return None
        path, key = _split_revision_from(self.revision_from)
        try:
            data = json.loads((self.root / path).read_text())
        except (OSError, json.JSONDecodeError):
            return None
        found, value = lookup(data, key)
        return str(value) if found else None

    def step(self, name: str) -> Step:
        for s in self.steps:
            if s.name == name:
                return s
        raise CadConfigError(f"no step named {name!r}; steps: {[s.name for s in self.steps]}")

    def part_label(self, part: str) -> str:
        pid = self.part_ids.get(part)
        pretty = part.replace("_", " ")
        return f"{pid} · {pretty}" if pid else pretty

def lookup(data: Any, dotted: str) -> Tuple[bool, Any]:
    """``(found, value)`` for a dotted key path into nested dicts."""
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node

def _split_revision_from(spec: str) -> Tuple[str, str]:
    path, sep, key = spec.rpartition(":")
    if not sep or not path or not key:
        raise CadConfigError(
            f"revision_from must be 'path/to/file.json:dotted.key', got {spec!r}"
        )
    return path, key

_TOP_KEYS = {
    "name", "title", "revision", "revision_from", "python", "exports_dir",
    "preview_dir", "docs_dir", "steps", "parts_file", "part_ids", "checks",
    "printer", "package", "serve", "html_pages", "site", "view", "holes", "slicer", "explore",
    "dossier", "gates", "release",
}

def _require_dict(value: Any, where: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CadConfigError(f"{where} must be a mapping, got {type(value).__name__}")
    return value

def _require_list(value: Any, where: str) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CadConfigError(f"{where} must be a list, got {type(value).__name__}")
    return value

def _parse_steps(raw: Any) -> List[Step]:
    steps: List[Step] = []
    seen: set = set()
    for i, item in enumerate(_require_list(raw, "cad.steps")):
        item = _require_dict(item, f"cad.steps[{i}]")
        if not item.get("name") or not item.get("run"):
            raise CadConfigError(f"cad.steps[{i}] needs both 'name' and 'run'")
        name = str(item["name"])
        if name in seen:
            raise CadConfigError(f"cad.steps: duplicate step name {name!r}")
        needs = [str(n) for n in _require_list(item.get("needs"), f"cad.steps[{i}].needs")]
        for n in needs:
            if n not in seen:
                raise CadConfigError(
                    f"cad.steps[{i}] ({name}) needs {n!r}, which is not an earlier step"
                )
        seen.add(name)
        steps.append(Step(
            name=name,
            run=str(item["run"]),
            log=str(item["log"]) if item.get("log") else None,
            timeout_s=int(item.get("timeout_s", 1800)),
            needs=needs,
        ))
    return steps

def _parse_checks(raw: Any) -> List[Check]:
    checks: List[Check] = []
    for i, item in enumerate(_require_list(raw, "cad.checks")):
        item = _require_dict(item, f"cad.checks[{i}]")
        if not item.get("id") or not item.get("file"):
            raise CadConfigError(f"cad.checks[{i}] needs both 'id' and 'file'")
        pass_key = item.get("pass_key", "pass")
        if isinstance(pass_key, list):
            pass_key = [str(k) for k in pass_key]
            if not pass_key:
                raise CadConfigError(f"cad.checks[{i}].pass_key list is empty")
        else:
            pass_key = str(pass_key)
        links = []
        for j, link in enumerate(_require_list(item.get("links"), f"cad.checks[{i}].links")):
            if isinstance(link, str):
                link = {"url": link}
            link = _require_dict(link, f"cad.checks[{i}].links[{j}]")
            if not link.get("url"):
                raise CadConfigError(f"cad.checks[{i}].links[{j}] needs 'url'")
            links.append({"url": str(link["url"]), "label": str(link.get("label", link["url"]))})
        checks.append(Check(
            id=str(item["id"]),
            title=str(item.get("title") or item["id"]),
            file=str(item["file"]),
            pass_key=pass_key,
            evidence=[str(e) for e in _require_list(item.get("evidence"), f"cad.checks[{i}].evidence")],
            links=links,
        ))
    return checks

def _parse_printer(raw: Any) -> Printer:
    raw = _require_dict(raw, "cad.printer")
    bed = raw.get("bed_mm")
    if bed is not None:
        bed = _require_list(bed, "cad.printer.bed_mm")
        if len(bed) not in (2, 3):
            raise CadConfigError("cad.printer.bed_mm must be [x, y] or [x, y, z]")
        bed = tuple(float(v) for v in bed)
    return Printer(name=str(raw.get("name", "")), bed_mm=bed)

def _default_python(root: Path) -> str:
    venv = root / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable

def from_dict(root: Path, data: Dict[str, Any]) -> CadProject:
    """Build a ``CadProject`` from an already-parsed ``cad:`` mapping."""
    root = Path(root).resolve()
    data = _require_dict(data, "cad")
    if data.get("revision_from"):
        _split_revision_from(str(data["revision_from"]))
    python = data.get("python")
    if python:
        p = Path(str(python))
        python = str(p if p.is_absolute() or "/" not in str(python) else root / p)
    package = _require_dict(data.get("package"), "cad.package")
    serve = _require_dict(data.get("serve"), "cad.serve")
    exports_dir = root / str(data.get("exports_dir", "exports"))
    return CadProject(
        root=root,
        name=str(data.get("name") or root.name),
        title=str(data.get("title") or data.get("name") or root.name),
        revision=str(data.get("revision") or ""),
        revision_from=str(data.get("revision_from") or ""),
        python=python or _default_python(root),
        exports_dir=exports_dir,
        preview_dir=root / str(data.get("preview_dir", "preview")),
        docs_dir=root / str(data.get("docs_dir", "docs")),
        steps=_parse_steps(data.get("steps")),
        parts_file=root / str(data.get("parts_file") or Path(str(data.get("exports_dir", "exports"))) / "geometry-checks.json"),
        part_ids={str(k): str(v) for k, v in _require_dict(data.get("part_ids"), "cad.part_ids").items()},
        checks=_parse_checks(data.get("checks")),
        printer=_parse_printer(data.get("printer")),
        package=PackageSpec(
            name=str(package.get("name", "")),
            include=[str(g) for g in _require_list(package.get("include"), "cad.package.include")],
        ),
        serve=ServeSpec(host=str(serve.get("host", "127.0.0.1")), port=int(serve.get("port", 0))),
        html_pages=[str(p) for p in _require_list(data.get("html_pages"), "cad.html_pages")],
        site=_require_dict(data.get("site"), "cad.site"),
        view=_require_dict(data.get("view"), "cad.view"),
        holes=_require_dict(data.get("holes"), "cad.holes"),
        slicer=_require_dict(data.get("slicer"), "cad.slicer"),
        explore=_require_dict(data.get("explore"), "cad.explore"),
        release=_require_dict(data.get("release"), "cad.release"),
        dossier=root / str(data["dossier"]) if data.get("dossier") else None,
        gates=_require_dict(data.get("gates"), "cad.gates") if "gates" in data else None,
        unknown_keys=sorted(set(data) - _TOP_KEYS),
    )

def find_config(root: Path) -> Optional[Path]:
    """``<root>/cad-agent.yaml`` if it is a file, else None."""
    config = root / CONFIG_NAME
    return config if config.is_file() else None

def other_cad_configs(root: Path) -> List[str]:
    """Names of the other ``*.yaml`` / ``*.yml`` files in ``root`` with a top-level ``cad:`` key, sorted.

    They are never read as the config. The not-found error names them, so a project whose ``cad:`` section
    sits in a file under another name learns to rename it to ``cad-agent.yaml``."""
    names = []
    for path in sorted(root.glob("*.y*ml")):
        if path.name == CONFIG_NAME or path.suffix not in (".yaml", ".yml") or not path.is_file():
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if re.search(r"^cad:", text, re.MULTILINE):
            names.append(path.name)
    return names

def load_project(root: Union[str, Path, None] = None) -> CadProject:
    """Read the ``cad:`` section of ``<root>/cad-agent.yaml`` (root defaults to cwd)."""
    root = Path(root or Path.cwd()).resolve()
    config = find_config(root)
    if config is None:
        others = other_cad_configs(root)
        hint = (f"; {', '.join(others)} {'has' if len(others) == 1 else 'have'} a cad: section but only "
                f"{CONFIG_NAME} is read: rename it to {CONFIG_NAME}") if others else ""
        raise CadConfigError(
            f"{CONFIG_NAME} not found in {root}; a CAD project needs one with a cad: section{hint}"
        )
    try:
        import yaml
    except ImportError as exc:
        raise CadConfigError(
            f"reading the nested cad: section needs PyYAML ({exc}); pip install pyyaml"
        ) from exc
    try:
        data = yaml.safe_load(config.read_text()) or {}
    except yaml.YAMLError as exc:
        raise CadConfigError(f"{config}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict) or "cad" not in data:
        raise CadConfigError(f"{config} has no cad: section")
    return from_dict(root, data["cad"])
