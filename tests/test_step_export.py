"""Reproducible STEP export: ``cadagent.geometry.export_step`` and ``step_timestamp`` (#91), and assemblies (#150).

The time-stamp tests need no CAD kernel, so they run in the core CI job; the export tests need CadQuery (OCP) and
skip without it. Shapes are kept tiny.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from cadagent import geometry


# ----------------------------------------------------------------------------------- the header time stamp

def test_the_time_stamp_is_a_fixed_date_without_source_date_epoch(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    assert geometry.step_timestamp() == geometry.STEP_DATE == "2000-01-01T00:00:00"
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "")                    # set but empty counts as unset
    assert geometry.step_timestamp() == geometry.STEP_DATE


def test_the_time_stamp_follows_source_date_epoch_in_utc(monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")                # the local zone must not matter
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        assert geometry.step_timestamp() == "2023-11-14T22:13:20"
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
        assert geometry.step_timestamp() == "1970-01-01T00:00:00"
    finally:
        monkeypatch.undo()
        if hasattr(time, "tzset"):
            time.tzset()


@pytest.mark.parametrize("bad", ["-1", "1.5", "1e9", "soon", "１２", "99999999999999999999"])
def test_a_malformed_source_date_epoch_is_an_error_not_ignored(monkeypatch, bad):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", bad)
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH"):
        geometry.step_timestamp()


# ----------------------------------------------------------------------------------- export_step (CadQuery)

@pytest.fixture
def cq(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    return pytest.importorskip("cadquery")


def _two_boxes(cq):
    return cq.Compound.makeCompound([cq.Solid.makeBox(1, 1, 1),
                                     cq.Solid.makeBox(1, 1, 1).translate(cq.Vector(3, 0, 0))])


def _file_name(path):
    """The FILE_NAME record of the header, with OCCT's line wrapping removed."""
    head = path.read_text().split("ENDSEC;")[0]
    return re.sub(r"\n\s*", "", re.search(r"FILE_NAME\(.*?\);", head, re.S).group(0))


def _records(path):
    """The DATA section as one string per record, line wrapping removed."""
    data = path.read_text().split("DATA;", 1)[1].split("ENDSEC;", 1)[0]
    return [r for r in re.sub(r"\r?\n\s*", "", data).split(";") if r]


def _read_back(path):
    """(product names, assembly-link ids) as OCCT's reader reads the file."""
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.STEPControl import STEPControl_Reader
    from OCP.StepBasic import StepBasic_Product
    from OCP.StepRepr import StepRepr_NextAssemblyUsageOccurrence

    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_ReturnStatus.IFSelect_RetDone
    model = reader.StepModel()

    def strings(kind, field):
        out, it = [], model.Entities()
        it.SelectType(kind.get_type_descriptor_s(), True)
        it.Start()
        while it.More():
            out.append(getattr(it.Value(), field)().ToCString())
            it.Next()
        return out

    return strings(StepBasic_Product, "Name"), strings(StepRepr_NextAssemblyUsageOccurrence, "Id")


def test_the_same_shape_exported_seconds_apart_is_the_same_bytes(tmp_path, cq):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    box = cq.Workplane().box(2, 3, 4)
    for folder in ("a", "b"):
        geometry.export_step(box, tmp_path / folder / "box.step")
        geometry.export_step(_two_boxes(cq), tmp_path / folder / "two.step")
        # Other exports in between move OCCT's per-process product and assembly-link counters on.
        cq.exporters.export(cq.Workplane().box(1, 1, 1), str(tmp_path / folder / "other.step"))
        geometry.export_step(cq.Workplane().sphere(1), tmp_path / folder / "ball.step")
        if folder == "a":
            time.sleep(1.1)                          # the header's time stamp has one-second resolution
    for name in ("box.step", "two.step"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name
    assert "Open CASCADE STEP translator" not in (tmp_path / "a" / "box.step").read_text()
    assert not list(tmp_path.glob("*/.*.part"))      # no temporary file left behind


def test_the_header_names_the_file_and_its_date_follows_source_date_epoch(tmp_path, cq, monkeypatch):
    out = geometry.export_step(cq.Workplane().box(1, 2, 3), tmp_path / "part.step")
    assert out == tmp_path / "part.step"
    assert _file_name(out).startswith("FILE_NAME('part.step','2000-01-01T00:00:00',")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    geometry.export_step(cq.Workplane().box(1, 2, 3), out)
    assert _file_name(out).startswith("FILE_NAME('part.step','2023-11-14T22:13:20',")


def test_the_product_is_named_after_the_file_or_the_name_given(tmp_path, cq):
    plain = geometry.export_step(cq.Workplane().box(1, 2, 3), tmp_path / "bracket.step")
    assert _read_back(plain) == (["bracket"], [])
    named = geometry.export_step(cq.Workplane().box(1, 2, 3), tmp_path / "b2.step", name="it's a \\ part")
    product = next(r for r in _records(named) if "= PRODUCT(" in r)
    assert "PRODUCT('it''s a \\\\ part','it''s a \\\\ part'," in product   # quote and backslash doubled in the file
    assert _read_back(named) == (["it's a \\ part"], [])                 # and read back as given


@pytest.mark.parametrize("name", ["6'", "x'y,z", "q' x)", "(a,b)", "6'\"", "a'\"x)"])
def test_a_quote_not_followed_by_a_comma_or_bracket_reads_back(tmp_path, cq, name):
    out = geometry.export_step(cq.Workplane().box(1, 1, 1), tmp_path / "part.step", name=name)
    assert _read_back(out) == ([name], [])


@pytest.mark.parametrize("name", ["post (6')", "a', b", "rod 1/4' ,x", "a')", "a'\")", "a' \" )", "a'\"\",b"])
def test_a_name_that_occts_reader_would_lose_is_refused(tmp_path, cq, name):
    """OCCT's reader reads these back as no name at all: a doubled quote, then only spaces or double quotes, then
    ',' or ')'."""
    with pytest.raises(ValueError, match="misreads.*another name="):
        geometry.export_step(cq.Workplane().box(1, 1, 1), tmp_path / "part.step", name=name)
    with pytest.raises(ValueError, match="misreads.*rename the file"):
        geometry.export_step(cq.Workplane().box(1, 1, 1), tmp_path / f"{name.replace('/', '-')}.step", name="part")
    assert not list(tmp_path.iterdir())


def _settings():
    """The current values of the writer settings export_step uses."""
    from OCP.Interface import Interface_Static

    return [(k, Interface_Static.IVal_s(k) if isinstance(v, int) else Interface_Static.CVal_s(k))
            for k, v in geometry.STEP_SETTINGS]


def _put(settings):
    from OCP.Interface import Interface_Static

    for key, value in settings:
        assert (Interface_Static.SetIVal_s if isinstance(value, int) else Interface_Static.SetCVal_s)(key, value)


def _schema(path):
    return re.sub(r"\s+", " ", re.search(r"FILE_SCHEMA\(\((.*?)\)\)", path.read_text(), re.S).group(1)).strip()


def _fused_filleted(cq):
    """Faces of mixed tolerance, so the precision mode changes the file (two plain boxes have one tolerance)."""
    return cq.Workplane().box(4, 4, 1).union(cq.Workplane().sphere(1.3)).edges().fillet(0.2)


def test_writer_settings_left_by_earlier_code_do_not_change_the_bytes(tmp_path, cq):
    cq.exporters.export(cq.Workplane().box(1, 1, 1), str(tmp_path / "first.step"))     # registers the settings
    saved = _settings()
    shapes = {"pair": _two_boxes(cq), "blob": _fused_filleted(cq)}
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
    first = {n: geometry.export_step(s, tmp_path / "a" / f"{n}.step").read_bytes() for n, s in shapes.items()}
    try:
        # Process-wide settings that an earlier export, or project code, can leave behind.
        cq.exporters.export(cq.Workplane().box(2, 3, 4), str(tmp_path / "other.step"),
                            opt={"write_pcurves": False, "precision_mode": 1})
        _put([("write.step.schema", "AP242DIS"), ("write.step.unit", "M")])
        again = {n: geometry.export_step(s, tmp_path / "b" / f"{n}.step").read_bytes() for n, s in shapes.items()}
    finally:
        _put(saved)
    for n in shapes:
        assert again[n] == first[n], n


def test_the_projects_own_writer_settings_are_put_back(tmp_path, cq):
    """A project that chose AP242 for its own cadquery exports keeps it after export_step, even a failed one."""
    box = cq.Workplane().box(1, 1, 1)
    cq.exporters.export(box, str(tmp_path / "first.step"))                              # registers the settings
    saved = _settings()
    try:
        _put([("write.step.schema", "AP242DIS"), ("write.precision.mode", 1), ("write.step.unit", "M")])
        chosen = _settings()
        ours = geometry.export_step(box, tmp_path / "ours.step")
        assert _schema(ours).startswith("'AUTOMOTIVE_DESIGN")
        assert _settings() == chosen
        cq.exporters.export(box, str(tmp_path / "theirs.step"))       # cadquery sets only pcurves, precision, units
        assert _schema(tmp_path / "theirs.step").startswith("'AP242_MANAGED_MODEL_BASED_3D_ENGINEERING")
        _put([("write.precision.mode", 1), ("write.step.unit", "M")])
        chosen = _settings()
        with pytest.raises(geometry.GeometryError, match="could not write"):
            geometry.export_step(box, tmp_path / "no-such-folder" / "x.step")
        assert _settings() == chosen
    finally:
        _put(saved)


def test_a_multi_solid_shape_numbers_its_products_and_links_within_the_file(tmp_path, cq):
    for i in range(2):                                    # earlier multi-solid exports in this process
        cq.exporters.export(_two_boxes(cq), str(tmp_path / f"warm{i}.step"))
    out = geometry.export_step(_two_boxes(cq), tmp_path / "pair.step")
    assert _read_back(out) == (["pair", "pair.1", "pair.2"], ["1", "2"])


def test_the_geometry_is_what_cadquery_writes(tmp_path, cq):
    """Only the header, the product names and the assembly-link ids differ from cadquery.exporters.export."""
    def normalised(path):
        rows = []
        for r in _records(path):
            r = re.sub(r"= PRODUCT\('[^']*','[^']*',", "= PRODUCT(N,N,", r)
            rows.append(re.sub(r"= NEXT_ASSEMBLY_USAGE_OCCURRENCE\('\d+',", "= NEXT_ASSEMBLY_USAGE_OCCURRENCE(I,", r))
        return rows

    for label, shape in (("box", cq.Workplane().box(2, 3, 4)),
                         ("pair", cq.Workplane().add([cq.Solid.makeBox(1, 1, 1),
                                                      cq.Solid.makeBox(1, 1, 1).translate(cq.Vector(3, 0, 0))]))):
        ours = geometry.export_step(shape, tmp_path / f"{label}.step")
        theirs = tmp_path / f"{label}.cq.step"
        cq.exporters.export(shape, str(theirs))
        assert normalised(ours) == normalised(theirs), label
        back = cq.importers.importStep(str(ours)).val()
        assert back.Volume() == pytest.approx(cq.Compound.makeCompound(shape.vals()).Volume(), rel=1e-9)


def test_a_name_that_is_not_ascii_is_refused(tmp_path, cq):
    with pytest.raises(ValueError, match="printable ASCII.*another name="):
        geometry.export_step(cq.Workplane().box(1, 1, 1), tmp_path / "part.step", name="Gehäuse")
    for name in (None, "housing"):              # a name= does not help: the header carries the file's own name
        with pytest.raises(ValueError, match="printable ASCII.*rename the file"):
            geometry.export_step(cq.Workplane().box(1, 1, 1), tmp_path / "Gehäuse.step", name=name)
    with pytest.raises(ValueError, match="no shapes"):
        geometry.export_step(cq.Workplane(), tmp_path / "empty.step")
    assert not list(tmp_path.iterdir())


# ----------------------------------------------------------------------------------- export_step (cadquery Assembly)

# A small robot: nested assemblies, unnamed nodes (cadquery names them with a uuid), one shape used three times,
# a transparent colour, a part with no colour, and enough coloured products for OCCT to order their styles by heap
# address. Shared by the in-process tests and the child processes below.
ROBOT = textwrap.dedent("""
    import cadquery as cq

    def robot(legs=3, femur_colour=(0.2, 0.4, 0.6, 1.0)):
        top = cq.Assembly(name="robot")
        bolt = cq.Workplane().cylinder(6, 1.5)
        for i in range(legs):
            leg = cq.Assembly(name=f"leg{i}")
            leg.add(cq.Workplane().box(3, 3, 20 + i), name="femur", color=cq.Color(*femur_colour))
            leg.add(cq.Workplane().box(2, 2, 15), loc=cq.Location((0, 0, -17)), color=cq.Color(0.9, 0.2, 0.1, 0.5))
            for k in range(2):
                leg.add(bolt, loc=cq.Location((1, k, 0)), color=cq.Color("gray"))
            top.add(leg, loc=cq.Location((i * 10, 0, 0), (0, 0, 1), i * 15))
        top.add(cq.Workplane().sphere(5), name="head", color=cq.Color("yellow"))
        top.add(cq.Workplane().box(40, 30, 4))
        return top
""")


def _robot(**kwargs):
    space = {}
    exec(ROBOT, space)                                    # noqa: S102 (the test's own source above)
    return space["robot"](**kwargs)


CHILD = ROBOT + textwrap.dedent("""
    import sys
    from cadagent.geometry import export_step
    held = [cq.Workplane().box(1, 1, 1 + i).val() for i in range(int(sys.argv[2]))]   # move the heap
    for i in range(int(sys.argv[2])):                     # and OCCT's per-process counters
        robot().export(sys.argv[1] + f".warm{i}.step")
    export_step(robot(), sys.argv[1])
    robot().export(sys.argv[1] + ".cadquery.step")
""")


def test_an_assembly_exported_in_two_processes_is_the_same_bytes(tmp_path, cq):
    """Assembly.save gives another file in each process (time, uuids, link ids, style order); export_step does not."""
    src = str(Path(geometry.__file__).resolve().parents[2])
    env = {k: v for k, v in os.environ.items() if k != "SOURCE_DATE_EPOCH"}
    env["PYTHONPATH"] = os.pathsep.join([src, env.get("PYTHONPATH", "")])
    out = {}
    for folder, warm in (("a", 0), ("b", 3)):
        (tmp_path / folder).mkdir()
        path = tmp_path / folder / "robot.step"
        r = subprocess.run([sys.executable, "-c", CHILD, str(path), str(warm)], capture_output=True, text=True,
                           env=env, timeout=300)
        assert r.returncode == 0, r.stderr
        out[folder] = path
        if folder == "a":
            time.sleep(1.1)                               # the header's time stamp has one-second resolution
    assert out["a"].read_bytes() == out["b"].read_bytes()
    cq_a, cq_b = (Path(f"{out[f]}.cadquery.step").read_text() for f in "ab")
    assert cq_a != cq_b                                   # what this fixes: cadquery's own files differ
    assert re.search(r"PRODUCT\('[0-9a-f]{8}-", cq_a) and not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", out["a"].read_text())


def _shuffle_style_tail(model):
    """Reverse the order of the presentation graphs at the end of ``model``, as another heap layout can."""
    from cadagent.geometry._assembly_step import _MDGPR

    total = model.NbEntities()
    graphs = [i for i in range(1, total + 1) if model.Entity(i).DynamicType().Name() == _MDGPR]
    bounds = list(zip(graphs, graphs[1:] + [total + 1]))
    for start, end in bounds[1:]:                         # each later graph's block to the front of the tail,
        for k in range(end - start):                      # a record at a time (OCCT refuses overlapping moves);
            model.ChangeOrder(start + k, graphs[0] + k)   # the blocks after it keep their numbers
    return len(graphs)


def _transferred(cq, assy):
    from cadquery.occ_impl.assembly import toCAF
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_StepModelType
    from OCP.XSControl import XSControl_WorkSession

    _top, doc = toCAF(assy, True)
    writer = STEPCAFControl_Writer(XSControl_WorkSession(), False)
    writer.SetColorMode(True)
    writer.SetNameMode(True)
    assert writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs)
    return writer, writer.Writer().Model()                # the model is emptied when the writer goes


def _types(model):
    return [model.Entity(i).DynamicType().Name() for i in range(1, model.NbEntities() + 1)]


def _style_records(writer, path):
    """The written records from the first presentation graph on: the colour tail."""
    assert writer.Write(str(path))
    records = _records(path)
    return records[next(i for i, r in enumerate(records) if "MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION" in r):]


def test_the_colour_records_get_one_order_whatever_order_occt_wrote(tmp_path, cq):
    from cadagent.geometry._assembly_step import order_style_tail

    (w1, plain), (w2, shuffled) = _transferred(cq, _robot()), _transferred(cq, _robot())
    before = _types(shuffled)
    assert _shuffle_style_tail(shuffled) >= 3
    assert _types(shuffled) != before                              # the records really moved
    assert order_style_tail(plain, "plain") and order_style_tail(shuffled, "shuffled")
    tail = _style_records(w1, tmp_path / "plain.step")
    assert tail == _style_records(w2, tmp_path / "shuffled.step") and len(tail) > 20
    _w3, single = _transferred(cq, cq.Assembly(cq.Workplane().box(1, 1, 1), name="one", color=cq.Color("red")))
    assert order_style_tail(single, "single") is False            # one graph: nothing to order


def test_an_assembly_file_names_its_nodes_and_numbers_its_links(tmp_path, cq):
    out = geometry.export_step(_robot(legs=2), tmp_path / "robot.step")
    products, links = _read_back(out)
    assert products[0] == "robot" and {"leg0", "leg1", "femur", "head"} <= set(products)
    assert {"leg0.2", "leg0.3", "leg1.2", "robot.4"} <= set(products)      # unnamed: <parent>.<k>
    # The two bolts of a leg are one product (one shape, one colour), placed by the links leg0.3 and leg0.4.
    assert re.search(r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\('\d+',\s*'leg0\.4'", out.read_text())
    assert links == [str(i) for i in range(1, len(links) + 1)]
    assert _file_name(out).startswith("FILE_NAME('robot.step','2000-01-01T00:00:00',")
    unnamed = cq.Assembly()                                           # cadquery names the root with a uuid too
    unnamed.add(cq.Workplane().box(1, 1, 1))
    assert _read_back(geometry.export_step(unnamed, tmp_path / "frame.step"))[0][:2] == ["frame", "frame.1"]
    assert _read_back(geometry.export_step(_robot(legs=1), tmp_path / "r.step", name="dog"))[0][0] == "dog"


def test_a_sub_assembly_added_twice_names_its_unnamed_nodes_in_each_place(tmp_path, cq):
    """Assembly.add copies a sub-assembly with its names, so both copies of the leg's unnamed part share one uuid;
    each is still named after its own place. (The part is one product, named after its first place; OCCT's writer,
    as with Assembly.save, keeps the name of one of its two links.)"""
    leg = cq.Assembly(name="leg")
    leg.add(cq.Workplane().box(1, 1, 4), color=cq.Color("red"))
    top = cq.Assembly(name="robot")
    top.add(leg, name="left")
    top.add(leg, name="right", loc=cq.Location((5, 0, 0)))
    out = geometry.export_step(top, tmp_path / "robot.step")
    products, _ids = _read_back(out)
    links = re.findall(r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\('\d+',\s*'([^']*)'", out.read_text())
    assert products == ["robot", "left", "left.1", "right"] and sorted(links) == ["", "", "", "right.1"]
    back = cq.Assembly.importStep(str(out))
    assert {"left", "right", "right.1"} <= {name for name, _node in back.traverse()}
    assert round(back.toCompound().Volume(), 6) == 8.0


def test_an_assembly_reads_back_as_cadquery_wrote_it(tmp_path, cq):
    """Colours, shapes and places are those of Assembly.save; only names, ids, the header and the order differ."""
    ours = geometry.export_step(_robot(), tmp_path / "ours.step")
    theirs = tmp_path / "theirs.step"
    _robot().export(str(theirs))

    def content(path):
        rows = []
        for _name, node in cq.Assembly.importStep(str(path)).traverse():
            colour = tuple(round(c, 4) for c in node.color.toTuple()) if node.color else None
            volume = round(node.obj.Volume(), 6) if node.obj is not None else None
            rows.append((colour, volume, tuple(round(v, 6) for v in node.loc.toTuple()[0])))
        return sorted(rows, key=repr)

    assert content(ours) == content(theirs) and len(content(ours)) > 10


def test_a_change_to_the_assembly_changes_the_file(tmp_path, cq):
    base = geometry.export_step(_robot(), tmp_path / "a" / "robot.step") if (tmp_path / "a").mkdir() is None else 0
    (tmp_path / "b").mkdir()
    recoloured = geometry.export_step(_robot(femur_colour=(0.2, 0.4, 0.7, 1.0)), tmp_path / "b" / "robot.step")
    assert base.read_bytes() != recoloured.read_bytes()
    (tmp_path / "c").mkdir()
    longer = geometry.export_step(_robot(legs=4), tmp_path / "c" / "robot.step")
    assert base.read_bytes() != longer.read_bytes()


def test_an_assembly_keeps_the_projects_writer_settings(tmp_path, cq):
    cq.exporters.export(cq.Workplane().box(1, 1, 1), str(tmp_path / "first.step"))      # registers the settings
    _robot().export(str(tmp_path / "registers-stepcaf.step"))
    from OCP.Interface import Interface_Static

    keys = [k for k, _ in geometry.STEP_SETTINGS] + ["write.stepcaf.subshapes.name"]
    saved = [(k, Interface_Static.IVal_s(k) if k != "write.step.schema" and "unit" not in k
              else Interface_Static.CVal_s(k)) for k in keys]
    try:
        _put([("write.step.schema", "AP242DIS"), ("write.stepcaf.subshapes.name", 0)])
        chosen = [(k, Interface_Static.CVal_s(k)) for k in keys]
        geometry.export_step(_robot(legs=1), tmp_path / "ours.step")
        assert [(k, Interface_Static.CVal_s(k)) for k in keys] == chosen
        assert _schema(tmp_path / "ours.step").startswith("'AUTOMOTIVE_DESIGN")
    finally:
        _put(saved)


def test_what_an_assembly_file_cannot_carry_the_same_way_is_refused(tmp_path, cq):
    styled = cq.Assembly(name="styled")
    block = cq.Workplane().box(2, 2, 2)
    styled.add(block, name="block")
    styled.addSubshape(block.faces(">Z").val(), name="top face", color=cq.Color("red"))
    with pytest.raises(ValueError, match="sub-shape"):
        geometry.export_step(styled, tmp_path / "styled.step")
    named = cq.Assembly(name="asm")
    named.add(cq.Workplane().box(1, 1, 1), name="Gehäuse")
    with pytest.raises(ValueError, match="printable ASCII"):
        geometry.export_step(named, tmp_path / "asm.step")
    with pytest.raises(ValueError, match="empty"):
        geometry.export_step(cq.Assembly(name="nothing"), tmp_path / "nothing.step")
    # Names cadquery's reader would refuse or misread (it rebuilds the tree with Assembly.add, and takes a child with
    # the root's name for the top): the default name of an unnamed root, name=, and a user name like the
    # <parent>.<k> given to an unnamed sibling.
    frame = cq.Assembly()
    frame.add(cq.Workplane().box(1, 1, 1), name="frame")
    frame.add(cq.Workplane().box(2, 1, 1), name="lid")
    with pytest.raises(ValueError, match="written as 'frame', the name of one of its children"):
        geometry.export_step(frame, tmp_path / "frame.step")
    with pytest.raises(ValueError, match="written as 'lid', the name of one of its children"):
        geometry.export_step(frame, tmp_path / "f.step", name="lid")
    twins = cq.Assembly(name="robot")
    twins.add(cq.Workplane().box(1, 1, 1))                            # written robot.1
    twins.add(cq.Workplane().box(2, 1, 1), name="robot.1")
    with pytest.raises(ValueError, match=r"child of the assembly node 'robot' would be written as 'robot\.1', a sib"):
        geometry.export_step(twins, tmp_path / "twins.step")
    holder = cq.Assembly(cq.Workplane().box(1, 1, 1), name="arm")    # a shape and children: its shape is arm_part
    holder.add(cq.Workplane().box(1, 2, 1), name="arm_part")
    with pytest.raises(ValueError, match="written as 'arm_part', the label of its parent's own shape"):
        geometry.export_step(holder, tmp_path / "arm.step")
    with pytest.raises(ValueError, match="rename the file"):
        geometry.export_step(_robot(legs=1), tmp_path / "Gehäuse.step")
    assert not list(tmp_path.iterdir())

    # The reader keys deeper nodes by path (leg0/bolt), so a name may come back at another level, in either order.
    (tmp_path / "ok").mkdir()
    deep = cq.Assembly(name="robot")
    inner = cq.Assembly(name="inner")
    inner.add(cq.Workplane().box(1, 1, 1), name="robot")              # a grandchild with the root's name
    deep.add(inner)
    back = cq.Assembly.importStep(str(geometry.export_step(deep, tmp_path / "ok" / "deep.step")))
    assert sorted(name for name, _node in back.traverse()) == ["inner", "robot", "robot"]
    assert round(back.toCompound().Volume(), 6) == 1.0
    for bolt_first in (True, False):
        top, leg = cq.Assembly(name="robot"), cq.Assembly(name="leg0")
        leg.add(cq.Workplane().box(1, 1, 1), name="bolt")
        if bolt_first:
            top.add(cq.Workplane().box(2, 2, 3), name="bolt")
        top.add(leg)
        if not bolt_first:
            top.add(cq.Workplane().box(2, 2, 3), name="bolt")
        back = cq.Assembly.importStep(str(geometry.export_step(top, tmp_path / "ok" / f"bolt{bolt_first}.step")))
        assert sorted(name for name, _node in back.traverse()) == ["bolt", "bolt", "leg0", "robot"]
        assert round(back.toCompound().Volume(), 6) == 13.0
