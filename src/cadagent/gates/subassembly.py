"""Scoped internal plans and rigid insertion; an adapter around the ordinary sequence rules.

No geometry is fused or excluded. A compound relation is the nearest/blocked relation over every member pair.
Tool sweeps expand parent modules back to real part names and always receive the original fastener spec.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from cadagent.gates.assembly import (SequenceWorld, _instances, _plan, direction_vector, normalise_steps,
                                     run_sequence, sweep_pair)
from cadagent.gates.fasteners import FastenerSpec, owner
from cadagent.gates.verdict import Check

ASSUMPTIONS = [
    "Each declared subassembly is assumed rigid at its modelled relative poses. Its internal insertion and tool "
    "sequence is checked separately, without parent obstacles; this does not prove joint strength or rigidity.",
    "Conditional service_after entries assume their listed prerequisites are already removed. The prerequisites' "
    "own removal, tool access, wiring disconnection and harness slack are not verified by that conditional check.",
]


class ScopedWorld(SequenceWorld):
    """A subset/compound view; the underlying geometry and fastener identities are unchanged."""
    def __init__(self, world, names, groups, specs):
        self.world, self.names, self.groups, self.specs = world, list(names), groups, specs
        self.fastener_keys = {sp.instance_key(i) for sp in specs.values() for i in range(len(sp.axes))}

    def members(self, key):
        return self.groups.get(key, [key])

    def kind(self, key):
        return "part" if key in self.groups else ("fastener" if key in self.fastener_keys else self.world.kind(key))

    def box(self, key):
        boxes = [self.world.box(k) for k in self.members(key)]
        return tuple((min if i < 3 else max)(b[i] for b in boxes) for i in range(6))

    def relate_at(self, key, shift, other):
        relations = [self.world.relate_at(k, shift, q) for k in self.members(key) for q in self.members(other)]
        # Unknown is not clear even if another member is known to be clear. Never average member gaps.
        selected = next((r for r in relations if r.state == "unknown"), None)
        selected = selected or next((r for r in relations if r.interferes), None)
        selected = selected or min(relations, key=lambda r: r.gap_mm if r.gap_mm is not None else 0.0)
        return replace(selected, a=key, b=other,
                       witness={**selected.witness, "member_pair": [selected.a, selected.b]})

    def tool(self, spec, i, tool_name, decl, present, step, later=()):
        expand = lambda keys: list(dict.fromkeys(k for name in keys for k in self.members(name)))
        return self.world.tool(self.specs[spec.name], i, tool_name, decl, expand(present), step, expand(later))


def _preflight(world, steps, specs, label):
    """Reject incomplete/ambiguous plans before any geometry result can look qualified."""
    orders = [s["order"] for s in steps]
    if not orders or any(isinstance(o, bool) or not isinstance(o, int) for o in orders) or len(set(orders)) != len(orders):
        raise ValueError(f"{label}: nonempty steps with unique integer orders are required")
    plan = _plan(steps, world.names, {k: world.kind(k) for k in world.names}, specs)
    for key, fitted in plan["fitted"].items():
        if len(fitted) != 1:
            raise ValueError(f"{label}: {key} must be fitted exactly once (got {fitted})")
    for s in steps:
        problems = plan["refs"][s["order"]]["problems"]
        if problems:
            raise ValueError(f"{label}, step {s['order']}: {'; '.join(problems)}")
        if direction_vector(s["direction"]) is None:
            raise ValueError(f"{label}, step {s['order']}: direction is required")
    for name, spec in specs.items():
        at = plan["install"][name]
        if at is None or len(plan["named"][name]) > 1:
            raise ValueError(f"{label}: fastener {name} must be installed exactly once")
        for party in [*spec.stack, spec.into]:
            keys = _instances(plan["parts"], party)
            if not keys or any(plan["first_fit"].get(k, at + 1) > at for k in keys):
                raise ValueError(f"{label}: fastener {name} precedes or cannot resolve {party}")
    return plan


def _prepare(world, steps, fasteners, subassemblies, overlaps, service_after):
    if not isinstance(subassemblies, Mapping) or not subassemblies:
        raise ValueError("subassemblies must be a nonempty mapping")
    specs = ({n: FastenerSpec.coerce(f, n) for n, f in fasteners.items()} if isinstance(fasteners, Mapping)
             else {sp.name: sp for sp in (FastenerSpec.coerce(f) for f in (fasteners or ()))})
    groups, membership, internals = {}, {}, {}
    for name, declaration in subassemblies.items():
        if (not isinstance(name, str) or not name or owner(name) != name or name in world.names or name in specs
                or name in map(owner, world.names)):
            raise ValueError(f"ambiguous subassembly name {name!r}")
        if not isinstance(declaration, Mapping) or set(declaration) != {"members", "steps"}:
            raise ValueError(f"subassembly {name}: declare exactly members and steps (no nested modules)")
        members = declaration["members"]
        if not isinstance(members, (list, tuple)) or not members:
            raise ValueError(f"subassembly {name}: members must be a nonempty list of exact instance keys")
        for key in members:
            if not isinstance(key, str) or key not in world.names:
                raise ValueError(f"subassembly {name}: unknown member {key!r}; use exact geometry keys")
            if key in membership:
                raise ValueError(f"member {key!r} is duplicate or shared by subassemblies")
            membership[key] = name
        groups[name] = list(members)
        if isinstance(declaration["steps"], (str, bytes, Mapping)):
            raise ValueError(f"subassembly {name}: steps must be a sequence")
        internals[name] = normalise_steps(declaration["steps"])
    instance_specs = {}
    for name, spec in specs.items():
        if not spec.axes:
            raise ValueError(f"fastener {name}: no axes declared")
        for i in range(len(spec.axes)):
            key = spec.instance_key(i)
            if key in instance_specs:
                raise ValueError(f"fastener solid {key}: duplicate declaration")
            instance_specs[key] = name
    for key in world.names:
        if world.kind(key) == "fastener" and key not in instance_specs:
            raise ValueError(f"fastener solid {key}: no fastener declaration")
    parts = [k for k in world.names if k not in instance_specs and world.kind(k) != "fastener"]

    def scope(party):
        keys = _instances(parts, party)
        if not keys:
            raise ValueError(f"unknown part reference {party!r}")
        scopes = {membership.get(k) for k in keys}
        if len(scopes) != 1:
            raise ValueError(f"ambiguous part reference {party!r}: instances cross module boundaries")
        return next(iter(scopes))

    internal_specs = {name: {} for name in groups}
    parent_specs = {}
    for name, spec in specs.items():
        scopes = {scope(p) for p in [*spec.stack, spec.into]}
        module = next(iter(scopes)) if len(scopes) == 1 else None
        keys = [spec.instance_key(i) for i in range(len(spec.axes))]
        if module is not None:
            if any(k not in world.names or membership.get(k) != module for k in keys):
                raise ValueError(f"internal fastener {name}: every attached solid must be a member of {module}")
            internal_specs[module][name] = spec
        else:
            if any(k in membership for k in keys):
                raise ValueError(f"external retainer {name} cannot be a member of a module")
            remap = lambda party: scope(party) or party
            stack, into = [remap(p) for p in spec.stack], remap(spec.into)
            if into in stack:
                raise ValueError(f"external fastener {name}: ambiguous clamping across a module boundary")
            parent_specs[name] = replace(spec, clamps=stack[0], stack=stack, into=into)
    for key in membership:
        if key in instance_specs and instance_specs[key] not in internal_specs[membership[key]]:
            raise ValueError(f"member fastener {key} is not installed by that module's internal plan")
    internal_overlaps = {name: [] for name in groups}
    parent_overlaps = []
    for overlap in overlaps:
        if not isinstance(overlap, Mapping):
            raise ValueError("intended overlaps must be mappings with a real pair and an explicit reason")
        pair = overlap.get("parts", [])
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or
                any(not isinstance(k, str) or k in groups for k in pair)):
            raise ValueError("intended overlaps must name real pairs, never a blanket subassembly")
        if not str(overlap.get("reason", "")).strip():
            raise ValueError("intended overlaps require an explicit reason")
        scopes = {membership.get(k, scope(k) if k not in instance_specs else None) for k in pair}
        if len(scopes) != 1:
            raise ValueError("cross-boundary intended overlaps are not supported for rigid module insertion")
        module = next(iter(scopes))
        (internal_overlaps[module] if module else parent_overlaps).append(overlap)
    names = [k for k in world.names if k not in membership] + list(groups)
    parent_world = ScopedWorld(world, names, groups, specs)
    parent_steps = normalise_steps(steps)
    # Parent fit/onto names are units. Retainer parties are remapped only for ordering, never for tool geometry.
    parent_plan = _preflight(parent_world, parent_steps, parent_specs, "parent")
    for name, members in groups.items():
        _preflight(ScopedWorld(world, members, {}, specs), internals[name], internal_specs[name], name)
    if service_after is not None and not isinstance(service_after, Mapping):
        raise ValueError("service_after must map module names to exact removed parent keys")
    service_plans = {}
    for name, removed in (service_after or {}).items():
        if name not in groups or not isinstance(removed, (list, tuple)) or any(not isinstance(k, str) for k in removed):
            raise ValueError("service_after needs a known module and a list of exact removed parent keys")
        if len(set(removed)) != len(removed) or name in removed or any(k not in names for k in removed):
            raise ValueError(f"service_after {name}: duplicate, unknown, ambiguous or target-member prerequisite")
        retainers = [spec.instance_key(i) for spec in parent_specs.values()
                     if name in [*spec.stack, spec.into] for i in range(len(spec.axes))]
        missing = sorted(set(retainers) - set(removed))
        if missing:
            raise ValueError(f"service_after {name}: external retaining fasteners remain: {', '.join(missing)}")
        service_plans[name] = {"assumed_removed": list(removed), "external_retainers": retainers}
    return (specs, groups, internals, internal_specs, internal_overlaps, parent_world, parent_steps,
            parent_specs, parent_overlaps, parent_plan, service_plans)


def run_subassemblies(world, steps, fasteners, *, tools, options, tol, intended_overlaps, service,
                      subassemblies, service_after):
    result = {"checks": [], "steps": [], "exclusions": [], "not_checked": [], "subassemblies": {}, "service_after": {}}
    if not options.tool_access:
        result["checks"].append(Check("subassemblies:declarations", "fail",
                                      "scoped module qualification requires internal and parent tool access checks"))
        return result
    try:
        prepared = _prepare(world, steps, fasteners, subassemblies, list(intended_overlaps), service_after)
    except (ValueError, TypeError) as exc:
        result["checks"].append(Check("subassemblies:declarations", "fail", str(exc)))
        return result
    (specs, groups, internals, internal_specs, internal_overlaps, parent_world, parent_steps,
     parent_specs, parent_overlaps, parent_plan, service_plans) = prepared
    requested = set(groups) if service is True else set([service] if isinstance(service, str) else (service or [])) & set(groups)
    if requested - set(service_plans):
        result["checks"].append(Check("subassemblies:service", "fail",
                                      "module service requires explicit service_after prerequisites",
                                      sorted(requested - set(service_plans))))
        return result
    # Scoped groups require complete internal checks even when ordinary parent options are permissive.
    internal_options = replace(options, tool_access=True, missing_direction="fail")
    for name, members in groups.items():
        internal = run_sequence(ScopedWorld(world, members, {}, specs), internals[name], internal_specs[name],
                                tools=tools, options=internal_options, tol=tol,
                                intended_overlaps=internal_overlaps[name])
        result["subassemblies"][name] = {"members": members, "checks": [c.to_dict() for c in internal["checks"]],
                                         "steps": internal["steps"], "not_checked": internal["not_checked"]}
        result["checks"] += [replace(c, id=f"subassembly:{name}:{c.id}") for c in internal["checks"]]
        complete = all(c.status == "pass" for c in internal["checks"]) and not internal["not_checked"]
        result["checks"].append(Check(f"subassembly:{name}:qualified", "pass" if complete else "fail",
                                      "internal sequence fully checked" if complete else "internal sequence is failed or incomplete",
                                      members))
        result["exclusions"] += [{**e, "scope": name} for e in internal["exclusions"]]
    if any(c.status == "fail" for c in result["checks"]):
        result["not_checked"].append({"what": "parent insertion", "reason": "internal sequence failed or incomplete"})
        return result
    # The ordinary service mode is not a substitute for explicit module prerequisites.
    ordinary_service = ([k for k in parent_world.names if k not in groups] if service is True else
                        [k for k in ([service] if isinstance(service, str) else (service or [])) if k not in groups])
    parent = run_sequence(parent_world, parent_steps, parent_specs, tools=tools, options=options, tol=tol,
                          intended_overlaps=parent_overlaps, service=ordinary_service)
    for key in ("checks", "steps", "exclusions", "not_checked"):
        result[key] += parent[key]
    for row in result["steps"]:
        if row["fit"] in groups:
            row["members"] = groups[row["fit"]]
    for name, evidence in service_plans.items():
        step = next(s for s in parent_steps if s["fit"] == name)
        direction = direction_vector(step["direction"])
        remaining = [k for k in parent_world.names if k != name and k not in evidence["assumed_removed"]]
        paths = [sweep_pair(parent_world, name, direction, other, options=options, tol=tol) for other in remaining]
        blocked = [r for r in paths if r["state"] != "clear"]
        status = "fail" if blocked else "pass"
        evidence = {**evidence, "status": status, "members": groups[name], "remaining": remaining,
                    "withdrawal_direction": [-c for c in direction], "blocked": blocked,
                    "prerequisite_removal_verified": False, "prerequisite_tool_access_verified": False}
        result["service_after"][name] = evidence
        result["checks"].append(Check(f"service_after:{name}", status,
                                      "conditional withdrawal blocked or undecided" if blocked else
                                      "conditional withdrawal clear after the listed prerequisites are already removed",
                                      [name] + [r["part"] for r in blocked], evidence))
    return result
